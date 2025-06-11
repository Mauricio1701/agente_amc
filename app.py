from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import uuid
import os
from datetime import datetime
from core.database import Database
from core.deepseek_client import DeepSeekClient
from core.voice_handler import VoiceHandler
from core.amazon_client_amc import generate_amc_report
from core.file_downloader import download_and_process_csv, extract_filename_from_url
import csv
import io
import requests
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'amazon_amc_analyzer_secret_key')

# Inicialización de componentes
db = Database()
deepseek_client = DeepSeekClient()
voice_handler = VoiceHandler()

# Gestor de sesiones
@app.before_request
def before_request():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    deepseek_client.chat_history.set_session_id(session['session_id'])

@app.route('/')
def index():
    # Cargar el historial de chat para la sesión actual
    chat_history = deepseek_client.chat_history.get_history()
    return render_template('index.html', now=datetime.now(), chat_history=chat_history)

def parse_csv_content(content: str, max_rows: int = 100):
    """Parsea contenido CSV y devuelve headers y filas estructuradas"""
    try:
        if not content:
            return None, []
        
        # Usar el módulo csv de Python para parsing correcto
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)
        
        if not rows:
            return None, []
        
        headers = rows[0] if rows else []
        data_rows = rows[1:max_rows+1] if len(rows) > 1 else []
        
        return {
            'headers': headers,
            'rows': data_rows,
            'total_rows': len(rows) - 1,  # -1 para excluir header
            'showing_rows': len(data_rows),
            'has_more': len(rows) > max_rows + 1
        }
    except Exception as e:
        logger.error(f"Error parsing CSV: {str(e)}")
        return None

@app.route('/chat', methods=['POST'])
def chat():
    try:
        query = request.form.get('query', '')
        if not query:
            return jsonify({'error': 'No se proporcionó consulta'}), 400
        
        # Detectar si el usuario está solicitando una consulta SQL o un reporte
        query_lower = query.lower()
        sql_request_keywords = [
        'consulta sql', 'genera sql', 'crear sql', 'generar sql', 'dame una consulta', 
        'necesito una consulta', 'sql para', 'amc-sql', 'sql de amc', 'amc sql', 'sql amc',
        'consulta amc', 'consulta de amc', 'consulta amc-sql', 'amc sql query', 'amc-sql query',
        
        'reporte', 'muestra las', 'mostrar', 'dame un reporte', 'obtener datos', 'ver datos',
        'dame datos', 'quiero datos', 'necesito datos', 'extraer datos', 'consultar datos',
        
        'calcula', 'calcular', 'calcules', 'calculemos', 'cálculo', 'cálculos',
        'mide', 'medir', 'medición', 'métrica', 'métricas', 'estadística', 'estadísticas',
        
        'acos', 'tacos', 'advertising cost of sale', 'total advertising cost of sale',
        'rentabilidad', 'roi publicitario', 'retorno de inversión', 'eficiencia publicitaria',
        'costo publicitario', 'gasto publicitario', 'inversión publicitaria',
        
        'ventas por ads', 'ventas por anuncios', 'ventas atribuidas', 'ventas totales',
        'gasto por ads', 'gasto en ads', 'costo por ads', 'inversión en ads',
        'conversiones', 'conversion', 'ventas', 'sales', 'revenue',
        
        'por asin', 'por campaña', 'por campaign', 'por región', 'por dispositivo',
        'por creative', 'por creativo', 'por fecha', 'por día', 'por mes',
        'agrupado por', 'agrupada por', 'segmentado por', 'dividido por',
        
        'análisis', 'analizar', 'analiza', 'compara', 'comparar', 'comparación',
        'rendimiento', 'performance', 'eficiencia', 'optimización',
        
        'muéstrame', 'muestrame', 'dame', 'obtén', 'extrae', 'genera',
        'lista', 'listar', 'enumera', 'presenta', 'proporciona',
        
        'impresiones', 'impressions', 'clics', 'clicks', 'vistas', 'views',
        'tráfico', 'traffic', 'audiencia', 'audience', 'segmentos', 'segments',
        'atribución', 'attribution', 'eventos', 'events',
        
        'consulta para', 'reporte de', 'reporte para', 'datos de', 'información de',
        'estadísticas de', 'métricas de', 'análisis de', 'rendimiento de',
        
        'quiero ver', 'necesito ver', 'quiero saber', 'necesito saber',
        'quiero conocer', 'necesito conocer', 'quiero analizar', 'necesito analizar'
    ]
        
        is_sql_request = any(keyword in query_lower for keyword in sql_request_keywords)
        
        # Si parece una solicitud de SQL, devolver solo la consulta SQL
        if is_sql_request:
            # Intentar generar SQL hasta 3 veces para asegurar calidad
            for attempt in range(3):
                sql_query = deepseek_client.generate_amc_sql(query)
                
                # Verificar si la respuesta parece un SQL válido
                if sql_query and 'SELECT' in sql_query.upper() and 'FROM' in sql_query.upper():
                    # Guardar en el historial la pregunta y la respuesta SQL
                    deepseek_client.chat_history.add_message(query, sql_query)
                    return jsonify({'response': sql_query})
                
                app.logger.warning(f"Intento {attempt+1} de generar SQL no válido: {sql_query}")
            
            # Si todos los intentos fallan, usar el método normal
            app.logger.info("No se pudo generar SQL válido, respondiendo normalmente")
        
        file_content = ""
        # Manejar archivo adjunto si existe
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            app.logger.info(f"Archivo recibido: {file.filename}")
            
            try:
                # Procesar el contenido del archivo
                from core.file_processor import process_file
                file_content = process_file(file)
                app.logger.info(f"Archivo procesado. Longitud del contenido: {len(file_content)}")
            except Exception as e:
                app.logger.error(f"Error procesando archivo: {str(e)}")
                file_content = f"[No se pudo procesar completamente el archivo: {file.filename}. Error: {str(e)}]"
        
        # Obtener respuesta usando analyze_with_context
        response = deepseek_client.analyze_with_context(query, file_content=file_content)
        
        # Guardar explícitamente la conversación en el historial SOLO UNA VEZ
        deepseek_client.chat_history.add_message(query, response)
        
        return jsonify({'response': response})
    except Exception as e:
        app.logger.error(f"Error en proceso de chat: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/save_chat_history", methods=["POST"])
