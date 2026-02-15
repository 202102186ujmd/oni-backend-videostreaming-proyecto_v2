# Routers/ingress_router.py
"""
Router para gestión de Ingress en LiveKit.
Expone endpoints REST para crear, listar, actualizar y eliminar ingress (RTMP, WHIP, URL).
"""
from __future__ import annotations
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field, field_validator
from livekit import api as lk_api
from Services.livekit_ingress import LiveKitIngressService
from auth.basic_auth import verify_basic_auth


router = APIRouter(
    prefix="/ingress",
    tags=["ingress"],
    dependencies=[Depends(verify_basic_auth)]
)


# Dependency: obtiene singleton desde main
def get_ingress_service() -> LiveKitIngressService:
    from main import get_ingress_service as get_service
    return get_service()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class IngressCreateRequest(BaseModel):
    """Request model para crear un nuevo ingress."""
    input_type: Literal["rtmp", "whip", "url"] = Field(
        ...,
        description="Tipo de entrada: 'rtmp', 'whip', o 'url'"
    )
    name: str = Field(..., min_length=1, description="Nombre descriptivo del ingress")
    room_name: str = Field(..., min_length=1, description="Sala destino del stream")
    participant_identity: str = Field(..., min_length=1, description="Identidad del participante")
    participant_name: Optional[str] = Field(None, description="Nombre visible del participante")
    url: Optional[str] = Field(None, description="URL fuente (requerido para type='url')")
    enable_transcoding: Optional[bool] = Field(None, description="Habilitar transcodificación")

    @field_validator("url")
    @classmethod
    def validate_url_for_type(cls, v, info):
        """Valida que url esté presente cuando input_type es 'url'."""
        # Note: info.data is used in Pydantic v2 to access other fields
        if hasattr(info, 'data') and info.data.get('input_type') == 'url' and not v:
            raise ValueError("url es requerido cuando input_type es 'url'")
        return v


class IngressUpdateRequest(BaseModel):
    """Request model para actualizar un ingress existente."""
    name: Optional[str] = Field(None, min_length=1, description="Nuevo nombre")
    room_name: Optional[str] = Field(None, min_length=1, description="Nueva sala destino")
    participant_identity: Optional[str] = Field(None, min_length=1, description="Nueva identidad")
    participant_name: Optional[str] = Field(None, description="Nuevo nombre visible")
    enable_transcoding: Optional[bool] = Field(None, description="Cambiar transcodificación")


class IngressInfoResponse(BaseModel):
    """Response model con información de un ingress."""
    ingress_id: str
    name: str
    room_name: str
    participant_identity: str
    participant_name: Optional[str] = None
    input_type: int
    url: Optional[str] = None
    stream_key: Optional[str] = None
    status: Optional[dict] = None

    class Config:
        from_attributes = True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def map_input_type_to_int(input_type: str) -> int:
    """
    Mapea string input type a integer enum value.
    
    - "rtmp" -> 0 (IngressInput.RTMP_INPUT)
    - "whip" -> 1 (IngressInput.WHIP_INPUT)
    - "url" -> 2 (IngressInput.URL_INPUT)
    """
    mapping = {
        "rtmp": 0,
        "whip": 1,
        "url": 2,
    }
    return mapping[input_type.lower()]


def info_to_response(info: lk_api.IngressInfo) -> IngressInfoResponse:
    """Convierte IngressInfo del SDK a modelo de respuesta."""
    # Extract status information safely
    status_dict = None
    if hasattr(info, 'state') and info.state:
        status_dict = {
            "status": getattr(info.state, "status", None),
            "error": getattr(info.state, "error", None),
            "started_at": getattr(info.state, "started_at", None),
            "ended_at": getattr(info.state, "ended_at", None),
        }
    
    return IngressInfoResponse(
        ingress_id=info.ingress_id,
        name=info.name,
        room_name=info.room_name,
        participant_identity=info.participant_identity,
        participant_name=getattr(info, "participant_name", None),
        input_type=info.input_type,
        url=getattr(info, "url", None),
        stream_key=getattr(info, "stream_key", None),
        status=status_dict,
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "",
    response_model=IngressInfoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nuevo ingress",
    description="Crea un punto de ingreso RTMP, WHIP o URL para streaming hacia una sala LiveKit."
)
async def create_ingress_endpoint(
    payload: IngressCreateRequest,
    service: LiveKitIngressService = Depends(get_ingress_service)
):
    """
    Crea un nuevo ingress para recibir streams externos.
    
    - **RTMP**: Para OBS Studio u otras herramientas de streaming
    - **WHIP**: Para WebRTC ingress (navegadores, apps)
    - **URL**: Para pull de streams desde una URL externa
    """
    try:
        input_type_int = map_input_type_to_int(payload.input_type)
        
        info = await service.create_ingress(
            input_type=input_type_int,
            name=payload.name,
            room_name=payload.room_name,
            participant_identity=payload.participant_identity,
            participant_name=payload.participant_name,
            url=payload.url,
            enable_transcoding=payload.enable_transcoding,
        )
        
        return info_to_response(info)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "",
    response_model=List[IngressInfoResponse],
    summary="Listar todos los ingress",
    description="Obtiene una lista de todos los ingress configurados."
)
async def list_ingress_endpoint(
    service: LiveKitIngressService = Depends(get_ingress_service)
):
    """Lista todos los ingress sin filtros."""
    try:
        items = await service.list_ingress()
        return [info_to_response(item) for item in items]
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{room_name}",
    response_model=List[IngressInfoResponse],
    summary="Listar ingress por sala",
    description="Obtiene todos los ingress asociados a una sala específica."
)
async def list_ingress_by_room_endpoint(
    room_name: str = Path(..., min_length=1, description="Nombre de la sala"),
    service: LiveKitIngressService = Depends(get_ingress_service)
):
    """Lista ingress filtrados por nombre de sala."""
    try:
        items = await service.list_ingress(room_name=room_name)
        return [info_to_response(item) for item in items]
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/{ingress_id}",
    response_model=IngressInfoResponse,
    summary="Actualizar un ingress",
    description="Actualiza la configuración de un ingress existente. El ingress debe estar inactivo."
)
async def update_ingress_endpoint(
    ingress_id: str = Path(..., min_length=1, description="ID del ingress a actualizar"),
    payload: IngressUpdateRequest = ...,
    service: LiveKitIngressService = Depends(get_ingress_service)
):
    """
    Actualiza un ingress existente.
    
    Nota: El ingress debe estar inactivo para poder ser actualizado.
    Solo se actualizan los campos proporcionados en el request.
    """
    try:
        info = await service.update_ingress(
            ingress_id=ingress_id,
            name=payload.name,
            room_name=payload.room_name,
            participant_identity=payload.participant_identity,
            participant_name=payload.participant_name,
            enable_transcoding=payload.enable_transcoding,
        )
        return info_to_response(info)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/{ingress_id}",
    response_model=IngressInfoResponse,
    summary="Eliminar un ingress",
    description="Elimina un ingress por su ID."
)
async def delete_ingress_endpoint(
    ingress_id: str = Path(..., min_length=1, description="ID del ingress a eliminar"),
    service: LiveKitIngressService = Depends(get_ingress_service)
):
    """
    Elimina un ingress permanentemente.
    
    El ingress será removido y ya no podrá recibir streams.
    """
    try:
        info = await service.delete_ingress(ingress_id=ingress_id)
        return info_to_response(info)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
