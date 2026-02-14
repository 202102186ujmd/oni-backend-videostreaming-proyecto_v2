from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from Services.livekit_participants import (
    LiveKitParticipantService,
    ParticipantSummary,
    TokenResult,
    ROLE_EMITTER,
    ROLE_VIEWER,
)
from auth.basic_auth import verify_basic_auth

router = APIRouter(prefix="/participants",
                   tags=["participants"],
                   dependencies=[Depends(verify_basic_auth)]
                   )

# ---------------------- DEPENDENCY -----------------------------
def get_participant_service() -> LiveKitParticipantService:
    return LiveKitParticipantService()

# ---------------------- MODELOS -----------------------------
class TokenRequest(BaseModel):
    room_name: str = Field(..., min_length=1)
    identity: str = Field(..., min_length=1, max_length=128)
    role: Literal[ROLE_EMITTER, ROLE_VIEWER]
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


    @field_validator("role", mode="before")
    def to_lower_role(cls, v: str) -> str:
        return v.lower()

class MultiTokenRequest(BaseModel):
    rooms: List[str] = Field(..., min_items=1)
    identity: str = Field(..., min_length=1, max_length=128)
    role: Literal[ROLE_EMITTER, ROLE_VIEWER]
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    ttl_seconds: Optional[int] = None

    @field_validator("role", mode="before")
    def to_lower_role(cls, v: str) -> str:
        return v.lower()

class TokenResponse(BaseModel):
    status: str
    message: str
    identity: str
    token: str
    expiration_date: datetime

class MultiTokenResponse(BaseModel):
    tokens: Dict[str, TokenResponse]

class ParticipantSummaryResponse(BaseModel):
    room: str
    identity: str
    name: str
    role: str
    is_emitter: bool
    is_viewer: bool

def summary_to_response(summary: ParticipantSummary) -> ParticipantSummaryResponse:
    return ParticipantSummaryResponse(
        room=summary.room,
        identity=summary.identity,
        name=summary.name,
        role=summary.role,
        is_emitter=summary.is_emitter,
        is_viewer=summary.is_viewer,
    )

def token_result_to_response(result: TokenResult) -> TokenResponse:
    return TokenResponse(
        status=result.status,
        message=result.message,
        identity=result.identity,
        token=result.token,
        expiration_date=result.expiration_date,
    )

# ---------------------- ENDPOINTS -----------------------------
@router.post("/token", response_model=TokenResponse, status_code=201)
async def generate_token_endpoint(
    payload: TokenRequest,
    service: LiveKitParticipantService = Depends(get_participant_service),
):
    """
    Genera un token de acceso para un participante en un room específico.
    """
    try:
        token_result = await service.generate_token(**payload.dict())
        return token_result_to_response(token_result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(exc)}")

@router.post("/token/batch", response_model=MultiTokenResponse, status_code=201)
async def generate_tokens_multiple_endpoint(
    payload: MultiTokenRequest,
    service: LiveKitParticipantService = Depends(get_participant_service),
):
    """
    Genera tokens para múltiples rooms.

    - Retorna un diccionario con los tokens generados por room
    """
    try:
        token_results = await service.generate_tokens_for_rooms(**payload.dict())
        
        if not token_results:
            raise HTTPException(
                status_code=404, 
                detail="No se pudieron generar tokens para ninguno de los rooms especificados"
            )
        
        response_tokens = {
            room: token_result_to_response(result) 
            for room, result in token_results.items()
        }
        
        return MultiTokenResponse(tokens=response_tokens)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(exc)}")

#@router.get("", response_model=List[ParticipantSummaryResponse])
async def list_participants_endpoint(
    service: LiveKitParticipantService = Depends(get_participant_service),
):
    """
    Lista todos los participantes activos en todos los rooms.
    """
    try:
        summaries = await service.list_all_active_participants()
        return [summary_to_response(s) for s in summaries]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/{room_name}", response_model=List[ParticipantSummaryResponse])
async def list_room_participants_endpoint(
    room_name: str,
    service: LiveKitParticipantService = Depends(get_participant_service),
):
    """
    Lista todos los participantes activos en un room específico.
    """
    try:
        summaries = await service.list_room_participants(room_name=room_name)
        return [summary_to_response(s) for s in summaries]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.delete("", status_code=204)
async def remove_participant_endpoint(
    room_name: str = Query(..., description="Nombre del room"),
    identity: str = Query(..., description="Identity del participante a remover"),
    service: LiveKitParticipantService = Depends(get_participant_service),
):
    """
    Remueve un participante específico de un room.
    """
    try:
        await service.remove_participant(room_name=room_name, identity=identity)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))