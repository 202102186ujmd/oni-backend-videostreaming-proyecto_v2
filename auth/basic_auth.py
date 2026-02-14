# auth/basic_auth.py
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from config import settings

logger = logging.getLogger(__name__)

# --- Inicializar esquema de seguridad ---
security = HTTPBasic()

def verify_basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Verifica credenciales HTTP Basic Auth.
    Se usa en Swagger con ventana emergente (candado).
    """
    username = credentials.username
    password = credentials.password

    if username != settings.API_USER or password != settings.API_PASSWORD:
        logger.warning(f"Intento fallido de autenticación con usuario: {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.info(f"Usuario autenticado correctamente: {username}")
    return {"username": username}
