/**
 * ORION Dashboard JavaScript
 * Handles tab switching, theme toggle, status updates, and real-time data
 */

// ===== Configuration =====
const CONFIG = {
    updateInterval: 30000, // 30 seconds
    apiBase: '/api',
    endpoints: {
        health: '/health',
        status: '/status',
        metrics: '/metrics',
        user: '/user'
    }
};

// ===== State Management =====
const state = {
    currentTab: 'dashboard',
    theme: localStorage.getItem('orion-theme') || 'dark',
    user: null,
    services: {},
    lastUpdate: null
};

// ===== Initialize on DOM Load =====
document.addEventListener('DOMContentLoaded', () => {
    initializeTheme();
    initializeTabs();
    initializeThemeToggle();
    initializeUser();
    initializeStatusUpdates();

    // Start periodic updates
    setInterval(updateAllStatus, CONFIG.updateInterval);
});

// ===== Theme Management =====
function initializeTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
    updateThemeIcon();
}

function initializeThemeToggle() {
    const toggle = document.getElementById('themeToggle');
    if (toggle) {
        toggle.addEventListener('click', toggleTheme);
    }
}

function toggleTheme() {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', state.theme);
    localStorage.setItem('orion-theme', state.theme);
    updateThemeIcon();
    logActivity(`Switched to ${state.theme} mode`);
}

function updateThemeIcon() {
    const icon = document.querySelector('.theme-icon');
    if (icon) {
        icon.textContent = state.theme === 'dark' ? '🌙' : '☀️';
    }
}

// ===== Tab Management =====
function initializeTabs() {
    const tabs = document.querySelectorAll('.nav-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
}

function switchTab(tabName) {
    // Update state
    state.currentTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `${tabName}-tab`);
    });

    // Log activity
    logActivity(`Switched to ${tabName} tab`);

    // Load iframe if not loaded yet (lazy loading)
    loadTabContent(tabName);
}

function loadTabContent(tabName) {
    const iframeMap = {
        'metrics': 'grafana-iframe',
        'workflows': 'n8n-iframe',
        'knowledge': 'anythingllm-iframe',
        'chat': 'orion-chat-iframe'
    };

    const iframeId = iframeMap[tabName];
    if (iframeId) {
        const iframe = document.getElementById(iframeId);
        if (iframe && !iframe.dataset.loaded) {
            // Mark as loaded to prevent reload
            iframe.dataset.loaded = 'true';
        }
    }
}

// ===== User Information =====
async function initializeUser() {
    try {
        // Try to get user info from Authelia headers (passed by Traefik)
        const response = await fetch(CONFIG.apiBase + CONFIG.endpoints.user);

        if (response.ok) {
            const data = await response.json();
            state.user = data;
            updateUserDisplay(data);
        } else {
            // Fallback to generic user
            updateUserDisplay({ username: 'Guest', displayName: 'Guest User' });
        }
    } catch (error) {
        console.error('Failed to fetch user info:', error);
        updateUserDisplay({ username: 'Guest', displayName: 'Guest User' });
    }
}

function updateUserDisplay(user) {
    const userNameEl = document.querySelector('.user-name');
    if (userNameEl) {
        userNameEl.textContent = user.displayName || user.username || 'Guest';
    }
}

// ===== Status Updates =====
async function initializeStatusUpdates() {
    // Initial status fetch
    await updateAllStatus();
}

async function updateAllStatus() {
    try {
        // Update connection status
        updateConnectionStatus(true);

        // Fetch status from API
        const response = await fetch(CONFIG.apiBase + CONFIG.endpoints.status);

        if (response.ok) {
            const data = await response.json();
            updateServiceCards(data);
            updateResourceMetrics(data);
            state.lastUpdate = new Date();
            updateLastUpdateTime();
        } else {
            console.error('Failed to fetch status');
            updateConnectionStatus(false);
        }
    } catch (error) {
        console.error('Error updating status:', error);
        updateConnectionStatus(false);
    }
}

