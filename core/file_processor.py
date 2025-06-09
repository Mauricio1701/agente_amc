#file_processor.py
import os
import logging
import pandas as pd
from io import BytesIO
import PyPDF2
import docx
import docx2txt  # Añadido
import pytesseract
from pdf2image import convert_from_path
import unicodedata
import chardet

logger = logging.getLogger(__name__)  # Añadido


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

def process_file(file):
    """Procesa diferentes tipos de archivos y extrae su contenido como texto"""
    try:
        filename = file.filename if hasattr(file, 'filename') else 'unknown'
        content = ""
        
        # Detectar el tipo de archivo por la extensión
        ext = os.path.splitext(filename)[1].lower()
        
        # Para procesar con las funciones existentes, necesitamos guardar el archivo temporalmente
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, filename)
        
        # Guardar temporalmente el archivo subido
        try:
            if hasattr(file, 'save'):
                file.save(temp_file_path)
            else:
                # Si es un objeto de archivo estándar
                if hasattr(file, 'seek'):
                    file.seek(0)
                with open(temp_file_path, 'wb') as f:
                    if hasattr(file, 'read'):
                        f.write(file.read())
                    else:
                        f.write(file)
        except Exception as e:
            logger.error(f"Error guardando archivo temporal: {str(e)}")
            return f"Error al procesar el archivo: {str(e)}"
        
        # Manejar archivos CSV
        if ext == '.csv':
            try:
                # Usar pandas para leer el archivo guardado
                df = pd.read_csv(temp_file_path)
                content = f"Archivo CSV: {filename}\n"
                content += f"Número de filas: {len(df)}\n"
                content += f"Columnas: {', '.join(df.columns.tolist())}\n\n"
                content += "Primeras 10 filas:\n"
                content += df.head(10).to_string()
            except Exception as e:
                logger.error(f"Error procesando CSV: {str(e)}")
                content = f"Error al procesar archivo CSV: {str(e)}"
                
        # Manejar archivos Excel
        elif ext in ['.xlsx', '.xls']:
            try:
                df = pd.read_excel(temp_file_path)
                content = f"Archivo Excel: {filename}\n"
                content += f"Número de filas: {len(df)}\n"
                content += f"Columnas: {', '.join(df.columns.tolist())}\n\n"
                content += "Primeras 10 filas:\n"
                content += df.head(10).to_string()
            except Exception as e:
                logger.error(f"Error procesando Excel: {str(e)}")
                content = f"Error al procesar archivo Excel: {str(e)}"
                
        # Manejar archivos PDF
        elif ext == '.pdf':
            try:
                # Usar la función existente para procesar PDF
                content = f"Archivo PDF: {filename}\n\n"
                content += "Contenido:\n"
                content += extract_pdf_text(temp_file_path)
            except Exception as e:
                logger.error(f"Error procesando PDF: {str(e)}")
                content = f"Error al procesar archivo PDF: {str(e)}"
                
        # Manejar archivos Word
        elif ext in ['.docx', '.doc']:
            try:
                content = f"Archivo Word: {filename}\n\n"
                content += "Contenido:\n"
                if ext == '.docx':
                    content += extract_docx_text(temp_file_path)
                else:
                    content += docx2txt.process(temp_file_path)
            except Exception as e:
                logger.error(f"Error procesando Word: {str(e)}")
                content = f"Error al procesar archivo Word: {str(e)}"
                
        # Manejar archivos de texto
        elif ext in ['.txt', '.md', '.json', '.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.sql']:
            try:
                content = safe_read(temp_file_path)
            except Exception as e:
                logger.error(f"Error procesando archivo de texto: {str(e)}")
                content = f"Error al procesar archivo de texto: {str(e)}"
        
        # Tipo de archivo no soportado
        else:
            content = f"Tipo de archivo no soportado: {ext}"
            
        # Limpiar el archivo temporal
        try:
            os.remove(temp_file_path)
        except:
            pass
            
        return content
    except Exception as e:
        logger.error(f"Error general procesando archivo: {str(e)}")
        return f"Error procesando el archivo: {str(e)}"