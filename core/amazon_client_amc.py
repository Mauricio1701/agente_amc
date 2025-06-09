#core/amazon_client_amc.py
import os
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import jwt
from dotenv import load_dotenv
import time
import uuid

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AmazonTokenManager:
    def __init__(self):
        self.access_token = None
        self.token_expiry = None
        self._load_credentials()
        
        if not self.access_token or self.is_token_expired():
            self.refresh_access_token()

    def _load_credentials(self):
        required_env_vars = [
            "AMAZON_AMC_CLIENT_ID",
            "AMAZON_AMC_CLIENT_SECRET",
            "AMAZON_AMC_ACCESS_TOKEN",
            "AMAZON_AMC_REFRESH_TOKEN",
            "AMAZON_AMC_MARKETPLACE_ID"
        ]
        for var in required_env_vars:
            if not os.getenv(var):
                raise ValueError(f"Falta la variable de entorno: {var}")
        
        self.client_id = os.getenv("AMAZON_AMC_CLIENT_ID")
        self.client_secret = os.getenv("AMAZON_AMC_CLIENT_SECRET")
        self.access_token = os.getenv("AMAZON_AMC_ACCESS_TOKEN")
        self.refresh_token = os.getenv("AMAZON_AMC_REFRESH_TOKEN")
        self.marketplace_id = os.getenv("AMAZON_AMC_MARKETPLACE_ID")
        
        self._decode_token_expiry()

    def _decode_token_expiry(self):
        try:
            decoded_token = jwt.decode(self.access_token, options={"verify_signature": False})
            self.token_expiry = datetime.fromtimestamp(decoded_token["exp"])
        except Exception as e:
            logger.error(f"Error al decodificar el token: {str(e)}")
            self.token_expiry = datetime.now()  

    def is_token_expired(self) -> bool:
        if not self.token_expiry:
            return True
        buffer_time = timedelta(minutes=5)
        return datetime.now() >= (self.token_expiry - buffer_time)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException)
    )
    def refresh_access_token(self):
        url = "https://api.amazon.com/auth/o2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        try:
            response = requests.post(url, headers=headers, data=payload, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token", self.refresh_token)
            self._decode_token_expiry()
            
            logger.info("Token de acceso renovado exitosamente")
            return self.access_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al renovar el token: {str(e)}")
            if response and response.status_code == 401:
                raise Exception("Credenciales inválidas. Verifica AMAZON_AMC_CLIENT_ID, AMAZON_AMC_CLIENT_SECRET o AMAZON_AMC_REFRESH_TOKEN.")
            raise

    def get_headers(self) -> Dict[str, str]:
        if self.is_token_expired():
            self.refresh_access_token()
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Amazon-Advertising-API-ClientId": self.client_id,
            "Amazon-Advertising-API-AdvertiserId": os.getenv("AMAZON_AMC_ADVERTISER_ID", ""),
            "Amazon-Advertising-API-MarketplaceId": self.marketplace_id,
            "Content-Type": "application/vnd.amcworkflows.v1+json",
            "Accept": "application/vnd.amcworkflows.v1+json"
        }

token_manager = AmazonTokenManager()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def make_amazon_request(endpoint: str, method: str = "GET", body: Optional[Dict] = None) -> Dict:
    base_url = "https://advertising-api.amazon.com"
    url = f"{base_url}{endpoint}"
    headers = token_manager.get_headers()

    try:
        if method.upper() == "POST":
            response = requests.post(url, headers=headers, json=body, timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)
        
        response.raise_for_status()
        result = response.json() if response.content else {"message": "No content"}
        logger.info(f"Solicitud exitosa a {url}: {result}")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"Error en la solicitud a Amazon API: {url} - {str(e)}")
        try:
            error_detail = response.json() if response.content else {"message": str(e)}
        except:
            error_detail = {"message": str(e)}
        error_detail["error"] = True
        return error_detail

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def generate_amc_report(
    instance_id: str,
    sql_query: str,
    output_format: str = "CSV",
    max_wait_time: int = 600,
    poll_interval: int = 10
) -> Dict:
    """
    Genera un reporte AMC de forma autónoma: crea un workflow, lo ejecuta, espera a que termine y devuelve las URLs de descarga.
    
    Args:
        instance_id (str): ID de la instancia AMC.
        sql_query (str): Consulta AMC-SQL para el reporte.
        output_format (str): Formato del reporte (por defecto, "CSV").
        max_wait_time (int): Tiempo máximo de espera en segundos (por defecto, 600).
        poll_interval (int): Intervalo de polling en segundos (por defecto, 10).
    
    Returns:
        Dict: Resultado con las URLs de descarga o un mensaje de error.
    """
   
    workflow_id = f"report-{uuid.uuid4().hex[:8]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    logger.info(f"Generando reporte con workflow_id: {workflow_id}")

    # Paso 1: Crear el workflow
    logger.info("Creando workflow...")
    body = {
        "sqlQuery": sql_query,
        "workflowId": workflow_id,
        "outputFormat": output_format
    }
    create_result = make_amazon_request(f"/amc/reporting/{instance_id}/workflows", method="POST", body=body)
    if create_result.get("error"):
        logger.error(f"Error al crear workflow: {create_result['message']}")
        return create_result

    # Paso 2: Ejecutar el workflow
    logger.info("Ejecutando workflow...")
    execute_result = make_amazon_request(f"/amc/reporting/{instance_id}/workflowExecutions", method="POST", body={"workflowId": workflow_id})
    if execute_result.get("error"):
        logger.error(f"Error al ejecutar workflow: {execute_result['message']}")
        return execute_result
    
    workflow_execution_id = execute_result.get("workflowExecutionId", workflow_id)
    logger.info(f"Workflow ejecutado. ID de ejecución: {workflow_execution_id}")

    # Paso 3: Esperar a que el workflow termine
    start_time = time.time()
    while True:
        if time.time() - start_time > max_wait_time:
            logger.error("Tiempo máximo de espera alcanzado")
            return {"error": True, "message": "Tiempo máximo de espera alcanzado"}
        
        status_result = make_amazon_request(f"/amc/reporting/{instance_id}/workflowExecutions/{workflow_execution_id}")
        if status_result.get("error"):
            logger.error(f"Error al verificar estado: {status_result['message']}")
            return status_result
        
        status = status_result.get("status", "UNKNOWN")
        logger.info(f"Estado del workflow: {status}")
        if status == "SUCCEEDED":
            break
        elif status in ["FAILED", "CANCELLED"]:
            logger.error(f"Workflow falló con estado: {status}")
            return {"error": True, "message": f"Workflow falló con estado: {status}"}
        
        time.sleep(poll_interval)

    # Paso 4: Obtener las URLs de descarga
    logger.info("Obteniendo URLs de descarga...")
    download_result = make_amazon_request(f"/amc/reporting/{instance_id}/workflowExecutions/{workflow_execution_id}/downloadUrls")
    if download_result.get("error"):
        logger.error(f"Error al obtener URLs: {download_result['message']}")
        return download_result

    logger.info("Reporte generado exitosamente")
    return download_result