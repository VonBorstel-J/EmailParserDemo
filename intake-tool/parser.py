# parser.py

import os
import yaml
import logging
import re
import time
import spacy
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Union, List
from cachetools import TTLCache, cachedmethod
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    AsyncRetrying
)
from aiohttp import ClientSession, ClientError, ClientTimeout
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.cloud import aiplatform
from google.cloud.aiplatform_v1.types import PredictRequest
from logging.handlers import RotatingFileHandler
from cerberus import Validator
import hashlib
import json
import requests

# Configuration Loader with Dynamic Reloading
from config_loader import ConfigLoader  # Avoid circular imports by importing from config_loader.py

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Setup basic logger
logger = logging.getLogger("parser")
logger.setLevel(logging.DEBUG)  # Initial level; will be overridden by config

def setup_logger(log_config: Dict[str, Any]) -> None:
    """
    Configures the logger with file and console handlers based on the provided configuration.

    Args:
        log_config (Dict[str, Any]): Logging configuration from config.yaml.
    """
    if log_config.get('create_logs_dir_if_not_exists', False):
        os.makedirs(os.path.dirname(log_config['file_path']), exist_ok=True)
        logger.debug("Logs directory created.")

    # Clear existing handlers to prevent duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()

    # File handler with rotation to manage log file size
    file_handler = RotatingFileHandler(
        log_config['file_path'],
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(
        logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
    )
    logger.addHandler(file_handler)

    # Console handler for real-time logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
    )
    logger.addHandler(console_handler)

    # Set logging level based on configuration
    logger.setLevel(getattr(logging, log_config.get('level', 'DEBUG').upper(), logging.DEBUG))
    logger.debug(f"Parser logging configured with level: {log_config.get('level', 'DEBUG').upper()}")

def log_exception(e: Exception, message: str, strict_mode: bool) -> None:
    """
    Logs exceptions with appropriate severity based on strict_mode.

    Args:
        e (Exception): The exception that was raised.
        message (str): Custom message to log.
        strict_mode (bool): Determines logging level and whether to raise the exception.
    """
    if strict_mode:
        logger.error(message, exc_info=True)
        raise e
    else:
        logger.warning(f"{message}: {e}")

