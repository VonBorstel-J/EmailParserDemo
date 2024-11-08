import os
import yaml
import logging
import requests
import re
import time
from dataclasses import dataclass
from typing import Dict, Any, Union
from dotenv import load_dotenv
from cachetools import LRUCache, cachedmethod
from functools import wraps
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  
from requests.exceptions import ReadTimeout, ConnectionError
from openai import OpenAI, OpenAIError
from logging.handlers import RotatingFileHandler

# Load environment variables from .env file
load_dotenv()

# Setup basic logger
logger = logging.getLogger("parser")
logger.setLevel(logging.DEBUG)  # Initial level; will be overridden by config

def performance_monitor(func):
    """Decorator to monitor performance metrics of functions."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        logger.debug(f"Performance: {func.__name__} took {elapsed_time:.2f}s")
        return result
    return wrapper


@retry(
    stop=stop_after_attempt(2),  # Retry up to 2 times
    wait=wait_exponential(multiplier=1, min=5, max=20),  # Exponential backoff, starting with 5 seconds
    retry=retry_if_exception_type((ReadTimeout, ConnectionError))  # Only retry on specific exceptions
)
def send_request_with_retry(session, url, payload):
    """Send request with retry logic using tenacity."""
    try:
        response = session.post(url, json=payload, timeout=200)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Request failed: {e}")
        raise  # Re-raise the exception for tenacity to handle

@dataclass
class ParserConfig:
    prompt_template: str
    logging_level: str
    logging_file: str
    create_logs_dir: bool
    field_validation: Dict[str, str]
    cache_dir: str
    max_tokens: int
    lm_studio_base_url: str
    lm_studio_api_key: str
    generation_config: Dict[str, Any]

class EmailParser:
    def __init__(self, config_path: str = 'parser.config.yaml') -> None:
        """Initialize the EmailParser."""
        self.config = self._load_config(config_path)
        self._configure_logging()
        self.field_validation = self.config.field_validation
        self.lm_studio_url = self.config.lm_studio_base_url
        self.lm_studio_api_key = self.config.lm_studio_api_key
        self.generation_config = self.config.generation_config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.lm_studio_api_key}",
            "Content-Type": "application/json"
        })
        self.cache = LRUCache(maxsize=500)  # Adjust maxsize as needed

        # Initialize OpenAI client pointing to LM Studio's API
        self.client = OpenAI(
            base_url=f"{self.lm_studio_url}/v1",
            api_key=self.lm_studio_api_key
        )

    def _load_config(self, config_path: str) -> ParserConfig:
        """Load and validate the YAML configuration file."""
        logger.debug(f"Loading configuration from {config_path}")
        if not os.path.exists(config_path):
            logger.critical(f"Configuration file not found: {config_path}")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, 'r') as file:
                config_data = yaml.safe_load(file)

            # Validate required fields, excluding 'generation_config'
            required_fields = ['prompt_template', 'logging', 'field_validation', 'lm_studio']
            for field in required_fields:
                if field not in config_data:
                    logger.critical(f"Missing required configuration field: {field}")
                    raise KeyError(f"Missing required configuration field: {field}")

            prompt_template = config_data['prompt_template']
            logging_config = config_data['logging']
            field_validation = config_data['field_validation']
            lm_studio_config = config_data['lm_studio']
            
            # Use an empty dictionary as the default for generation_config if not present
            generation_config = config_data.get('generation_config', {})

            return ParserConfig(
                prompt_template=prompt_template,
                logging_level=logging_config.get('level', 'DEBUG'),
                logging_file=logging_config.get('file_path', 'logs/parser.log'),
                create_logs_dir=logging_config.get('create_logs_dir_if_not_exists', True),
                field_validation=field_validation,
                cache_dir=config_data.get('cache_dir', './cache'),
                max_tokens=config_data.get('max_tokens', 1024),
                lm_studio_base_url=lm_studio_config['base_url'],
                lm_studio_api_key=lm_studio_config['api_key'],
                generation_config=generation_config  # Optional field
            )

        except yaml.YAMLError as e:
            logger.critical(f"Error parsing configuration file: {e}")
            raise

    def _configure_logging(self) -> None:
        """Configure logging with rotation and proper formatting."""
        if self.config.create_logs_dir:
            os.makedirs(os.path.dirname(self.config.logging_file), exist_ok=True)
            logger.debug("Logs directory created.")

        # Clear existing handlers
        if logger.hasHandlers():
            logger.handlers.clear()

        # File handler with rotation
        file_handler = RotatingFileHandler(
            self.config.logging_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(
            logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
        )
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
        )
        logger.addHandler(console_handler)

        # Set logging level
        logger.setLevel(getattr(logging, self.config.logging_level.upper(), logging.DEBUG))
        logger.debug(f"Logging configured with level: {self.config.logging_level.upper()}")

    def check_lm_studio_connection(self) -> bool:
        """Check if LM Studio is available."""
        url = f"{self.lm_studio_url}/v1/models"
        try:
            response = self.session.get(url, timeout=10)
            if response.ok:
                logger.info("Successfully connected to LM Studio.")
                return True
            else:
                logger.error(f"LM Studio connection failed with status code {response.status_code}.")
                return False
        except requests.RequestException as e:
            logger.error(f"Failed to connect to LM Studio: {e}")
            return False

    @performance_monitor
    @cachedmethod(lambda self: self.cache, key=lambda self, email_content, chat_mode=False: email_content)
    def parse_email(self, email_content: str, chat_mode: bool = False) -> Union[Dict[str, Any], str]:
        """Parse email content using LM Studio with caching and performance monitoring."""
        if not self.check_lm_studio_connection():
            logger.error("LM Studio is unavailable or not running.")
            return "LM Studio is unavailable or not running. Please check your server."

        prompt = self.config.prompt_template.replace('{{email_content}}', email_content)
        payload = {
            "prompt": prompt,
            "max_tokens": self.config.max_tokens,
            **self.generation_config
        }

        try:
            # Send request with retry logic
            result = send_request_with_retry(self.session, f"{self.lm_studio_url}/v1/completions", payload)
            completion = result.get('choices', [{}])[0].get('text', '').strip()
            if not completion:
                logger.warning("Empty completion received from LM Studio.")
                return "No valid completion generated."

            # Clean and parse the response
            parsed_data = self._parse_response(completion)
            validated_data = self._validate_parsed_fields(parsed_data)
            return validated_data

        except OpenAIError as e:
            logger.error(f"OpenAI error during parsing: {e}", exc_info=True)
            return "Error communicating with LM Studio."
        except Exception as e:
            logger.error(f"Unexpected error during parsing: {e}", exc_info=True)
            return "Internal error during parsing."

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse the LM Studio response to extract fields."""
        logger.debug("Parsing LM Studio response.")
        parsed_data = {}
        current_section = None

        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('**') and line.endswith('**'):
                section_name = line.strip('*').strip().lower().replace(' ', '_')
                parsed_data[section_name] = {}
                current_section = section_name
            elif line.startswith('-') and current_section:
                parts = line[1:].split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip().lower().replace(' ', '_').replace('(', '').replace(')', '')
                    value = parts[1].strip()
                    # Detect loops by checking for repeated content
                    if key in parsed_data[current_section] and parsed_data[current_section][key] == value:
                        logger.warning(f"Loop detected for field '{key}' with value '{value}'.")
                        raise ValueError(f"Loop detected in parsing for field '{key}'.")
                    parsed_data[current_section][key] = value
        logger.debug(f"Parsed data: {parsed_data}")
        return parsed_data
    
    
    def _validate_parsed_fields(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parsed fields using regex patterns and flag invalid entries without stopping the process."""
        logger.debug("Validating parsed fields.")
        validated_data = {}
    
        for section, fields in parsed_data.items():
            validated_data[section] = {}
            for key, value in fields.items():
                pattern_key = f"{key}_pattern"
                pattern = self.field_validation.get(pattern_key)
    
                if pattern and value != "N/A":
                    # Check if the value matches the expected pattern
                    if not re.match(pattern, value):
                        # Flag as invalid format but continue processing
                        logger.warning(f"Validation failed for {key}: {value}")
                        validated_data[section][key] = f"{value} (Invalid Format)"
                    else:
                        # If valid, assign the value as-is
                        validated_data[section][key] = value
                else:
                    # If no pattern or value is "N/A", assign the value as-is
                    validated_data[section][key] = value
    
        # Log repeated patterns but do not raise exceptions
        if self._detect_repeated_patterns(validated_data):
            logger.warning("Repeated output patterns detected in validated data.")
    
        logger.debug(f"Validated data: {validated_data}")
        return validated_data
    
    def _detect_repeated_patterns(self, data: Dict[str, Any]) -> bool:
        """Log repeated patterns in the validated data instead of stopping the process."""
        logger.debug("Checking for repeated patterns in validated data.")
        seen = {}
        has_repeats = False  # Track if any repeats were found for logging purposes
    
        for section, fields in data.items():
            for key, value in fields.items():
                if value in seen:
                    seen[value] += 1
                    if seen[value] > 3:  # Threshold for repetition
                        has_repeats = True
                        logger.debug(f"Value '{value}' repeated {seen[value]} times in section '{section}', field '{key}'")
                else:
                    seen[value] = 1
    
        return has_repeats
