# KeystoneEmailParser

# ProductionDemo Backend
<img src="backend/static/img/tech-background.webp" alt="Logo" width="200"/>

## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Technologies Used](#technologies-used)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Directory Structure](#directory-structure)
- [Logging](#logging)
- [Error Handling](#error-handling)
- [Contributing](#contributing)
- [License](#license)

## Introduction

**ProductionDemo** is a backend application developed using Flask, designed to parse and process email content. It leverages LM Studio for natural language processing, extracting relevant information from emails based on predefined templates and validation rules. The application offers endpoints for health checks, email parsing, and exporting parsed data to PDF and CSV formats. It also includes robust logging, rate limiting, and caching mechanisms to ensure reliability and performance.

## Features

- **Email Parsing:** Extracts structured data from raw email content using LM Studio.
- **Validation:** Validates extracted fields against predefined regex patterns.
- **Export Options:** Allows exporting parsed data to PDF and CSV formats.
- **Health Monitoring:** Provides a health check endpoint to monitor application status and dependencies.
- **Rate Limiting:** Protects endpoints from abuse with configurable rate limits.
- **Logging:** Comprehensive logging with log rotation for both application and parser logs.
- **Caching:** Implements an LRU cache to optimize performance and reduce redundant processing.
- **CORS Support:** Enables cross-origin requests with configurable settings.
- **Dockerized:** Containerized setup for easy deployment and scalability.

## Technologies Used

- **Backend:**
  - Python 3.12
  - Flask
  - Flask-CORS
  - Flask-Limiter
  - Docker
  - LM Studio API
  - OpenAI API
  - Tenacity for retry mechanisms
  - Cachetools for caching
- **Frontend:**
  - HTML, CSS, JavaScript
  - Parallax Effects for UI enhancement
- **Others:**
  - Docker
  - YAML for configuration
  - Environment Variables with `dotenv`

## Prerequisites

- **Docker:** Ensure Docker is installed on your machine. [Install Docker](https://docs.docker.com/get-docker/)
- **LM Studio:** The application relies on LM Studio for natural language processing. Make sure LM Studio is running and accessible.
- **Python 3.12:** If you plan to run the application outside Docker for development purposes.

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/ProductionDemo.git
   cd ProductionDemo/backend
Using Docker:

Build the Docker Image:

bash
Copy code
docker build -t productiondemo-backend .
Run the Docker Container:

bash
Copy code
docker run -d -p 5000:5000 --name productiondemo-backend productiondemo-backend
Without Docker (For Development):

Create a Virtual Environment:

bash
Copy code
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
Install Dependencies:

bash
Copy code
pip install -r requirements.txt
Configuration
The application uses a parser.config.yaml file for configuration and a .env file for environment variables.

Environment Variables (.env):

Create a .env file in the backend directory with the following variables:

env
Copy code
FLASK_ENV=development
# Add other environment variables as needed
Parser Configuration (parser.config.yaml):

The provided parser.config.yaml includes configurations for prompt templates, field validation patterns, logging, caching, and LM Studio settings.

Example:

yaml
Copy code
lm_studio:
  base_url: "http://localhost:3000"
  api_key: "lm-studio"

prompt_template: |
  [INST] You are a precise email parsing assistant. Extract and format the following information from the email below, matching the fields of our intake form exactly. Use only information explicitly stated in the email. Mark required fields with an asterisk (*). Use "N/A" if information is not found. Avoid repetition and keep the response concise.

  Email content:
  {{email_content}}

  Limit your response to 300 tokens or fewer.

  Format the response exactly as follows:

  **ASSIGNER INFORMATION**
  - Assigner Name*: 
  - Assigner Email*: 
  - Assigner Phone*: 
  - Assigner Phone Extension: 

  **ASSIGNMENT INFORMATION**
  - Claim Number*: 
  - Policy Number: 
  - Date of Loss*: 
  - Client (Assigner's Company)*: 
  - Insurance Carrier*: 
  - Insured's Name*: 
  - Insured's Phone Number 1*: 
  - Insured's Phone Number 2: 
  - Insured's Email: 
  - Address of Risk Location*: 
  - Is this related to a CAT event?*:
  - CAT Event Name: 

  **ADDITIONAL PARTY INFORMATION**
  - Additional Party Name: 
  - Additional Party Company: 
  - Additional Party Phone: 
  - Additional Party Email: 

  **DESCRIPTION OF SERVICES NEEDED**
  - Describe the services needed*: 
  - Type of Expert Needed*: 
  - Type of Damage*: 
  - Areas of Property to Inspect*: 

  **QUESTIONS TO HELP US SPEED UP ASSIGNMENT PROCESSING**
  - Is a budget required before proceeding?*:
  - Number of Buildings/Units (if commercial): 
  - Call Required Before Inspection: 
  - Call Required After Inspection: 
  - Repair Recommendations Needed: 
  - Cost Estimate Required: 
  - Permission for Third-Party Tarp Removal: 
  - Tile Matching Information (for tile roof): 
  - Roof Diagram Needed: 
      
  **OTHER**
  - Notes/Comments: 
  - Attachments: 

  Fill in each field with information from the email only. Use "N/A" if not found. [/INST]

field_validation:
  assigner_name_pattern: '^[A-Za-z\s]+$'
  assigner_email_pattern: '^[\w\.-]+@[\w\.-]+\.\w+$'
  assigner_phone_pattern: '^\d{3}-\d{3}-\d{4}$'
  assigner_phone_extension_pattern: '^\d+$'
  claim_number_pattern: '^BX-\d{8}$'
  policy_number_pattern: '^BCR-\d{4}-\d{5}$'
  date_of_loss_pattern: '^(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}(st|nd|rd|th)?, \d{4}$'
  client_company_pattern: '^[A-Za-z\s]+$'
  insurance_carrier_pattern: '^[A-Za-z\s]+$'
  insured_name_pattern: '^[A-Za-z\s]+$'
  insured_phone_pattern: '^\d{3}-\d{3}-\d{4}$'
  insured_email_pattern: '^[\w\.-]+@[\w\.-]+\.\w+$'
  risk_location_pattern: '^.+$'
  cat_event_related_pattern: '^(Yes|No)$'
  cat_event_name_pattern: '^[A-Za-z\s]+$'
  additional_party_name_pattern: '^[A-Za-z\s]+$'
  additional_party_company_pattern: '^[A-Za-z\s]+$'
  additional_party_phone_pattern: '^\d{3}-\d{3}-\d{4}$'
  additional_party_email_pattern: '^[\w\.-]+@[\w\.-]+\.\w+$'
  services_needed_pattern: '^.+$'
  expert_needed_pattern: '^.+$'
  damage_type_pattern: '^.+$'
  property_inspect_pattern: '^.+$'
  budget_required_pattern: '^(Yes|No)$'
  number_of_buildings_pattern: '^\d+$'
  call_before_inspection_pattern: '^(Yes|No)$'
  call_after_inspection_pattern: '^(Yes|No)$'
  repair_recommendations_pattern: '^(Yes|No)$'
  cost_estimate_pattern: '^(Yes|No)$'
  permission_tarp_removal_pattern: '^(Yes|No)$'
  tile_matching_pattern: '^.+$'
  roof_diagram_pattern: '^(Yes|No)$'
  notes_comments_pattern: '^.*$'
  attachments_pattern: '^.*$'

logging:
  level: "DEBUG"  # Can be set to INFO or ERROR in production
  file_path: "logs/parser.log"
  create_logs_dir_if_not_exists: True

cache_dir: "./cache"
max_tokens: 2000
Running the Application
Using Docker
Ensure Docker is running and execute the following commands:

bash
Copy code
# Build the Docker image
docker build -t productiondemo-backend .

# Run the Docker container
docker run -d -p 5000:5000 --name productiondemo-backend productiondemo-backend
The backend will be accessible at http://localhost:5000.

Without Docker (For Development)
Activate Virtual Environment:

bash
Copy code
source venv/bin/activate  # On Windows: venv\Scripts\activate
Run the Flask Application:

bash
Copy code
python app.py
The application will start in development mode and be accessible at http://localhost:5000.

API Endpoints
Health Check
URL: /health

Method: GET

Description: Checks the health status of the application and its components.

Response:

json
Copy code
{
  "status": "healthy",
  "components": {
    "lm_studio": true,
    "config": true,
    "static_files": true,
    "templates": true,
    "cache_size": 100
  },
  "performance": {
    "memory_usage_mb": 150.25
  }
}
Serve Frontend
URL: /
Method: GET
Description: Serves the frontend application.
Response: Renders index.html.
Parse Email
URL: /parse_email

Method: POST

Description: Parses the provided email content and extracts structured data.

Rate Limit: 10 requests per minute.

Request Body:

json
Copy code
{
  "email_content": "Raw email content here..."
}
Response:

Success (200):

json
Copy code
{
  "result": {
    "assigner_information": {
      "assigner_name": "John Doe",
      "assigner_email": "john.doe@example.com",
      ...
    },
    ...
  }
}
Error (4xx/5xx):

json
Copy code
{
  "error": "Description of the error."
}
Export Parsed Data to PDF
URL: /export_pdf

Method: POST

Description: Exports the parsed data to a PDF file.

Request Body:

json
Copy code
{
  "parsed_data": { /* Parsed data object */ }
}
Response: Returns the generated PDF as a downloadable file.

Export Parsed Data to CSV
URL: /export_csv

Method: POST

Description: Exports the parsed data to a CSV file.

Request Body:

json
Copy code
{
  "parsed_data": { /* Parsed data object */ }
}
Response: Returns the generated CSV as a downloadable file.

Directory Structure
lua
Copy code
backend/
├── Dockerfile
├── .dockerignore
├── exporter.py
├── app.py
├── parser.py
├── parser.config.yaml
├── requirements.txt
├── models/
│   ├── version.txt
│   ├── models--meta-llama--Llama-3.2-1B/
│   ├── models--meta-llama--Llama-3.2-3B/
│   ├── llama_1b/
│   ├── llama_3b/
│   └── nuextract/
├── templates/
│   └── index.html
├── logs/
│   ├── parser.log
│   └── app.log
├── static/
│   ├── styles.css
│   ├── script.js
│   └── img/
│       └── tech-background.webp
└── __pycache__/
    ├── exporter.cpython-312.pyc
    └── parser.cpython-312.pyc
Description
Dockerfile: Docker configuration for containerizing the backend application.
.dockerignore: Specifies files and directories to ignore when building the Docker image.
exporter.py: Contains functions to export parsed data to PDF and CSV formats.
app.py: Main Flask application file handling routes, configurations, and middleware.
parser.py: Implements the EmailParser class responsible for parsing email content.
parser.config.yaml: YAML configuration file for the parser, including prompt templates and validation patterns.
requirements.txt: Lists Python dependencies required for the application.
models/: Directory containing model files and versions for LM Studio.
templates/index.html: Frontend HTML template served by Flask.
logs/: Directory containing application and parser logs with rotation.
static/: Contains static assets like CSS, JavaScript, and images.
pycache/: Compiled Python files for performance optimization.
Logging
The application employs robust logging mechanisms to monitor and debug operations.

Log Levels:

DEBUG: Detailed information, typically of interest only when diagnosing problems.
INFO: Confirmation that things are working as expected.
WARNING: An indication that something unexpected happened.
ERROR: Due to a more serious problem, the software has not been able to perform some function.
CRITICAL: A serious error, indicating that the program itself may be unable to continue running.
Log Files:

Application Logs: Stored in logs/app.log.
Parser Logs: Stored in logs/parser.log.
Log Rotation:

Each log file has a maximum size of 10MB.
Maintains up to 5 backup log files.
Ensures logs do not consume excessive disk space.
Configuration:

Modify the logging section in parser.config.yaml to adjust log levels and file paths.
Error Handling
The application includes comprehensive error handling to ensure reliability and provide meaningful feedback.

HTTP Error Handlers:

404 Not Found: Returns a JSON response indicating the resource was not found.
429 Too Many Requests: Indicates rate limits have been exceeded.
500 Internal Server Error: General server error handler.
Parser Errors:

Validates parsed fields and flags any that do not match expected patterns without halting the process.
Logs all errors with appropriate severity levels for debugging.
Retry Mechanisms:

Utilizes the tenacity library to implement retries with exponential backoff for transient failures when communicating with LM Studio.
Contributing
Contributions are welcome! Please follow these steps to contribute:

Fork the Repository

Create a Feature Branch:

bash
Copy code
git checkout -b feature/YourFeature
Commit Your Changes:

bash
Copy code
git commit -m "Add some feature"
Push to the Branch:

bash
Copy code
git push origin feature/YourFeature
Open a Pull Request

Please ensure your code adheres to the project's coding standards and includes appropriate tests.

License
This project is licensed under the MIT License.

Contact Information:

Developer: Jordan VonBorstel jvonborstel@keystoneexperts.com

Project Repository: EmailParserDemo

Made with ❤️ by JVB