function updateServiceCards(data) {
    const services = data.services || {};

    // Update ORION Core
    if (services.orion_core) {
        updateCard('orion-core', services.orion_core);
        setMetric('orion-uptime', services.orion_core.uptime || '--');
        setMetric('orion-requests', formatNumber(services.orion_core.requests || 0));
    }

    // Update vLLM
    if (services.vllm) {
        updateCard('vllm', services.vllm);
        setMetric('gpu-temp', `${services.vllm.gpu_temp || '--'}°C`);
    }

    // Update Qdrant
    if (services.qdrant) {
        updateCard('qdrant', services.qdrant);
        setMetric('qdrant-collections', services.qdrant.collections || '--');
        setMetric('qdrant-vectors', formatNumber(services.qdrant.vectors || 0));
    }

    // Update Authelia
    if (services.authelia) {
        updateCard('authelia', services.authelia);
        setMetric('auth-sessions', services.authelia.sessions || '--');
    }
}

function updateResourceMetrics(data) {
    const resources = data.resources || {};

    // GPU Usage
    if (resources.gpu) {
        const gpuUsage = (resources.gpu.used / resources.gpu.total) * 100;
        updateProgressBar('gpu-usage', gpuUsage);
        setTextContent('gpu-usage-text',
            `${formatBytes(resources.gpu.used)} / ${formatBytes(resources.gpu.total)}`);
    }

    // Disk Usage
    if (resources.disk) {
        const diskUsage = (resources.disk.used / resources.disk.total) * 100;
        updateProgressBar('disk-usage', diskUsage);
        setTextContent('disk-usage-text',
            `${formatBytes(resources.disk.used)} / ${formatBytes(resources.disk.total)}`);
    }

    // Memory Usage
    if (resources.memory) {
        const memUsage = (resources.memory.used / resources.memory.total) * 100;
        updateProgressBar('memory-usage', memUsage);
        setTextContent('memory-usage-text',
            `${formatBytes(resources.memory.used)} / ${formatBytes(resources.memory.total)}`);
    }
}

function updateCard(cardId, service) {
    const card = document.getElementById(`${cardId}-card`);
    if (!card) return;

    const badge = card.querySelector('.status-badge');
    if (badge) {
        badge.className = 'status-badge';
        badge.classList.add(service.status || 'unknown');
        badge.textContent = (service.status || 'unknown').toUpperCase();
    }
}

function updateProgressBar(id, percentage) {
    const bar = document.getElementById(`${id}-bar`);
    if (bar) {
        bar.style.width = `${Math.min(percentage, 100)}%`;
        bar.className = 'progress-bar';

        if (percentage > 90) {
            bar.classList.add('critical');
        } else if (percentage > 75) {
            bar.classList.add('warning');
        }
    }
}

function setMetric(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setTextContent(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('connectionStatus');
    if (statusEl) {
        statusEl.className = 'connection-status';
        if (connected) {
            statusEl.classList.add('connected');
            statusEl.textContent = 'Connected';
        } else {
            statusEl.textContent = 'Disconnected';
        }
    }
}

function updateLastUpdateTime() {
    const el = document.getElementById('lastUpdate');
    if (el && state.lastUpdate) {
        el.textContent = state.lastUpdate.toLocaleTimeString();
    }
}

// ===== Activity Log =====
function logActivity(message) {
    const log = document.getElementById('activityLog');
    if (!log) return;

    const item = document.createElement('div');
    item.className = 'activity-item';

    const time = document.createElement('span');
    time.className = 'activity-time';
    time.textContent = new Date().toLocaleTimeString();

    const text = document.createElement('span');
    text.className = 'activity-text';
    text.textContent = message;

    item.appendChild(time);
    item.appendChild(text);

    // Insert at top
    log.insertBefore(item, log.firstChild);

    // Keep only last 10 items
    while (log.children.length > 10) {
        log.removeChild(log.lastChild);
    }
}

// ===== Utility Functions =====
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

// ===== Action Handlers =====
function openService(path) {
    window.open(path, '_blank');
    logActivity(`Opened ${path}`);
}

function refreshStatus() {
    logActivity('Refreshing status...');
    updateAllStatus();
}

// ===== Error Handling =====
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
});

// ===== Expose functions globally for inline onclick handlers =====
window.openService = openService;
window.refreshStatus = refreshStatus;
