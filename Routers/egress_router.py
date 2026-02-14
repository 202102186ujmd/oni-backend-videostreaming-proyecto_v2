# routers/egress_router.py
from __future__ import annotations
import asyncio
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from livekit import api as lk_api
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from Services.livekit_egress import LiveKitEgressService
from livekit.api.twirp_client import TwirpError
from google.protobuf.json_format import MessageToDict
from auth.basic_auth import verify_basic_auth

router = APIRouter(prefix="/egress",
                   tags=["egress"],
                   dependencies=[Depends(verify_basic_auth)]
                   )

# Dependencia: espera que haya una instancia singleton creada externamente
def get_egress_service() -> LiveKitEgressService:
    return LiveKitEgressService()  # si usas singleton inyectado en app, reemplaza por app.state.service

class RoomRecordRequest(BaseModel):
    room_name: str = Field(..., min_length=1)
    filename: Optional[str] = None

class ParticipantRecordRequest(BaseModel):
    room_name: str = Field(..., min_length=1)
    identity: str = Field(..., min_length=1)

class EmittersRecordRequest(BaseModel):
    room_name: str = Field(..., min_length=1)
    min_tracks: int = Field(default=1, ge=1)

class FullRecordRequest(BaseModel):
    room_name: str = Field(..., min_length=1)

class EgressInfoResponse(BaseModel):
    egress_id: str
    room_name: Optional[str] = None
    status: Optional[int] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None

class EgressParticipantInfoResponse(BaseModel):
    egress_id: str
    identity: Optional[str] = None
    status: Optional[int] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error: Optional[str] = None

class FullRecordResponse(BaseModel):
    room: List[str]
    participants: List[str]

class StopRecordingsRequest(BaseModel):
    room: List[str] = Field(default_factory=list)
    participants: List[str] = Field(default_factory=list)

class StopRecordingsResponse(BaseModel):
    egress_id: str
    status: Optional[int] = None
    error: Optional[str] = None
    message: Optional[str] = None

class EmittersRecordIdsResponse(BaseModel):
    participants: List[str] = Field(default_factory=list)




LOCAL_TZ = ZoneInfo("America/El_Salvador")  # Cambia a tu zona si es necesario

def info_to_response(info: lk_api.EgressInfo) -> EgressInfoResponse:
    started_at = None
    ended_at = None
    try:
        if getattr(info, "started_at", None):
            started_at = datetime.fromtimestamp(info.started_at / 1e9, tz=timezone.utc).astimezone(LOCAL_TZ).isoformat()
        if getattr(info, "ended_at", None):
            ended_at = datetime.fromtimestamp(info.ended_at / 1e9, tz=timezone.utc).astimezone(LOCAL_TZ).isoformat()
    except Exception:
        pass

    return EgressInfoResponse(
        egress_id=info.egress_id,
        room_name=getattr(info, "room_name", None),
        status=getattr(info, "status", None),
        started_at=started_at,
        ended_at=ended_at,
        error=getattr(info, "error", None),
    )

def format_egress_response(info) -> dict:
    """
    Normaliza la respuesta de egress para la API.
    Convierte timestamps nanosegundos a ISO 8601 en zona horaria local.
    """
    started_at = None
    ended_at = None
    try:
        if info.started_at:
            started_at = datetime.fromtimestamp(info.started_at / 1e9, tz=timezone.utc).astimezone(LOCAL_TZ).isoformat()
        if info.ended_at:
            ended_at = datetime.fromtimestamp(info.ended_at / 1e9, tz=timezone.utc).astimezone(LOCAL_TZ).isoformat()
    except Exception:
        pass

    return {
        "status": 200,
        "message": "Grabación iniciada correctamente",
        "room_name": getattr(info, "room_name", None),
        "identity": info.participant.identity if info.participant else None,
        "egress_id": getattr(info, "egress_id", None),
        "started_at": started_at,
        #"ended_at": ended_at,
        "error": getattr(info, "error", ""),
    }




#Inicia la grabacion de un room en especifico
@router.post("/room", 
            response_model=EgressInfoResponse, 
            status_code=status.HTTP_201_CREATED
            )
