// WireGuard WebUI Frontend Application Logic

let serverConfig = {};
let runtimeStatus = {};
let peersList = [];
let nextSuggestedIp = "";
let currentViewingConfig = "";
let currentViewingPeer = null;
let qrCodeInstance = null;
let pollTimer = null;

// Format bytes into readable format
function formatBytes(bytes, decimals = 2) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Relative time formatting
function formatRelativeTime(epochSec) {
  if (!epochSec || epochSec === 0) return '从未连接';
  const now = Math.floor(Date.now() / 1000);
  const diff = now - epochSec;
  if (diff < 10) return '刚刚';
  if (diff < 60) return `${diff} 秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

// Toast notification
function showToast(message, type = 'info') {
  const toast = document.getElementById('toastBox');
  const msgEl = document.getElementById('toastMsg');
  const iconEl = document.getElementById('toastIcon');

  const icons = {
    info: 'ℹ️',
    success: '✅',
    error: '❌',
    warning: '⚠️'
  };

  iconEl.textContent = icons[type] || 'ℹ️';
  msgEl.textContent = message;

  toast.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.classList.remove('show');
  }, 3500);
}

// Modal management
function openModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.add('active');
}

function closeModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.remove('active');
}

// Theme management
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('wg_theme', next);
  document.getElementById('themeBtn').textContent = next === 'dark' ? '🌓' : '☀️';
}

function initTheme() {
  const saved = localStorage.getItem('wg_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const themeBtn = document.getElementById('themeBtn');
  if (themeBtn) themeBtn.textContent = saved === 'dark' ? '🌓' : '☀️';
}

// ----------------- Auth API ----------------- //
async function checkAuth() {
  try {
    const res = await fetch('/api/auth/status');
    const data = await res.json();
    if (!data.authenticated) {
      openModal('loginModal');
      return false;
    }
    return true;
  } catch (e) {
    console.error('Auth check error:', e);
    return false;
  }
}

async function submitLogin() {
  const username = document.getElementById('loginUser').value.trim();
  const password = document.getElementById('loginPass').value;

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '登录失败，请检查账号密码', 'error');
      return;
    }
    closeModal('loginModal');
    showToast('登录成功', 'success');
    refreshAll();
  } catch (e) {
    showToast('请求失败，请检查网络连接', 'error');
  }
}

async function handleLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
    showToast('已安全退出', 'info');
    openModal('loginModal');
  } catch (e) {
    location.reload();
  }
}

function openPasswordModal() {
  document.getElementById('oldPwdInput').value = '';
  document.getElementById('newPwdInput').value = '';
  document.getElementById('confirmPwdInput').value = '';
  openModal('passwordModal');
}

async function submitChangePassword() {
  const oldPwd = document.getElementById('oldPwdInput').value;
  const newPwd = document.getElementById('newPwdInput').value;
  const confirmPwd = document.getElementById('confirmPwdInput').value;

  if (!oldPwd || !newPwd) {
    showToast('请输入原密码和新密码', 'warning');
    return;
  }
  if (newPwd !== confirmPwd) {
    showToast('两次输入的新密码不一致', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '修改失败', 'error');
      return;
    }
    closeModal('passwordModal');
    showToast('密码修改成功，请牢记新密码', 'success');
  } catch (e) {
    showToast('请求失败', 'error');
  }
}

// ----------------- Server & Port API ----------------- //
async function loadServerInfo() {
  try {
    const res = await fetch('/api/server');
    if (res.status === 401) {
      openModal('loginModal');
      return;
    }
    const data = await res.json();
    serverConfig = data.server || {};
    runtimeStatus = data.runtime || {};

    // Update UI elements
    const port = runtimeStatus.listen_port || serverConfig.listen_port || 51820;
    document.getElementById('statListenPort').textContent = port;

    const endpoint = `${serverConfig.endpoint_host || '127.0.0.1'}:${port}`;
    document.getElementById('statEndpoint').textContent = endpoint;

    document.getElementById('statSubnet').textContent = serverConfig.address || '10.8.0.1/24';

    const isRunning = runtimeStatus.is_active;
    const statusTextEl = document.getElementById('serverStatusText');
    const dotEl = document.getElementById('serverDot');
    if (isRunning) {
      statusTextEl.textContent = '运行中';
      statusTextEl.style.color = 'var(--success)';
      dotEl.className = 'pulse-dot online';
    } else {
      statusTextEl.textContent = '已停止';
      statusTextEl.style.color = 'var(--danger)';
      dotEl.className = 'pulse-dot offline';
    }

    const modeBadge = document.getElementById('runtimeModeBadge');
    if (runtimeStatus.mode === 'native') {
      modeBadge.textContent = 'Linux 内核驱动';
      modeBadge.className = 'badge badge-success';
    } else {
      modeBadge.textContent = '模拟开发模式';
      modeBadge.className = 'badge badge-warning';
    }

    // Traffic & active count
    const totalRx = runtimeStatus.total_rx || 0;
    const totalTx = runtimeStatus.total_tx || 0;
    document.getElementById('statTraffic').textContent = `↓ ${formatBytes(totalRx)} / ↑ ${formatBytes(totalTx)}`;

    const onlineCount = runtimeStatus.online_count || 0;
    const totalPeers = (peersList || []).length;
    document.getElementById('statPeersCount').textContent = `${onlineCount} / ${totalPeers} 台在线`;

  } catch (e) {
    console.error('Failed to load server info:', e);
  }
}

// Quick Port Change
function openQuickPortModal() {
  const currentPort = serverConfig.listen_port || 51820;
  document.getElementById('quickPortInput').value = currentPort;
  openModal('quickPortModal');
}

async function submitQuickPort() {
  const inputEl = document.getElementById('quickPortInput');
  const newPort = parseInt(inputEl.value, 10);

  if (isNaN(newPort) || newPort < 1 || newPort > 65535) {
    showToast('请输入有效的端口号 (1-65535)', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/server', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ listen_port: newPort })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '端口修改失败', 'error');
      return;
    }

    closeModal('quickPortModal');
    showToast(`端口已成功更改为 ${newPort} 并即时生效！`, 'success');
    await refreshAll();
  } catch (e) {
    showToast('网络请求失败', 'error');
  }
}

// Server Global Settings Modal
function openServerSettingsModal() {
  document.getElementById('settingListenPort').value = serverConfig.listen_port || 51820;
  document.getElementById('settingEndpointHost').value = serverConfig.endpoint_host || '';
  document.getElementById('settingAddress').value = serverConfig.address || '10.8.0.1/24';
  document.getElementById('settingDns').value = serverConfig.dns || '1.1.1.1, 8.8.8.8';
  document.getElementById('settingServerPubKey').value = serverConfig.server_public_key || '';
  document.getElementById('settingMtu').value = serverConfig.mtu || 1420;
  document.getElementById('settingKeepalive').value = serverConfig.persistent_keepalive || 25;
  document.getElementById('settingPostUp').value = serverConfig.post_up || '';
  document.getElementById('settingPostDown').value = serverConfig.post_down || '';

  openModal('serverSettingsModal');
}

async function autoDetectPublicIp() {
  try {
    const res = await fetch('/api/server/detect-ip', { method: 'POST' });
    const data = await res.json();
    if (data.public_ip) {
      document.getElementById('settingEndpointHost').value = data.public_ip;
      showToast(`已检测到公网 IP: ${data.public_ip}`, 'success');
    }
  } catch (e) {
    showToast('探测公网 IP 失败，请手动输入', 'warning');
  }
}

function copyServerPubKey() {
  const pubKey = document.getElementById('settingServerPubKey').value;
  if (!pubKey) return;
  navigator.clipboard.writeText(pubKey);
  showToast('服务端公钥已复制到剪贴板', 'success');
}

async function submitServerSettings() {
  const listenPort = parseInt(document.getElementById('settingListenPort').value, 10);
  const endpointHost = document.getElementById('settingEndpointHost').value.trim();
  const address = document.getElementById('settingAddress').value.trim();
  const dns = document.getElementById('settingDns').value.trim();
  const mtu = parseInt(document.getElementById('settingMtu').value, 10) || 1420;
  const persistent_keepalive = parseInt(document.getElementById('settingKeepalive').value, 10) || 25;
  const post_up = document.getElementById('settingPostUp').value.trim();
  const post_down = document.getElementById('settingPostDown').value.trim();

  if (isNaN(listenPort) || listenPort < 1 || listenPort > 65535) {
    showToast('请输入有效的监听端口 (1-65535)', 'warning');
    return;
  }

  const payload = {
    listen_port: listenPort,
    endpoint_host: endpointHost,
    address: address,
    dns: dns,
    mtu: mtu,
    persistent_keepalive: persistent_keepalive,
    post_up: post_up,
    post_down: post_down
  };

  try {
    const res = await fetch('/api/server', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '保存配置失败', 'error');
      return;
    }
    closeModal('serverSettingsModal');
    showToast('服务端配置保存成功！', 'success');
    await refreshAll();
  } catch (e) {
    showToast('网络请求异常', 'error');
  }
}

async function restartWireGuardInterface() {
  if (!confirm('确定要重启 WireGuard 网络接口吗？这可能会造成瞬间网络闪断。')) return;
  try {
    const res = await fetch('/api/server/restart', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '重启接口失败', 'error');
      return;
    }
    showToast('WireGuard 接口已成功重启！', 'success');
    await refreshAll();
  } catch (e) {
    showToast('请求重启失败', 'error');
  }
}

// ----------------- Peers API & Table Rendering ----------------- //
async function loadPeers(showNotice = false) {
  try {
    const res = await fetch('/api/peers');
    if (res.status === 401) {
      openModal('loginModal');
      return;
    }
    const data = await res.json();
    peersList = data.peers || [];
    nextSuggestedIp = data.next_suggested_ip || '10.8.0.2';

    document.getElementById('peerCountBadge').textContent = `${peersList.length} 个客户端`;
    const onlineCount = data.online_count || 0;
    document.getElementById('statPeersCount').textContent = `${onlineCount} / ${peersList.length} 台在线`;

    renderPeersTable(peersList);

    if (showNotice) {
      showToast('客户端列表已刷新', 'info');
    }
  } catch (e) {
    console.error('Failed to load peers:', e);
  }
}

function filterPeers() {
  const query = document.getElementById('peerSearchInput').value.toLowerCase().trim();
  if (!query) {
    renderPeersTable(peersList);
    return;
  }
  const filtered = peersList.filter(p => {
    return (p.name && p.name.toLowerCase().includes(query)) ||
           (p.ip && p.ip.toLowerCase().includes(query)) ||
           (p.public_key && p.public_key.toLowerCase().includes(query));
  });
  renderPeersTable(filtered);
}

function renderPeersTable(peers) {
  const tbody = document.getElementById('peersTableBody');
  if (!peers || peers.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
          <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">📱</div>
          <div style="font-size: 0.95rem; font-weight: 600; margin-bottom: 0.25rem;">暂无 WireGuard 客户端</div>
          <div style="font-size: 0.8rem; margin-bottom: 1rem;">点击上方 "➕ 添加客户端" 在线生成密钥对并生成手机扫码连接配置</div>
          <button class="btn btn-primary btn-sm" onclick="openAddPeerModal()">➕ 立即添加</button>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = peers.map(peer => {
    const stats = peer.runtime_stats || {};
    const isOnline = stats.is_online;
    const isEnabled = peer.enabled;

    let statusBadge = '';
    if (!isEnabled) {
      statusBadge = '<span class="badge badge-danger">⛔ 已停用</span>';
    } else if (isOnline) {
      statusBadge = '<span class="badge badge-success"><span class="pulse-dot online"></span> 在线</span>';
    } else {
      statusBadge = '<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3);"><span class="pulse-dot offline"></span> 离线</span>';
    }

    const rx = stats.transfer_rx || 0;
    const tx = stats.transfer_tx || 0;
    const trafficStr = `↓ ${formatBytes(rx)} / ↑ ${formatBytes(tx)}`;
    const handshakeStr = formatRelativeTime(stats.latest_handshake);

    const pubKeyShort = peer.public_key ? `${peer.public_key.slice(0, 6)}...${peer.public_key.slice(-6)}` : '未设置';

    return `
      <tr style="border-bottom: 1px solid var(--border-color); ${!isEnabled ? 'opacity: 0.6;' : ''}">
        <td style="padding: 0.85rem 1rem;">${statusBadge}</td>
        
        <!-- Peer Name -->
        <td style="padding: 0.85rem 1rem;">
          <div style="font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 0.4rem;">
            📱 ${escapeHtml(peer.name)}
          </div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.15rem;">
            创建于: ${new Date(peer.created_at).toLocaleDateString()}
          </div>
        </td>

        <!-- Assigned IP -->
        <td style="padding: 0.85rem 1rem;">
          <span style="font-family: monospace; font-weight: 600; color: var(--primary); background: rgba(59, 130, 246, 0.1); padding: 0.2rem 0.5rem; border-radius: 4px;">
            ${peer.ip}
          </span>
        </td>

        <!-- Public Key with copy -->
        <td style="padding: 0.85rem 1rem;">
          <span style="font-family: monospace; font-size: 0.8rem; cursor: pointer; color: var(--text-secondary);" title="点击复制完整公钥: ${peer.public_key}" onclick="copyText('${peer.public_key}', '公钥已复制')">
            ${pubKeyShort} 📋
          </span>
        </td>

        <!-- Handshake -->
        <td style="padding: 0.85rem 1rem; color: var(--text-secondary); font-size: 0.8rem;">
          ${handshakeStr}
        </td>

        <!-- Traffic -->
        <td style="padding: 0.85rem 1rem; font-size: 0.8rem; font-family: monospace;">
          ${trafficStr}
        </td>

        <!-- Action Buttons -->
        <td style="padding: 0.85rem 1rem; text-align: right;">
          <div style="display: inline-flex; align-items: center; gap: 0.4rem;">
            
            <!-- QR Code Button (Primary Highlight) -->
            <button class="btn btn-primary btn-sm" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);" onclick="showPeerQRCode('${peer.id}')" title="生成手机连接二维码">
              📱 二维码
            </button>

            <!-- Download Conf Button -->
            <a class="btn btn-secondary btn-sm" href="/api/peers/${peer.id}/download" download title="下载 WireGuard 配置文件">
              📥 下载
            </a>

            <!-- Toggle Switch -->
            <label class="toggle-switch" title="${isEnabled ? '点击禁用此客户端' : '点击启用此客户端'}">
              <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="togglePeerState('${peer.id}')">
              <span class="toggle-slider"></span>
            </label>

            <!-- Delete Button -->
            <button class="btn btn-danger btn-sm" onclick="deletePeerConfirm('${peer.id}', '${escapeHtml(peer.name)}')" title="删除客户端">
              🗑️
            </button>

          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// ----------------- Add Peer & Online Key Generation ----------------- //
