# exporter.py

import io
import csv
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

def export_to_pdf(parsed_data: dict) -> bytes:
    """
    Exports the parsed data to a PDF with improved formatting.

    Args:
        parsed_data (dict): Parsed email data.

    Returns:
        bytes: PDF file in bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50)
    elements = []
    styles = getSampleStyleSheet()
    section_style = styles['Heading2']
    key_style = styles['Normal']
    value_style = styles['BodyText']

    # Add Title
    title = Paragraph("Parsed Email Report", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 20))

    # Loop through sections and add formatted content
    for section, fields in parsed_data.items():
        elements.append(Paragraph(section.replace('_', ' ').upper(), section_style))
        elements.append(Spacer(1, 10))
        
        # Format each key-value pair
        table_data = []
        for key, value in fields.items():
            formatted_key = key.replace('_', ' ').title()
            table_data.append([Paragraph(f"<b>{formatted_key}:</b>", key_style), Paragraph(str(value), value_style)])

        # Create a table for each section's content with improved styling
        table = Table(table_data, colWidths=[150, 350])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))

    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def export_to_csv(parsed_data: dict) -> str:
    """
    Exports the parsed data to a CSV string with enhanced formatting.

    Args:
        parsed_data (dict): Parsed email data.

    Returns:
        str: CSV content as a string.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Add title and timestamp at the top
    writer.writerow(["Parsed Email Report"])
    writer.writerow([f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])  # Empty row for spacing

    # Loop through sections
    for section, fields in parsed_data.items():
        # Add section header row
        writer.writerow([section.replace('_', ' ').upper()])
        writer.writerow(['Field', 'Value'])  # Add sub-headers for section

        # Add each key-value pair in the section
        for key, value in fields.items():
            formatted_key = key.replace('_', ' ').title()
            
            # Write key and value; handle nested dictionaries if any
            if isinstance(value, dict):
                writer.writerow([f"{formatted_key}:"])
                for sub_key, sub_value in value.items():
                    formatted_sub_key = f"  - {sub_key.replace('_', ' ').title()}"
                    writer.writerow([formatted_sub_key, sub_value])
            else:
                writer.writerow([formatted_key, value])

        writer.writerow([])  # Blank row after each section for spacing

    # Return CSV string
    return output.getvalue()
