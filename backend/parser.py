import re
import json
import logging
import yaml
import os
import time
from typing import Dict, Any, Tuple, Union
from dataclasses import dataclass
from openai import OpenAI
from logging.handlers import RotatingFileHandler
from cachetools import LRUCache, cached
from functools import wraps

# Initialize the OpenAI client pointing to LM Studio's API
client = OpenAI(
    base_url="http://localhost:3000/v1",
    api_key="lm-studio"
)

# Constants for model versions
MODEL_VERSIONS = {
    "meta-llama/Llama-3.2-1B": "1.0.0",
    "meta-llama/Llama-3.2-3B": "1.0.0",
    "numind/NuExtract-v1.5": "1.5.0"
}

# LRU Cache for _generate_response
_generate_response_cache = LRUCache(maxsize=100)  # Set reasonable cache size limit

class ModelNotFoundError(Exception):
    """Raised when model files are not found"""
    pass

class ModelVersionError(Exception):
    """Raised when model version is incompatible"""
    pass

class TransientModelError(Exception):
    """Raised for transient model errors, suitable for retrying"""
    pass

def performance_monitor(func):
    """Decorator to monitor performance metrics of functions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        args[0].logger.debug(
            f"Performance: {func.__name__} took {elapsed_time:.2f}s"
        )
        return result
    return wrapper

@dataclass
class ParserConfig:
    """Configuration class for EmailParser"""
    model_size: str
    cache_dir: str
    logging_level: str
    logging_file: str
    create_logs_dir: bool
    generation_config: Dict[str, Any]
    prompt_template: str
    field_validation: Dict[str, str]
    model_path: str
    max_tokens: int

class EmailParser:
    def __init__(self, 
                 model_size: str = 'meta-llama/Llama-3.2-1B', 
                 config_path: str = 'parser.config.yaml',
                 device: str = None) -> None:
        """
        Initialize the EmailParser with improved error handling and validation.
        """
        # Initialize basic logging before configuration is loaded
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

        # Stage 1: Load and validate configuration
        self.logger.info("Stage 1: Loading and validating configuration...")
        try:
            self.config = self._load_and_validate_config(config_path, model_size)
            self._configure_logging()
            self.logger.info("Configuration loaded and logging configured.")
        except Exception as e:
            self.logger.critical(f"Failed at Stage 1: {str(e)}", exc_info=True)
            raise

        # Field validation patterns
        self.phone_pattern = re.compile(self.config.field_validation.get('phone_pattern', ''))
        self.email_pattern = re.compile(self.config.field_validation.get('email_pattern', ''))
        self.date_pattern = re.compile(self.config.field_validation.get('date_pattern', ''))

    def _configure_logging(self) -> None:
        """Configure logging with rotation and proper formatting"""
        if self.config.create_logs_dir:
            os.makedirs(os.path.dirname(self.config.logging_file), exist_ok=True)
            self.logger.debug("Logs directory created.")

        # Clear existing handlers
        self.logger.handlers.clear()

        # Configure file handler with rotation
        file_handler = RotatingFileHandler(
            self.config.logging_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(
            logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
        )
        self.logger.addHandler(file_handler)

        # Configure console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
        )
        self.logger.addHandler(console_handler)

        # Set logging level
        self.logger.setLevel(getattr(logging, self.config.logging_level.upper(), logging.DEBUG))
        self.logger.debug(f"Logging configured with level: {self.config.logging_level.upper()}")

    def _load_and_validate_config(self, config_path: str, model_size: str) -> ParserConfig:
        """
        Load and validate configuration from YAML file.
        """
        self.logger.debug(f"Loading configuration from {config_path}")
        if not os.path.exists(config_path):
            raise ValueError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, 'r') as file:
                config_data = yaml.safe_load(file)

            # Extract model-specific configuration based on model size
            model_key = ('llama_1b' if '1B' in model_size else
                         'llama_3b' if '3B' in model_size else
                         'nuextract' if 'NuExtract' in model_size else
                         None)
            model_config = config_data.get('models', {}).get(model_key, {})

            if not model_config:
                raise ValueError(f"Configuration for {model_key} not found")

            self.logger.debug(f"Configuration for {model_key} loaded.")

            return ParserConfig(
                model_size=model_config.get('repo_id'),
                cache_dir=config_data.get('cache_dir', './models'),
                logging_level=config_data.get('logging', {}).get('level', 'DEBUG'),
                logging_file=config_data.get('logging', {}).get('file_path', 'logs/parser.log'),
                create_logs_dir=config_data.get('logging', {}).get('create_logs_dir_if_not_exists', True),
                generation_config=model_config.get('generation_config', {}),
                prompt_template=model_config.get('prompt_template', ''),
                field_validation=config_data.get('field_validation', {}),
                model_path=os.path.abspath(model_config.get('model_path', './models')),
                max_tokens=model_config.get('max_tokens', 1024)
            )

        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing configuration file: {str(e)}")
        except Exception as e:
            raise ValueError(f"Unexpected error loading configuration: {str(e)}")

    @performance_monitor
    def parse_email(self, email_text: str, chat_mode: bool = False) -> Union[Dict[str, Any], str]:
        self.logger.info("Starting email parsing...")

        # Stage 5: Construct prompt
        self.logger.info("Constructing prompt...")
        prompt = (
            "You are an AI assistant that provides helpful and informative responses.\n"
            f"User: {email_text}\n"
            "Assistant:"
        ) if chat_mode else self.config.prompt_template.replace('{{email_content}}', email_text)

        self.logger.debug(f"Constructed prompt: {prompt[:500]}...")

        # Generate model response
        self.logger.info("Generating response...")
        try:
            response = self._generate_response(prompt, chat_mode)
            self.logger.debug(f"Model response: {response[:500]}...")

            if chat_mode:
                assistant_reply = response.split('Assistant:')[-1].strip()
                self.logger.info("Chat mode response parsed successfully.")
                return assistant_reply
            else:
                parsed_data = self._parse_response(response)
                self.logger.info("Email parsed successfully.")
                return parsed_data

        except Exception as e:
            self.logger.error(f"Error generating response: {str(e)}", exc_info=True)
            raise

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse the model's response to extract the sections and fields."""
        self.logger.debug(f"Raw response to parse: {response}")
        parsed_data = {}
        current_section = None

        try:
            lines = response.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for section headers, now properly handling ** markers
                if line.startswith('**') and line.endswith('**'):
                    section_name = line.strip('*').strip()
                    # Convert section name to snake_case without any extra characters
                    current_section = section_name.lower().replace(' ', '_').replace(':', '')
                    parsed_data[current_section] = {}
                    continue
                
                # Parse key-value pairs
                if line.startswith('-') and current_section:
                    parts = [p.strip() for p in line[1:].split(':', 1)]
                    if len(parts) == 2:
                        # Clean up the key name
                        key = parts[0].lower().replace(' ', '_').replace('(', '').replace(')', '')
                        value = parts[1].strip()
                        parsed_data[current_section][key] = value

            return parsed_data
        except Exception as e:
            self.logger.error(f"Error parsing response: {e}", exc_info=True)
            return {}

    def _validate_response(self, field: str, response: str) -> str:
        """
        Validate the response based on the field type.
        """
        response = response.strip()
        if not response or response == "{{" + field + "}}":
            return "N/A"

        if 'phone' in field:
            if not self.phone_pattern.match(response):
                self.logger.warning(f"Invalid phone number format: {response}")
                return "Invalid phone number"
        elif 'email' in field:
            if not self.email_pattern.match(response):
                self.logger.warning(f"Invalid email format: {response}")
                return "Invalid email address"
        elif 'date' in field:
            if not self.date_pattern.match(response):
                self.logger.warning(f"Invalid date format: {response}")
                return "Invalid date"

        return response

    @cached(_generate_response_cache)
    @performance_monitor
    def _generate_response(self, prompt: str, chat_mode: bool = False) -> str:
        """
        Generate response using the OpenAI API, with detailed error handling.
        """
        self.logger.debug(f"Generating response for model: {self.config.model_size}")
        try:
            if chat_mode:
                # Use Chat Completion API
                completion = client.chat.completions.create(
                    model=self.config.model_size,
                    messages=[
                        {"role": "system", "content": "You are an AI assistant that helps parse email content."},
                        {"role": "user", "content": prompt}
                    ],
                    **self.config.generation_config,
                    stream=True
                )
                
                response_content = ""
                for chunk in completion:
                    if chunk.choices[0].delta.content:
                        response_content += chunk.choices[0].delta.content
                return response_content.strip()
            
            else:
                # Use Completion API for regular mode
                completion = client.completions.create(
                    model=self.config.model_size,
                    prompt=prompt,
                    **self.config.generation_config
                )
                return completion.choices[0].text.strip()
    
        except OpenAIError as e:
            self.logger.error(f"OpenAI API error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in _generate_response: {e}", exc_info=True)
            raise