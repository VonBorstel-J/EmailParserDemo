# exporter.py

import io
import csv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def export_to_pdf(parsed_data: dict) -> bytes:
    """
    Exports the parsed data to a PDF.

    Args:
        parsed_data (dict): Parsed email data.

    Returns:
        bytes: PDF file in bytes.
    """
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50  # Starting position

    for section, fields in parsed_data.items():
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, section.replace('_', ' ').upper())
        y -= 20
        p.setFont("Helvetica", 12)
        for key, value in fields.items():
            if isinstance(value, dict):
                # Handle nested dictionaries if any
                for sub_key, sub_value in value.items():
                    p.drawString(60, y, f"{sub_key.replace('_', ' ').title()}: {sub_value}")
                    y -= 15
            else:
                p.drawString(60, y, f"{key.replace('_', ' ').title()}: {value}")
                y -= 15
            if y < 50:
                p.showPage()
                y = height - 50
        y -= 10

    p.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def export_to_csv(parsed_data: dict) -> str:
    """
    Exports the parsed data to a CSV string.

    Args:
        parsed_data (dict): Parsed email data.

    Returns:
        str: CSV content as a string.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow(['Section', 'Field', 'Value'])

    for section, fields in parsed_data.items():
        for key, value in fields.items():
            writer.writerow([section.replace('_', ' ').upper(), key.replace('_', ' ').title(), value])

    return output.getvalue()
