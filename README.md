# WireGuard WebUI - 现代化 WireGuard Web 管理控制台

一套轻量、高效、功能完整的 WireGuard VPN 可视化 Web 管理系统。专为快速部署、零学习成本管理设计，完美满足端口热修改、在线密钥对生成、手机扫码秒级接入等实用需求。

---

## 🌟 核心特性

- ⚡ **页面直接修改监听端口**
  - 安装完成后，可在 Web 界面直接修改 WireGuard UDP 监听端口（如从 `51820` 切换到 `443` 或 `51821`）。
  - 服务端动态热生效，无需重启宿主机，新生成的所有客户端配置与二维码自动同步为新端口。
- 🔑 **Curve25519 密钥对在线生成**
  - 在线一键生成标准 Curve25519 客户端私钥（Private Key）与公钥（Public Key）。
  - 支持手动输入私钥自动推导公钥，支持一键生成后量子预共享密钥（PSK）。
  - 内置独立“密钥对工具箱”，方便随时生成和测试 WireGuard 密钥。
- 📱 **一键生成手机连接二维码**
  - 填写客户端信息后点击“保存并生成二维码”，立刻弹出高清二维码。
  - 打开手机官方 **WireGuard App**（iOS / Android），选择“扫描二维码”对准屏幕扫码，一秒即可成功连接！
  - 提供 `.conf` 配置文件一键下载与纯文本复制。
- 📊 **实时流量与握手监控**
  - 实时监控客户端握手时间（如“刚刚”、“2分钟前”、“从未连接”）。
  - 自动统计上传/下载吞吐量（KB / MB / GB 动态换算）。
  - 在线状态呼吸灯指示（3分钟内握手自动点亮绿色呼吸灯）。
- ⏯️ **客户端一键启用 / 停用**
  - 支持临时禁用某个客户端，内核级断开且不影响其他用户，再次启用无需重新配置。
- 🛡️ **安全与多平台驱动**
  - 内置管理员身份验证（默认账号 `admin`，初始密码 `admin`，支持页面修改密码）。
  - Linux 环境下直接驱动内核级 WireGuard 与 iptables NAT 转发规则。
  - 包含跨平台模拟/开发驱动模式，Windows/macOS 环境下免安装 WireGuard 内核也可完整测试和体验前端管理流程。

---

## 🚀 两种安装部署方式

你可以根据使用习惯选择 **直接安装（Linux 宿主机原生运行）** 或 **Docker 容器化部署**：

---

### 方案 A：直接安装（推荐，性能最高且无需 Docker）

直接部署在 Linux 宿主机上，由 Systemd 守护进程管理，原生驱动 Linux 内核 WireGuard 模块，支持页面直接热切换端口。

#### 1. 一键脚本安装（支持 Ubuntu / Debian / CentOS / Rocky / AlmaLinux）

在服务器终端中执行：

```bash
# 方式一：克隆仓库并执行安装
git clone https://github.com/JBl9527/wg-web.git /opt/wireguard-webui
cd /opt/wireguard-webui
chmod +x install.sh
sudo ./install.sh
```

或者使用单行命令一键拉取执行：
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/JBl9527/wg-web/main/install.sh)"
```

> **一键脚本自动处理：**
> - 安装 `wireguard`、`wireguard-tools`、`iptables`、`python3` 及依赖；
> - 开启 Linux 内核转发 (`net.ipv4.ip_forward = 1`)；
> - 自动创建 Python 独立虚拟环境，隔绝系统环境污染；
> - 注册并开机自启 Systemd 系统服务 `wg-webui.service`；
> - 自动配置防火墙规则放行对应端口。

#### 2. 直接安装的管理命令

| 操作 | 对应命令 |
| :--- | :--- |
| **查看运行状态** | `systemctl status wg-webui` |
| **查看实时日志** | `journalctl -u wg-webui -f` |
| **重启 Web 服务** | `systemctl restart wg-webui` |
| **停止 Web 服务** | `systemctl stop wg-webui` |
| **启动 Web 服务** | `systemctl start wg-webui` |

---

### 方案 B：Docker 容器化部署

如果你习惯使用 Docker 管理服务器服务，可通过 Docker 或 Docker Compose 秒级启动。

#### 1. 使用 Docker Compose 部署（推荐）

```bash
# 1. 克隆代码
git clone https://github.com/JBl9527/wg-web.git
cd wg-web

