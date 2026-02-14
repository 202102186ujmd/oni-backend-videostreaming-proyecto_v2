# auth/basic_auth.py
import logging
import secrets
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

    # Use secrets.compare_digest to prevent timing attacks
    username_correct = secrets.compare_digest(username.encode('utf-8'), settings.API_USER.encode('utf-8'))
    password_correct = secrets.compare_digest(password.encode('utf-8'), settings.API_PASSWORD.encode('utf-8'))
    
    if not (username_correct and password_correct):
        logger.warning("Intento fallido de autenticación con usuario: %s", username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.info("Usuario autenticado correctamente: %s", username)
    return {"username": username}
