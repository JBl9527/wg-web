#!/usr/bin/env bash
# ==============================================================================
# WireGuard WebUI 一键自动化安装与部署脚本
# 支持系统: Ubuntu / Debian / CentOS / Rocky Linux / AlmaLinux
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN}      WireGuard WebUI 自动化安装向导              ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. 检查是否为 Root 权限
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[错误] 请使用 root 用户或 sudo 执行此脚本！${NC}"
  exit 1
fi

INSTALL_DIR="/opt/wireguard-webui"
WEB_PORT=8000
WG_PORT=51820

# 2. 识别系统发行版并安装基础依赖
echo -e "\n${YELLOW}[1/6] 正在识别系统环境并安装必要依赖...${NC}"
if [ -f /etc/debian_version ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y wireguard wireguard-tools iptables iproute2 curl git python3 python3-pip python3-venv qrencode
elif [ -f /etc/redhat-release ]; then
    yum install -y epel-release || dnf install -y epel-release || true
    yum install -y wireguard-tools iptables iproute curl git python3 python3-pip qrencode || \
    dnf install -y wireguard-tools iptables iproute curl git python3 python3-pip qrencode
else
    echo -e "${RED}[警告] 未识别的 Linux 发行版，尝试使用包管理器安装基础工具...${NC}"
fi

# 3. 开启内核 IPv4 / IPv6 转发 (IP Forwarding)
echo -e "\n${YELLOW}[2/6] 配置并启用 Linux 内核网络转发 (ip_forward)...${NC}"
cat > /etc/sysctl.d/99-wireguard-forward.conf <<EOF
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sysctl -p /etc/sysctl.d/99-wireguard-forward.conf > /dev/null 2>&1 || sysctl -w net.ipv4.ip_forward=1 > /dev/null

# 4. 检测主网卡名称
MAIN_IFACE=$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -n 1)
if [ -z "$MAIN_IFACE" ]; then
    MAIN_IFACE="eth0"
fi
echo -e "   检测到服务器主网卡名称: ${GREEN}${MAIN_IFACE}${NC}"

# 5. 部署应用代码到 /opt/wireguard-webui
echo -e "\n${YELLOW}[3/6] 部署程序文件至 ${INSTALL_DIR}...${NC}"
mkdir -p "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}/data"
mkdir -p /etc/wireguard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
if [ -n "$SCRIPT_DIR" ] && [ -f "${SCRIPT_DIR}/run.py" ]; then
    echo -e "   从本地目录复制应用文件..."
    cp -rf "${SCRIPT_DIR}"/* "${INSTALL_DIR}/" || true
else
    echo -e "   从 GitHub 拉取最新源码..."
    if [ -d "${INSTALL_DIR}/.git" ]; then
        cd "${INSTALL_DIR}" && git pull
    else
        git clone https://github.com/JBl9527/wg-web.git "${INSTALL_DIR}"
    fi
fi

# 6. 配置 Python 虚拟环境与依赖
echo -e "\n${YELLOW}[4/6] 配置 Python 虚拟运行环境与依赖包...${NC}"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

# 7. 配置 Systemd 系统守护进程服务
echo -e "\n${YELLOW}[5/6] 注册并启动 Systemd 系统服务 (wg-webui.service)...${NC}"
cat > /etc/systemd/system/wg-webui.service <<EOF
[Unit]
Description=WireGuard WebUI Management Service
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment="PYTHONUNBUFFERED=1"
Environment="WG_CONF_PATH=/etc/wireguard/wg0.conf"
Environment="WG_DATA_DIR=${INSTALL_DIR}/data"
Environment="WEBUI_PORT=${WEB_PORT}"
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/run.py --host 0.0.0.0 --port ${WEB_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wg-webui.service
systemctl restart wg-webui.service

# 8. 防火墙端口放行 (UFW / Firewalld)
echo -e "\n${YELLOW}[6/6] 配置防火墙策略...${NC}"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    echo -e "   检测到 UFW 防火墙开启，自动放行端口..."
    ufw allow ${WEB_PORT}/tcp comment 'WireGuard WebUI' || true
    ufw allow ${WG_PORT}/udp comment 'WireGuard VPN' || true
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    echo -e "   检测到 Firewalld 开启，自动放行端口..."
    firewall-cmd --permanent --add-port=${WEB_PORT}/tcp || true
    firewall-cmd --permanent --add-port=${WG_PORT}/udp || true
    firewall-cmd --reload || true
fi

# 获取公网 IP
SERVER_IP=$(curl -s -m 3 https://api.ipify.org || curl -s -m 3 https://ifconfig.me || echo "你的服务器公网IP")

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}🎉 WireGuard WebUI 安装完成并已成功运行！${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "🌐 Web 管理端访问地址 : ${BLUE}http://${SERVER_IP}:${WEB_PORT}${NC}"
echo -e "⚡ WireGuard 监听端口 : ${YELLOW}UDP ${WG_PORT}${NC} ${GREEN}(可在网页端直接修改)${NC}"
echo -e "🔑 默认管理员账号     : ${BLUE}admin${NC}"
echo -e "🔒 默认管理员密码     : ${BLUE}admin${NC} (请登录后第一时间点击右上角修改密码)"
echo -e "\n常用管理命令："
echo -e "  查看运行状态 : ${YELLOW}systemctl status wg-webui${NC}"
echo -e "  查看实时日志 : ${YELLOW}journalctl -u wg-webui -f${NC}"
echo -e "  重启管理服务 : ${YELLOW}systemctl restart wg-webui${NC}"
echo -e "  停止管理服务 : ${YELLOW}systemctl stop wg-webui${NC}"
echo -e "${GREEN}======================================================${NC}\n"
