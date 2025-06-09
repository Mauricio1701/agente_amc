#file_processor.py
import PyPDF2
import docx
import pytesseract
from pdf2image import convert_from_path
import unicodedata
import chardet

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000)
        result = chardet.detect(raw_data)
        return result['encoding'] or 'utf-8'

def safe_read(file_path, default_encoding='utf-8'):
    try:
        encoding = detect_encoding(file_path)
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, 'rb') as f:
            return f.read().decode('latin-1', errors='replace')

def extract_docx_text(file_path):
    try:
        doc = docx.Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            try:
                full_text.append(para.text)
            except:
                full_text.append("[TEXTO NO LEGIBLE]")
        return '\n'.join(full_text)
    except Exception as e:
        print(f"Error procesando DOCX: {str(e)}")
        return safe_read(file_path)

def extract_pdf_text(file_path, max_pages=50):
    text = ""
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for i, page in enumerate(reader.pages):
                if i >= max_pages:
                    break
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if len(text.strip()) < 100:
            images = convert_from_path(file_path, first_page=1, last_page=min(3, len(reader.pages)))
            for img in images:
                text += pytesseract.image_to_string(img) + "\n"
    except Exception as e:
        print(f"Error procesando PDF: {str(e)}")
        text = safe_read(file_path)
    return text[:100000]

def process_file(file_path, file_type):
    try:
        if file_type == 'pdf':
            return extract_pdf_text(file_path)
        elif file_type == 'docx':
            return extract_docx_text(file_path)
        elif file_type in ('jpg', 'png', 'jpeg'):
            return pytesseract.image_to_string(file_path)
        else:
            return "Formato no soportado"
    except Exception as e:
        return f"Error al procesar archivo: {str(e)}"
