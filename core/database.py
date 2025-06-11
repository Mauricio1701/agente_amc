import os
import json
import uuid
import time
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector
import logging
from mysql.connector import Error
from typing import List, Dict, Optional, Union

load_dotenv()  # Carga las variables del .env

class Database:
    def __init__(self):
        self.config = {
            'host': os.getenv('MYSQL_HOST', '203.161.49.197'),  # Default al host proporcionado
            'port': int(os.getenv('MYSQL_PORT', 3306)),
            'user': os.getenv('MYSQL_USER', 'administrator'),
            'password': os.getenv('MYSQL_PASSWORD', 'Rw+@ZR@WJzqBUq6Y'),
            'database': os.getenv('MYSQL_DATABASE', 'promolider_agentl_db'),
            'raise_on_warnings': False
        }
        required_fields = ['host', 'port', 'user', 'database']
        missing = [field for field in required_fields if not self.config[field]]
        if missing:
            raise ValueError(
                f"Faltan variables de entorno requeridas: {', '.join(missing)}")

        self._initialize_database()

    def _get_connection(self, use_database: bool = True) -> mysql.connector.connection.MySQLConnection:
        config = self.config.copy()
        if not use_database:
            config.pop('database', None)
        config.update({
            'connection_timeout': 60,
            'get_warnings': False,  # Cambiado a False para eliminar warnings
        })
        max_retries = 3
        retry_count = 0
        while retry_count < max_retries:
            try:
                conn = mysql.connector.connect(**config)
                return conn
            except Error as e:
                retry_count += 1
                if retry_count == max_retries:
                    raise RuntimeError(f"Error de conexión a MySQL: {e}")
                time.sleep(2)  # Esperar 2 segundos antes de reintentar

    def _initialize_database(self) -> None:
        conn = None
        cursor = None
        try:
            # Primero verificamos si la base de datos existe
            conn = self._get_connection(use_database=False)
            cursor = conn.cursor()
            
            # Verificar si la base de datos existe
            cursor.execute(f"SHOW DATABASES LIKE '{self.config['database']}'")
            db_exists = cursor.fetchone()
            
            if not db_exists:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            
            cursor.execute(f"USE {self.config['database']}")

            # Verificar si las tablas existen antes de crearlas
            cursor.execute("SHOW TABLES")
            existing_tables = [table[0] for table in cursor.fetchall()]
            
            # Crear tablas solo si no existen
            if 'user_files' not in existing_tables:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_files (
                        file_id VARCHAR(36) PRIMARY KEY,
                        file_name VARCHAR(255) NOT NULL,
                        file_type VARCHAR(50) NOT NULL,
                        processed_text LONGTEXT,
                        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_file_type (file_type),
                        INDEX idx_upload_date (upload_date)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()
            
            if 'agent_knowledge' not in existing_tables:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS agent_knowledge (
                        knowledge_id INT AUTO_INCREMENT PRIMARY KEY,
                        topic VARCHAR(255) NOT NULL,
                        facts JSON NOT NULL,
                        source VARCHAR(255) DEFAULT NULL,
                        last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE INDEX idx_topic (topic),
                        INDEX idx_last_accessed (last_accessed)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()

            if 'reports' not in existing_tables:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS reports (
                        file_id VARCHAR(36) PRIMARY KEY,
                        file_name VARCHAR(255) NOT NULL,
                        timestamp DATETIME NOT NULL,
                        FOREIGN KEY (file_id) REFERENCES user_files(file_id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()

            if 'sessions' not in existing_tables:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id VARCHAR(36) PRIMARY KEY,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_activity DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()

            if 'chat_history' not in existing_tables:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        session_id VARCHAR(36) PRIMARY KEY,
                        dialogue JSON NOT NULL,
                        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
                        INDEX idx_last_updated (last_updated)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()
            
            if 'report_files' not in existing_tables:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS report_files (
                        file_id VARCHAR(36) PRIMARY KEY,
                        report_id VARCHAR(100) NOT NULL,
                        file_name VARCHAR(255) NOT NULL,
                        file_content LONGTEXT NOT NULL,
                        file_size INT DEFAULT 0,
                        download_url TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_report_id (report_id),
                        INDEX idx_created_at (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()

        except Exception as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Error al inicializar base de datos: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    # Resto del código permanece igual
    def save_file(self, file_id: str, file_name: str, file_type: str, processed_text: str) -> bool:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_files 
                (file_id, file_name, file_type, processed_text)
                VALUES (%s, %s, %s, %s)
            """, (file_id, file_name, file_type, processed_text))
            conn.commit()
            return True
        except Error:
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def get_file_text(self, file_id: str) -> Optional[str]:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT processed_text FROM user_files 
                WHERE file_id = %s
            """, (file_id,))
            result = cursor.fetchone()
            return result['processed_text'] if result else None
        except Error:
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def get_all_files(self) -> List[Dict[str, str]]:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT file_id, file_name, file_type, processed_text, upload_date
                FROM user_files 
                ORDER BY upload_date DESC
            """)
            return cursor.fetchall()
        except Error:
            return []
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def delete_file(self, file_id: str) -> bool:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM user_files 
                WHERE file_id = %s
            """, (file_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            return deleted
        except Error:
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def get_file_count(self) -> int:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM user_files")
            return cursor.fetchone()[0]
        except Error:
            return 0
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def save_knowledge(self, knowledge: List[Dict]) -> bool:
        """Guarda el conocimiento en la base de datos."""
        if not knowledge:
            return True  # No hay nada que guardar
            
        try:
            conn = self._get_connection()
            if not conn:
                return False
                
            cursor = conn.cursor()
            
            # Primero limpiar la tabla
            cursor.execute("DELETE FROM agent_knowledge")
            
            # Insertar nuevos datos
            for item in knowledge:
                topic = item.get("topic", "")
                if not topic:
                    continue
                    
                facts = item.get("facts", [])
                if isinstance(facts, list):
                    facts_json = json.dumps(facts, ensure_ascii=False)
                else:
                    facts_json = json.dumps([str(facts)], ensure_ascii=False)
                    
                source = item.get("source", "chat")
                
                # Convertir last_accessed a string si es datetime
                last_accessed = item.get("last_accessed")
                if isinstance(last_accessed, datetime):
                    last_accessed = last_accessed.isoformat()
                elif not last_accessed:
                    last_accessed = datetime.now().isoformat()
                
                cursor.execute(
                    "INSERT INTO agent_knowledge (topic, facts, source, last_accessed) VALUES (%s, %s, %s, %s)",
                    (topic, facts_json, source, last_accessed)
                )
                
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            return False

    def get_all_knowledge(self) -> List[Dict]:
        """Obtiene todo el conocimiento almacenado en la base de datos."""
        try:
            conn = self._get_connection()
            if not conn:
                return []
                
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT topic, facts, source, last_accessed FROM agent_knowledge")
            result = cursor.fetchall()
            
            knowledge = []
            for row in result:
                item = {
                    "topic": row["topic"],
                    "source": row.get("source", "unknown"),
                    "last_accessed": row.get("last_accessed")
                }
                
                # Convertir el campo facts de JSON a lista
                if isinstance(row["facts"], str):
                    try:
                        item["facts"] = json.loads(row["facts"])
                    except:
                        item["facts"] = [row["facts"]]
                else:
                    item["facts"] = row["facts"] if row["facts"] else []
                    
                knowledge.append(item)
                
            cursor.close()
            conn.close()
            return knowledge
        except Exception as e:
            print(f"Error obteniendo conocimiento: {str(e)}")
            return []

    def clear_knowledge(self) -> bool:
        """Limpia toda la tabla de conocimiento."""
        try:
            conn = self._get_connection()
            if not conn:
                return False
                
            cursor = conn.cursor()
            cursor.execute("DELETE FROM agent_knowledge")
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"Error al limpiar conocimiento: {str(e)}")
            return False

    def save_report(self, file_id: str, file_name: str, timestamp: datetime) -> bool:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reports (file_id, file_name, timestamp)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE file_name=VALUES(file_name), timestamp=VALUES(timestamp)
            """, (file_id, file_name, timestamp))
            conn.commit()
            return True
        except Error:
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def get_all_reports(self) -> List[Dict[str, Union[str, datetime]]]:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT file_id, file_name, timestamp
                FROM reports 
                ORDER BY timestamp DESC
            """)
            return cursor.fetchall()
        except Error:
            return []
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def create_session(self, session_id: str) -> bool:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (session_id)
                VALUES (%s)
            """, (session_id,))
            conn.commit()
            return True
        except Error:
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def update_session_activity(self, session_id: str) -> bool:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions 
                SET last_activity = CURRENT_TIMESTAMP
                WHERE session_id = %s
            """, (session_id,))
            conn.commit()
            updated = cursor.rowcount > 0
            return updated
        except Error:
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def save_chat(self, session_id: str, query: str, response: str) -> bool:
        dialogue = [{"user_message": query, "ai_response": response,
                     "timestamp": datetime.now().isoformat()}]
        return self.save_chat_history(session_id, dialogue)


    def get_chat_history(self, session_id: str, limit: int = 20) -> List[Dict[str, str]]:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT dialogue
                FROM chat_history 
                WHERE session_id = %s
            """, (session_id,))
            result = cursor.fetchone()
            if result and result['dialogue']:
                dialogue = json.loads(result['dialogue'])
                if not isinstance(dialogue, list):
                    dialogue = [dialogue]
                return dialogue[-limit:]
            return []
        except Error:
            return []
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def get_chat_by_id(self, chat_id: int) -> Optional[Dict[str, str]]:
        return None

    def delete_chat(self, chat_id: int) -> bool:
        return False

    def save_chat_history(self, session_id: str, dialogue: List[Dict]) -> bool:
        conn = None
        cursor = None
        try:
            # Asegurarse de que dialogue sea una lista
            if not isinstance(dialogue, list):
                dialogue = []
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Comprobamos si el registro existe
            cursor.execute(
                "SELECT 1 FROM chat_history WHERE session_id = %s", (session_id,))
            exists = cursor.fetchone() is not None
            
            dialogue_json = json.dumps(dialogue, ensure_ascii=False)
            
            if exists:
                # Actualizar el registro existente con un diálogo vacío o nuevo
                cursor.execute("""
                    UPDATE chat_history 
                    SET dialogue = %s,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                """, (dialogue_json, session_id))
            else:
                # Insertar un nuevo registro
                cursor.execute("""
                    INSERT INTO chat_history (session_id, dialogue)
                    VALUES (%s, %s)
                """, (session_id, dialogue_json))
            
            conn.commit()
            return True
        except Error as e:
            print(f"Error al guardar historial: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def clear_chat_history(self, session_id: str) -> bool:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Primero intentamos actualizar con un diálogo vacío
            cursor.execute("""
                UPDATE chat_history 
                SET dialogue = '[]',
                    last_updated = CURRENT_TIMESTAMP
                WHERE session_id = %s
            """, (session_id,))
            
            updated = cursor.rowcount > 0
            conn.commit()
            
            # Si no se actualizó ningún registro, intentamos eliminar
            if not updated:
                cursor.execute("""
                    DELETE FROM chat_history 
                    WHERE session_id = %s
                """, (session_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
                return deleted
            
            return True
        except Error as e:
            print(f"Error al limpiar historial: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
    
    def save_report_file(self, report_id: str, file_name: str, file_content: str, download_url: str = None) -> str:
        """Guarda un archivo CSV de reporte en la base de datos"""
        conn = None
        cursor = None
        try:
            file_id = str(uuid.uuid4())
            file_size = len(file_content.encode('utf-8'))
            
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO report_files (file_id, report_id, file_name, file_content, file_size, download_url)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (file_id, report_id, file_name, file_content, file_size, download_url))
            conn.commit()
            return file_id
        except Exception as e:
            print(f"Error al guardar archivo de reporte: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
                
    def get_all_report_files(self) -> List[Dict]:
        """Obtiene todos los archivos de reportes guardados"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT file_id, report_id, file_name, file_size, download_url, created_at
                FROM report_files 
                ORDER BY created_at DESC
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Error al obtener archivos de reporte: {str(e)}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
    
    def get_report_file_info(self, file_id: str) -> Optional[Dict]:
        """Obtiene información completa de un archivo de reporte"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT file_id, report_id, file_name, file_size, download_url, created_at
                FROM report_files 
                WHERE file_id = %s
            """, (file_id,))
            return cursor.fetchone()
        except Exception as e:
            print(f"Error al obtener información del archivo: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def get_report_files(self, report_id: str) -> List[Dict]:
        """Obtiene todos los archivos de un reporte específico"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT file_id, report_id, file_name, file_size, download_url, created_at
                FROM report_files 
                WHERE report_id = %s
                ORDER BY created_at DESC
            """, (report_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"Error al obtener archivos de reporte: {str(e)}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
    def delete_report_file(self, file_id: str) -> bool:
        """Elimina un archivo de reporte"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM report_files 
                WHERE file_id = %s
            """, (file_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            return deleted
        except Exception as e:
            print(f"Error al eliminar archivo de reporte: {str(e)}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def get_report_file_content(self, file_id: str) -> Optional[str]:
        """Obtiene el contenido de un archivo específico"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT file_content FROM report_files 
                WHERE file_id = %s
            """, (file_id,))
            result = cursor.fetchone()
            return result['file_content'] if result else None
        except Exception as e:
            print(f"Error al obtener contenido del archivo: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
            
    def get_report_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Obtiene un archivo de reporte específico por su ID"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT file_id, report_id, file_name, file_size, download_url, created_at,
                    LENGTH(file_content) as content_length
                FROM report_files 
                WHERE file_id = %s
            """, (file_id,))
            result = cursor.fetchone()
            return result
        except Exception as e:
            print(f"Error al obtener archivo por ID: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

if __name__ == "__main__":
    db = Database()
    print(f"Total archivos: {db.get_file_count()}")
    print(f"Total conocimiento: {len(db.get_all_knowledge())}")
    print(f"Total reportes: {len(db.get_all_reports())}")