
import os
from PyPDF2 import PdfReader


def extract_text_from_pdf(file_path):
    """Extract readable text from an uploaded PDF resume."""

    if not os.path.exists(file_path):
        raise FileNotFoundError("Resume file not found.")

    try:
        reader = PdfReader(file_path)

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password protected.")

        text = []

        for page in reader.pages:
            page_text = page.extract_text() or ""
            text.append(page_text)

        extracted_text = "\n".join(text).strip()

        if not extracted_text:
            raise ValueError(
                "No readable text found. Please upload a text-based PDF."
            )

        return extracted_text

    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"Unable to read PDF: {error}")


def parse_resume(file_path):
    """Return extracted resume text."""

    return extract_text_from_pdf(file_path)
