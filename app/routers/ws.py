from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..auth import decode_session_token
from ..config import settings
from ..tasks import handle_ws_connection

router = APIRouter()


@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    # Authenticate via session cookie
    token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        await websocket.close(code=1008, reason="Not authenticated")
        return

    try:
        data = decode_session_token(token)
    except Exception:
        await websocket.close(code=1008, reason="Invalid session")
        return

    user_id = data["id"]
    await handle_ws_connection(websocket, user_id)
