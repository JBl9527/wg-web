import os
import sys
import hashlib
import secrets
import urllib.request
import json
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("WG_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "wg_ui_config.json"
WG_CONF_PATH = Path(os.environ.get("WG_CONF_PATH", "/etc/wireguard/wg0.conf" if sys.platform != "win32" else DATA_DIR / "wg0.conf"))

# WebUI defaults
DEFAULT_WEB_PORT = int(os.environ.get("WEBUI_PORT", "8000"))
DEFAULT_WEB_HOST = os.environ.get("WEBUI_HOST", "0.0.0.0")
SESSION_COOKIE_NAME = "wg_session_token"

# Default Server Settings
DEFAULT_WG_PORT = int(os.environ.get("WG_DEFAULT_PORT", "51820"))
DEFAULT_WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
DEFAULT_WG_SUBNET = os.environ.get("WG_SUBNET", "10.8.0.0/24")
DEFAULT_WG_SERVER_IP = os.environ.get("WG_SERVER_IP", "10.8.0.1")
DEFAULT_WG_DNS = os.environ.get("WG_DNS", "1.1.1.1, 8.8.8.8")
DEFAULT_MTU = 1420
DEFAULT_KEEPALIVE = 25

def hash_password(password: str, salt: str = None) -> str:
    """Hash a password with SHA-256 and salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt:hash."""
    try:
        salt, expected_hash = stored_hash.split(":", 1)
        actual_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
        return secrets.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False

def detect_public_ip() -> str:
    """Attempt to detect public IP address for WireGuard endpoint."""
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com"
    ]
    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                ip = resp.read().decode('utf-8').strip()
                if ip and len(ip.split('.')) == 4:
                    return ip
        except Exception:
            continue
    return "127.0.0.1"
