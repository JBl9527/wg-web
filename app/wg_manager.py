import os
import sys
import shutil
import subprocess
import time
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from app.config import WG_CONF_PATH, DEFAULT_WG_INTERFACE
from app.storage import storage


class WireGuardManager:
    """
    Manages interaction with the WireGuard kernel/tools and system configuration.
    Provides live status, port updates, peer sync, and mock/simulation fallback.
    """

    def __init__(self):
        self.interface = storage.get_server_config().get("interface", DEFAULT_WG_INTERFACE)
        self.conf_path = WG_CONF_PATH
        self.is_linux = sys.platform.startswith("linux")
        self.has_wg_bin = shutil.which("wg") is not None
        self.has_wg_quick = shutil.which("wg-quick") is not None
        self._simulated_stats: Dict[str, Dict[str, Any]] = {}

    @property
    def is_native_available(self) -> bool:
        """Returns True if running on Linux with WireGuard tools available and privileged."""
        return self.is_linux and self.has_wg_bin

    def sync_config_file(self) -> Path:
        """
        Generate and write server wg0.conf to disk.
        """
        conf_content = storage.generate_server_wg_conf()
        self.conf_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.conf_path, "w", encoding="utf-8") as f:
            f.write(conf_content)

        # Restrict permissions on Linux
        if self.is_linux:
            try:
                os.chmod(self.conf_path, 0o600)
            except Exception:
                pass

        return self.conf_path

    def update_listen_port(self, new_port: int) -> Tuple[bool, str]:
        """
        Directly update the WireGuard server listen port.
        Applies changes immediately to the running kernel interface and persists to wg0.conf.
        """
        try:
            # 1. Update storage
            storage.update_server_config({"listen_port": new_port})

            # 2. Sync config file
            self.sync_config_file()

            # 3. Apply to active interface if running
            if self.is_native_available and self.is_interface_active():
                cmd = ["wg", "set", self.interface, "listen-port", str(new_port)]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if proc.returncode != 0:
                    return False, f"Failed to set port on running interface: {proc.stderr.strip()}"
                return True, f"Listen port updated to {new_port} and applied dynamically."
            elif not self.is_native_available:
                return True, f"Listen port updated to {new_port} (Simulation/Dev mode)."
            else:
                return True, f"Listen port updated to {new_port} in config (Interface is not currently up)."
        except Exception as e:
            return False, f"Error updating listen port: {str(e)}"

    def add_or_update_peer_runtime(self, peer: Dict[str, Any]) -> Tuple[bool, str]:
        """Dynamically add or update peer in running WireGuard interface without restart."""
        self.sync_config_file()
        if not self.is_native_available or not self.is_interface_active():
            return True, "Config synced (interface not active or simulated)"

        pub_key = peer.get("public_key")
        ip = peer.get("ip")
        psk = peer.get("preshared_key")
        enabled = peer.get("enabled", True)

        if not enabled:
            return self.remove_peer_runtime(pub_key)

        cmd = ["wg", "set", self.interface, "peer", pub_key, "allowed-ips", f"{ip}/32"]
        if psk:
            # write temporary PSK to pipe or file
            # WireGuard accepts preshared-key via temp file
            tmp_psk = Path(f"/tmp/wg_psk_{os.getpid()}.key")
            try:
                tmp_psk.write_text(psk.strip(), encoding="utf-8")
                tmp_psk.chmod(0o600)
                cmd.extend(["preshared-key", str(tmp_psk)])
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            finally:
                if tmp_psk.exists():
                    tmp_psk.unlink()
        else:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if proc.returncode != 0:
            return False, f"Failed to sync peer: {proc.stderr.strip()}"
        return True, "Peer synced"

    def remove_peer_runtime(self, public_key: str) -> Tuple[bool, str]:
        """Dynamically remove peer from running interface."""
        self.sync_config_file()
        if not self.is_native_available or not self.is_interface_active():
            return True, "Config synced"

        cmd = ["wg", "set", self.interface, "peer", public_key, "remove"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            return False, f"Failed to remove peer from interface: {proc.stderr.strip()}"
        return True, "Peer removed"

    def is_interface_active(self) -> bool:
        """Check if wg0 interface is up."""
        if not self.is_native_available:
            return True  # In simulation, report active

        try:
            proc = subprocess.run(["wg", "show", self.interface], capture_output=True, text=True, timeout=3)
            return proc.returncode == 0
        except Exception:
            return False

    def ensure_interface_up(self) -> Tuple[bool, str]:
        """Ensure that the WireGuard interface is started on system boot."""
        if not self.is_native_available:
            return True, "Simulation mode active"

        if not self.is_interface_active():
            self.sync_config_file()
            if self.has_wg_quick:
                try:
                    proc = subprocess.run(["wg-quick", "up", self.interface], capture_output=True, text=True, timeout=10)
                    if proc.returncode == 0:
                        return True, "WireGuard interface automatically started."
                    return False, f"Failed to bring up interface: {proc.stderr.strip()}"
                except Exception as e:
                    return False, str(e)
            return False, "wg-quick not found"
        return True, "WireGuard interface is already active."

    def restart_interface(self) -> Tuple[bool, str]:
        """Restart WireGuard interface (down then up)."""
        self.sync_config_file()
        if not self.is_native_available:
            return True, "WireGuard interface reloaded (Simulated mode)"

        if not self.has_wg_quick:
            return False, "wg-quick utility not found"

        try:
            # Try wg-quick down
            subprocess.run(["wg-quick", "down", self.interface], capture_output=True, text=True, timeout=10)
            time.sleep(1)
            # wg-quick up
            up_proc = subprocess.run(["wg-quick", "up", self.interface], capture_output=True, text=True, timeout=10)
            if up_proc.returncode != 0:
                return False, f"Failed to start WireGuard: {up_proc.stderr.strip()}"
            return True, "WireGuard interface successfully restarted."
        except Exception as e:
            return False, f"Failed to restart WireGuard: {str(e)}"

    def get_runtime_status(self) -> Dict[str, Any]:
        """
        Parse `wg show <interface> dump` to get interface and per-peer real-time stats.
        """
        is_active = self.is_interface_active()
        server_cfg = storage.get_server_config()
        port = server_cfg.get("listen_port", 51820)
        peers_stats: Dict[str, Dict[str, Any]] = {}

        if self.is_native_available and is_active:
            try:
                proc = subprocess.run(["wg", "show", self.interface, "dump"], capture_output=True, text=True, timeout=4)
                if proc.returncode == 0:
                    lines = proc.stdout.strip().split("\n")
                    # First line is interface info:
                    # private_key, public_key, listen_port, fwmark
                    if lines and len(lines) > 0:
                        parts = lines[0].split("\t")
                        if len(parts) >= 3 and parts[2].isdigit():
                            port = int(parts[2])

                    # Subsequent lines are peers:
                    # public_key, preshared_key, endpoint, allowed_ips, latest_handshake, transfer_rx, transfer_tx, persistent_keepalive
                    now_ts = int(time.time())
                    for line in lines[1:]:
                        p_parts = line.split("\t")
                        if len(p_parts) >= 8:
                            pub_k = p_parts[0]
                            endpoint = p_parts[2] if p_parts[2] != "(none)" else ""
                            latest_handshake = int(p_parts[4]) if p_parts[4].isdigit() else 0
                            rx = int(p_parts[5]) if p_parts[5].isdigit() else 0
                            tx = int(p_parts[6]) if p_parts[6].isdigit() else 0

                            # Peer is considered online if last handshake was within 180 seconds (3 mins)
                            is_online = (latest_handshake > 0) and ((now_ts - latest_handshake) < 180)

                            peers_stats[pub_k] = {
                                "endpoint": endpoint,
                                "latest_handshake": latest_handshake,
                                "transfer_rx": rx,
                                "transfer_tx": tx,
                                "is_online": is_online
                            }
            except Exception as e:
                print(f"[WireGuard] Warning: Failed to parse wg show dump: {e}")
        else:
            # Simulation stats for local development / testing
            peers = storage.get_peers()
            for p in peers:
                pub = p.get("public_key")
                peers_stats[pub] = {
                    "endpoint": f"{p.get('ip')}:58231",
                    "latest_handshake": int(time.time()) - 42,
                    "transfer_rx": 1024 * 1024 * 12,
                    "transfer_tx": 1024 * 1024 * 4,
                    "is_online": p.get("enabled", True)
                }

        # Calculate totals
        total_rx = sum(stat["transfer_rx"] for stat in peers_stats.values())
        total_tx = sum(stat["transfer_tx"] for stat in peers_stats.values())
        online_count = sum(1 for stat in peers_stats.values() if stat["is_online"])

        return {
            "interface": self.interface,
            "is_active": is_active,
            "mode": "native" if self.is_native_available else "simulation",
            "listen_port": port,
            "total_rx": total_rx,
            "total_tx": total_tx,
            "online_count": online_count,
            "peers_stats": peers_stats
        }


# Singleton instance
wg_manager = WireGuardManager()
