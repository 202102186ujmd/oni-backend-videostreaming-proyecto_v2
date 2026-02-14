"""
Endpoints para gestionar salas de LiveKit apoyándose en `LiveKitRoomService`.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, conint
from Services.livekit_room import LiveKitRoomService
from livekit import api as lk_api
from auth.basic_auth import verify_basic_auth


router = APIRouter(prefix="/rooms",
                   tags=["rooms"],
                   dependencies=[Depends(verify_basic_auth)]
                   )


def get_room_service() -> LiveKitRoomService:
    return LiveKitRoomService()


# ------------------------------------------------------
#   MODELOS
# ------------------------------------------------------

class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)

    # 0 = ilimitado en LiveKit → máximo permitido
    max_participants: conint(ge=0) = Field(
        0,
        description="Número máximo de participantes (0 = sin límite)")
    # 0 = nunca cerrar → máximo permitido
    empty_timeout: conint(ge=0) = Field(
        0,
        description="Tiempo para cerrar sala al quedar vacía (0 = nunca cierra)")



class RoomResponse(BaseModel):
    room_id: str
    room_name: str
    max_participants: Optional[int] = None
    empty_timeout_second: Optional[int] = None
    creation_time: Optional[str] = None
    num_participants: Optional[int] = None
    num_publishers: Optional[int] = None
    active_recording: Optional[bool] = None


class APIResponse(BaseModel):
    status: int
    message: str
    data: Any


# ------------------------------------------------------
#   HELPERS
# ------------------------------------------------------

def room_to_response(room: lk_api.Room) -> RoomResponse:
    creation_time = getattr(room, "creation_time", None)
    if creation_time is not None:
        try:
            creation_time = datetime.fromtimestamp(creation_time).isoformat()
        except (ValueError, OSError, TypeError):
            creation_time = str(creation_time)

    return RoomResponse(
        room_id=room.sid,
        room_name=room.name,
        max_participants=getattr(room, "max_participants", None),
        empty_timeout_second=getattr(room, "empty_timeout", None),
        creation_time=creation_time,
        num_participants=getattr(room, "num_participants", None),
        num_publishers=getattr(room, "num_publishers", None)
    )


# ------------------------------------------------------
#   POST /rooms
# ------------------------------------------------------

@router.post("", summary="Crear sala", status_code=status.HTTP_201_CREATED)
async def create_room_endpoint(
    payload: RoomCreateRequest,
    service: LiveKitRoomService = Depends(get_room_service),
) -> APIResponse:
    """ Crear una sala especifica para la transmision de video y  audio
    """

    # Validar si la sala ya existe
    rooms = await service.list_rooms()
    for room in rooms:
        if room.name == payload.name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La sala ya existe y está activa"
            )

    # Crear sala nueva
    try:
        room = await service.create_room(
            name=payload.name,
            max_participants=payload.max_participants,
            empty_timeout=payload.empty_timeout
        )
    except lk_api.ApiError as exc:
        raise HTTPException(status_code=exc.status or 500, detail=str(exc))

    return APIResponse(
        status=201,
        message="Sala creada con éxito",
        data=room_to_response(room)
    )


# ------------------------------------------------------
#   GET /rooms
# ------------------------------------------------------

@router.get("", summary="Listar salas activas")
async def list_rooms_endpoint(
    service: LiveKitRoomService = Depends(get_room_service),
) -> APIResponse:

    try:
        rooms = await service.list_rooms()
    except lk_api.ApiError as exc:
        raise HTTPException(status_code=exc.status or 500, detail=str(exc))

    rooms_list = [room_to_response(room) for room in rooms]

    return APIResponse(
        status=200,
        message="Lista de salas activas",
        data=rooms_list
    )


# ------------------------------------------------------
#   DELETE /rooms
# ------------------------------------------------------

@router.delete("/{room_name}", summary="Eliminar sala por nombre")
async def delete_room_endpoint(
    room_name: str,
    service: LiveKitRoomService = Depends(get_room_service),
) -> APIResponse:

    # 1. Verificar si la sala existe antes de eliminarla
    try:
        rooms = await service.list_rooms()
    except lk_api.ApiError as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando salas: {exc}")

    # Buscar la sala por nombre
    room_exists = any(room.name == room_name for room in rooms)

    if not room_exists:
        raise HTTPException(
            status_code=404,
            detail=f"La sala '{room_name}' no existe o ya fue eliminada."
        )

    # 2. Intentar eliminar la sala
    try:
        await service.delete_room(room_name=room_name)
    except lk_api.ApiError as exc:
        raise HTTPException(status_code=exc.status or 500, detail=str(exc))

    return APIResponse(
        status=200,
        message="Sala eliminada con éxito",
        data=None
    )
