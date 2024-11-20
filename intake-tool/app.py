# app.py

import os
import logging
import psutil  # For CPU and Disk usage metrics
import time
import sys
import asyncio
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
from google.cloud import secretmanager, storage, logging as cloud_logging, monitoring_v3
from google.cloud.monitoring_v3 import Query
from google.cloud.aiplatform import gapic as aiplatform_gapic
from google.cloud.aiplatform_v1.types import PredictRequest
from exporter import export_to_pdf, export_to_csv
from functools import lru_cache
from tenacity import retry, stop_after_attempt, wait_exponential
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import json
import yaml
from threading import Lock
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
from starlette.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Optional
import atexit
from parser import EmailParser  # Ensure EmailParser does not import app.py
from google.cloud.logging.handlers import CloudLoggingHandler

# Import ConfigLoader from config_loader.py
from config_loader import ConfigLoader

# Load environment variables from .env file
load_dotenv()

# Initialize ConfigLoader
config_loader = ConfigLoader.get_instance()
config = config_loader.config

# Initialize FastAPI app
app = FastAPI()

# Configuration for AsyncIOScheduler
scheduler = AsyncIOScheduler()

# Initialize Google Cloud Logging
client_logging = cloud_logging.Client()
client_logging.setup_logging()

# Ensure credentials.json is loaded
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
if not os.path.exists(credentials_path):
    logging.getLogger("app").critical("GCP credentials file 'credentials.json' not found. Ensure it is uploaded.")
    sys.exit(1)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

# Initialize Logging
logger = logging.getLogger("app")
logger.setLevel(getattr(logging, config['logging']['level'].upper(), logging.DEBUG))

# Remove default handlers to avoid duplicate logs
if logger.hasHandlers():
    logger.handlers.clear()

# Add Cloud Logging handler with structured logging
cloud_handler = CloudLoggingHandler(client_logging)
cloud_handler.setFormatter(logging.Formatter(
    '{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(module)s", "message": "%(message)s"}'
))
logger.addHandler(cloud_handler)

# CORS configuration based on environment
ENV = os.getenv('FLASK_ENV', 'development')
if ENV == 'production':
    allowed_origins = config['app']['cors']['production']['allowed_origins']
else:
    allowed_origins = config['app']['cors']['development']['allowed_origins']

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Initialize Limiter with dynamic rate limits from config
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialize Google Cloud Secret Manager client
secret_client = secretmanager.SecretManagerServiceClient()

# Initialize Google Cloud Storage client
GCP_PROJECT = os.getenv('GCP_PROJECT', 'forensicemailparser')
storage_client = storage.Client(project=GCP_PROJECT)

# Initialize Google Cloud Monitoring client
monitoring_client = monitoring_v3.MetricServiceClient()
project_name = f"projects/{GCP_PROJECT}"

# Centralize Vertex AI client initialization with a factory pattern
class VertexAIClientFactory:
    """
    Factory for creating and managing a single Vertex AI client instance.
    """
    _client = None

    @classmethod
    def get_client(cls):
        """
        Retrieves the Vertex AI PredictionServiceClient instance.
        """
        if cls._client is None:
            cls._client = aiplatform_gapic.PredictionServiceClient()
        return cls._client

vertex_client = VertexAIClientFactory.get_client()

# Initialize EmailParser
email_parser = EmailParser(config_path='config.yaml')  # Updated to use 'config.yaml'

# Initialize Jinja2 Templates
templates = Jinja2Templates(directory="templates")

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Utility Functions
def _get_memory_usage():
    """
    Get current memory usage of the application.

    Returns:
        float or str: Memory usage in MB or "N/A" if an error occurs.
    """
    try:
        process = psutil.Process(os.getpid())
        mem = process.memory_info().rss / (1024 * 1024)  # Convert to MB
        return round(mem, 2)
    except Exception as e:
        logger.error(f"Error fetching memory usage: {e}")
        return "N/A"

def _get_cpu_usage():
    """
    Get current CPU usage percentage of the application.

    Returns:
        float or str: CPU usage percentage or "N/A" if an error occurs.
    """
    try:
        cpu = psutil.cpu_percent(interval=1)
        return cpu
    except Exception as e:
        logger.error(f"Error fetching CPU usage: {e}")
        return "N/A"

