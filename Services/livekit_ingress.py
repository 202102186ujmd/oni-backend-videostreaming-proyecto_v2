# Services/livekit_ingress.py
"""
Servicio para gestión de Ingress en LiveKit.
Permite crear, listar, actualizar y eliminar puntos de ingreso
para streams RTMP, WHIP y URL.
"""
from __future__ import annotations
import logging
from typing import List, Optional
from livekit import api as lk_api
from config import settings


logger = logging.getLogger(__name__)


class LiveKitIngressService:
    """
    Servicio para gestionar Ingress de LiveKit.
    
    Operaciones:
    - Crear ingress (RTMP, WHIP, URL)
    - Listar ingress activos
    - Actualizar configuración de ingress
    - Eliminar ingress
    """
    
    def __init__(
        self,
        *,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self._url = url or str(settings.LIVEKIT_URL)
        self._api_key = api_key or settings.LIVEKIT_API_KEY
        self._api_secret = api_secret or settings.LIVEKIT_API_SECRET
        self._client_instance: Optional[lk_api.LiveKitAPI] = None

    async def _get_client(self) -> lk_api.LiveKitAPI:
        """Obtiene o crea una instancia del cliente LiveKit API."""
        if self._client_instance is None:
            self._client_instance = lk_api.LiveKitAPI(
                url=self._url,
                api_key=self._api_key,
                api_secret=self._api_secret,
            )
        return self._client_instance

    async def close(self) -> None:
        """Cierra el cliente si es necesario."""
        if self._client_instance:
            try:
                await self._client_instance.aclose()
            except Exception as e:
                logger.debug("Error cerrando LiveKit client: %s", e)
            finally:
                self._client_instance = None

    async def create_ingress(
        self,
        *,
        input_type: int,  # 0=RTMP, 1=WHIP, 2=URL
        name: str,
        room_name: str,
        participant_identity: str,
        participant_name: Optional[str] = None,
        url: Optional[str] = None,  # Required for URL_INPUT
        enable_transcoding: Optional[bool] = None,
    ) -> lk_api.IngressInfo:
        """
        Crea un nuevo punto de ingress.
        
        Args:
            input_type: Tipo de entrada (0=RTMP, 1=WHIP, 2=URL)
            name: Nombre descriptivo del ingress
            room_name: Sala destino del stream
            participant_identity: Identidad del participante en la sala
            participant_name: Nombre visible del participante
            url: URL fuente (requerido solo para URL_INPUT)
            enable_transcoding: Habilitar transcodificación
            
        Returns:
            IngressInfo con URLs de conexión y detalles
        """
        logger.info(
            "Creando ingress: name=%s, room=%s, type=%s, identity=%s",
            name, room_name, input_type, participant_identity
        )
        
        client = await self._get_client()
        
        request_kwargs = {
            "input_type": input_type,
            "name": name,
            "room_name": room_name,
            "participant_identity": participant_identity,
        }
        
        if participant_name:
            request_kwargs["participant_name"] = participant_name
        if url is not None:
            request_kwargs["url"] = url
        if enable_transcoding is not None:
            request_kwargs["enable_transcoding"] = enable_transcoding
            
        try:
            info = await client.ingress.create_ingress(
                lk_api.CreateIngressRequest(**request_kwargs)
            )
            logger.info("Ingress creado: id=%s, url=%s", info.ingress_id, getattr(info, 'url', None))
            return info
        except Exception as e:
            logger.error("Error al crear ingress: %s", e)
            raise

    async def list_ingress(
        self,
        *,
        room_name: Optional[str] = None,
        ingress_id: Optional[str] = None,
    ) -> list:
        """
        Lista los ingress, opcionalmente filtrados por sala o ID.
        """
        logger.info("Listando ingress: room=%s, id=%s", room_name, ingress_id)
        
        client = await self._get_client()
        
        request_kwargs = {}
        if room_name:
            request_kwargs["room_name"] = room_name
        if ingress_id:
            request_kwargs["ingress_id"] = ingress_id
            
        try:
            response = await client.ingress.list_ingress(
                lk_api.ListIngressRequest(**request_kwargs)
            )
            items = list(response.items)
            logger.info("Se encontraron %d ingress", len(items))
            return items
        except Exception as e:
            logger.error("Error al listar ingress: %s", e)
            raise

    async def update_ingress(
        self,
        *,
        ingress_id: str,
        name: Optional[str] = None,
        room_name: Optional[str] = None,
        participant_identity: Optional[str] = None,
        participant_name: Optional[str] = None,
        enable_transcoding: Optional[bool] = None,
    ) -> lk_api.IngressInfo:
        """
        Actualiza la configuración de un ingress existente (debe estar inactivo).
        """
        logger.info("Actualizando ingress: id=%s", ingress_id)
        
        client = await self._get_client()
        
        request_kwargs = {"ingress_id": ingress_id}
        if name is not None:
            request_kwargs["name"] = name
        if room_name is not None:
            request_kwargs["room_name"] = room_name
        if participant_identity is not None:
            request_kwargs["participant_identity"] = participant_identity
        if participant_name is not None:
            request_kwargs["participant_name"] = participant_name
        if enable_transcoding is not None:
            request_kwargs["enable_transcoding"] = enable_transcoding
            
        try:
            info = await client.ingress.update_ingress(
                lk_api.UpdateIngressRequest(**request_kwargs)
            )
            logger.info("Ingress actualizado: id=%s", info.ingress_id)
            return info
        except Exception as e:
            logger.error("Error al actualizar ingress: %s", e)
            raise

    async def delete_ingress(self, *, ingress_id: str) -> lk_api.IngressInfo:
        """
        Elimina un ingress por su ID.
        """
        logger.info("Eliminando ingress: id=%s", ingress_id)
        
        client = await self._get_client()
        
        try:
            info = await client.ingress.delete_ingress(
                lk_api.DeleteIngressRequest(ingress_id=ingress_id)
            )
            logger.info("Ingress eliminado: id=%s", ingress_id)
            return info
        except Exception as e:
            logger.error("Error al eliminar ingress: %s", e)
            raise
