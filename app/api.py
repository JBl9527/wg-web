import io
import time
import secrets
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    SESSION_COOKIE_NAME,
    detect_public_ip
)
from app.crypto import (
    generate_keypair,
    derive_public_key,
    generate_preshared_key,
    validate_key
)
from app.storage import storage
from app.wg_manager import wg_manager

# Active user sessions
active_sessions: Dict[str, float] = {}

app = FastAPI(title="WireGuard WebUI", version="1.0.0")


# ---------------- Schemas ---------------- #
class LoginRequest(BaseModel):
    username: str
    password: str

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

class ServerConfigUpdate(BaseModel):
    listen_port: Optional[int] = Field(None, ge=1, le=65535)
    endpoint_host: Optional[str] = None
    address: Optional[str] = None
    dns: Optional[str] = None
    mtu: Optional[int] = None
    persistent_keepalive: Optional[int] = None
    post_up: Optional[str] = None
    post_down: Optional[str] = None
    server_private_key: Optional[str] = None
    server_public_key: Optional[str] = None

class KeyDeriveRequest(BaseModel):
    private_key: str

class CreatePeerRequest(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    private_key: Optional[str] = None
    public_key: Optional[str] = None
    preshared_key: Optional[str] = None
    allowed_ips: Optional[str] = "0.0.0.0/0, ::/0"
    dns: Optional[str] = None
    mtu: Optional[int] = 1420
    persistent_keepalive: Optional[int] = 25

class UpdatePeerRequest(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    allowed_ips: Optional[str] = None
    dns: Optional[str] = None
    preshared_key: Optional[str] = None
    enabled: Optional[bool] = None

class QRCodeGenRequest(BaseModel):
    content: str


# ---------------- Auth Middleware / Dependency ---------------- #
def get_current_user(request: Request) -> str:
    """Validate session token from cookie or header."""
    auth_enabled = storage.data.get("auth", {}).get("auth_enabled", True)
    if not auth_enabled:
        return "admin"

    token = request.cookies.get(SESSION_COOKIE_NAME) or request.headers.get("X-Session-Token")
    if not token or token not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    # Check expiry (default 7 days)
    if time.time() - active_sessions[token] > 7 * 86400:
        del active_sessions[token]
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired"
        )
    return "admin"


# ---------------- Auth Endpoints ---------------- #
@app.post("/api/auth/login")
def login(creds: LoginRequest, response: Response):
    if not storage.verify_login(creds.username, creds.password):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    token = secrets.token_hex(32)
    active_sessions[token] = time.time()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=7 * 86400,
        httponly=True,
        samesite="lax"
    )
    return {"status": "ok", "message": "Login successful", "token": token}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token and token in active_sessions:
        del active_sessions[token]
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok", "message": "Logged out"}


@app.get("/api/auth/status")
def auth_status(request: Request):
    auth_enabled = storage.data.get("auth", {}).get("auth_enabled", True)
    if not auth_enabled:
        return {"authenticated": True, "username": "admin"}

    token = request.cookies.get(SESSION_COOKIE_NAME) or request.headers.get("X-Session-Token")
    if token and token in active_sessions:
        return {"authenticated": True, "username": storage.data.get("auth", {}).get("username", "admin")}
    return {"authenticated": False}


@app.post("/api/auth/change-password")
def change_password(req: PasswordChangeRequest, user: str = Depends(get_current_user)):
    success = storage.change_password(req.old_password, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="Current password incorrect")
    return {"status": "ok", "message": "Password updated successfully"}


# ---------------- Key Management Endpoints ---------------- #
@app.get("/api/keys/generate")
def api_generate_keypair(user: str = Depends(get_current_user)):
    """Online generation of standard WireGuard Curve25519 keypair and optional PSK."""
    kp = generate_keypair()
    psk = generate_preshared_key()
    return {
        "private_key": kp["private_key"],
        "public_key": kp["public_key"],
        "preshared_key": psk
    }


@app.post("/api/keys/derive")
def api_derive_public_key(req: KeyDeriveRequest, user: str = Depends(get_current_user)):
    """Derive WireGuard public key from a provided private key."""
    try:
        pub = derive_public_key(req.private_key)
        return {"public_key": pub}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------- Server & Port Management Endpoints ---------------- #
@app.get("/api/server")
def get_server_info(user: str = Depends(get_current_user)):
    """Retrieve server configuration and runtime status."""
    server_cfg = storage.get_server_config()
    runtime = wg_manager.get_runtime_status()
    # Mask server private key for security in UI output
    safe_server_cfg = dict(server_cfg)
    if "server_private_key" in safe_server_cfg:
        priv = safe_server_cfg["server_private_key"]
        safe_server_cfg["server_private_key_masked"] = priv[:4] + "..." + priv[-4:] if len(priv) >= 8 else "***"

    return {
        "server": safe_server_cfg,
        "runtime": runtime
    }


@app.put("/api/server")
def update_server_settings(req: ServerConfigUpdate, user: str = Depends(get_current_user)):
    """
    Update server configuration.
    CRITICAL: When `listen_port` is changed, it is immediately updated on the running WireGuard
    interface and written to wg0.conf! All subsequent peer configs automatically reflect the new port.
    """
    updates = req.model_dump(exclude_unset=True)
    if not updates:
        return {"status": "ok", "message": "No changes requested"}

    # If listen_port is being changed
    if "listen_port" in updates and updates["listen_port"] is not None:
        new_port = updates["listen_port"]
        ok, msg = wg_manager.update_listen_port(new_port)
        if not ok:
            raise HTTPException(status_code=500, detail=f"Failed to update listen port: {msg}")

    # Process other fields
    other_updates = {k: v for k, v in updates.items() if k != "listen_port"}
    if other_updates:
        storage.update_server_config(other_updates)
        wg_manager.sync_config_file()

    return {
        "status": "ok",
        "message": f"Server configuration updated successfully. Current port: {storage.get_server_config().get('listen_port')}",
        "server": storage.get_server_config()
    }


