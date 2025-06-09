from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import uuid
import os
from datetime import datetime
from core.database import Database
from core.deepseek_client import DeepSeekClient
from core.voice_handler import VoiceHandler
from core.amazon_client_amc import generate_amc_report

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
    query = request.form.get('query', '')
    if not query:
        return jsonify({'error': 'No se proporcionó consulta'}), 400
    
    try:
        response = process_query(query)
        
        # Guardar explícitamente la conversación en el historial
        if not deepseek_client.chat_history.add_message(query, response):
            app.logger.warning("No se pudo guardar la conversación en el historial")
        
        return jsonify({'response': response})
    except Exception as e:
        app.logger.error(f"Error en proceso de chat: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/reports/delete', methods=['POST'])
def delete_report():
    file_id = request.form.get('file_id')
    if not file_id:
        flash('No se proporcionó ID de archivo', 'warning')
        return redirect(url_for('reports'))
    
    try:
        if db.delete_file(file_id):
            flash('Reporte eliminado con éxito', 'success')
        else:
            flash('No se pudo eliminar el reporte', 'danger')
    except Exception as e:
        flash(f'Error al eliminar reporte: {str(e)}', 'danger')
    
    return redirect(url_for('reports'))

# Modificar la ruta reports() para incluir la fecha actual
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