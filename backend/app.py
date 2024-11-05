import os
import yaml
import logging
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
from werkzeug.middleware.proxy_fix import ProxyFix
import re
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed

# Load environment variables from .env file
load_dotenv()

# Step 1: Set up a basic logger to handle configuration loading errors
logging.basicConfig(level=logging.DEBUG)
basic_logger = logging.getLogger("basic_logger")

def setup_logging(config):
    """Set up logging based on the configuration."""
    log_level = config.get('logging', {}).get('level', 'DEBUG').upper()
    log_file = config.get('logging', {}).get('file_path', 'logs/app.log')
    create_logs_dir = config.get('logging', {}).get('create_logs_dir_if_not_exists', True)

    if create_logs_dir:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Remove all handlers associated with the root logger object.
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def load_config():
    """Load and validate the YAML configuration file."""
    config_path = os.path.join(os.path.dirname(__file__), 'parser.config.yaml')
    try:
        basic_logger.debug(f"Attempting to load configuration from {config_path}")
        with open(config_path, 'r') as file:
            config_data = yaml.safe_load(file)
            validate_config(config_data)
            basic_logger.debug("Configuration loaded successfully.")
            return config_data
    except FileNotFoundError:
        basic_logger.critical(f"Configuration file not found at {config_path}")
        raise
    except yaml.YAMLError as e:
        basic_logger.critical(f"Error parsing configuration file: {e}")
        raise
    except Exception as e:
        basic_logger.critical(f"Unexpected error loading configuration: {e}")
        raise

def validate_config(config):
    """Validate the presence of necessary configuration fields."""
    required_fields = ['models', 'field_validation', 'cache_dir', 'logging', 'lm_studio']
    for field in required_fields:
        if field not in config:
            basic_logger.critical(f"Missing required configuration field: {field}")
            raise KeyError(f"Missing required configuration field: {field}")

    # Validate models
    if not config['models']:
        basic_logger.critical("No models defined in the configuration.")
        raise KeyError("No models defined in the configuration.")

def clean_response(text):
    """Clean and format the model's response."""
    # Remove code block markers
    text = re.sub(r'```.*?\n', '', text, flags=re.DOTALL)
    text = text.replace('```', '')

    # Remove any content after [INST] tag
    if '[INST]' in text:
        text = text.split('[INST]')[0]

    # Process the text line by line to clean up formatting
    current_section = None
    cleaned_lines = []
    sections = {}

    for line in text.split('\n'):
        # Strip whitespace and skip empty lines
        line = line.strip()
        if not line:
            continue

        # Handle section headers
        if line.startswith('**') and line.endswith('**'):
            current_section = line
            if current_section not in sections:
                sections[current_section] = True
                # Add a newline before sections (except the first one)
                if cleaned_lines:
                    cleaned_lines.append('')
                cleaned_lines.append(current_section)
        # Handle field lines
        elif line.startswith('-'):
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                cleaned_lines.append(f"{key}: {value}")
        # Handle field values that got split across lines
        elif current_section and ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                cleaned_lines.append(f"- {key}: {value}")

    # Join lines with single newlines
    return '\n'.join(cleaned_lines)

def check_lm_studio_connection(lm_studio_config):
    """Verify connection to LM Studio and check model availability."""
    try:
        response = requests.get(
            f"{lm_studio_config['base_url']}/v1/models",
            headers={"Authorization": f"Bearer {lm_studio_config['api_key']}"},
            timeout=lm_studio_config['timeout']
        )
        if response.ok:
            models = response.json()
            logger.info(f"LM Studio connected successfully. Available models: {[model['id'] for model in models.get('data', [])]}")
            return True
        logger.error(f"LM Studio returned status {response.status_code}")
        return False
    except requests.RequestException as e:
        logger.error(f"Failed to connect to LM Studio: {e}")
        return False

@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def make_lm_studio_request(payload):
    """Make a POST request to LM Studio with retry logic."""
    response = requests.post(
        f"{LM_STUDIO_CONFIG['base_url']}/v1/completions",
        headers={"Authorization": f"Bearer {LM_STUDIO_CONFIG['api_key']}"},
        json=payload,
        timeout=60  # Reduced timeout
    )
    response.raise_for_status()
    return response.json()