def save_chat_history_from_frontend():
    """
    Recibe el historial del chat desde el frontend (HTML) y lo muestra en la consola
    """
    data = request.get_json()
    chat_history = data.get("chat_history")

    if not chat_history:
        logger.warning("No se recibió historial de chat para guardar.")
        return jsonify({"message": "No hay historial de chat para procesar."}), 200

    # Mostrar el historial de chat en la consola
    logger.info("===== HISTORIAL DE CHAT GUARDADO =====")
    logger.info(f"Total de mensajes: {len(chat_history)}")
    
    # Crear una representación visual del array para mostrar en consola
    array_representation = []
    for idx, msg in enumerate(chat_history):
        array_representation.append({
            "index": idx,
            "user_message": msg.get('user_message', ''),
            "ai_response": msg.get('ai_response', '')
        })
        
        logger.info(f"\n--- Mensaje {idx + 1} ---")
        logger.info(f"USUARIO: {msg.get('user_message', '')}")
        logger.info(f"ASISTENTE: {msg.get('ai_response', '')}")
    
    logger.info("===== FIN DEL HISTORIAL =====")
    
    # Formato JSON para depuración (opcional)
    logger.info(f"JSON completo: {json.dumps(chat_history, ensure_ascii=False, indent=2)}")
    
    # Devolver el array completo para visualizarlo
    return jsonify({
        "message": "Historial de chat guardado en la consola del servidor.",
        "status": "success",
        "count": len(chat_history),
        "array_data": array_representation
    }), 200
@app.route('/reports')
def reports():
    all_reports = db.get_all_report_files() or []
    return render_template('reports/list.html', reports=all_reports, now=datetime.now())