async def record_room_endpoint(payload: RoomRecordRequest,
                                service: LiveKitEgressService = Depends(get_egress_service)
                                ):
    try:
        info = await service.record_room(room_name=payload.room_name,  filename=payload.filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return format_egress_response(info)

# Inicia la grabacion de un participante de un room en especifico
@router.post("/participant", 
            response_model=EgressParticipantInfoResponse, 
            status_code=status.HTTP_201_CREATED
            )
async def record_participant_endpoint(payload: ParticipantRecordRequest, 
                                        service: LiveKitEgressService = Depends(get_egress_service)
                                        ):
    try:
        info = await service.record_participant(room_name=payload.room_name, identity=payload.identity)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return format_egress_response(info)

# inicia la grabacion de todos los emisores de un room en especifico
@router.post("/emitters", response_model=EmittersRecordIdsResponse, status_code=status.HTTP_201_CREATED)
async def record_emitters_endpoint(payload: EmittersRecordRequest, service: LiveKitEgressService = Depends(get_egress_service)):
    try:
        infos = await service.record_all_emitters(room_name=payload.room_name, min_tracks=payload.min_tracks)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
    egress_ids = [i.egress_id for i in infos]
    return EmittersRecordIdsResponse(participants=egress_ids)

# Inicia la grabacion de Room y todo los emitter de dicho room
@router.post("/full", response_model=FullRecordResponse, 
                    status_code=status.HTTP_201_CREATED
            )
async def full_record_endpoint(payload: FullRecordRequest, service: LiveKitEgressService = Depends(get_egress_service)):
    try:
        result = await service.full_record(room_name=payload.room_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return FullRecordResponse(**result)

# Detiene una grabacion room o participant segun el egress_id
@router.post("/stop", response_model=EgressInfoResponse)
async def stop_recording_endpoint(
    egress_id: str = Query(..., min_length=1), 
    service: LiveKitEgressService = Depends(get_egress_service)
):
    try:
        info = await service.stop_recording(egress_id=egress_id)
        message = "Grabación detenida correctamente"
    except TwirpError as exc:
        if exc.code == "failed_precondition":
            # La grabación ya estaba detenida
            all_recordings = await service.list_recordings()
            existing = next((r for r in all_recordings if r.egress_id == egress_id), None)
            if existing:
                resp = info_to_response(existing)
                resp.message = "La grabación ya estaba finalizada"
                return resp
            else:
                raise HTTPException(status_code=404, detail=f"Egress {egress_id} no encontrado")
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not info:
        raise HTTPException(status_code=404, detail="Egress no encontrado")

    resp = info_to_response(info)
    resp.message = message
    return resp


@router.post("/stop/by-ids", response_model=List[StopRecordingsResponse])
async def stop_recordings_by_ids(
    payload: StopRecordingsRequest,
    service: LiveKitEgressService = Depends(get_egress_service)
):
    """
    Detiene múltiples grabaciones enviando un JSON con room y participants egress_id.
    Continúa aunque alguno falle y reporta error por cada ID.
    """
    all_ids = payload.room + payload.participants
    results: List[StopRecordingsResponse] = []

    async def stop_one(egress_id: str) -> StopRecordingsResponse:
        try:
            info = await service.stop_recording(egress_id=egress_id)
            return StopRecordingsResponse(
                egress_id=egress_id,
                status=info.status,
                message="Grabación detenida correctamente",
            )
        except Exception as exc:
            return StopRecordingsResponse(
                egress_id=egress_id,
                error=str(exc),
            )

    # Ejecutamos todas las detenciones en paralelo
    tasks = [stop_one(eid) for eid in all_ids]
    results = await asyncio.gather(*tasks)
    return results

# Devuleve una lista de las Grabaciones Realizadas
@router.get("", response_model=List[EgressInfoResponse], include_in_schema=False)
async def list_recordings_endpoint(service: LiveKitEgressService = Depends(get_egress_service)):
    try:
        infos = await service.list_recordings()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return [info_to_response(i) for i in infos]


# Devuelve una lista de la grabaciones segun el room
@router.get("/list/by-room/{room_name}", include_in_schema=False)
async def list_recordings_by_room_endpoint(
    room_name: str,
    active_only: bool = False,
    service: LiveKitEgressService = Depends(get_egress_service),
):
    try:
        items = await service.list_recordings_by_room(
            room_name=room_name,
            active_only=active_only
        )

        cleaned = []

        for item in items:
            data = MessageToDict(item, preserving_proto_field_name=True)

            # -------------------------
            # Obtener el archivo principal
            # -------------------------
            filepath = None
            if "room_composite" in data:
                outputs = data["room_composite"].get("file_outputs", [])
                if outputs:
                    filepath = outputs[0].get("filepath")

            # file_results contiene metadata útil
            file_info = None
            if "file_results" in data and len(data["file_results"]) > 0:
                file_info = data["file_results"][0]
            else:
                file_info = {}

            cleaned.append({
                "egress_id": data.get("egress_id"),
                "room_name": data.get("room_name"),
                "status": data.get("status"),

                # ruta en el bucket
                "file": filepath,

                # URL completa (si existe)
                "url": file_info.get("location"),

                # metadata útil
                "size": file_info.get("size"),
                "duration": file_info.get("duration"),
                "started_at": file_info.get("started_at"),
                "ended_at": file_info.get("ended_at"),
            })

        return cleaned

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


