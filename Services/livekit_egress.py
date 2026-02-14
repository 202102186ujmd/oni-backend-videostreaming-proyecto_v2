# Services/livekit_egress.py
from __future__ import annotations
import asyncio
from livekit.protocol.egress import EgressInfo
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from sys import prefix
from typing import Dict, Iterable, List, Optional
from uuid import uuid4
from pathlib import PurePosixPath
from datetime import datetime, timezone
from livekit import api as lk_api
from config import settings
from zoneinfo import ZoneInfo
from google.protobuf.json_format import MessageToDict
import asyncio


DEFAULT_FILE_TYPE = lk_api.EncodedFileType.MP4

LOCAL_TZ = ZoneInfo("America/El_Salvador")


class LiveKitEgressService:
    """
    Servicio de egress / grabación para LiveKit.
    Compatible con LiveKit 1.0.19.
    Mantiene batches en memoria y un cliente reutilizable.
    """

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        file_type: lk_api.EncodedFileType = DEFAULT_FILE_TYPE,
    ) -> None:
        self._url = url or str(settings.LIVEKIT_URL)
        self._api_key = api_key or settings.LIVEKIT_API_KEY
        self._api_secret = api_secret or settings.LIVEKIT_API_SECRET
        self._file_type = file_type

        self._logger = logging.getLogger(__name__)
        self._client_instance: Optional[lk_api.LiveKitAPI] = None


    
    # Cliente
    
    async def client(self) -> lk_api.LiveKitAPI:
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
                close_fn = getattr(self._client_instance, "close", None)
                if asyncio.iscoroutinefunction(close_fn):
                    await close_fn()
                elif callable(close_fn):
                    close_fn()
            except Exception as e:
                self._logger.debug("Error cerrando LiveKit client: %s", e)
            finally:
                self._client_instance = None

    
    # Helpers S3 / Archivos
    def _normalize_prefix_and_filename(self, *, filename: str, prefix: Optional[str]) -> (Optional[str], str):
        p = PurePosixPath(filename)
        combined_prefix = "/".join(filter(None, [prefix, str(p.parent)])) if str(p.parent) != "." else prefix
        filename_only = p.name
        if combined_prefix:
            combined_prefix = str(PurePosixPath(combined_prefix))
        return combined_prefix, filename_only

    def _s3_upload(self) -> lk_api.S3Upload:
        """
        Retorna configuración básica de S3/MinIO.
        El path se define en `filepath` de EncodedFileOutput.
        """
        return lk_api.S3Upload(
            access_key=settings.MINIO_ACCESS_KEY,
            secret=settings.MINIO_SECRET_KEY,
            bucket=settings.MINIO_BUCKET_NAME,
            region=settings.MINIO_REGION,
            endpoint=settings.MINIO_ENDPOINT,
            force_path_style=settings.MINIO_FORCE_PATH_STYLE,
        )


    def _file_output(self, *, filename: str, prefix: Optional[str] = None) -> lk_api.EncodedFileOutput:
    # concatenar prefijo + filename en filepath
        if prefix:
            filepath = f"{prefix}/{filename}".replace("//", "/")
        else:
            filepath = filename

        return lk_api.EncodedFileOutput(
            file_type=self._file_type,
            filepath=filepath,
            s3=self._s3_upload(),
        )


    
    # START ROOM RECORDING
    #async def record_room(self, *, room_name: str, layout: Optional[str] = None, file_prefix: Optional[str] = None, filename: Optional[str] = None) -> lk_api.EgressInfo:
    async def record_room(self, *, room_name: str, filename: Optional[str] = None) -> lk_api.EgressInfo:
        layout ="grid"
        file_prefix = "Rooms"
        filename = filename or f"room_{room_name}_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
        self._logger.info("Iniciando room composite: room=%s layout=%s", room_name, layout)
        client = await self.client()
        info = await client.egress.start_room_composite_egress(
            lk_api.RoomCompositeEgressRequest(
                room_name=room_name,
                layout=layout,
                file_outputs=[self._file_output(filename=filename, prefix=file_prefix or room_name)],
            )
        )
        return info

    #Star Participant Record
    async def record_participant(self, *, room_name: str, identity: str) -> lk_api.EgressInfo:
        file_prefix = "Participants"
        filename = f"participant_{identity}_{room_name}_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}.mp4"

        self._logger.info("Iniciando participant egress: room=%s identity=%s", room_name, identity)

        client = await self.client()
        info = await client.egress.start_participant_egress(
            lk_api.ParticipantEgressRequest(
                room_name=room_name,
                identity=identity,
                file_outputs=[self._file_output(filename=filename, prefix=file_prefix or room_name)],
            )
        )
        return info

    async def record_all_emitters(self, *, room_name: str, min_tracks: int = 1) -> List[lk_api.EgressInfo]:
        client = await self.client()
        participants_resp = await client.room.list_participants(lk_api.ListParticipantsRequest(room=room_name))
        tasks = []

        for participant in participants_resp.participants:
            active_tracks = [
                t for t in (participant.tracks or [])
                if (not getattr(t, "muted", False)) and getattr(t, "type", None) in (lk_api.TrackType.AUDIO, lk_api.TrackType.VIDEO)
            ]
            if len(active_tracks) < min_tracks:
                self._logger.debug("Skipping %s tracks(%d) < min(%d)", participant.identity, len(active_tracks), min_tracks)
                continue

            #filename = f"participant_{room_name}_{participant.identity}_{uuid4().hex[:8]}.mp4"
            filename = f"participant_{room_name}_{participant.identity}_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
            tasks.append(client.egress.start_participant_egress(
                lk_api.ParticipantEgressRequest(
                    room_name=room_name,
                    identity=participant.identity,
                    file_outputs=[self._file_output(filename=filename, prefix=room_name)],
                )
            ))

        if not tasks:
            return []
            

        infos = await asyncio.gather(*tasks, return_exceptions=True)
        successful = [i for i in infos if isinstance(i, lk_api.EgressInfo)]
        errors = [e for e in infos if isinstance(e, Exception)]
        if errors:
            self._logger.error("Errores al iniciar egress por participante: %s", errors)

        
        return successful

    
    #--------------------------Metodos para el full record-------------------------------------------------
    async def record_all_emitters2(self, *, room_name: str, min_tracks: int = 1) -> List[lk_api.EgressInfo]:
        client = await self.client()
        participants_resp = await client.room.list_participants(lk_api.ListParticipantsRequest(room=room_name))
        tasks = []

        for participant in participants_resp.participants:
            active_tracks = [
                t for t in (participant.tracks or [])
                if (not getattr(t, "muted", False)) and getattr(t, "type", None) in (lk_api.TrackType.AUDIO, lk_api.TrackType.VIDEO)
            ]
            if len(active_tracks) < min_tracks:
                self._logger.debug("Skipping %s tracks(%d) < min(%d)", participant.identity, len(active_tracks), min_tracks)
                continue

            #filename = f"participant_{room_name}_{participant.identity}_{uuid4().hex[:8]}.mp4"
            filename = f"participant_{room_name}_{participant.identity}_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
            prefix =  f"full/{room_name}_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}"
            tasks.append(client.egress.start_participant_egress(
                lk_api.ParticipantEgressRequest(
                    room_name=room_name,
                    identity=participant.identity,
                    file_outputs=[self._file_output(filename=filename, prefix=prefix)],
                )
            ))

        if not tasks:
            return []
            

        infos = await asyncio.gather(*tasks, return_exceptions=True)
        successful = [i for i in infos if isinstance(i, lk_api.EgressInfo)]
        errors = [e for e in infos if isinstance(e, Exception)]
        if errors:
            self._logger.error("Errores al iniciar egress por participante: %s", errors)

        return successful

    #async def record_room(self, *, room_name: str, layout: Optional[str] = None, file_prefix: Optional[str] = None, filename: Optional[str] = None) -> lk_api.EgressInfo:
    async def record_room2(self, *, room_name: str, file_prefix: Optional[str] = None) -> lk_api.EgressInfo:
        layout ="grid"
        file_prefix = f"full/{room_name}_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}"
        filename = f"room_{room_name}_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
        self._logger.info("Iniciando room composite: room=%s layout=%s", room_name, layout)
        client = await self.client()
        info = await client.egress.start_room_composite_egress(
            lk_api.RoomCompositeEgressRequest(
                room_name=room_name,
                layout=layout,
                file_outputs=[self._file_output(filename=filename ,prefix=file_prefix or room_name)],
            )
        )
        return info

    async def full_record(self, *, room_name: str) -> Dict[str, List[str]]:
        room_task = asyncio.create_task(self.record_room2(room_name=room_name))
        emitters_task = asyncio.create_task(self.record_all_emitters2(room_name=room_name))
        room_info, emitter_infos = await asyncio.gather(room_task, emitters_task)
        return {"room": [room_info.egress_id], "participants": [i.egress_id for i in emitter_infos]}

    
    # STOP RECORDING
    async def stop_recording(self, *, egress_id: str) -> lk_api.EgressInfo:
        client = await self.client()
        stop = await client.egress.stop_egress(lk_api.StopEgressRequest(egress_id=egress_id))
        return stop

    
    # LIST / INFO
    async def list_recordings(self) -> List[lk_api.EgressInfo]:
        client = await self.client()
        resp = await client.egress.list_egress(lk_api.ListEgressRequest())
        return list[EgressInfo](resp.items)
    

    async def list_recordings_by_room(self, *, room_name: str, active_only: bool = False) -> List[lk_api.EgressInfo]:
        client = await self.client()
        req = lk_api.ListEgressRequest(room_name=room_name)
        if active_only:
            req.active = True
        resp = await client.egress.list_egress(req)
        return list(resp.items)