@app.route('/reports/generate', methods=['GET', 'POST'])
def generate_report():
    """Página para generar nuevos reportes"""
    if request.method == 'POST':
        natural_request = request.form.get('natural_request', '')
        improved_prompt = request.form.get('improved_prompt', '')
        sql_query = request.form.get('sql_query', '')
        instance_id = request.form.get('instance_id', 'amc088a9col')
        
        if not sql_query and improved_prompt:
            # Generar SQL desde prompt mejorado
            sql_query = deepseek_client.generate_amc_sql(improved_prompt)
            return jsonify({'sql_query': sql_query})
        
        if not improved_prompt and natural_request:
            # Mejorar prompt desde lenguaje natural
            improved_prompt = deepseek_client.improve_prompt(natural_request)
            return jsonify({'improved_prompt': improved_prompt})
        
        if sql_query and instance_id:
            # Generar reporte
            try:
                result = generate_amc_report(instance_id, sql_query)
                
                if not result.get('error') and result.get('downloadUrls'):
                    # Procesar y guardar archivos CSV
                    report_id = result.get('workflowExecutionId', str(uuid.uuid4()))
                    saved_files = []
                    
                    for url in result.get('downloadUrls', []):
                        if url.lower().endswith('.csv') or 'csv' in url.lower():
                            logger.info(f"Procesando archivo CSV: {url}")
                            
                            # Descargar y procesar el archivo
                            csv_data = download_and_process_csv(url)
                            
                            if csv_data:
                                # Generar nombre de archivo
                                filename = extract_filename_from_url(url)
                                if not filename.startswith('amc_report_'):
                                    now = datetime.now()
                                    date_str = now.strftime('%Y%m%d_%H%M%S')
                                    filename = f'amc_report_{date_str}.csv'
                                
                                # Guardar en la base de datos
                                file_id = db.save_report_file(
                                    report_id=report_id,
                                    file_name=filename,
                                    file_content=csv_data['content'],
                                    download_url=url
                                )
                                
                                if file_id:
                                    saved_files.append({
                                        'file_id': file_id,
                                        'filename': filename,
                                        'rows': csv_data['rows'],
                                        'size_bytes': csv_data['size_bytes']
                                    })
                                    logger.info(f"Archivo guardado en BD: {filename} ({csv_data['rows']} filas)")
                                else:
                                    logger.error(f"Error al guardar archivo en BD: {filename}")
                    
                    # Agregar información de archivos guardados al resultado
                    result['saved_files'] = saved_files
                    result['report_id'] = report_id
                
                return jsonify(result)
            except Exception as e:
                logger.error(f"Error en generación de reporte: {str(e)}")
                return jsonify({'error': True, 'message': str(e)}), 500
                
    return render_template('reports/generate.html')


@app.route('/reports/<file_id>/delete', methods=['POST'])
def delete_report(file_id):
    """Elimina un reporte específico"""
    try:
        success = db.delete_report_file(file_id)
        if success:
            flash('Reporte eliminado exitosamente', 'success')
        else:
            flash('No se pudo eliminar el reporte', 'error')
    except Exception as e:
        logger.error(f"Error al eliminar reporte: {str(e)}")
        flash('Error interno al eliminar el reporte', 'error')
    
    return redirect(url_for('reports'))

@app.route('/reports/files/<file_id>/download')
def download_saved_file(file_id):
    """Descarga un archivo CSV guardado en la base de datos"""
    try:
        # Obtener información del archivo
        file_info = db.get_report_file_info(file_id)
        if not file_info:
            return "Archivo no encontrado", 404
        
        # Obtener el contenido
        content = db.get_report_file_content(file_id)
        if not content:
            return "Contenido no encontrado", 404
        
        # Crear respuesta con el archivo
        from flask import Response
        return Response(
            content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={file_info["file_name"]}'
            }
        )
    except Exception as e:
        logger.error(f"Error al descargar archivo: {str(e)}")
        return "Error interno del servidor", 500

