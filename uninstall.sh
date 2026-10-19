#!/usr/bin/env bash
# ==============================================================================
# WireGuard WebUI 完全卸载清理脚本
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${RED}======================================================${NC}"
echo -e "${RED}         WireGuard WebUI 完全卸载向导                 ${NC}"
echo -e "${RED}======================================================${NC}"

# 1. 检查是否为 Root 权限
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[错误] 请使用 root 用户或 sudo 执行此脚本！${NC}"
  exit 1
fi

INSTALL_DIR="/opt/wireguard-webui"
SERVICE_FILE="/etc/systemd/system/wg-webui.service"
WEB_PORT=8000
WG_PORT=51820

# 交互确认（支持 -y 参数跳过确认）
if [ "$1" != "-y" ] && [ "$1" != "--yes" ]; then
    echo -e "${YELLOW}警告：此操作将彻底停止并删除 WireGuard WebUI 服务、应用文件及相关配置！${NC}"
    read -r -p "确定要继续完全卸载吗？(y/N): " confirm
    if [[ ! "$confirm" =~ ^[yY]$ ]]; then
        echo -e "${GREEN}已取消卸载操作。${NC}"
        exit 0
    fi
fi

# 2. 停止并禁用 Systemd 系统服务
echo -e "\n${YELLOW}[1/5] 停止并注销 Systemd 守护服务...${NC}"
if systemctl is-active --quiet wg-webui.service 2>/dev/null; then
    systemctl stop wg-webui.service
    echo -e "   已停止 wg-webui.service 服务"
fi

if systemctl is-enabled --quiet wg-webui.service 2>/dev/null; then
    systemctl disable wg-webui.service
    echo -e "   已禁用 wg-webui.service 开机自启"
fi

if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl reset-failed 2>/dev/null || true
    echo -e "   已删除系统服务文件: $SERVICE_FILE"
fi

# 3. 停止 WireGuard 接口 (触发 PostDown iptables 规则清理)
echo -e "\n${YELLOW}[2/5] 关闭 WireGuard 网络接口 (wg0)...${NC}"
if command -v wg-quick >/dev/null 2>&1; then
    wg-quick down wg0 2>/dev/null || true
    echo -e "   已关闭 wg0 接口并清理 NAT 转发规则"
fi

# 4. 删除应用目录与配置文件
echo -e "\n${YELLOW}[3/5] 清理程序文件与配置文件...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "   已删除应用目录: $INSTALL_DIR"
fi

# 询问或清理 /etc/wireguard/wg0.conf
if [ -f "/etc/wireguard/wg0.conf" ]; then
    rm -f "/etc/wireguard/wg0.conf"
    echo -e "   已清理 WireGuard 配置文件: /etc/wireguard/wg0.conf"
fi

# 清理 sysctl 转发配置
if [ -f "/etc/sysctl.d/99-wireguard-forward.conf" ]; then
    rm -f "/etc/sysctl.d/99-wireguard-forward.conf"
    echo -e "   已清理 sysctl 转发配置文件"
fi

# 5. 防火墙端口关闭与清理
echo -e "\n${YELLOW}[4/5] 清理防火墙放行规则...${NC}"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw delete allow ${WEB_PORT}/tcp 2>/dev/null || true
    ufw delete allow ${WG_PORT}/udp 2>/dev/null || true
    echo -e "   已移除 UFW 端口规则: ${WEB_PORT}/tcp, ${WG_PORT}/udp"
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --remove-port=${WEB_PORT}/tcp 2>/dev/null || true
    firewall-cmd --permanent --remove-port=${WG_PORT}/udp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    echo -e "   已移除 Firewalld 端口规则: ${WEB_PORT}/tcp, ${WG_PORT}/udp"
fi

echo -e "\n${YELLOW}[5/5] 验证清理状态...${NC}"
# 检查是否还有残留进程
if pgrep -f "run.py" >/dev/null 2>&1; then
    pkill -f "run.py" 2>/dev/null || true
fi

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}🎉 WireGuard WebUI 已完全卸载干净！${NC}"
echo -e "${GREEN}   所有服务、配置、虚拟环境及端口规则均已清理完毕。${NC}"
echo -e "${GREEN}======================================================${NC}\n"
