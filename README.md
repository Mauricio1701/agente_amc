# Configurar el entorno virtual

### En Windows
python -m venv venv
venv\Scripts\activate

### Instalar requerimientos
pip install -r requirements.txt

# Configurar el archivo .env (credenciales)


DEEPSEEK_API_KEY=tu_api_key_aqui

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=tuusuario
MYSQL_PASSWORD=tupassword
MYSQL_DATABASE=nombre_base_datos

AMAZON_AMC_CLIENT_ID=tu_client_id
AMAZON_AMC_CLIENT_SECRET=tu_client_secret
AMAZON_AMC_ACCESS_TOKEN=tu_access_token
AMAZON_AMC_REFRESH_TOKEN=tu_refresh_token
AMAZON_AMC_PROFILE_ID=tu_profile_id
AMAZON_AMC_ADVERTISER_ID=tu_advertiser_id
AMAZON_AMC_MARKETPLACE_ID=tu_marketplace_id


# Ejecutar la aplicación

### Activar el entorno virtual primero
.venv\Scripts\activate
flask run