function openAddPeerModal() {
  document.getElementById('addPeerName').value = `Phone-${peersList.length + 1}`;
  document.getElementById('addPeerIp').value = nextSuggestedIp;
  document.getElementById('addPeerSuggestedIpText').textContent = `已自动推荐空闲 IP: ${nextSuggestedIp}`;
  document.getElementById('addPeerAllowedIps').value = '0.0.0.0/0, ::/0';
  document.getElementById('addPeerDns').value = serverConfig.dns || '1.1.1.1, 8.8.8.8';

  const port = serverConfig.listen_port || 51820;
  const host = serverConfig.endpoint_host || '127.0.0.1';
  document.getElementById('addPeerEndpoint').value = `${host}:${port}`;

  // Auto-generate keys right away so the user doesn't even need to click
  generateKeysForAddPeer();

  openModal('addPeerModal');
}

async function generateKeysForAddPeer() {
  try {
    const res = await fetch('/api/keys/generate');
    const data = await res.json();
    document.getElementById('addPeerPrivateKey').value = data.private_key;
    document.getElementById('addPeerPublicKey').value = data.public_key;
    showToast('已在线生成高强度 Curve25519 密钥对', 'success');
  } catch (e) {
    showToast('生成密钥对失败', 'error');
  }
}

async function generatePSKForAddPeer() {
  try {
    const res = await fetch('/api/keys/generate');
    const data = await res.json();
    document.getElementById('addPeerPSK').value = data.preshared_key;
    showToast('已生成量子防护预共享密钥 (PSK)', 'success');
  } catch (e) {
    showToast('生成 PSK 失败', 'error');
  }
}

