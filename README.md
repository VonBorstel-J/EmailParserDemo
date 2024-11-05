# KeystoneEmailParser

**KeystoneEmailParser** is a lightweight, Dockerized web application designed to parse and extract structured data from insurance-related emails. It leverages **React** for a dynamic frontend and **Flask** for the backend, integrating OCR capabilities and exporting functionalities. The application supports parsing email content, images, and PDFs, providing real-time progress updates and allowing users to export parsed data as PDF or CSV files.

## **Features**

- **Frontend:**
  - Built with React for a responsive and interactive user interface.
  - Paste email content or upload document images (JPG, PNG) and PDFs.
  - Select between different parsing methods (Llama 1B or Llama 3B).
  - Real-time progress bar during parsing.
  - Display parsed data in a structured JSON format.
  - Export parsed data as PDF or CSV files.

- **Backend:**
  - Flask server handling API requests.
  - Integrates Llama 3.2 for natural language processing and data extraction.
  - OCR capabilities using Tesseract for images and PDFs.
  - Real-time progress updates without using WebSockets.
  - Comprehensive logging based on configuration.
  - Error handling and notifications.

- **Containerization:**
  - Dockerized frontend and backend for easy deployment and scalability.
  - Docker Compose to orchestrate multi-container applications.

## **File Structure**
KeystoneEmailParser/ ├── backend/ │ ├── app.py │ ├── exporter.py │ ├── parser.py │ ├── parser.config.yaml │ ├── requirements.txt │ ├── Dockerfile │ └── models/ │ ├── llama_1b/ │ │ ├── config.json │ │ ├── pytorch_model.bin │ │ └── tokenizer.json │ └── llama_3b/ │ ├── config.json │ ├── pytorch_model.bin │ └── tokenizer.json ├── frontend/ │ ├── public/ │ │ └── index.html │ ├── src/ │ │ ├── components/ │ │ │ ├── ParserForm.js │ │ │ └── ParsedResult.js │ │ ├── App.js │ │ ├── index.js │ │ └── styles.css │ ├── package.json │ ├── package-lock.json │ └── Dockerfile ├── docker-compose.yml ├── .env └── README.md

## **Setup Instructions**

### **Prerequisites**

- **Docker** and **Docker Compose** installed on your machine.
- **Git** (optional, for version control).
- **Sufficient Disk Space:** Ensure you have enough space to store the Llama models (~several GBs).

### **Backend Setup**

1. **Navigate to the Backend Directory:**

   ```bash
   cd backend



