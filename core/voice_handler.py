#voice_handler.py
import speech_recognition as sr
import pyttsx3
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceHandler:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.engine = None
        self.is_speaking = False
        self._initialize_engine()
        self._configure_recognizer()

    def _initialize_engine(self):
        try:
            self.engine = pyttsx3.init()
            self._configure_engine()
        except Exception as e:
            logger.error(f"Error inicializando el motor de voz: {str(e)}")
            raise

    def _configure_engine(self):
        try:
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 0.9)
            voices = self.engine.getProperty('voices')
            spanish_voice_found = False
            for voice in voices:
                logger.info(f"Voz disponible: {voice.name} (ID: {voice.id})")
                if "spanish" in voice.name.lower() or "es-es" in voice.id.lower():
                    self.engine.setProperty('voice', voice.id)
                    logger.info(f"Voz configurada: {voice.name}")
                    spanish_voice_found = True
                    break
            if not spanish_voice_found:
                logger.warning("No se encontró una voz en español. Usando voz por defecto.")
                self.engine.setProperty('voice', voices[0].id)
                logger.info(f"Voz predeterminada configurada: {voices[0].name}")
        except Exception as e:
            logger.error(f"Error configurando el motor de voz: {str(e)}")
            raise

    def _configure_recognizer(self):
        try:
            self.recognizer.energy_threshold = 200  # Reducido para mayor sensibilidad
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 1.0
            logger.info("Reconocedor de voz configurado con umbral de energía 200, ajuste dinámico activado y pause_threshold de 1.0 segundos.")
        except Exception as e:
            logger.error(f"Error configurando el reconocedor de voz: {str(e)}")
            raise

    def recognize_speech(self, timeout=5, phrase_time_limit=10):
        try:
            with sr.Microphone() as source:
                logger.info("Ajustando al ruido ambiental...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logger.info(f"Umbral de energía ajustado: {self.recognizer.energy_threshold}")
                
                logger.info("Escuchando...")
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                
                logger.info("Procesando audio...")
                text = self.recognizer.recognize_google(audio, language="es-ES")
                logger.info(f"Texto reconocido: {text}")
                return text
        except sr.WaitTimeoutError:
            logger.warning("Tiempo de espera agotado. No se detectó voz.")
            return None
        except sr.UnknownValueError:
            logger.warning("No se pudo entender el audio.")
            return None
        except sr.RequestError as e:
            logger.error(f"Error en el servicio de reconocimiento: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado en el reconocimiento de voz: {str(e)}")
            return None

    def text_to_speech(self, text):
        if not self.engine:
            logger.error("Motor de voz no inicializado.")
            return

        try:
            if not text:
                logger.warning("No se proporcionó texto para sintetizar.")
                return

            self.is_speaking = True
            logger.info(f"Sintetizando texto a voz: {text[:50]}...")
            
            self.engine.stop()
            self.engine.say(text)
            self.engine.runAndWait()
            logger.info("Reproducción de voz completada.")
        except Exception as e:
            logger.error(f"Error en la síntesis de voz: {str(e)}")
            try:
                logger.info("Reintentando inicialización del motor de voz...")
                self.engine = pyttsx3.init()
                self._configure_engine()
                self.engine.say(text)
                self.engine.runAndWait()
                logger.info("Reproducción de voz completada después de reiniciar el motor.")
            except Exception as e2:
                logger.error(f"Error al reiniciar el motor de voz: {str(e2)}")
        finally:
            self.is_speaking = False

    def stop_speech(self):
        try:
            if self.is_speaking and self.engine:
                self.engine.stop()
                logger.info("Reproducción de voz detenida.")
            self.is_speaking = False
        except Exception as e:
            logger.error(f"Error deteniendo la voz: {str(e)}")