# 2. 启动容器
docker compose up -d
```

> **💡 关于网络模式：**
> 项目默认配置为 `network_mode: host`。
> - **优势**：容器直接与宿主机网络栈共享，**在 Web 界面随时修改 WireGuard 监听端口（如从 51820 改为 51825）后立即在宿主机生效**，无需重新映射 Docker 端口或重启容器；同时享受 100% 原生内核数据包吞吐速度。

#### 2. 使用 Docker CLI 单行命令运行

```bash
docker run -d \
  --name wireguard-webui \
  --restart unless-stopped \
  --network host \
  --cap-add NET_ADMIN \
  --cap-add SYS_MODULE \
  -v $(pwd)/data:/app/data \
  -v /etc/wireguard:/etc/wireguard \
  -v /lib/modules:/lib/modules:ro \
  -e WEBUI_PORT=8000 \
  -e WEBUI_HOST=0.0.0.0 \
  -e WG_DEFAULT_PORT=51820 \
  $(docker build -q .)
```

#### 3. Docker 常用管理命令

```bash
# 查看运行日志
docker compose logs -f

# 重启容器
docker compose restart

# 停止并移除容器
docker compose down
```

---

### 访问方式

安装成功后，打开浏览器访问：
```text
http://<你的服务器公网IP>:8000
默认管理员账号: admin
默认初始密码  : admin  (登录后请在右上角及时修改)
```

---

## 📖 详细使用指南

### 1. 修改 WireGuard 监听端口

1. 登录 Web 管理界面；
2. 在顶部仪表盘中的 **"WireGuard 监听端口"** 卡片右上角，点击 **"⚡ 修改端口"**（或进入右上角“服务端设置”）；
3. 输入新的 UDP 端口号（例如 `51825`），点击 **"立即保存并生效"**；
4. WireGuard 接口将动态平滑切换至新端口，所有新生成的客户端配置与二维码均自动使用该新端口。

> ⚠️ **注意：** 修改端口后，请确保云服务器厂商安全组（阿里云/腾讯云/华为云/AWS 等）或本地防火墙已放行该 UDP 端口。

---

### 2. 在线生成密钥对与添加客户端

1. 点击界面中的 **"➕ 添加客户端"** 按钮；
2. 输入设备名称（例如 `iPhone 16 Pro`）；
3. 点击 **"⚡ 在线一键生成密钥对"**，系统将自动利用安全的 Curve25519 算法生成客户端私钥与公钥；
4. 系统已自动推荐下一个空闲内网 IP（如 `10.8.0.2`、`10.8.0.3`）；
5. 路由模式支持快捷切换：
   - **全局代理模式** (`0.0.0.0/0, ::/0`)：手机所有流量均走 VPN 加密加速；
   - **局域网分流模式** (`10.8.0.0/24`)：仅访问 VPN 内网资源，外网直连。

---

### 3. 手机扫码一键连接

1. 在添加客户端弹窗中，点击绿色按钮 **"✨ 保存并立即生成二维码"**（或在客户端列表右侧点击 **"📱 二维码"** 按钮）；
2. 页面正中央将渲染出高清晰度的连接二维码；
3. **手机端操作：**
   - 打开手机上安装的 **WireGuard 官方 App**（App Store 或 Google Play 搜索 WireGuard 免费安装）；
   - 点击 App 右上角 **"+"** 号图标；
   - 选择 **"扫描二维码" (Create from QR code)**；
   - 对准电脑屏幕上的二维码扫描；
   - 随意见输入一个隧道名称（例如 `MyVPS`），点击保存并允许添加 VPN 配置；
   - 打开连接开关，手机即刻安全连入 VPN！

---

## 🛠️ 项目结构

```text
wireguard-webui/
├── app/
│   ├── __init__.py
│   ├── api.py              # FastAPI 路由控制器 (端口修改, 密钥生成, 二维码, Peers管理)
│   ├── config.py           # 配置与环境变量、公网IP探测、密码哈希
│   ├── crypto.py           # Curve25519 密钥对生成、公钥推导与 PSK 模块
│   ├── storage.py          # 客户端配置持久化与 wg0.conf / 客户端 .conf 生成
│   ├── wg_manager.py       # WireGuard 内核工具交互控制器与状态解析
│   └── static/             # 纯前端现代化单页面应用
│       ├── index.html      # 主界面与功能弹窗
│       ├── css/style.css   # 深浅主题、状态指示灯、响应式排版样式
│       └── js/
│           ├── app.js      # 前端交互与实时轮询
│           └── qrcode.min.js # 高性能本地离线二维码渲染引擎
├── data/                   # 持久化数据目录
├── install.sh              # Linux 系统一键安装与服务配置脚本
├── uninstall.sh            # Linux 系统完全卸载清理脚本
├── wg-webui.service        # Systemd 服务单元文件
├── Dockerfile              # Docker 镜像构建文件
├── docker-compose.yml      # Docker Compose 编排文件
├── requirements.txt        # Python 依赖清单
├── run.py                  # 应用启动主入口
└── README.md               # 项目使用说明文档
```

---

## 🗑️ 完全卸载指南

如果你不再需要使用该程序，可按以下方式完全清理卸载：

### 1. 直接安装方式的完全卸载

#### 方式 A：一键自动化卸载脚本（最简单、最干净）

在服务器终端中执行：

```bash
# 进入安装目录执行卸载脚本
cd /opt/wireguard-webui
sudo ./uninstall.sh
```

或者使用网络单行命令直接彻底卸载：
```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/JBl9527/wg-web/main/uninstall.sh)"
```

> **自动化卸载将自动完成：**
> - 停止并禁用 `wg-webui.service` 系统服务并注销；
> - 关闭 WireGuard `wg0` 接口并自动回滚清理 iptables NAT 转发规则；
> - 删除 `/opt/wireguard-webui` 程序源码与 Python 虚拟环境；
> - 清理 `/etc/wireguard/wg0.conf` 及内核转发配置文件；
> - 自动清理关闭 UFW 或 Firewalld 防火墙中放行的端口（8000 与 51820）。

#### 方式 B：手动逐步卸载命令（按需逐条核对）

```bash
# 1. 停止并注销守护服务
sudo systemctl stop wg-webui
sudo systemctl disable wg-webui
sudo rm -f /etc/systemd/system/wg-webui.service
sudo systemctl daemon-reload