def _get_disk_usage():
    """
    Get current disk usage statistics.

    Returns:
        dict or str: Disk usage details or "N/A" if an error occurs.
    """
    try:
        disk = psutil.disk_usage('/')
        return {
            'total_gb': round(disk.total / (1024 ** 3), 2),
            'used_gb': round(disk.used / (1024 ** 3), 2),
            'free_gb': round(disk.free / (1024 ** 3), 2),
            'percent_used': disk.percent
        }
    except Exception as e:
        logger.error(f"Error fetching disk usage: {e}")
        return "N/A"

def get_secret(secret_name, fallback=None):
    """
    Retrieve secret from GCP Secret Manager with optional fallback.

    Args:
        secret_name (str): Name of the secret to retrieve.
        fallback (str, optional): Fallback value if retrieval fails.

    Returns:
        str: Secret value or fallback.
    """
    try:
        project_id = os.getenv('GCP_PROJECT', 'forensicemailparser')
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode('UTF-8')
    except Exception as e:
        logger.error(f"Failed to retrieve secret '{secret_name}': {e}")
        return fallback

def load_valid_api_keys():
    """
    Load valid API keys from GCP Secret Manager.

    Returns:
        set: A set of valid API keys.
    """
    try:
        keys = get_secret('VALID_API_KEYS')  # Store as comma-separated in Secret Manager
        if keys:
            return set(key.strip() for key in keys.split(','))
        else:
            logger.warning("No API keys found in Secret Manager.")
            return set()
    except Exception as e:
        logger.error(f"Error loading API keys: {e}")
        return set()

VALID_API_KEYS = load_valid_api_keys()