def get_active_model():
    """
    Get the first available model from the configuration that is loaded in LM Studio.
    Returns a tuple of (model_id, model_config).
    """
    try:
        logger.debug("Fetching available models from LM Studio")
        response = requests.get(
            f"{LM_STUDIO_CONFIG['base_url']}/v1/models",
            headers={"Authorization": f"Bearer {LM_STUDIO_CONFIG['api_key']}"},
            timeout=LM_STUDIO_CONFIG['timeout']
        )

        if not response.ok:
            logger.error(f"Failed to get models: Status {response.status_code}")
            return (None, None)

        available_models = response.json().get('data', [])
        if not available_models:
            logger.error("No models found in LM Studio response")
            return (None, None)

        available_model_ids = [model['id'] for model in available_models]

        # Iterate through configured models and select the first available one
        for model_name, model_info in config['models'].items():
            repo_id = model_info.get('repo_id')
            if repo_id in available_model_ids:
                logger.info(f"Selected model: {repo_id}")
                return (repo_id, model_info)

        logger.error("No matching models from configuration are available in LM Studio")
        return (None, None)

    except requests.RequestException as e:
        logger.error(f"Request error getting active model: {e}")
        return (None, None)
    except Exception as e:
        logger.error(f"Unexpected error getting active model: {e}")
        return (None, None)

# Step 2: Load configuration
config = load_config()

# Step 3: Set up the main logger based on the loaded configuration
logger = setup_logging(config)

# LM Studio configuration from config file
LM_STUDIO_CONFIG = config['lm_studio']

# Step 4: Initialize Flask app
app = Flask(__name__,
    static_folder='static',
    static_url_path='/static',
    template_folder='templates'
)

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# CORS configuration
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Adjust as needed for security
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Perform setup tasks immediately after initializing the app
logger.info("Starting up Flask application...")
if not check_lm_studio_connection(LM_STUDIO_CONFIG):
    logger.warning("LM Studio connection failed at startup")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to monitor application status."""
    health_data = {
        "status": "unhealthy",
        "components": {
            "lm_studio": False,
            "config": bool(config),
            "static_files": os.path.exists('static'),
            "templates": os.path.exists('templates')
        }
    }

    try:
        if check_lm_studio_connection(LM_STUDIO_CONFIG):
            health_data["components"]["lm_studio"] = True
            health_data["status"] = "healthy"
    except Exception as e:
        logger.error(f"Health check failed: {e}")

    return jsonify(health_data)

@app.route('/')
def serve_frontend():
    """Serve the frontend application."""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error serving frontend: {e}")
        return jsonify({"error": "Failed to load application"}), 500

@app.route('/parse_email', methods=['POST'])
def parse_email():
    """Endpoint to parse email content."""
    try:
        logger.info("Received email parse request")

        # Validate request data
        data = request.get_json()
        if not data or 'email_content' not in data:
            logger.error("Missing email content in request")
            return jsonify({'error': 'No email content provided'}), 400

        email_content = data['email_content']
        logger.debug(f"Email content length: {len(email_content)}")

        # Get active model
        model_id, model_config = get_active_model()
        if not model_id or not model_config:
            logger.error("No active model found in LM Studio")
            return jsonify({'error': 'No active model found in LM Studio'}), 503

        logger.info(f"Using model: {model_id}")

        # Prepare request payload
        prompt = model_config["prompt_template"].replace("{{email_content}}", email_content)
        payload = {
            "model": model_id,
            "prompt": prompt,
            "max_tokens": model_config["max_tokens"],
            **model_config["generation_config"]
        }

        # Make request to LM Studio with retry logic
        logger.info("Sending request to LM Studio")
        try:
            result = make_lm_studio_request(payload)
            logger.debug(f"Raw LM Studio response: {result}")
        except requests.RequestException as e:
            logger.error(f"Request to LM Studio failed: {str(e)}")
            return jsonify({'error': f'Failed to connect to LM Studio: {str(e)}'}), 503

        # Extract and validate completion
        completion = result.get('choices', [{}])[0].get('text', '').strip()
        if not completion:
            logger.warning("Empty completion received from LM Studio")
            return jsonify({'error': 'No valid completion generated'}), 500

        # Clean and format the response
        cleaned_response = clean_response(completion)
        if not cleaned_response:
            logger.warning("No valid content after cleaning response")
            return jsonify({'error': 'No valid content generated'}), 500

        # Validate fields using regex patterns
        validated_response = validate_parsed_fields(cleaned_response)

        logger.info("Successfully processed email parsing request")
        return jsonify({'result': validated_response}), 200

    except Exception as e:
        logger.error(f"Unexpected error in parse_email: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

def validate_parsed_fields(parsed_text):
    """
    Validate parsed fields using regex patterns defined in the configuration.
    Returns the parsed text with validations applied or annotations if invalid.
    """
    field_patterns = config.get('field_validation', {})
    validated_lines = []

    for line in parsed_text.split('\n'):
        if ':' not in line:
            validated_lines.append(line)
            continue
        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()
        pattern_key = f"{key.lower()}_pattern"
        pattern = field_patterns.get(pattern_key)
        if pattern and value != "N/A":
            if not re.match(pattern, value):
                logger.warning(f"Validation failed for {key}: {value}")
                value += " (Invalid)"
        validated_lines.append(f"{key}: {value}")

    return '\n'.join(validated_lines)

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application...")
    app.run(host='0.0.0.0', port=5000, debug=False)
