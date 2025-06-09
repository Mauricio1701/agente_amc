#chat_history.py
import logging
from datetime import datetime
from typing import List, Dict, Optional
from core.database import Database

logger = logging.getLogger(__name__)

class ChatHistory:
    def __init__(self):
        self.db = Database()
        self.session_id = None
        self.current_dialogue = []  # Lista para almacenar los mensajes de la sesión actual

    def set_session_id(self, session_id: str) -> bool:
        """Configura el session_id para las operaciones de chat. Devuelve True si se configuró correctamente."""
        if not session_id or not isinstance(session_id, str):
            logger.error("Session ID inválido o no proporcionado")
            return False
        self.session_id = session_id
        if not self.db.update_session_activity(session_id):
            if not self.db.create_session(session_id):
                logger.error(f"No se pudo crear la sesión con ID: {session_id}")
                self.session_id = None
                return False
        # Cargar el historial existente para este session_id, si lo hay
        existing_history = self.db.get_chat_history(self.session_id)
        if existing_history and isinstance(existing_history, dict):
            self.current_dialogue = existing_history.get('dialogue', [])
        logger.info(f"Session ID configurado: {self.session_id}")
        return True

    def add_message(self, user_message: str, ai_response: str) -> bool:
        if not self.session_id:
            logger.error("Session ID no configurado")
            return False
        try:
            self.current_dialogue.append({
                "user_message": user_message,
                "ai_response": ai_response,
                "timestamp": datetime.now().isoformat()
            })
            success = self.db.save_chat_history(self.session_id, self.current_dialogue)
            if success:
                logger.info(f"Mensaje añadido al historial de la sesión {self.session_id}: {user_message[:30]}...")
            else:
                logger.error(f"Fallo al añadir mensaje para session_id: {self.session_id}")
            return success
        except Exception as e:
            logger.error(f"Error al añadir mensaje: {str(e)}")
            return False

    def save_chat(self, query: str, response: str) -> bool:
        """Método heredado para compatibilidad: redirige a add_message."""
        return self.add_message(query, response)

    def get_history(self, limit: int = 20) -> List[Dict[str, str]]:
        if not self.session_id:
            logger.error("Session ID no configurado")
            return []
        try:
            history = self.db.get_chat_history(self.session_id)
            if not history:
                logger.info(f"No hay historial para session_id: {self.session_id}")
                return []
            logger.info(f"Historial recuperado para session_id: {self.session_id}, {len(history)} entradas")
            return history
        except Exception as e:
            logger.error(f"Error al obtener historial de chat: {str(e)}")
            return []

    def get_chat_by_id(self, chat_id: int) -> Optional[Dict[str, str]]:
        """Recupera un chat específico por su chat_id."""
        if not self.session_id:
            logger.error("Session ID no configurado")
            return None
        try:
            chat = self.db.get_chat_by_id(chat_id)
            if chat:
                logger.info(f"Chat recuperado: chat_id={chat_id}")
            else:
                logger.warning(f"No se encontró chat con chat_id={chat_id}")
            return chat
        except Exception as e:
            logger.error(f"Error al obtener chat por ID: {str(e)}")
            return None

    def delete_chat(self, chat_id: int) -> bool:
        """Elimina un chat específico por su chat_id."""
        if not self.session_id:
            logger.error("Session ID no configurado")
            return False
        try:
            success = self.db.delete_chat(chat_id)
            if success:
                logger.info(f"Chat eliminado: chat_id={chat_id}")
            else:
                logger.warning(f"No se pudo eliminar chat con chat_id={chat_id}")
            return success
        except Exception as e:
            logger.error(f"Error al eliminar chat: {str(e)}")
            return False

    def clear_history(self) -> bool:
        """Limpia el historial de la sesión actual."""
        if not self.session_id:
            logger.error("Session ID no configurado")
            return False
        try:
            # Vaciar la lista en memoria
            self.current_dialogue = []
            
            # Intentar primero guardar una lista vacía
            success = self.db.save_chat_history(self.session_id, [])
            
            # Si falla, intentar borrar el registro por completo
            if not success:
                success = self.db.clear_chat_history(self.session_id)
            
            # Registrar el resultado
            if success:
                logger.info(f"Historial limpiado para session_id: {self.session_id}")
            else:
                logger.error(f"Fallo al limpiar historial para session_id: {self.session_id}")
            
            return success
        except Exception as e:
            logger.error(f"Error al limpiar historial: {str(e)}")
            return False