def validate_api_key(api_key: Optional[str]) -> bool:
    """
    Validate API key against the list of valid keys.

    Args:
        api_key (str): API key to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    return api_key in VALID_API_KEYS

def get_config():
    """
    Accessor to fetch the latest configuration.

    Returns:
        dict: Latest configuration dictionary.
    """
    return config_loader.config

# Dependency to inject configuration
async def get_current_config():
    return get_config()

# Dependency to validate API Key
async def api_key_dependency(request: Request):
    api_key = request.headers.get('X-API-Key')
    if not api_key or not validate_api_key(api_key):
        logger.warning("Invalid or missing API key.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return api_key

# Dependency to inject Vertex AI client
async def get_vertex_client():
    return VertexAIClientFactory.get_client()

# Dependency to inject EmailParser
async def get_email_parser():
    return email_parser

# Health Monitoring using GCP Operations Suite
def check_vertex_ai_quota():
    """
    Check Vertex AI API usage quotas using GCP Monitoring APIs.

    Returns:
        str: Quota information or "N/A" if unavailable.
    """
    try:
        # Example: Query the number of prediction requests in the last minute
        interval = monitoring_v3.TimeInterval(
            end_time={'seconds': int(time.time())},
            start_time={'seconds': int(time.time()) - 60},
        )
        results = monitoring_client.list_time_series(
            request={
                "name": project_name,
                "filter": 'metric.type="aiplatform.googleapis.com/prediction/count"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        total_requests = 0
        for result in results:
            for point in result.points:
                total_requests += int(point.value.int64_value)
        # Placeholder quota limit
        QUOTA_LIMIT = 1000  # Example quota limit
        quota_remaining = QUOTA_LIMIT - total_requests
        return f"{quota_remaining} requests remaining out of {QUOTA_LIMIT}"
    except Exception as e:
        logger.error(f"Failed to check Vertex AI quota: {e}")
        return "N/A"

def get_vertex_ai_latency():
    """
    Retrieve Vertex AI latency metrics using GCP Monitoring APIs.

    Returns:
        float or str: Average latency in ms or "N/A" if unavailable.
    """
    try:
        interval = monitoring_v3.TimeInterval(
            end_time={'seconds': int(time.time())},
            start_time={'seconds': int(time.time()) - 60},
        )
        results = monitoring_client.list_time_series(
            request={
                "name": project_name,
                "filter": 'metric.type="aiplatform.googleapis.com/prediction/latency"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        latencies = []
        for result in results:
            for point in result.points:
                latencies.append(float(point.value.double_value))
        if latencies:
            average_latency = sum(latencies) / len(latencies)
            return round(average_latency, 2)
        else:
            return "N/A"
    except Exception as e:
        logger.error(f"Failed to retrieve Vertex AI latency: {e}")
        return "N/A"

def get_vertex_ai_resource_usage():
    """
    Retrieve Vertex AI resource usage metrics using GCP Monitoring APIs.

    Returns:
        str: Resource usage details or "N/A" if unavailable.
    """
    try:
        # Placeholder implementation
        # Implement specific resource usage checks as needed
        return "Resource usage details not implemented"
    except Exception as e:
        logger.error(f"Failed to retrieve Vertex AI resource usage: {e}")
        return "N/A"

def check_secret_manager():
    """
    Check connectivity to GCP Secret Manager.

    Returns:
        bool: True if accessible, False otherwise.
    """
    try:
        _ = get_secret('VERTEX_AI_ENDPOINT', fallback="None")
        return True
    except Exception as e:
        logger.error(f"Secret Manager health check failed: {e}")
        return False

def check_cloud_storage():
    """
    Check connectivity to GCP Cloud Storage.

    Returns:
        bool: True if accessible, False otherwise.
    """
    try:
        buckets = list(storage_client.list_buckets())
        return True if buckets else False
    except Exception as e:
        logger.error(f"Cloud Storage health check failed: {e}")
        return False

def perform_health_checks():
    """
    Perform all enabled health checks based on configuration.

    Returns:
        dict: Health data including status and performance metrics.
    """
    current_config = get_config()
    health_data = {
        "status": "unhealthy",
        "components": {
            "vertex_ai": False,
            "secret_manager": False,
            "cloud_storage": False,
            "config": True,
            "static_files": os.path.exists('static'),
            "templates": os.path.exists('templates'),
            "credentials": os.path.exists(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))
        },
        "performance": {
            "memory_usage_mb": _get_memory_usage(),
            "cpu_usage_percent": _get_cpu_usage(),
            "disk_usage": _get_disk_usage(),
            "vertex_ai_latency_ms": "N/A",
            "vertex_ai_quota": "N/A",
            "vertex_ai_resource_usage": "N/A"
        }
    }

    # Check Vertex AI connectivity with retries
    try:
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
        def check_vertex_ai():
            vertex_client.get_endpoint(name=current_config['ai']['vertex_ai']['endpoint'])
        check_vertex_ai()
        health_data["components"]["vertex_ai"] = True
    except Exception as e:
        logger.error(f"Vertex AI connectivity check failed: {e}")

    # Check Secret Manager connectivity
    if current_config['health_checks']['enable_secret_manager']:
        health_data["components"]["secret_manager"] = check_secret_manager()

    # Check Cloud Storage connectivity
    if current_config['health_checks']['enable_cloud_storage']:
        health_data["components"]["cloud_storage"] = check_cloud_storage()

    # Check Vertex AI latency
    if current_config['health_checks']['enable_vertex_ai_latency']:
        latency = get_vertex_ai_latency()
        health_data["performance"]["vertex_ai_latency_ms"] = latency

    # Check Vertex AI quota
    if current_config['health_checks']['enable_vertex_ai_quota']:
        quota = check_vertex_ai_quota()
        health_data["performance"]["vertex_ai_quota"] = quota

    # Check Vertex AI resource usage
    if current_config['health_checks']['enable_vertex_ai_resource_usage']:
        resource_usage = get_vertex_ai_resource_usage()
        health_data["performance"]["vertex_ai_resource_usage"] = resource_usage

    # Determine overall health status
    health_data["status"] = "healthy" if all(health_data["components"].values()) else "unhealthy"
    return health_data

def log_health_data(health_data):
    """
    Log the health data in a structured format.

    Args:
        health_data (dict): Health data to log.
    """
    logger.info(f"Health Check: {json.dumps(health_data)}")

# Health Check Endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint to monitor application status.

    Returns:
        JSONResponse: JSON response containing health data.
    """
    health_data = perform_health_checks()
    return JSONResponse(content=health_data)

# Serve Frontend
@app.get("/", response_class=Response)
async def serve_frontend(request: Request):
    """
    Serve the frontend application.

    Args:
        request (Request): Incoming request.

    Returns:
        HTMLResponse or JSONResponse: Rendered HTML template or error JSON.
    """
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"Error serving frontend: {e}")
        raise HTTPException(status_code=500, detail="Failed to load application")