function setAddPeerRoute(routeStr) {
  document.getElementById('addPeerAllowedIps').value = routeStr;
}

// Bind auto public key derivation when private key is edited manually
document.addEventListener('DOMContentLoaded', () => {
  const privInput = document.getElementById('addPeerPrivateKey');
  if (privInput) {
    privInput.addEventListener('input', async (e) => {
      const priv = e.target.value.trim();
      if (priv.length >= 40) {
        try {
          const res = await fetch('/api/keys/derive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ private_key: priv })
          });
          const data = await res.json();
          if (data.public_key) {
            document.getElementById('addPeerPublicKey').value = data.public_key;
          }
        } catch (err) {}
      }
    });
  }
});

async function submitAddPeer(showQR = true) {
  const name = document.getElementById('addPeerName').value.trim();
  const privateKey = document.getElementById('addPeerPrivateKey').value.trim();
  const publicKey = document.getElementById('addPeerPublicKey').value.trim();
  const psk = document.getElementById('addPeerPSK').value.trim();
  const ip = document.getElementById('addPeerIp').value.trim();
  const allowedIps = document.getElementById('addPeerAllowedIps').value.trim();
  const dns = document.getElementById('addPeerDns').value.trim();

  if (!name) {
    showToast('请输入客户端备注名称', 'warning');
    return;
  }
  if (!privateKey && !publicKey) {
    showToast('请在线生成或填入客户端密钥对', 'warning');
    return;
  }
  if (!ip) {
    showToast('请输入或分配客户端 IP', 'warning');
    return;
  }

  const payload = {
    name: name,
    private_key: privateKey,
    public_key: publicKey,
    preshared_key: psk || null,
    ip: ip,
    allowed_ips: allowedIps,
    dns: dns
  };

  try {
    const res = await fetch('/api/peers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '添加客户端失败', 'error');
      return;
    }

    closeModal('addPeerModal');
    showToast(`客户端 '${data.peer.name}' 添加成功！`, 'success');
    await refreshAll();

    if (showQR && data.peer && data.peer.id) {
      // Immediately display the QR code modal for mobile phone scanning!
      showPeerQRCode(data.peer.id);
    }
  } catch (e) {
    showToast('网络请求失败', 'error');
  }
}

