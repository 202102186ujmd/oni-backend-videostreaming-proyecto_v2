# config.py — Configuración central del LiveKit Manager API
import logging
from typing import Optional
from pydantic import Field, AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ---------------------------
    # API BASIC AUTH
    # ---------------------------
    API_USER: str = Field(..., env="API_USER")
    API_PASSWORD: str = Field(..., env="API_PASSWORD")

    # ---------------------------
    # LIVEKIT CONFIG
    # ---------------------------
    LIVEKIT_URL: AnyHttpUrl = Field(..., env="LIVEKIT_URL")              # HTTP API
    LIVEKIT_WS_URL: str = Field(..., env="LIVEKIT_WS_URL")               # WebSocket URL (ws/wss)
    LIVEKIT_HTTP_URL: Optional[AnyHttpUrl] = Field(None, env="LIVEKIT_HTTP_URL")  # Opcional

    LIVEKIT_API_KEY: str = Field(..., env="LIVEKIT_API_KEY")
    LIVEKIT_API_SECRET: str = Field(..., env="LIVEKIT_API_SECRET")
    LIVEKIT_VERIFY_SSL: bool = Field(default=False, env="LIVEKIT_VERIFY_SSL")

    # ---------------------------
    # MINIO CONFIG
    # ---------------------------
    MINIO_ENDPOINT: str = Field(..., env="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: str = Field(..., env="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = Field(..., env="MINIO_SECRET_KEY")
    MINIO_BUCKET_NAME: str = Field(..., env="MINIO_BUCKET_NAME")

    MINIO_REGION: str = Field(default="us-east-1", env="MINIO_REGION")
    MINIO_FORCE_PATH_STYLE: bool = Field(default=True, env="MINIO_FORCE_PATH_STYLE")
    MINIO_USE_SSL: bool = Field(default=False, env="MINIO_USE_SSL")
    MINIO_AUTO_CREATE_BUCKET: bool = Field(default=True, env="MINIO_AUTO_CREATE_BUCKET")

    # ---------------------------
    # EGRESS CONFIG
    # ---------------------------
    EGRESS_STORAGE_PATH: str = Field(default="recordings", env="EGRESS_STORAGE_PATH")
    EGRESS_AUTO_CLEANUP_ENABLED: bool = Field(default=False, env="EGRESS_AUTO_CLEANUP_ENABLED")
    EGRESS_AUTO_CLEANUP_DAYS: int = Field(default=7, env="EGRESS_AUTO_CLEANUP_DAYS")
    EGRESS_DEFAULT_FILE_TYPE: str = Field(default="mp4", env="EGRESS_DEFAULT_FILE_TYPE")

    # ---------------------------
    # ROOM DEFAULTS
    # ---------------------------
    ROOM_DEFAULT_MAX_PARTICIPANTS: int = Field(default=0, env="ROOM_DEFAULT_MAX_PARTICIPANTS")  # 0 = ilimitado
    ROOM_DEFAULT_EMPTY_TIMEOUT: int = Field(default=300, env="ROOM_DEFAULT_EMPTY_TIMEOUT")  # 5 minutos
    ROOM_DEFAULT_AUTO_RECORD: bool = Field(default=False, env="ROOM_DEFAULT_AUTO_RECORD")

    # ---------------------------
    # TOKEN CONFIG
    # ---------------------------
    TOKEN_DEFAULT_TTL_SECONDS: int = Field(default=14400, env="TOKEN_DEFAULT_TTL_SECONDS")  # 4 horas

    # ---------------------------
    # API CONFIG
    # ---------------------------
    API_TITLE: str = Field(default="LiveKit Manager API", env="API_TITLE")
    API_VERSION: str = Field(default="1.0.0", env="API_VERSION")
    API_PREFIX: str = Field(default="/api/v1", env="API_PREFIX")
    DEBUG: bool = Field(default=False, env="DEBUG")

    # ---------------------------
    # CORS CONFIG
    # ---------------------------
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="CORS_ORIGINS"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")

    # ---------------------------
    # CONFIG
    # ---------------------------
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    # ---------------------------
    # VALIDACIONES (Pydantic v2)
    # ---------------------------
    @field_validator("LIVEKIT_URL", mode="before")
    @classmethod
    def ensure_http(cls, v):
        """El SDK LiveKitAPI necesita HTTP, no WS."""
        if isinstance(v, str) and v.startswith(("ws://", "wss://")):
            return v.replace("ws://", "http://").replace("wss://", "https://")
        return v

    @field_validator("LIVEKIT_WS_URL", mode="before")
    @classmethod
    def ensure_ws(cls, v):
        """Garantizar que el WebSocket URL use ws:// o wss://."""
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v.replace("http://", "ws://").replace("https://", "wss://")
        return v

    @field_validator("MINIO_ENDPOINT", mode="before")
    @classmethod
    def strip_minio_slash(cls, v):
        """Quitar slash final si existe."""
        return v.rstrip("/") if isinstance(v, str) else v

    @field_validator("EGRESS_STORAGE_PATH", mode="before")
    @classmethod
    def normalize_path(cls, v):
        """Remover slash inicial y final, pero permitir rutas relativas."""
        if isinstance(v, str):
            return v.strip("/")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Permitir CORS_ORIGINS como string separado por comas o lista."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("EGRESS_AUTO_CLEANUP_DAYS")
    @classmethod
    def validate_cleanup_days(cls, v):
        """Asegurar que los días de limpieza sean positivos."""
        if v < 1:
            raise ValueError("EGRESS_AUTO_CLEANUP_DAYS debe ser al menos 1")
        return v

    @field_validator("TOKEN_DEFAULT_TTL_SECONDS")
    @classmethod
    def validate_token_ttl(cls, v):
        """Asegurar que el TTL del token sea razonable."""
        if v < 60:
            raise ValueError("TOKEN_DEFAULT_TTL_SECONDS debe ser al menos 60 segundos")
        if v > 86400:  # 24 horas
            raise ValueError("TOKEN_DEFAULT_TTL_SECONDS no debe exceder 86400 segundos (24h)")
        return v

    # ---------------------------
    # PROPIEDADES ÚTILES
    # ---------------------------
    @property
    def minio_url(self) -> str:
        """URL completa de MinIO con protocolo."""
        protocol = "https" if self.MINIO_USE_SSL else "http"
        return f"{protocol}://{self.MINIO_ENDPOINT}"

    @property
    def is_production(self) -> bool:
        """Detectar si estamos en producción."""
        return not self.DEBUG and self.LIVEKIT_VERIFY_SSL

    def get_livekit_client_config(self) -> dict:
        """Retorna configuración lista para LiveKitAPI."""
        return {
            "host": str(self.LIVEKIT_URL),
            "api_key": self.LIVEKIT_API_KEY,
            "api_secret": self.LIVEKIT_API_SECRET,
            "insecure": not self.LIVEKIT_VERIFY_SSL,
        }


# ---------------------------
# Singleton de settings (caché)
# ---------------------------
@lru_cache()
def get_settings() -> Settings:
    """
    Obtiene la instancia singleton de Settings.
    Usa caché para evitar recargar el .env en cada llamada.
    """
    return Settings()


# Export directo
settings = get_settings()


# ---------------------------
# Validación al inicio
# ---------------------------
def validate_settings():
    """
    Valida que todas las configuraciones críticas estén presentes.
    Llama esto en el startup de FastAPI.
    """
    required_fields = [
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET_NAME",
    ]
    
    missing = []
    for field in required_fields:
        if not getattr(settings, field, None):
            missing.append(field)
    
    if missing:
        raise ValueError(
            f"Faltan las siguientes configuraciones requeridas: {', '.join(missing)}"
        )
    
    logger.info("✅ Configuración validada correctamente")
    logger.info("   - LiveKit URL: %s", settings.LIVEKIT_URL)
    logger.info("   - MinIO: %s", settings.minio_url)
    logger.info("   - Bucket: %s", settings.MINIO_BUCKET_NAME)
    logger.info("   - Modo: %s", 'Producción' if settings.is_production else 'Desarrollo')