# Parse Email Endpoint
@app.post("/parse_email")
@limiter.limit(lambda request: get_config()['app']['rate_limit']['parse_email'])
async def parse_email_endpoint(request: Request, api_key: str = Depends(api_key_dependency), 
                               email_parser: EmailParser = Depends(get_email_parser)):
    """
    Endpoint to parse email content.

    Args:
        request (Request): Incoming request.
        api_key (str): Validated API key.
        email_parser (EmailParser): Email parser instance.

    Returns:
        JSONResponse: Parsed data JSON or error message.
    """
    try:
        logger.info("Received email parse request")

        # Validate request data
        data = await request.json()
        if not data or 'email_content' not in data:
            logger.error("Missing email content in request")
            raise HTTPException(status_code=400, detail="No email content provided")

        email_content = data['email_content']
        if not isinstance(email_content, str) or not email_content.strip():
            logger.error("Invalid email content format")
            raise HTTPException(status_code=400, detail="Invalid email content provided")

        logger.debug(f"Email content length: {len(email_content)}")

        # Delegate parsing to EmailParser with retries for transient errors
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
        async def parse_email_with_retry(content):
            return await email_parser.parse_email(content)

        response = await parse_email_with_retry(email_content)

        if isinstance(response, dict) and 'error' in response:
            logger.error(f"Parsing error: {response['error']}")
            raise HTTPException(status_code=503, detail=response['error'])
        else:
            # Successfully parsed data
            logger.info("Successfully processed email parsing request")
            return JSONResponse(content={'result': response}, status_code=200)

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in parse_email: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Export PDF Endpoint
@app.post("/export_pdf")
async def export_pdf_endpoint(request: Request):
    """
    Endpoint to export parsed data to PDF.

    Args:
        request (Request): Incoming request.

    Returns:
        Response: PDF file download or error message.
    """
    try:
        data = await request.json()
        if not data or 'parsed_data' not in data:
            raise HTTPException(status_code=400, detail="No parsed data provided")

        # Assuming export_to_pdf is a synchronous function
        pdf_bytes = await asyncio.to_thread(export_to_pdf, data['parsed_data'])
        return Response(content=pdf_bytes, media_type='application/pdf',
                        headers={"Content-Disposition": "attachment; filename=exported_data.pdf"})
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error exporting PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to export PDF")

# Export CSV Endpoint
@app.post("/export_csv")
async def export_csv_endpoint(request: Request):
    """
    Endpoint to export parsed data to CSV.

    Args:
        request (Request): Incoming request.

    Returns:
        Response: CSV file download or error message.
    """
    try:
        data = await request.json()
        if not data or 'parsed_data' not in data:
            raise HTTPException(status_code=400, detail="No parsed data provided")

        # Assuming export_to_csv is a synchronous function
        csv_string = await asyncio.to_thread(export_to_csv, data['parsed_data'])
        return Response(content=csv_string, media_type='text/csv',
                        headers={"Content-Disposition": "attachment; filename=exported_data.csv"})
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to export CSV")

# Error Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Handle HTTP exceptions.

    Args:
        request (Request): Incoming request.
        exc (StarletteHTTPException): Exception instance.

    Returns:
        JSONResponse: JSON error message.
    """
    logger.warning(f"{exc.status_code} error: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Handle unhandled exceptions.

    Args:
        request (Request): Incoming request.
        exc (Exception): Exception instance.

    Returns:
        JSONResponse: JSON error message.
    """
    logger.error(f"Internal server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )

# Background Task: Periodic Health Checks
def periodic_health_check():
    """
    Perform periodic health checks and log the results.
    """
    logger.info("Performing periodic health checks")
    health_data = perform_health_checks()
    log_health_data(health_data)

# Schedule periodic health checks every 5 minutes
scheduler.add_job(periodic_health_check, 'interval', minutes=5)
scheduler.start()

# Graceful Shutdown of ConfigLoader Observer and APScheduler
async def shutdown_event():
    """
    Gracefully shutdown the application by stopping observers and background tasks.
    """
    logger.info("Shutting down application...")
    try:
        config_loader.observer.stop()
        config_loader.observer.join()
        scheduler.shutdown(wait=False)
        await email_parser.close()  # Ensure EmailParser.close() is async
        logger.info("Shutdown complete.")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

app.add_event_handler("shutdown", shutdown_event)

# Run the application with Uvicorn
# This block is typically placed under `if __name__ == '__main__':`
# but for better integration with ASGI servers, it's recommended to run via command line
# using `uvicorn app:app --host 0.0.0.0 --port 8080`