// ----------------- QR Code & Mobile Connection Modal ----------------- //
async function showPeerQRCode(peerId) {
  const peer = peersList.find(p => p.id === peerId);
  currentViewingPeer = peer;

  try {
    const res = await fetch(`/api/peers/${peerId}/config`);
    if (!res.ok) {
      showToast('获取客户端配置失败', 'error');
      return;
    }
    const confText = await res.text();
    currentViewingConfig = confText;

    // Subtitle
    const titleEl = document.getElementById('qrModalSubtitle');
    if (peer) {
      titleEl.textContent = `设备名称: ${peer.name} | 分配 IP: ${peer.ip} | 端口: ${serverConfig.listen_port || 51820}`;
    } else {
      titleEl.textContent = `配置端口: ${serverConfig.listen_port || 51820}`;
    }

    // Config Text
    document.getElementById('qrModalConfigText').textContent = confText;
    document.getElementById('configPreviewWrapper').style.display = 'none';
    document.getElementById('togglePreviewText').textContent = '展开配置内容';

    // Download Button href
    document.getElementById('downloadConfBtn').href = `/api/peers/${peerId}/download`;

    // Render QR Code in DOM using QRCode.js
    const container = document.getElementById('qrcodeContainer');
    container.innerHTML = ''; // clear previous
    new QRCode(container, {
      text: confText,
      width: 260,
      height: 260,
      colorDark: "#000000",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.M
    });

    openModal('qrCodeModal');
  } catch (e) {
    console.error('Failed to render QR Code:', e);
    showToast('生成二维码出错', 'error');
  }
}