# 2. 关闭并清理 WireGuard 网络接口与 NAT 规则
sudo wg-quick down wg0 2>/dev/null || true

# 3. 删除程序文件与配置文件
sudo rm -rf /opt/wireguard-webui
sudo rm -f /etc/wireguard/wg0.conf
sudo rm -f /etc/sysctl.d/99-wireguard-forward.conf

# 4. 清理防火墙端口（根据你启用的防火墙选其一）
# 若使用 UFW:
sudo ufw delete allow 8000/tcp
sudo ufw delete allow 51820/udp

# 若使用 Firewalld:
sudo firewall-cmd --permanent --remove-port=8000/tcp
sudo firewall-cmd --permanent --remove-port=51820/udp
sudo firewall-cmd --reload
```

---

### 2. Docker 部署方式的完全卸载

进入项目所在目录，执行以下清理命令即可彻底删除容器、网络、镜像与数据卷：

```bash
# 1. 进入项目目录
cd wg-web

# 2. 停止并删除容器、数据卷与构建的本地镜像
docker compose down -v --rmi all

# 3. （可选）清理挂载到宿主机的数据与配置文件
sudo rm -rf ./data
sudo rm -f /etc/wireguard/wg0.conf
```

---

## 🔒 常用维护命令

| 操作 | 对应命令 |
| :--- | :--- |
| **查看服务状态** | `systemctl status wg-webui` |
| **查看实时日志** | `journalctl -u wg-webui -f` |
| **重启 Web 服务** | `systemctl restart wg-webui` |
| **查看 WireGuard 内核状态** | `wg show` |
| **查看 NAT 转发规则** | `iptables -t nat -L -n -v` |
| **完全卸载清理** | `sudo ./uninstall.sh` |

---

## 📜 开源协议

本项目基于 MIT License 协议开源，欢迎自由使用与定制。
