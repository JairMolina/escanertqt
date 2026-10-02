"""Gestor de WebSockets para comunicación en tiempo real entre móviles y monitor."""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app.database.db import get_active_lote, get_stats
from app.services import usuarios

logger = logging.getLogger(__name__)

SEND_TIMEOUT = 3.0  # un cliente lento (celular sin señal) no debe frenar el broadcast a los demás

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Administra conexiones WebSocket concurrentes con soporte de broadcast."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, client_type: str = "desconocido"):
        """Acepta la conexión WebSocket y registra metadatos."""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_metadata[websocket] = {
            "client_type": client_type,
            "connected_at": datetime.now().isoformat(),
        }
        logger.info(
            "Cliente WS conectado (%s). Total conexiones activas: %d",
            client_type,
            len(self.active_connections),
        )

        # Enviar estado inicial al nuevo cliente (si el cliente ya se fue, no dejar la conexión registrada)
        try:
            active_lote = await run_in_threadpool(get_active_lote)
            stats = await run_in_threadpool(get_stats)
            await self.send_personal(
                websocket,
                event_type="CONEXION_ESTABLECIDA",
                data={
                    "mensaje": "Conexión en tiempo real activa con servidor Escaner TQT.",
                    "timestamp": datetime.now().isoformat(),
                    "lote_activo": active_lote,
                    "stats": stats,
                    "total_clientes": len(self.active_connections),
                },
            )
        except BaseException:
            self.disconnect(websocket)
            raise

    def disconnect(self, websocket: WebSocket):
        """Remueve la conexión desconectada."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_metadata:
            del self.connection_metadata[websocket]
        logger.info("Cliente WS desconectado. Conexiones restantes: %d", len(self.active_connections))

    async def broadcast(self, event_type: str, data: Optional[Any] = None):
        """Emite un evento estructurado a todos los clientes conectados."""
        payload = {
            "evento": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }
        message = json.dumps(payload, ensure_ascii=False)

        async def _enviar(connection):
            try:
                await asyncio.wait_for(connection.send_text(message), SEND_TIMEOUT)
                return None
            except Exception as e:  # noqa: BLE001 (incluye timeout de un cliente lento)
                logger.warning("Error enviando broadcast a cliente WS: %s", e)
                return connection

        # En paralelo: un cliente lento o colgado no retrasa a los demás
        resultados = await asyncio.gather(*(_enviar(c) for c in list(self.active_connections)))
        for dead_conn in [r for r in resultados if r is not None]:
            self.disconnect(dead_conn)

    async def send_personal(self, websocket: WebSocket, event_type: str, data: Optional[Any] = None):
        """Envía un mensaje a un cliente específico."""
        payload = {
            "evento": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))

    def count(self) -> int:
        """Número de conexiones activas."""
        return len(self.active_connections)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, client_type: str = "operador"):
    """
    Endpoint principal WebSocket.
    Acepta parámetro query opcional: /ws?client_type=monitor o /ws?client_type=operador.
    """
    origen = websocket.headers.get("origin")
    if origen is not None and urlsplit(origen).netloc.lower() != (websocket.headers.get("host") or "").lower():
        await websocket.close(code=1008)  # otra web intentando escuchar/emitir eventos de la planta (WebSocket entre sitios)
        return
    try:   # sin sesión válida no se acepta ni el apretón de manos: nadie escucha eventos de la planta sin iniciar sesión
        await run_in_threadpool(usuarios.validar_sesion, websocket.cookies.get(usuarios.COOKIE))
    except usuarios.SesionInvalidaError:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, client_type=client_type)
    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
                if not isinstance(msg, dict):
                    await manager.send_personal(websocket, "ACK", {"recibido": ""})
                    continue
                action = str(msg.get("action") or "").upper()

                if action == "PING":
                    await manager.send_personal(websocket, "PONG", {"timestamp": datetime.now().isoformat()})
                elif action == "GET_STATS":
                    stats = await run_in_threadpool(get_stats)
                    await manager.send_personal(websocket, "ESTADISTICAS_ACTUALIZADAS", stats)
                else:  # BROADCAST_SCAN/TARJETA_ESCANEADA ya no existe (SPEC 7.5): un cliente no puede emitir a los demás
                    await manager.send_personal(websocket, "ACK", {"recibido": action})
            except json.JSONDecodeError:
                if raw_text.strip().upper() == "PING":
                    await manager.send_personal(websocket, "PONG", {"timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("Error inesperado en WebSocket: %s", e)
        manager.disconnect(websocket)