function toggleConfigPreview() {
  const wrapper = document.getElementById('configPreviewWrapper');
  const textEl = document.getElementById('togglePreviewText');
  if (wrapper.style.display === 'none') {
    wrapper.style.display = 'block';
    textEl.textContent = '收起配置内容';
  } else {
    wrapper.style.display = 'none';
    textEl.textContent = '展开配置内容';
  }
}

function copyCurrentConfig() {
  if (!currentViewingConfig) return;
  navigator.clipboard.writeText(currentViewingConfig);
  showToast('WireGuard 客户端配置文本已复制到剪贴板！', 'success');
}

// ----------------- Peer Toggle & Delete ----------------- //
async function togglePeerState(peerId) {
  try {
    const res = await fetch(`/api/peers/${peerId}/toggle`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '切换状态失败', 'error');
      return;
    }
    showToast(data.message, 'info');
    await loadPeers(false);
  } catch (e) {
    showToast('操作失败', 'error');
  }
}

async function deletePeerConfirm(peerId, name) {
  if (!confirm(`确定要彻底删除客户端 "${name}" 吗？此操作不可逆。`)) return;
  try {
    const res = await fetch(`/api/peers/${peerId}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '删除失败', 'error');
      return;
    }
    showToast(`客户端 "${name}" 已删除`, 'success');
    await refreshAll();
  } catch (e) {
    showToast('删除请求异常', 'error');
  }
}

// ----------------- Standalone Keypair Tool Modal ----------------- //
function openKeygenModal() {
  generateToolKeypair();
  openModal('keygenModal');
}

async function generateToolKeypair() {
  try {
    const res = await fetch('/api/keys/generate');
    const data = await res.json();
    document.getElementById('toolPrivKey').value = data.private_key;
    document.getElementById('toolPubKey').value = data.public_key;
    document.getElementById('toolPsk').value = data.preshared_key;
    showToast('已在线生成全新 Curve25519 密钥对', 'success');
  } catch (e) {
    showToast('生成密钥出错', 'error');
  }
}

function copyInputText(elementId) {
  const el = document.getElementById(elementId);
  if (!el || !el.value) return;
  navigator.clipboard.writeText(el.value);
  showToast('已复制到剪贴板', 'success');
}

function copyText(str, msg = '已复制') {
  navigator.clipboard.writeText(str);
  showToast(msg, 'success');
}

function escapeHtml(text) {
  if (!text) return '';
  return text.replace(/[&<>"']/g, function(m) {
    return {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    }[m];
  });
}

// ----------------- Main Refresh Loop ----------------- //
async function refreshAll() {
  await loadServerInfo();
  await loadPeers();
}

// Initialization on DOM Ready
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  const isAuth = await checkAuth();
  if (isAuth) {
    await refreshAll();
  }

  // Periodic status poll (every 10s)
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const loginEl = document.getElementById('loginModal');
    if (loginEl && !loginEl.classList.contains('active')) {
      await loadServerInfo();
      await loadPeers(false);
    }
  }, 10000);
});
