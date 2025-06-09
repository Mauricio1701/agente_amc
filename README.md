# Configurar el entorno virtual

### En Windows
python -m venv venv <br>
venv\Scripts\activate <br>

### Instalar requerimientos
pip install -r requirements.txt

# Configurar el archivo .env (credenciales)


DEEPSEEK_API_KEY=tu_api_key_aqui <br>

MYSQL_HOST=localhost <br>
MYSQL_PORT=3306 <br>
MYSQL_USER=tuusuario <br>
MYSQL_PASSWORD=tupassword <br>
MYSQL_DATABASE=nombre_base_datos <br>

AMAZON_AMC_CLIENT_ID=tu_client_id<br>
AMAZON_AMC_CLIENT_SECRET=tu_client_secret<br>
AMAZON_AMC_ACCESS_TOKEN=tu_access_token<br>
AMAZON_AMC_REFRESH_TOKEN=tu_refresh_token<br>
AMAZON_AMC_PROFILE_ID=tu_profile_id<br>
AMAZON_AMC_ADVERTISER_ID=tu_advertiser_id<br>
AMAZON_AMC_MARKETPLACE_ID=tu_marketplace_id<br>


# Ejecutar la aplicación

### Activar el entorno virtual primero
.venv\Scripts\activate<br>
flask run
