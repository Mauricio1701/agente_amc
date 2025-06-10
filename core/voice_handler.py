#voice_handler.py
import speech_recognition as sr
import pyttsx3
import logging
import time

logging.basicConfig(level=logging.ERROR)
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
                if "spanish" in voice.name.lower() or "es-es" in voice.id.lower():
                    self.engine.setProperty('voice', voice.id)
                    spanish_voice_found = True
                    break
            if not spanish_voice_found:
                self.engine.setProperty('voice', voices[0].id)
        except Exception as e:
            logger.error(f"Error configurando el motor de voz: {str(e)}")
            raise

    def _configure_recognizer(self):
        try:
            self.recognizer.energy_threshold = 200
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 1.0
        except Exception as e:
            logger.error(f"Error configurando el reconocedor de voz: {str(e)}")
            raise

    def recognize_speech(self, timeout=5, phrase_time_limit=10):
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                
                text = self.recognizer.recognize_google(audio, language="es-ES")
                return text
        except sr.WaitTimeoutError:
            logger.error("Tiempo de espera agotado. No se detectó voz.")
            return None
        except sr.UnknownValueError:
            logger.error("No se pudo entender el audio.")
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
                return

            self.is_speaking = True
            
            self.engine.stop()
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            logger.error(f"Error en la síntesis de voz: {str(e)}")
            try:
                self.engine = pyttsx3.init()
                self._configure_engine()
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e2:
                logger.error(f"Error al reiniciar el motor de voz: {str(e2)}")
        finally:
            self.is_speaking = False

    def stop_speech(self):
        try:
            if self.is_speaking and self.engine:
                self.engine.stop()
            self.is_speaking = False
        except Exception as e:
            logger.error(f"Error deteniendo la voz: {str(e)}")