@app.post("/api/server/detect-ip")
def api_detect_public_ip(user: str = Depends(get_current_user)):
    """Detect the current public IP of the server."""
    ip = detect_public_ip()
    return {"public_ip": ip}


@app.post("/api/server/restart")
def restart_server(user: str = Depends(get_current_user)):
    """Restart WireGuard interface."""
    ok, msg = wg_manager.restart_interface()
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"status": "ok", "message": msg}


@app.get("/api/server/config-file")
def get_server_config_file(user: str = Depends(get_current_user)):
    """View full server wg0.conf content."""
    conf = storage.generate_server_wg_conf()
    return PlainTextResponse(conf)


# ---------------- Peer Management Endpoints ---------------- #
@app.get("/api/peers")
def list_peers(user: str = Depends(get_current_user)):
    """
    List all peers combined with real-time transfer and handshake stats.
    Also returns the next suggested IP for adding new peers.
    """
    peers = storage.get_peers()
    runtime = wg_manager.get_runtime_status()
    stats_map = runtime.get("peers_stats", {})

    enhanced_peers = []
    for peer in peers:
        p_dict = dict(peer)
        # mask private key
        priv = p_dict.get("private_key", "")
        p_dict["private_key_masked"] = priv[:4] + "..." + priv[-4:] if len(priv) >= 8 else "***"

        pub_key = peer.get("public_key")
        stat = stats_map.get(pub_key, {
            "endpoint": "",
            "latest_handshake": 0,
            "transfer_rx": 0,
            "transfer_tx": 0,
            "is_online": False
        })
        p_dict["runtime_stats"] = stat
        enhanced_peers.append(p_dict)

    # Next suggested IP
    try:
        next_ip = storage.get_next_available_ip()
    except Exception:
        next_ip = ""

    return {
        "peers": enhanced_peers,
        "next_suggested_ip": next_ip,
        "total_peers": len(peers),
        "online_count": runtime.get("online_count", 0)
    }


@app.post("/api/peers")
def create_peer(req: CreatePeerRequest, user: str = Depends(get_current_user)):
    """
    Add a new peer.
    Keys can be auto-generated or passed from online generation.
    """
    try:
        new_peer = storage.add_peer(req.model_dump())
        # Sync runtime WireGuard interface
        wg_manager.add_or_update_peer_runtime(new_peer)

        # Generate client configuration
        client_conf = storage.generate_client_wg_conf(new_peer["id"])

        return {
            "status": "ok",
            "peer": new_peer,
            "config": client_conf,
            "message": f"Peer '{new_peer['name']}' created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/peers/{peer_id}")
def get_peer(peer_id: str, user: str = Depends(get_current_user)):
    peer = storage.get_peer_by_id(peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")
    return peer


@app.put("/api/peers/{peer_id}")
def update_peer(peer_id: str, req: UpdatePeerRequest, user: str = Depends(get_current_user)):
    try:
        updated = storage.update_peer(peer_id, req.model_dump(exclude_unset=True))
        wg_manager.add_or_update_peer_runtime(updated)
        return {"status": "ok", "peer": updated, "message": "Peer updated successfully"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Peer not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/peers/{peer_id}")
def delete_peer(peer_id: str, user: str = Depends(get_current_user)):
    peer = storage.get_peer_by_id(peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")

    deleted = storage.delete_peer(peer_id)
    if deleted:
        wg_manager.remove_peer_runtime(deleted.get("public_key"))

    return {"status": "ok", "message": f"Peer '{peer.get('name')}' deleted successfully"}


@app.post("/api/peers/{peer_id}/toggle")
def toggle_peer(peer_id: str, user: str = Depends(get_current_user)):
    try:
        updated = storage.toggle_peer(peer_id)
        wg_manager.add_or_update_peer_runtime(updated)
        state_str = "启用" if updated.get("enabled") else "禁用"
        return {"status": "ok", "peer": updated, "message": f"Peer '{updated.get('name')}' 已{state_str}"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Peer not found")


@app.get("/api/peers/{peer_id}/config")
def get_peer_config(peer_id: str, user: str = Depends(get_current_user)):
    """Retrieve WireGuard client configuration text."""
    try:
        conf = storage.generate_client_wg_conf(peer_id)
        return PlainTextResponse(conf)
    except KeyError:
        raise HTTPException(status_code=404, detail="Peer not found")


@app.get("/api/peers/{peer_id}/download")
def download_peer_config(peer_id: str, user: str = Depends(get_current_user)):
    """Download .conf configuration file for WireGuard client."""
    peer = storage.get_peer_by_id(peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")

    conf = storage.generate_client_wg_conf(peer_id)
    filename = f"{peer.get('name', 'client')}.conf"

    return Response(
        content=conf,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/peers/{peer_id}/qrcode")
def get_peer_qrcode(peer_id: str, user: str = Depends(get_current_user)):
    """Generate and return PNG QR code directly from server for scanning with mobile."""
    try:
        conf = storage.generate_client_wg_conf(peer_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Peer not found")

    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3
        )
        qr.add_data(conf)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate QR code: {str(e)}")


@app.post("/api/qrcode")
def generate_qrcode_image(req: QRCodeGenRequest, user: str = Depends(get_current_user)):
    """Generate QR code PNG from arbitrary string content."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3
        )
        qr.add_data(req.content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate QR code: {str(e)}")


# ---------------- Mount Static Files & SPA Route ---------------- #
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h3>WireGuard WebUI is initializing...</h3>")