@app.route('/reports/<file_id>')
def view_report(file_id):
    """Ver un reporte específico"""
    # Obtener información del archivo
    report_info = db.get_report_file_info(file_id)
    if not report_info:
        flash('Reporte no encontrado', 'error')
        return redirect(url_for('reports'))
    
    # Obtener contenido del archivo
    file_content = db.get_report_file_content(file_id)
    
    # Parsear CSV si hay contenido
    csv_data = None
    if file_content:
        csv_data = parse_csv_content(file_content, max_rows=100)
    
    return render_template('reports/view.html', 
                         report=report_info, 
                         content=file_content,
                         csv_data=csv_data)


# Rutas para el historial de chat
@app.route('/chat/history')
def chat_history():
    history = deepseek_client.chat_history.get_history()
    
    # Asegurar que cada entrada tenga un timestamp válido
    for chat in history:
        if 'timestamp' not in chat or not chat['timestamp']:
            chat['timestamp'] = datetime.now()
        elif isinstance(chat['timestamp'], str):
            try:
                # Intentar convertir a datetime si es una cadena
                chat['timestamp'] = datetime.fromisoformat(chat['timestamp'])
            except ValueError:
                try:
                    # Segundo intento con otro formato
                    chat['timestamp'] = datetime.strptime(chat['timestamp'], '%Y-%m-%dT%H:%M:%S.%f')
                except ValueError:
                    # Si falla, usar la fecha actual
                    chat['timestamp'] = datetime.now()
    
    return render_template('chat/history.html', chat_history=history)


@app.route('/chat/clear', methods=['POST'])
def clear_chat():
    try:
        success = deepseek_client.chat_history.clear_history()
        
        # Si la solicitud viene de una petición AJAX, devolvemos JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': success, 'redirect': url_for('index')})
        
        # Si no, redirigimos a la página principal
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"Error al limpiar chat: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)})
        return redirect(url_for('index'))

# Rutas para la gestión de memoria
@app.route('/memory', methods=['GET'])
def view_memory():
    # Obtener el conocimiento directamente desde la base de datos
    knowledge = db.get_all_knowledge()
    
    # Si no hay conocimiento, inicializar como lista vacía
    if knowledge is None:
        knowledge = []
        
    # Formatear cada elemento para la presentación
    formatted_knowledge = []
    for item in knowledge:
        formatted_item = {
            'topic': item.get('topic', 'Sin tema'),
            'facts': item.get('facts', []),
            'source': item.get('source', 'Desconocido'),
            'last_accessed': item.get('last_accessed', datetime.now())
        }
        formatted_knowledge.append(formatted_item)
    
    return render_template('memory.html', knowledge=formatted_knowledge)

@app.route('/memory/clear', methods=['POST'])
def clear_memory():
    try:
        # Limpiar el conocimiento directamente en la base de datos
        success = db.clear_knowledge()
        
        # También limpiar la memoria en el cliente deepseek si existe
        if hasattr(deepseek_client, 'clear_memory'):
            deepseek_client.clear_memory()
            
        if success:
            message = "Memoria del sistema limpiada correctamente"
        else:
            message = "Error al limpiar la memoria del sistema"
            
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        app.logger.error(f"Error al limpiar memoria: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
# Manejo de voz
@app.route('/voice/listen', methods=['POST'])
def voice_listen():
    try:
        audio_data = request.files.get('audio')
        if not audio_data:
            return jsonify({'error': 'No se proporcionó audio'}), 400
            
        text = voice_handler.transcribe_audio(audio_data)
        return jsonify({'text': text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Funciones auxiliares
def process_query(query):
    # Procesamiento normal con contexto
    all_files_text = ""
    files = db.get_all_files()
    for file in files[:3]:  # Limitamos a los 3 archivos más recientes
        file_text = db.get_file_text(file['file_id'])
        if file_text:
            all_files_text += f"Contenido de {file['file_name']}:\n{file_text[:500]}...\n\n"
    
    # Obtener la respuesta del modelo
    response = deepseek_client.analyze_with_context(query, file_content=all_files_text, context_type="auto")
    
    return response

if __name__ == '__main__':
    app.run(debug=True, port=5000)