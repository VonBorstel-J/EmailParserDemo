# config_loader.py

import os
import json
import yaml
import logging
import sys
from threading import Lock
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from cerberus import Validator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure a basic logger for configuration loading
logger = logging.getLogger("config_loader")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
logger.addHandler(handler)

# Configuration Schema using Cerberus
CONFIG_SCHEMA = {
    'ai': {
        'type': 'dict',
        'required': True,
        'schema': {
            'generative_ai': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'provider': {'type': 'string', 'allowed': ['google', 'vertex_ai'], 'required': True},
                    'google': {
                        'type': 'dict',
                        'required': False,
                        'schema': {
                            'endpoint': {'type': 'string', 'required': True, 'regex': r'^https?://'},
                            'api_key': {'type': 'string', 'required': True},
                            'max_tokens': {'type': 'integer', 'min': 1, 'required': True}
                        }
                    },
                    'vertex_ai': {
                        'type': 'dict',
                        'required': False,
                        'schema': {
                            'model_name': {'type': 'string', 'required': True},
                            'max_tokens': {'type': 'integer', 'min': 1, 'required': True}
                        }
                    }
                }
            },
            'vertex_ai': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'endpoint': {'type': 'string', 'required': True},
                    'location': {'type': 'string', 'required': True}
                }
            }
        }
    },
    'logging': {
        'type': 'dict',
        'required': True,
        'schema': {
            'level': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 'required': True},
            'file_path': {'type': 'string', 'required': True},
            'create_logs_dir_if_not_exists': {'type': 'boolean', 'required': True}
        }
    },
    'batch_processing': {
        'type': 'dict',
        'required': True,
        'schema': {
            'enabled': {'type': 'boolean', 'required': True},
            'batch_size': {'type': 'integer', 'min': 1, 'required': True}
        }
    },
    'dynamic_token_adjustment': {
        'type': 'dict',
        'required': True,
        'schema': {
            'enabled': {'type': 'boolean', 'required': True},
            'max_tokens_threshold': {'type': 'integer', 'min': 1, 'required': True}
        }
    },
    'caching': {
        'type': 'dict',
        'required': True,
        'schema': {
            'enabled': {'type': 'boolean', 'required': True},
            'ttl': {'type': 'integer', 'min': 1, 'required': True},
            'dir': {'type': 'string', 'required': False}
        }
    },
    'health_checks': {  # Changed from 'health_check' to 'health_checks'
        'type': 'dict',
        'required': True,
        'schema': {
            'enable_vertex_ai_latency': {'type': 'boolean', 'required': True},
            'enable_vertex_ai_quota': {'type': 'boolean', 'required': True},
            'enable_vertex_ai_resource_usage': {'type': 'boolean', 'required': True},
            'enable_secret_manager': {'type': 'boolean', 'required': True},
            'enable_cloud_storage': {'type': 'boolean', 'required': True}
        }
    },
    'app': {
        'type': 'dict',
        'required': True,
        'schema': {
            'cors': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'production': {
                        'type': 'dict',
                        'required': True,
                        'schema': {
                            'allowed_origins': {'type': 'list', 'schema': {'type': 'string'}, 'required': True}
                        }
                    },
                    'development': {
                        'type': 'dict',
                        'required': True,
                        'schema': {
                            'allowed_origins': {'type': 'list', 'schema': {'type': 'string'}, 'required': True}
                        }
                    }
                }
            },
            'rate_limit': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'default': {'type': 'string', 'required': True},
                    'parse_email': {'type': 'string', 'required': True}
                }
            }
        }
    },
    'parser': {
        'type': 'dict',
        'required': True,
        'schema': {
            'prompt_template': {'type': 'string', 'required': True},
            'field_validation': {'type': 'dict', 'required': True},
            'logging': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'level': {'type': 'string', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 'required': True},
                    'file_path': {'type': 'string', 'required': True},
                    'create_logs_dir_if_not_exists': {'type': 'boolean', 'required': True}
                }
            },
            'cache': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'dir': {'type': 'string', 'required': True},
                    'ttl': {'type': 'integer', 'min': 1, 'required': True}
                }
            },
            'max_tokens': {'type': 'integer', 'min': 1, 'required': True},
            'dynamic_token_adjustment': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'enabled': {'type': 'boolean', 'required': True},
                    'max_tokens_threshold': {'type': 'integer', 'min': 1, 'required': True}
                }
            },
            'batch_processing': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'batch_size': {'type': 'integer', 'min': 1, 'required': True}
                }
            },
            'environment_specific': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'development': {'type': 'dict', 'required': True},
                    'production': {'type': 'dict', 'required': True}
                }
            },
            'strict_mode': {'type': 'boolean', 'required': False, 'default': True}
        }
    }
}

class ConfigLoader(FileSystemEventHandler):
    """
    Singleton class to load and watch the configuration file.
    Validates the configuration using Cerberus schema.
    """
    _instance = None
    _lock = Lock()

    def __init__(self, config_path='config.yaml'):
        if ConfigLoader._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            self.config_path = config_path
            self.load_config()
            self.observer = Observer()
            self.observer.schedule(self, path=os.path.dirname(os.path.abspath(config_path)) or '.', recursive=False)
            self.observer.start()
            ConfigLoader._instance = self

    @staticmethod
    def get_instance():
        """
        Retrieves the singleton instance of ConfigLoader.
        """
        if ConfigLoader._instance is None:
            with Lock():
                if ConfigLoader._instance is None:
                    ConfigLoader()
        return ConfigLoader._instance

    def load_config(self):
        """
        Loads and validates the configuration file.
        Logs detailed errors and exits gracefully if validation fails.
        """
        try:
            with open(self.config_path, 'r') as file:
                config = yaml.safe_load(file)
            validator = Validator(CONFIG_SCHEMA, purge_unknown=True)
            if not validator.validate(config):
                error_messages = validator.errors
                logger.critical(f"Configuration validation failed: {json.dumps(error_messages, indent=2)}")
                sys.exit(1)
            self.config = validator.document
            logger.info("Configuration loaded and validated successfully.")
        except FileNotFoundError:
            logger.critical(f"Configuration file '{self.config_path}' not found.")
            sys.exit(1)
        except yaml.YAMLError as e:
            logger.critical(f"Error parsing configuration file: {e}")
            sys.exit(1)
        except Exception as e:
            logger.critical(f"Unexpected error loading configuration: {e}")
            sys.exit(1)

    def on_modified(self, event):
        """
        Event handler for configuration file modifications.
        Reloads and validates the configuration upon changes.
        """
        if event.src_path.endswith(self.config_path):
            logger.info("Configuration file changed. Reloading...")
            self.load_config()
