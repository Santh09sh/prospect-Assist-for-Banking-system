"""
pdf_extractor.py — Extract bank statement transactions from PDF using Google Gemini API
=======================================================================================
"""

import io
import os
import logging
from typing import Optional
import PyPDF2

# API key: read from environment variable
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

logger = logging.getLogger(__name__)

# Try to use the new google.genai package first; fall back to deprecated one
_USE_NEW_SDK = False
try:
    from google import genai
    _client = genai.Client(api_key=GEMINI_API_KEY)
    _USE_NEW_SDK = True
except ImportError:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
    except ImportError:
        logger.warning("Neither google-genai nor google-generativeai is installed. PDF extraction will fail.")


def extract_csv_from_pdf(pdf_bytes: bytes, pdf_password: Optional[str] = None) -> bytes:
    """
    Extracts text from a PDF bank statement, sends it to Gemini API,
    and returns a normalized CSV byte string that can be parsed by our StatementParser.
    """
    # 1. Extract text from PDF
    text = ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            if pdf_password:
                success = reader.decrypt(pdf_password)
                if not success:
                    raise ValueError("Incorrect password for the PDF file.")
            else:
                raise ValueError("The PDF is password protected. Please provide a password.")
                
        # Take the first 10 pages
        for page in reader.pages[:10]:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    except Exception as e:
        logger.error(f"Failed to read PDF file: {e}")
        raise ValueError(f"Could not read the uploaded PDF file. Error: {e}")

    if not text.strip():
        raise ValueError("The uploaded PDF appears to be empty or contains no readable text.")

    # 2. Call Gemini API
    system_instruction = """You are a highly accurate financial data extraction assistant. 
Your task is to extract bank transactions from the provided raw PDF text and format them STRICTLY as a CSV.
The CSV MUST have exactly these columns: Date, Narration, Debit, Credit, Balance
- Date: Keep the date format as is, or YYYY-MM-DD.
- Narration: The transaction description.
- Debit: Amount deducted (leave blank if credit).
- Credit: Amount added (leave blank if debit).
- Balance: The running balance.

Return ONLY the raw CSV text. Do NOT wrap it in markdown block quotes like ```csv ... ```. Do NOT include any explanations."""

    prompt = f"{system_instruction}\n\nExtract transactions from this text:\n\n{text}"

    try:
        if _USE_NEW_SDK:
            # New SDK (google-genai)
            response = _client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            csv_text = response.text.strip()
        else:
            # Legacy SDK (google-generativeai) — deprecated but functional
            import google.generativeai as genai_legacy
            model = genai_legacy.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(prompt)
            csv_text = response.text.strip()

        # Strip markdown if the model hallucinated it
        if csv_text.startswith("```csv"):
            csv_text = csv_text[6:]
        if csv_text.startswith("```"):
            csv_text = csv_text[3:]
        if csv_text.endswith("```"):
            csv_text = csv_text[:-3]
            
        csv_text = csv_text.strip()
        
        return csv_text.encode('utf-8')
        
    except Exception as e:
        logger.error(f"Failed to extract transactions using Gemini API: {e}")
        raise ValueError(f"AI parsing failed. Please ensure the PDF is a valid bank statement. Details: {str(e)}")
