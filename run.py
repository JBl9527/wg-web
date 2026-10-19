#!/usr/bin/env python3
"""
WireGuard WebUI Launcher Script
"""

import argparse
import sys
import io

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import uvicorn
from app.config import DEFAULT_WEB_HOST, DEFAULT_WEB_PORT
from app.wg_manager import wg_manager
from app.storage import storage


def main():
    parser = argparse.ArgumentParser(description="WireGuard WebUI Server")
    parser.add_argument("--host", type=str, default=DEFAULT_WEB_HOST, help="WebUI bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_WEB_PORT, help="WebUI bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    # Pre-sync WireGuard server configuration on startup
    wg_manager.sync_config_file()

    server_cfg = storage.get_server_config()
    listen_port = server_cfg.get("listen_port", 51820)
    endpoint = f"{server_cfg.get('endpoint_host', '127.0.0.1')}:{listen_port}"

    print("=" * 60)
    print("WireGuard WebUI 正在启动...")
    print(f"Web 管理端访问地址 : http://{args.host}:{args.port}")
    print(f"WireGuard 监听端口 : UDP {listen_port} (可在网页端随时修改)")
    print(f"客户端连接终端地址 : {endpoint}")
    print(f"运行驱动模式       : {'Linux 原生内核驱动' if wg_manager.is_native_available else '模拟开发/跨平台模式'}")
    print(f"默认管理员账号     : admin")
    print(f"默认管理员密码     : admin")
    print("=" * 60)

    uvicorn.run("app.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
