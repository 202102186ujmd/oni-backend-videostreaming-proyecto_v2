# Services/livekit_room.py
"""
Servicio para gestión de salas LiveKit.
Compatible con livekit-api 1.0.7+
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional
from livekit import api
from config import settings

logger = logging.getLogger(__name__)


class LiveKitRoomService:
    """
    Servicio para gestionar salas de LiveKit.
    
    Operaciones:
    - Crear salas con configuración personalizada
    - Listar salas activas
    - Eliminar salas
    - Actualizar metadatos
    """
    
    def __init__(
        self,
        *,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        # En v1.0.x se usa 'url' en lugar de 'host'
        self._url = url or str(settings.LIVEKIT_URL)
        self._api_key = api_key or settings.LIVEKIT_API_KEY
        self._api_secret = api_secret or settings.LIVEKIT_API_SECRET

    async def _get_client(self) -> api.LiveKitAPI:
        """Crea una instancia del cliente LiveKit API."""
        # En v1.0.x el constructor cambió
        return api.LiveKitAPI(
            url=self._url,
            api_key=self._api_key,
            api_secret=self._api_secret,
        )

    async def create_room(
        self,
        *,
        name: str,
        max_participants: int = 0,
        empty_timeout: int = 300,
    ) -> api.Room:
        """
        Crea una nueva sala en LiveKit.
        
        Args:
            name: Nombre único de la sala
            max_participants: Número máximo de participantes (0 = ilimitado)
            empty_timeout: Segundos antes de eliminar sala vacía
            auto_record: Si se debe grabar automáticamente
            metadata: Metadatos adicionales en formato dict
            
        Returns:
            Objeto Room creado
        """


        logger.info(
            f"Creando sala '{name}' (max_participants={max_participants}, "
            f"empty_timeout={empty_timeout})"
        )
        
        try:
            lk = await self._get_client()
            room = await lk.room.create_room(
                api.CreateRoomRequest(
                    name=name,
                    max_participants=max_participants,
                    empty_timeout=empty_timeout
                )
            )
            await lk.aclose()
            
            logger.info(f"Sala '{name}' creada exitosamente (sid={room.sid})")
            return room
            
        except Exception as e:
            logger.error(f"Error al crear sala '{name}': {e}")
            raise

    async def get_room(self, *, room_name: str) -> Optional[api.Room]:
        """
        Obtiene información de una sala específica.
        
        Args:
            room_name: Nombre de la sala
            
        Returns:
            Objeto Room o None si no existe
        """
        try:
            lk = await self._get_client()
            response = await lk.room.list_rooms(
                api.ListRoomsRequest(names=[room_name])
            )
            await lk.aclose()
            
            return response.rooms[0] if response.rooms else None
                
        except Exception as e:
            logger.error(f"Error al obtener sala '{room_name}': {e}")
            return None

    async def list_rooms(self, *, names: Optional[List[str]] = None) -> List[api.Room]:
        """
        Lista todas las salas activas o filtra por nombres específicos.
        
        Args:
            names: Lista opcional de nombres de salas para filtrar
            
        Returns:
            Lista de objetos Room
        """
        try:
            lk = await self._get_client()
            request = api.ListRoomsRequest()
            if names:
                request.names.extend(names)
                    
            response = await lk.room.list_rooms(request)
            await lk.aclose()
            
            logger.info(f"Se encontraron {len(response.rooms)} sala(s)")
            return list(response.rooms)
            
        except Exception as e:
            logger.error(f"Error al listar salas: {e}")
            raise

    async def update_room_metadata(
        self,
        *,
        room_name: str,
        metadata: Dict[str, Any],
    ) -> api.Room:
        """
        Actualiza los metadatos de una sala existente.
        
        Args:
            room_name: Nombre de la sala
            metadata: Nuevos metadatos (reemplaza los existentes)
            
        Returns:
            Objeto Room actualizado
        """
        try:
            lk = await self._get_client()
            room = await lk.room.update_room_metadata(
                api.UpdateRoomMetadataRequest(
                    room=room_name,
                    metadata=json.dumps(metadata),
                )
            )
            await lk.aclose()
            
            logger.info(f"Metadatos actualizados para sala '{room_name}'")
            return room
            
        except Exception as e:
            logger.error(f"Error al actualizar metadatos de sala '{room_name}': {e}")
            raise

    async def delete_room(self, *, room_name: str) -> None:
        """
        Elimina una sala y desconecta a todos los participantes.
        
        Args:
            room_name: Nombre de la sala a eliminar
        """
        logger.info(f"Eliminando sala '{room_name}'")
        
        try:
            lk = await self._get_client()
            await lk.room.delete_room(
                api.DeleteRoomRequest(room=room_name)
            )
            await lk.aclose()
            
            logger.info(f"Sala '{room_name}' eliminada exitosamente")
            
        except Exception as e:
            logger.error(f"Error al eliminar sala '{room_name}': {e}")
            raise

    async def room_exists(self, *, room_name: str) -> bool:
        """
        Verifica si una sala existe.
        
        Args:
            room_name: Nombre de la sala
            
        Returns:
            True si la sala existe, False en caso contrario
        """
        room = await self.get_room(room_name=room_name)
        return room is not None