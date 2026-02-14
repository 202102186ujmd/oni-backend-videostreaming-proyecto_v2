from __future__ import annotations
import json
from typing import Any, Dict, Iterable, List, Optional
from datetime import datetime, timedelta
from livekit.api.access_token import AccessToken, VideoGrants
from livekit import api as lk_api
from config import settings

ROLE_EMITTER = "emitter"
ROLE_VIEWER = "viewer"

class ParticipantSummary:
    def __init__(self, room: str, identity: str, name: str, role: str):
        self.room = room
        self.identity = identity
        self.name = name
        self.role = role
        self.is_emitter = (role == ROLE_EMITTER)
        self.is_viewer = (role == ROLE_VIEWER)

class TokenResult:
    def __init__(
        self, 
        token: str, 
        identity: str, 
        expiration_date: datetime,
        status: str = "success",
        message: str = "Token generated successfully"
    ):
        self.token = token
        self.identity = identity
        self.expiration_date = expiration_date
        self.status = status
        self.message = message

class LiveKitParticipantService:
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

    async def _get_client(self) -> lk_api.LiveKitAPI:
        """Crea una instancia del cliente LiveKit API."""
        return lk_api.LiveKitAPI(
            url=self._url,
            api_key=self._api_key,
            api_secret=self._api_secret,
        )

    def _build_metadata(
        self,
        *,
        role: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload = {"role": role}
        if extra_metadata:
            payload.update(extra_metadata)
        return json.dumps(payload)

    async def room_exists(self, room_name: str) -> bool:
        """
        Verifica si un room existe en LiveKit consultando la lista de rooms activos.
        """
        lk = await self._get_client()
        try:
            response = await lk.room.list_rooms(
                lk_api.ListRoomsRequest(names=[room_name])
            )
            
            return len(response.rooms) > 0
        except Exception:
            return False
        finally:
            await lk.aclose()

    async def generate_token(
        self,
        *,
        room_name: str,
        identity: str,
        role: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        validate_room: Optional[bool] = False,
    ) -> TokenResult:
        role = role.lower()
        if role not in (ROLE_EMITTER, ROLE_VIEWER):
            raise ValueError(f"Rol desconocido: {role}")



        # Validar siempre que el room exista
        if not await self.room_exists(room_name):
            raise ValueError(f"El room '{room_name}' no existe")


        is_emitter = (role == ROLE_EMITTER)

        grants = VideoGrants(
            room=room_name,
            room_join=True,
            can_subscribe=True,
            can_publish=is_emitter,
            
            
        )

        # Calcular tiempo de expiración (default: 24 horas)
        if ttl_seconds is None:
            ttl_seconds = 86400  # 24 horas por defecto
        
        expiration_date = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        token = (
            AccessToken(api_key=self._api_key, api_secret=self._api_secret)
            .with_identity(identity)
            .with_name(name or identity)
            .with_metadata(self._build_metadata(role=role, extra_metadata=metadata))
            .with_grants(grants)
            .with_ttl(timedelta(seconds=ttl_seconds))
        )

        jwt_token = token.to_jwt()

        return TokenResult(
            token=jwt_token,
            identity=identity,
            expiration_date=expiration_date,
            status="success",
            message="Token generated successfully"
        )

    async def generate_tokens_for_rooms(
        self,
        *,
        rooms: Iterable[str],
        identity: str,
        role: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        validate_room: bool = False,
    ) -> Dict[str, TokenResult]:
        results = {}
        for room in rooms:
            try:
                token_result = await self.generate_token(
                    room_name=room,
                    identity=identity,
                    role=role,
                    name=name,
                    metadata=metadata,
                    ttl_seconds=ttl_seconds,
                    validate_room=validate_room,
                )
                results[room] = token_result
            except ValueError as e:
                # Si el room no existe, continuar con los demás
                continue
        return results

    async def list_all_active_participants(self) -> List[ParticipantSummary]:
        lk = await self._get_client()
        rooms_resp = await lk.room.list_rooms(lk_api.ListRoomsRequest())
        summaries: List[ParticipantSummary] = []
        for room in rooms_resp.rooms:
            participants_resp = await lk.room.list_participants(
                lk_api.ListParticipantsRequest(room=room.name)
            )
            for p in participants_resp.participants:
                summaries.append(
                    ParticipantSummary(
                        room=room.name,
                        identity=p.identity,
                        name=p.name or p.identity,
                        role=self._extract_role(p.metadata) or ROLE_VIEWER,
                    )
                )
        await lk.aclose()
        return summaries

    async def list_room_participants(self, *, room_name: str) -> List[ParticipantSummary]:
        lk = await self._get_client()
        participants_resp = await lk.room.list_participants(
            lk_api.ListParticipantsRequest(room=room_name)
        )
        participants = [
            ParticipantSummary(
                room=room_name,
                identity=p.identity,
                name=p.name or p.identity,
                role=self._extract_role(p.metadata) or ROLE_VIEWER,
            )
            for p in participants_resp.participants
        ]
        await lk.aclose()
        return participants

    @staticmethod
    def _extract_role(metadata_json: str | None) -> Optional[str]:
        if not metadata_json:
            return None
        try:
            d = json.loads(metadata_json)
        except json.JSONDecodeError:
            return None
        role = d.get("role")
        return role.lower() if isinstance(role, str) else None

    async def remove_participant(self, *, room_name: str, identity: str) -> None:
        lk = await self._get_client()
        await lk.room.remove_participant(
            lk_api.RoomParticipantIdentity(room=room_name, identity=identity)
        )
        await lk.aclose()