def performance_monitor(func):
    """
    Decorator to monitor performance metrics of asynchronous functions.

    Args:
        func (Callable): The asynchronous function to monitor.

    Returns:
        Callable: The wrapped function with performance monitoring.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            elapsed_time = time.time() - start_time
            logger.debug(f"Performance: {func.__name__} took {elapsed_time:.2f}s")
            return result
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Performance: {func.__name__} failed after {elapsed_time:.2f}s")
            raise e
    return wrapper

@dataclass
class ParserConfig:
    generative_ai: Dict[str, Any]
    vertex_ai: Dict[str, Any]
    logging: Dict[str, Any]
    batch_processing: Dict[str, Any]
    dynamic_token_adjustment: Dict[str, Any]
    caching: Dict[str, Any]
    prompt_template: str
    field_validation: Dict[str, str]
    environment_specific: Dict[str, Any]
    max_tokens: int
    strict_mode: bool

class EmailParser:
    """
    A class to parse email content using AI providers (Google Generative AI or Vertex AI).
    """

    def __init__(self, config_path: str = 'config.yaml') -> None:
        """
        Initializes the EmailParser with configuration, logging, caching, and AI clients.

        Args:
            config_path (str): Path to the configuration YAML file.
        """
        self.config_loader = ConfigLoader.get_instance()
        self.config = self.config_loader.config
        self.parser_config = self._load_parser_config()
        setup_logger(self.parser_config.logging)
        self.field_validation = self.parser_config.field_validation
        self.prompt_template = self.parser_config.prompt_template
        self.generation_config = self.config['parser'].get('generation_config', {})
        self.dynamic_token_adjustment = self.parser_config.dynamic_token_adjustment
        self.batch_size = self.parser_config.batch_processing.get('batch_size', 10)
        self.cache_ttl = self.parser_config.caching['ttl']
        self.strict_mode = self.parser_config.strict_mode

        # Initialize aiohttp session for asynchronous HTTP requests
        self.session = ClientSession(
            headers={
                "Content-Type": "application/json"
            },
            timeout=ClientTimeout(total=200)  # Timeout set to 200 seconds
        )

        # Initialize cache with hash-based keys and configurable TTL
        self.cache = TTLCache(maxsize=500, ttl=self.cache_ttl)

        # Initialize AI provider client based on config
        self.ai_provider = self.config['ai']['generative_ai']['provider']
        if self.ai_provider == "google":
            self.client = self._init_google_generative_ai()
        elif self.ai_provider == "vertex_ai":
            self.client = self._init_vertex_ai()
        else:
            logger.critical(f"Unsupported AI provider: {self.ai_provider}")
            raise ValueError(f"Unsupported AI provider: {self.ai_provider}")

        # Initialize spaCy model for entity recognition
        self.nlp = self._load_spacy_model()

    def _load_parser_config(self) -> ParserConfig:
        """
        Extracts the parser-specific configuration.

        Returns:
            ParserConfig: The parser configuration.
        """
        try:
            return ParserConfig(
                generative_ai=self.config['ai']['generative_ai'],
                vertex_ai=self.config['ai']['vertex_ai'],
                logging=self.config['parser']['logging'],
                batch_processing=self.config['parser']['batch_processing'],
                dynamic_token_adjustment=self.config['parser']['dynamic_token_adjustment'],
                caching=self.config['parser']['caching'],
                prompt_template=self.config['parser']['prompt_template'],
                field_validation=self.config['parser']['field_validation'],
                environment_specific=self.config['parser']['environment_specific'],
                max_tokens=self.config['parser']['max_tokens'],
                strict_mode=self.config['parser']['strict_mode']
            )
        except KeyError as e:
            log_exception(e, f"Missing required configuration field: {e}", self.config['parser'].get('strict_mode', True))

    def _load_spacy_model(self) -> spacy.language.Language:
        """
        Loads the spaCy model for entity recognition.

        Returns:
            spacy.language.Language: The loaded spaCy model.
        """
        try:
            nlp = spacy.load("en_core_web_sm")
            logger.debug("spaCy model loaded successfully.")
            return nlp
        except OSError:
            logger.info("Downloading spaCy 'en_core_web_sm' model...")
            from spacy.cli import download
            download("en_core_web_sm")
            nlp = spacy.load("en_core_web_sm")
            logger.debug("spaCy model downloaded and loaded successfully.")
            return nlp
        except Exception as e:
            log_exception(e, "Failed to load spaCy model", self.strict_mode)

    def _init_google_generative_ai(self):
        """
        Initializes the Google Generative AI client.

        Returns:
            Google Generative AI client instance.
        """
        try:
            from google.generativeai import client as google_ai_client
            google_ai_client.configure(api_key=self.config['ai']['generative_ai']['google']['api_key'])
            logger.debug("Google Generative AI client initialized.")
            return google_ai_client
        except ImportError as e:
            log_exception(e, "Google Generative AI client library not installed.", self.strict_mode)
        except Exception as e:
            log_exception(e, "Failed to initialize Google Generative AI client.", self.strict_mode)

    def _init_vertex_ai(self):
        """
        Initializes the Vertex AI client.

        Returns:
            Vertex AI PredictionServiceClient instance.
        """
        try:
            credentials = service_account.Credentials.from_service_account_file(
                os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            )
            aiplatform.init(credentials=credentials, project=os.getenv('GCP_PROJECT', 'forensicemailparser'))
            logger.debug("Vertex AI client initialized.")
            return aiplatform.PipelineServiceClient()
        except Exception as e:
            log_exception(e, "Failed to initialize Vertex AI client.", self.strict_mode)

    @performance_monitor
    @cachedmethod(lambda self: self.cache, key=lambda self, email_content, chat_mode=False: self._generate_cache_key(email_content, chat_mode))
    async def parse_email(self, email_content: str, chat_mode: bool = False) -> Union[Dict[str, Any], str]:
        """
        Parses a single email content using the configured AI provider with caching and performance monitoring.

        Args:
            email_content (str): The content of the email to parse.
            chat_mode (bool): Flag to enable chat-specific parsing (default: False).

        Returns:
            Union[Dict[str, Any], str]: Parsed and validated data or error message.
        """
        try:
            tokens = self._determine_token_limit(email_content)
            prompt = self._prepare_prompt(email_content)
            response = await self.send_request_with_retry(prompt, tokens)
            if 'error' in response:
                logger.error(f"AI provider error: {response['error']}")
                return {'error': response['error']}
            
            completion = self._extract_completion(response)
            if not completion:
                logger.warning("Empty completion received from AI provider.")
                return "No valid completion generated."

            parsed_data = self._parse_response(completion)
            validated_data = self._validate_parsed_fields(parsed_data)
            return validated_data

        except Exception as e:
            log_exception(e, "Unexpected error during parsing", self.strict_mode)
            return "Internal error during parsing."

    async def parse_emails(self, email_contents: List[str], chat_mode: bool = False) -> List[Union[Dict[str, Any], str]]:
        """
        Parses multiple email contents in batch using the configured AI provider with caching and performance monitoring.

        Args:
            email_contents (List[str]): List of email contents to parse.
            chat_mode (bool): Flag to enable chat-specific parsing (default: False).

        Returns:
            List[Union[Dict[str, Any], str]]: List of parsed and validated data or error messages.
        """
        try:
            tasks = []
            for content in email_contents:
                tasks.append(self.parse_email(content, chat_mode))
            
            # Limit concurrency based on configuration
            semaphore = asyncio.Semaphore(self.config['parser']['environment_specific'].get('development', {}).get('concurrency_limit', 10) if os.getenv('FLASK_ENV', 'development') == 'development' else self.config['parser']['environment_specific'].get('production', {}).get('concurrency_limit', 10))
            async def sem_task(task):
                async with semaphore:
                    return await task

            wrapped_tasks = [sem_task(task) for task in tasks]
            results = await asyncio.gather(*wrapped_tasks, return_exceptions=False)
            return results

        except Exception as e:
            log_exception(e, "Unexpected error during batch parsing", self.strict_mode)
            return [f"Internal error during parsing: {e}"] * len(email_contents)

    async def send_request_with_retry(self, prompt: str, max_tokens: int) -> Dict[str, Any]:
        """
        Sends a request to the configured AI provider with retry logic.

        Args:
            prompt (str): The prompt to send to the AI provider.
            max_tokens (int): Maximum number of tokens for the AI response.

        Returns:
            Dict[str, Any]: Response from the AI provider.
        """
        try:
            response = await self._send_ai_request(prompt, max_tokens)
            return response
        except Exception as e:
            log_exception(e, "AI request failed after retries", self.strict_mode)

    async def _send_ai_request(self, prompt: str, max_tokens: int) -> Dict[str, Any]:
        """
        Sends a request to the AI provider based on the configured provider.

        Args:
            prompt (str): The prompt to send.
            max_tokens (int): Maximum tokens for the response.

        Returns:
            Dict[str, Any]: AI provider response.
        """
        if self.ai_provider == "google":
            return await self._send_google_generative_ai_request(prompt, max_tokens)
        elif self.ai_provider == "vertex_ai":
            return await self._send_vertex_ai_request(prompt, max_tokens)
        else:
            error_msg = f"Unsupported AI provider: {self.ai_provider}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    async def _send_google_generative_ai_request(self, prompt: str, max_tokens: int) -> Dict[str, Any]:
        """
        Sends a request to Google Generative AI API.

        Args:
            prompt (str): The prompt to send.
            max_tokens (int): Maximum tokens for the response.

        Returns:
            Dict[str, Any]: Response from Google Generative AI.
        """
        try:
            response = await self.client.generate_text(
                prompt=prompt,
                max_tokens=max_tokens,
                **self.generation_config
            )
            return {"text": response.text}
        except Exception as e:
            log_exception(e, "Google Generative AI request failed", self.strict_mode)

    async def _send_vertex_ai_request(self, prompt: str, max_tokens: int) -> Dict[str, Any]:
        """
        Sends a request to Vertex AI endpoint.

        Args:
            prompt (str): The prompt to send.
            max_tokens (int): Maximum tokens for the response.

        Returns:
            Dict[str, Any]: Response from Vertex AI.
        """
        try:
            instances = [{"prompt": prompt}]
            parameters = {"max_tokens": max_tokens, **self.generation_config}
            request = PredictRequest(
                endpoint=self.config['ai']['vertex_ai']['model_name'],
                instances=instances,
                parameters=parameters
            )
            response = self.client.predict(request=request)
            if not response.predictions:
                raise ValueError("Empty response from Vertex AI")
            return response.predictions[0]
        except Exception as e:
            log_exception(e, "Vertex AI request failed", self.strict_mode)

    def _determine_token_limit(self, email_content: str) -> int:
        """
        Determines the token limit based on email content characteristics.

        Args:
            email_content (str): The email content.

        Returns:
            int: The determined token limit.
        """
        try:
            if self.dynamic_token_adjustment.get('enabled', False):
                doc = self.nlp(email_content)
                num_entities = len(doc.ents)
                keyword_density = self._calculate_keyword_density(doc)

                logger.debug(f"Number of entities: {num_entities}, Keyword density: {keyword_density}")

                tokens = self.parser_config.max_tokens
                if num_entities > 10 or keyword_density > 0.05:
                    tokens = min(tokens + 500, self.dynamic_token_adjustment.get('max_tokens_threshold', 2000))
                    logger.debug(f"Dynamically adjusted max_tokens to {tokens} based on entities or keyword density.")
                return tokens
            else:
                return self.parser_config.max_tokens
        except Exception as e:
            log_exception(e, "Error determining token limit", self.strict_mode)

    def _calculate_keyword_density(self, doc: spacy.tokens.Doc) -> float:
        """
        Calculates keyword density based on predefined keywords.

        Args:
            doc (spacy.tokens.Doc): The spaCy processed document.

        Returns:
            float: The keyword density.
        """
        keywords = {'insurance', 'claim', 'policy', 'loss', 'carrier', 'insured'}
        total_tokens = len(doc)
        keyword_tokens = sum(1 for token in doc if token.text.lower() in keywords)
        if total_tokens == 0:
            return 0.0
        density = keyword_tokens / total_tokens
        logger.debug(f"Keyword density calculated: {density}")
        return density

    def _prepare_prompt(self, email_content: str) -> str:
        """
        Prepares the AI prompt by injecting email content into the prompt template.

        Args:
            email_content (str): The email content.

        Returns:
            str: The prepared prompt.
        """
        try:
            prompt = self.prompt_template.replace('{{email_content}}', email_content)
            logger.debug("Prompt prepared successfully.")
            return prompt
        except Exception as e:
            log_exception(e, "Error preparing prompt", self.strict_mode)

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parses the AI provider's response to extract structured data.

        Args:
            response (str): The raw response from the AI provider.

        Returns:
            Dict[str, Any]: Parsed data.
        """
        try:
            parsed_data = {}
            current_section = None

            for line in response.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('**') and line.endswith('**'):
                    section_name = self._extract_section_name(line)
                    parsed_data[section_name] = {}
                    current_section = section_name
                    logger.debug(f"Parsing section: {section_name}")
                elif line.startswith('-') and current_section:
                    key, value = self._extract_key_value(line)
                    if key and value:
                        if key in parsed_data[current_section] and parsed_data[current_section][key] == value:
                            logger.warning(f"Loop detected for field '{key}' with value '{value}'.")
                            if self.strict_mode:
                                raise ValueError(f"Loop detected in parsing for field '{key}'.")
                            else:
                                parsed_data[current_section][key] = f"{value} (Loop Detected)"
                        else:
                            parsed_data[current_section][key] = value
                            logger.debug(f"Parsed field '{key}': '{value}'")
            logger.debug(f"Parsed data: {parsed_data}")
            return parsed_data
        except Exception as e:
            log_exception(e, "Error parsing AI response", self.strict_mode)

    def _extract_section_name(self, line: str) -> str:
        """
        Extracts the section name from a line starting and ending with '**'.

        Args:
            line (str): The line containing the section name.

        Returns:
            str: The extracted section name.
        """
        section_name = line.strip('*').strip().lower().replace(' ', '_')
        logger.debug(f"Extracted section name: {section_name}")
        return section_name

    def _extract_key_value(self, line: str) -> Union[tuple, tuple]:
        """
        Extracts key and value from a line starting with '-'.

        Args:
            line (str): The line containing the key-value pair.

        Returns:
            tuple: A tuple containing the key and value.
        """
        try:
            parts = line[1:].split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip().lower().replace(' ', '_').replace('(', '').replace(')', '')
                value = parts[1].strip()
                logger.debug(f"Extracted key-value pair: '{key}': '{value}'")
                return key, value
            else:
                logger.warning(f"Invalid key-value format: {line}")
                return None, None
        except Exception as e:
            logger.error(f"Error extracting key-value from line: {line} - {e}")
            return None, None

    def _validate_parsed_fields(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates parsed fields using regex patterns from configuration.

        Args:
            parsed_data (Dict[str, Any]): The parsed data to validate.

        Returns:
            Dict[str, Any]: Validated data.
        """
        try:
            validated_data = {}
            for section, fields in parsed_data.items():
                validated_data[section] = {}
                for key, value in fields.items():
                    pattern_key = f"{key}_pattern"
                    pattern = self.field_validation.get(pattern_key)

                    if pattern and value != "N/A":
                        if not re.match(pattern, value):
                            logger.warning(f"Validation failed for field '{key}': Value='{value}', Expected Pattern='{pattern}'")
                            if self.strict_mode:
                                raise ValueError(f"Validation failed for field '{key}' with value '{value}'")
                            else:
                                validated_data[section][key] = f"{value} (Invalid Format)"
                        else:
                            validated_data[section][key] = value
                            logger.debug(f"Field '{key}' validated successfully.")
                    else:
                        validated_data[section][key] = value
                        logger.debug(f"Field '{key}' does not require validation.")
            if self._detect_repeated_patterns(validated_data):
                logger.warning("Repeated output patterns detected in validated data.")
            logger.debug(f"Validated data: {validated_data}")
            return validated_data
        except Exception as e:
            log_exception(e, "Error validating parsed fields", self.strict_mode)

    def _detect_repeated_patterns(self, data: Dict[str, Any]) -> bool:
        """
        Detects repeated patterns in the validated data.

        Args:
            data (Dict[str, Any]): The validated data.

        Returns:
            bool: True if repeated patterns are detected, False otherwise.
        """
        try:
            seen = {}
            has_repeats = False

            for section, fields in data.items():
                for key, value in fields.items():
                    if value in seen:
                        seen[value] += 1
                        if seen[value] > 3:
                            has_repeats = True
                            logger.debug(f"Value '{value}' repeated {seen[value]} times in section '{section}', field '{key}'")
                    else:
                        seen[value] = 1

            logger.debug(f"Repeated patterns detected: {has_repeats}")
            return has_repeats
        except Exception as e:
            logger.error(f"Error detecting repeated patterns: {e}")
            return False

    def _generate_cache_key(self, email_content: str, chat_mode: bool = False) -> str:
        """
        Generates a unique cache key based on email content and chat mode.

        Args:
            email_content (str): The email content.
            chat_mode (bool): Chat mode flag.

        Returns:
            str: The generated cache key.
        """
        hash_input = f"{email_content}|{chat_mode}"
        cache_key = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        logger.debug(f"Generated cache key: {cache_key}")
        return cache_key

    def clear_cache(self) -> None:
        """
        Clears the cache manually.

        Logs the cache clearing action.
        """
        self.cache.clear()
        logger.info("Cache cleared manually.")

    @performance_monitor
    async def close(self):
        """
        Closes the aiohttp session gracefully.
        """
        try:
            await self.session.close()
            logger.debug("Aiohttp session closed successfully.")
        except Exception as e:
            logger.error(f"Error closing aiohttp session: {e}")

    def _extract_completion(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Extracts the completion text from the AI provider's response.

        Args:
            response (Dict[str, Any]): The AI provider's response.

        Returns:
            Optional[str]: The extracted completion text or None if not found.
        """
        try:
            if self.ai_provider == "google":
                return response.get("text")
            elif self.ai_provider == "vertex_ai":
                return response.get("text")  # Adjust based on actual response structure
            else:
                logger.error(f"Unsupported AI provider for extracting completion: {self.ai_provider}")
                return None
        except Exception as e:
            logger.error(f"Error extracting completion from response: {e}")
            return None
