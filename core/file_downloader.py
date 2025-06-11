import requests
import csv
import io
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

def download_and_process_csv(url: str, max_size_mb: int = 50) -> Optional[Dict]:
    """
    Descarga un archivo CSV desde una URL y retorna su contenido procesado
    
    Args:
        url (str): URL del archivo CSV
        max_size_mb (int): Tamaño máximo permitido en MB
    
    Returns:
        Dict con 'content' (texto), 'rows' (número de filas), 'headers' (cabeceras)
    """
    try:
        logger.info(f"Descargando archivo CSV desde: {url}")
        
        # Realizar la descarga con timeout
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()
        
        # Verificar el tamaño del archivo
        content_length = response.headers.get('content-length')
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > max_size_mb:
                logger.warning(f"Archivo demasiado grande: {size_mb:.2f}MB > {max_size_mb}MB")
                return None
        
        # Leer el contenido
        content = response.text
        
        # Procesar el CSV para obtener información adicional
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)
        
        headers = rows[0] if rows else []
        row_count = len(rows) - 1 if rows else 0  # -1 para excluir header
        
        logger.info(f"CSV procesado: {row_count} filas, {len(headers)} columnas")
        
        return {
            'content': content,
            'rows': row_count,
            'headers': headers,
            'size_bytes': len(content.encode('utf-8'))
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al descargar archivo: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error al procesar CSV: {str(e)}")
        return None

def extract_filename_from_url(url: str) -> str:
    """Extrae un nombre de archivo de una URL"""
    try:
        # Obtener la parte después del último '/'
        filename = url.split('/')[-1]
        # Remover parámetros de query
        filename = filename.split('?')[0]
        # Si no tiene extensión, agregar .csv
        if not filename.endswith('.csv'):
            filename += '.csv'
        return filename
    except:
        return 'report_file.csv'