from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import uuid
import os
from datetime import datetime
from core.database import Database
from core.deepseek_client import DeepSeekClient
from core.voice_handler import VoiceHandler
from core.amazon_client_amc import generate_amc_report
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

@app.route('/chat', methods=['POST'])
def chat():
    try:
        query = request.form.get('query', '')
        if not query:
            return jsonify({'error': 'No se proporcionó consulta'}), 400
        
        # Detectar si el usuario está solicitando una consulta SQL o un reporte
        query_lower = query.lower()
        sql_request_keywords = [
            'consulta sql', 'genera sql', 'crear sql', 'reporte', 'muestra las', 'mostrar', 
            'dame un reporte', 'obtener datos', 'generar sql', 'dame una consulta', 
            'necesito una consulta', 'sql para', 'amc-sql', 'sql de amc'
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
    all_reports = db.get_all_reports() or []
    return render_template('reports/list.html', reports=all_reports, now=datetime.now())

@app.route('/reports/<file_id>')
def view_report(file_id):
    file_text = db.get_file_text(file_id)
    report = next((r for r in db.get_all_reports() if r['file_id'] == file_id), None)
    if not report:
        return redirect(url_for('reports'))
    return render_template('reports/view.html', report=report, content=file_text)


@app.route('/reports/generate', methods=['GET', 'POST'])
def generate_report():
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
                return jsonify(result)
            except Exception as e:
                return jsonify({'error': True, 'message': str(e)}), 500
                
    return render_template('reports/generate.html')

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