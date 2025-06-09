#file_memory_handler.py
import os
from .database import Database

class FileMemoryHandler:
    def __init__(self):
        self.db = Database()

    def save_file_context(self, file_name, file_content):
        try:
            self.db.save_file(file_name=file_name, content=file_content)
            return f"📁 Archivo '{file_name}' guardado en memoria."
        except Exception as e:
            return f"⚠️ Error guardando archivo: {str(e)}"

    def get_all_file_contexts(self):
        try:
            files = self.db.get_all_files()
            return [file['content'] for file in files]
        except Exception as e:
            print(f"⚠️ Error al cargar archivos guardados: {str(e)}")
            return []

    def search_file_context(self, keyword):
        try:
            return self.db.search_file_content(keyword)
        except Exception as e:
            print(f"⚠️ Error buscando en archivos: {str(e)}")
            return []