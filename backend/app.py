import os
import logging
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from parser import EmailParser
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables from .env file
load_dotenv()

# Set Flask environment
flask_env = os.getenv('FLASK_ENV', 'development')

# Initialize Flask app
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

# Initialize Limiter for rate limiting
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]  # Adjust limits as needed
)

# Initialize EmailParser
email_parser = EmailParser(config_path='parser.config.yaml')

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Or set based on config

# Clear existing handlers
if logger.hasHandlers():
    logger.handlers.clear()

# File handler with rotation
file_handler = RotatingFileHandler(
    'logs/app.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setFormatter(
    logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
)
logger.addHandler(file_handler)

# Console handler for Flask app logs
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
)
logger.addHandler(console_handler)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to monitor application status."""
    health_data = {
        "status": "unhealthy",
        "components": {
            "lm_studio": False,
            "config": True,  # Assume config loaded if parser initialized
            "static_files": os.path.exists('static'),
            "templates": os.path.exists('templates'),
            "cache_size": len(email_parser.cache)
        },
        "performance": {
            "memory_usage_mb": self._get_memory_usage()
        }
    }

    try:
        if email_parser.check_lm_studio_connection():
            health_data["components"]["lm_studio"] = True
            health_data["status"] = "healthy"
    except Exception as e:
        logger.error(f"Health check failed: {e}")

    return jsonify(health_data)

def _get_memory_usage():
    """Utility function to get current memory usage."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem = process.memory_info().rss / (1024 * 1024)  # Convert to MB
        return round(mem, 2)
    except Exception as e:
        logger.error(f"Error fetching memory usage: {e}")
        return "N/A"

@app.route('/', methods=['GET'])
def serve_frontend():
    """Serve the frontend application."""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error serving frontend: {e}")
        return jsonify({"error": "Failed to load application"}), 500

@app.route('/parse_email', methods=['POST'])
@limiter.limit("10 per minute")  # Adjust rate limits as needed
def parse_email_endpoint():
    """Endpoint to parse email content."""
    try:
        logger.info("Received email parse request")

        # Validate request data
        data = request.get_json()
        if not data or 'email_content' not in data:
            logger.error("Missing email content in request")
            return jsonify({'error': 'No email content provided'}), 400

        email_content = data['email_content']
        if not isinstance(email_content, str) or not email_content.strip():
            logger.error("Invalid email content format")
            return jsonify({'error': 'Invalid email content provided'}), 400

        logger.debug(f"Email content length: {len(email_content)}")

        # Delegate parsing to EmailParser
        result = email_parser.parse_email(email_content)

        if isinstance(result, str):
            # It's an error message
            logger.error(f"Parsing error: {result}")
            return jsonify({'error': result}), 503
        else:
            # Successfully parsed data
            logger.info("Successfully processed email parsing request")
            return jsonify({'result': result}), 200

    except Exception as e:
        logger.error(f"Unexpected error in parse_email: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    logger.warning(f"404 error: {error}")
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(429)
def rate_limit_exceeded(error):
    """Handle rate limit errors."""
    logger.warning(f"Rate limit exceeded: {error}")
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application...")
    app.run(host='0.0.0.0', port=5000, debug=(flask_env == 'development'))
