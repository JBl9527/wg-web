import json
import uuid
import ipaddress
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from app.config import (
    CONFIG_FILE,
    DEFAULT_WG_PORT,
    DEFAULT_WG_INTERFACE,
    DEFAULT_WG_SERVER_IP,
    DEFAULT_WG_DNS,
    DEFAULT_MTU,
    DEFAULT_KEEPALIVE,
    detect_public_ip,
    hash_password,
    verify_password
)
from app.crypto import generate_keypair, derive_public_key


class StorageManager:
    """Manages persistent JSON storage for WireGuard WebUI state, server config, and peers."""

    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load configuration from JSON or initialize with defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[Storage] Warning: Failed to read {self.config_path}: {e}, initializing defaults.")
                self._initialize_defaults()
        else:
            self._initialize_defaults()
            self.save()

    def _initialize_defaults(self) -> None:
        """Initialize initial default server settings and empty peer list."""
        server_keys = generate_keypair()
        detected_ip = detect_public_ip()

        self.data = {
            "server": {
                "interface": DEFAULT_WG_INTERFACE,
                "listen_port": DEFAULT_WG_PORT,
                "server_private_key": server_keys["private_key"],
                "server_public_key": server_keys["public_key"],
                "address": f"{DEFAULT_WG_SERVER_IP}/24",
                "endpoint_host": detected_ip,
                "dns": DEFAULT_WG_DNS,
                "mtu": DEFAULT_MTU,
                "persistent_keepalive": DEFAULT_KEEPALIVE,
                "post_up": "iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE",
                "post_down": "iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE"
            },
            "auth": {
                "username": "admin",
                # default password: admin
                "password_hash": hash_password("admin"),
                "auth_enabled": True
            },
            "peers": []
        }

    def save(self) -> None:
        """Atomically persist current data state to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.config_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(self.config_path)

    # ---------------- Auth methods ---------------- #
    def verify_login(self, username: str, password: str) -> bool:
        auth = self.data.get("auth", {})
        if not auth.get("auth_enabled", True):
            return True
        if username != auth.get("username", "admin"):
            return False
        return verify_password(password, auth.get("password_hash", ""))

    def change_password(self, old_password: str, new_password: str) -> bool:
        if not self.verify_login(self.data.get("auth", {}).get("username", "admin"), old_password):
            return False
        self.data["auth"]["password_hash"] = hash_password(new_password)
        self.save()
        return True

    # ---------------- Server Config methods ---------------- #
    def get_server_config(self) -> Dict[str, Any]:
        """Return server configuration dictionary."""
        return self.data.get("server", {})

    def update_server_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update server configuration (e.g. listen_port, endpoint_host, address, etc.)"""
        server = self.data.setdefault("server", {})

        allowed_fields = [
            "listen_port", "endpoint_host", "address", "dns",
            "mtu", "persistent_keepalive", "post_up", "post_down",
            "server_private_key", "server_public_key"
        ]

        old_port = server.get("listen_port")
        for key in allowed_fields:
            if key in updates and updates[key] is not None:
                if key == "listen_port":
                    val = int(updates[key])
                    if not (1 <= val <= 65535):
                        raise ValueError("Port must be between 1 and 65535")
                    server[key] = val
                elif key == "server_private_key":
                    # Derive public key automatically if private key updated
                    priv = updates[key].strip()
                    server["server_private_key"] = priv
                    server["server_public_key"] = derive_public_key(priv)
                elif key == "server_public_key":
                    # if private key wasn't provided directly
                    if "server_private_key" not in updates:
                        server["server_public_key"] = updates[key].strip()
                else:
                    server[key] = updates[key]

        self.save()
        return server

    # ---------------- Peer methods ---------------- #
    def get_peers(self) -> List[Dict[str, Any]]:
        return self.data.get("peers", [])

    def get_peer_by_id(self, peer_id: str) -> Optional[Dict[str, Any]]:
        for peer in self.data.get("peers", []):
            if peer.get("id") == peer_id:
                return peer
        return None

    def get_peer_by_public_key(self, public_key: str) -> Optional[Dict[str, Any]]:
        for peer in self.data.get("peers", []):
            if peer.get("public_key") == public_key:
                return peer
        return None

    def get_next_available_ip(self) -> str:
        """Find the next available client IP address within the server subnet."""
        server_address = self.data.get("server", {}).get("address", "10.8.0.1/24")
        try:
            interface = ipaddress.IPv4Interface(server_address)
            network = interface.network
            server_ip = interface.ip
        except Exception:
            network = ipaddress.IPv4Network("10.8.0.0/24")
            server_ip = ipaddress.IPv4Address("10.8.0.1")

        used_ips = {server_ip}
        for peer in self.data.get("peers", []):
            try:
                pip = ipaddress.IPv4Address(peer.get("ip", "").split("/")[0])
                used_ips.add(pip)
            except Exception:
                continue

        for host in network.hosts():
            if host not in used_ips:
                return str(host)

        raise ValueError("No available IP addresses in subnet")

    def add_peer(self, peer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new peer client.
        Required: public_key, private_key
        Optional: name, ip, preshared_key, allowed_ips, dns
        """
        public_key = str(peer_data.get("public_key") or "").strip()
        private_key = str(peer_data.get("private_key") or "").strip()

        if not public_key and private_key:
            public_key = derive_public_key(private_key)
        elif not public_key and not private_key:
            kp = generate_keypair()
            private_key = kp["private_key"]
            public_key = kp["public_key"]

        # Check for duplicate public key
        if self.get_peer_by_public_key(public_key):
            raise ValueError(f"A peer with this public key already exists: {public_key}")

        ip_addr = str(peer_data.get("ip") or "").strip()
        if not ip_addr:
            ip_addr = self.get_next_available_ip()
        else:
            # Strip CIDR if passed e.g. 10.8.0.2/32 -> 10.8.0.2
            ip_addr = ip_addr.split("/")[0]

        # Check duplicate IP
        for p in self.data.get("peers", []):
            if p.get("ip") == ip_addr:
                raise ValueError(f"IP address {ip_addr} is already assigned to peer '{p.get('name')}'")

        server = self.data.get("server", {})
        now = datetime.now().isoformat()
        peer_id = str(uuid.uuid4())

        psk_raw = peer_data.get("preshared_key")
        psk = str(psk_raw).strip() if psk_raw else None

        allowed_ips = str(peer_data.get("allowed_ips") or "0.0.0.0/0, ::/0").strip()
        dns = str(peer_data.get("dns") or server.get("dns", DEFAULT_WG_DNS)).strip()
        name = str(peer_data.get("name") or "").strip() or f"Client-{len(self.data.get('peers', [])) + 1}"
        mtu = int(peer_data.get("mtu") or server.get("mtu", DEFAULT_MTU))
        persistent_keepalive = int(peer_data.get("persistent_keepalive") or server.get("persistent_keepalive", DEFAULT_KEEPALIVE))
        enabled = peer_data.get("enabled", True) if peer_data.get("enabled") is not None else True

        new_peer = {
            "id": peer_id,
            "name": name,
            "ip": ip_addr,
            "public_key": public_key,
            "private_key": private_key,
            "preshared_key": psk,
            "allowed_ips": allowed_ips,
            "dns": dns,
            "mtu": mtu,
            "persistent_keepalive": persistent_keepalive,
            "enabled": enabled,
            "created_at": now,
            "updated_at": now
        }

        self.data.setdefault("peers", []).append(new_peer)
        self.save()
        return new_peer

    def update_peer(self, peer_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing peer."""
        peer = self.get_peer_by_id(peer_id)
        if not peer:
            raise KeyError(f"Peer {peer_id} not found")

        if "name" in updates and updates["name"]:
            peer["name"] = str(updates["name"]).strip()

        if "ip" in updates and updates["ip"]:
            new_ip = str(updates["ip"]).strip().split("/")[0]
            # Check collision
            for p in self.data.get("peers", []):
                if p["id"] != peer_id and p.get("ip") == new_ip:
                    raise ValueError(f"IP address {new_ip} already in use")
            peer["ip"] = new_ip

        if "allowed_ips" in updates and updates["allowed_ips"]:
            peer["allowed_ips"] = str(updates["allowed_ips"]).strip()

        if "dns" in updates and updates["dns"]:
            peer["dns"] = str(updates["dns"]).strip()

        if "enabled" in updates:
            peer["enabled"] = bool(updates["enabled"])

        if "preshared_key" in updates:
            psk = updates["preshared_key"]
            peer["preshared_key"] = psk.strip() if psk else None

        if "private_key" in updates and updates["private_key"]:
            priv = updates["private_key"].strip()
            peer["private_key"] = priv
            peer["public_key"] = derive_public_key(priv)

        peer["updated_at"] = datetime.now().isoformat()
        self.save()
        return peer

    def delete_peer(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Remove a peer by ID."""
        peers = self.data.get("peers", [])
        for i, peer in enumerate(peers):
            if peer.get("id") == peer_id:
                deleted = peers.pop(i)
                self.save()
                return deleted
        return None

    def toggle_peer(self, peer_id: str) -> Dict[str, Any]:
        """Toggle peer enabled / disabled status."""
        peer = self.get_peer_by_id(peer_id)
        if not peer:
            raise KeyError(f"Peer {peer_id} not found")
        peer["enabled"] = not peer.get("enabled", True)
        peer["updated_at"] = datetime.now().isoformat()
        self.save()
        return peer

    # ---------------- WireGuard Config File Generation ---------------- #
    def generate_server_wg_conf(self) -> str:
        """
        Generate full content for /etc/wireguard/wg0.conf
        """
        server = self.data.get("server", {})
        lines = [
            "# Auto-generated by WireGuard WebUI",
            "[Interface]",
            f"Address = {server.get('address', '10.8.0.1/24')}",
            f"ListenPort = {server.get('listen_port', DEFAULT_WG_PORT)}",
            f"PrivateKey = {server.get('server_private_key', '')}",
        ]

        if server.get("post_up"):
            lines.append(f"PostUp = {server.get('post_up')}")
        if server.get("post_down"):
            lines.append(f"PostDown = {server.get('post_down')}")

        lines.append("")

        for peer in self.data.get("peers", []):
            if not peer.get("enabled", True):
                continue
            lines.append(f"# Peer: {peer.get('name', 'Client')}")
            lines.append("[Peer]")
            lines.append(f"PublicKey = {peer.get('public_key')}")
            if peer.get("preshared_key"):
                lines.append(f"PresharedKey = {peer.get('preshared_key')}")
            # Client allowed IP on server is single /32 IP
            lines.append(f"AllowedIPs = {peer.get('ip')}/32")
            lines.append("")

        return "\n".join(lines)

    def generate_client_wg_conf(self, peer_id: str) -> str:
        """
        Generate standard client WireGuard configuration file (.conf)
        This is what gets turned into a QR code for mobile phones!
        """
        peer = self.get_peer_by_id(peer_id)
        if not peer:
            raise KeyError(f"Peer {peer_id} not found")

        server = self.data.get("server", {})

        # Determine endpoint host:port
        # If server listen_port changes, it's immediately reflected here!
        endpoint_host = server.get("endpoint_host", "127.0.0.1")
        listen_port = server.get("listen_port", DEFAULT_WG_PORT)
        endpoint = f"{endpoint_host}:{listen_port}"

        # Subnet mask for client address
        client_address = f"{peer.get('ip')}/24"

        lines = [
            f"# Configuration for {peer.get('name', 'WireGuard Client')}",
            "[Interface]",
            f"PrivateKey = {peer.get('private_key', '')}",
            f"Address = {client_address}",
        ]

        if peer.get("dns"):
            lines.append(f"DNS = {peer.get('dns')}")
        if peer.get("mtu"):
            lines.append(f"MTU = {peer.get('mtu')}")

        lines.append("")
        lines.append("[Peer]")
        lines.append(f"PublicKey = {server.get('server_public_key', '')}")
        if peer.get("preshared_key"):
            lines.append(f"PresharedKey = {peer.get('preshared_key')}")

        lines.append(f"Endpoint = {endpoint}")
        lines.append(f"AllowedIPs = {peer.get('allowed_ips', '0.0.0.0/0, ::/0')}")
        if peer.get("persistent_keepalive"):
            lines.append(f"PersistentKeepalive = {peer.get('persistent_keepalive')}")

        return "\n".join(lines)


# Singleton instance
storage = StorageManager()
