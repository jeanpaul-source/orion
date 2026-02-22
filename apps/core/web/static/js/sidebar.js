/**
 * ORION Core - Sidebar Component
 * Handles live status, metrics, alerts, and context
 */

class Sidebar {
    constructor() {
        this.sidebar = document.getElementById('sidebar');
        this.collapseBtn = document.getElementById('collapseBtn');
        this.refreshBtn = document.getElementById('refreshBtn');

        this.state = 'expanded'; // expanded, mini, hidden
        this.updateInterval = null;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.restoreState();
        this.startAutoUpdate();
    }

    setupEventListeners() {
        // Collapse button
        this.collapseBtn.addEventListener('click', () => this.toggleState());

        // Refresh button
        this.refreshBtn.addEventListener('click', () => this.updateMetrics());

        // Context action buttons (delegated event handling)
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('context-btn')) {
                const cmd = e.target.dataset.cmd;
                const url = e.target.dataset.url;

                if (cmd && window.chat) {
                    window.chat.messageInput.value = cmd;
                    window.chat.handleSend();
                } else if (url) {
                    window.open(url, '_blank');
                }
            }
        });
    }

    toggleState() {
        const states = ['expanded', 'mini', 'hidden'];
        const currentIndex = states.indexOf(this.state);
        const nextIndex = (currentIndex + 1) % states.length;
        this.state = states[nextIndex];

        this.sidebar.dataset.state = this.state;
        this.saveState();

        // Update collapse button icon
        const icons = { expanded: '⬅️', mini: '➡️', hidden: '➡️' };
        this.collapseBtn.querySelector('.icon').textContent = icons[this.state];
    }

    saveState() {
        utils.storage.set('sidebar-state', this.state);
    }

    restoreState() {
        const saved = utils.storage.get('sidebar-state');
        if (saved) {
            this.state = saved;
            this.sidebar.dataset.state = saved;

            const icons = { expanded: '⬅️', mini: '➡️', hidden: '➡️' };
            this.collapseBtn.querySelector('.icon').textContent = icons[this.state];
        }
    }

    startAutoUpdate() {
        // Initial update
        this.updateMetrics();

        // Update every 30 seconds
        this.updateInterval = setInterval(() => {
            this.updateMetrics();
        }, 30000);
    }

    stopAutoUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    async updateMetrics() {
        try {
            // Fetch real data from API
            const response = await fetch('/api/hybrid/status');

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const data = await response.json();

            this.updateHealthStatus(data.services);
            this.updateMetricValues(data.metrics);
            this.updateAlerts(data.alerts);
            this.updateActivity(data.recent_activity);

        } catch (error) {
            console.error('Failed to update metrics:', error);
            // Fallback to showing last known data or error state
            this.showError('Unable to fetch system metrics');
        }
    }

    showError(message) {
        // Show error in alerts section
        const container = document.getElementById('alerts');
        if (container) {
            container.innerHTML = `
                <div class="alert alert-error">
                    <span class="alert-icon">❌</span>
                    <div class="alert-content">
                        <span class="alert-message">${message}</span>
                        <span class="alert-time">Just now</span>
                    </div>
                </div>
            `;
        }
    }

    updateHealthStatus(services) {
        Object.entries(services).forEach(([service, status]) => {
            const item = document.querySelector(`[data-service="${service}"]`);
            if (item) {
                const statusEl = item.querySelector('.service-status');
                statusEl.textContent = status.value;
                statusEl.className = `service-status status-${status.state}`;
            }
        });

        // Update overall health icon
        const allHealthy = Object.values(services).every(s => s.state === 'healthy');
        const healthIcon = document.getElementById('healthIcon');
        if (healthIcon) {
            healthIcon.textContent = allHealthy ? '🟢' : '🟡';
        }
    }

    updateMetricValues(metrics) {
        // GPU
        if (metrics.gpu) {
            this.updateProgress('gpu', metrics.gpu.percent, metrics.gpu.text);
        }

        // Disk
        if (metrics.disk) {
            this.updateProgress('disk', metrics.disk.percent, metrics.disk.text);

            // Update individual drive details if available
            if (metrics.disk.drives && metrics.disk.drives.length > 0) {
                this.updateDriveDetails(metrics.disk.drives);
            }
        }

        // Memory
        if (metrics.memory) {
            this.updateProgress('memory', metrics.memory.percent, metrics.memory.text);
        }
    }

    updateDriveDetails(drives) {
        const container = document.getElementById('driveDetails');
        if (!container) return;

        container.innerHTML = drives.map(drive => {
            const percentClass = drive.percent > 90 ? 'critical' : drive.percent > 75 ? 'warning' : '';
            return `
                <div class="drive-detail">
                    <div class="drive-header">
                        <span class="drive-path">${drive.path}</span>
                        <span class="drive-usage">${drive.text}</span>
                    </div>
                    <div class="progress-bar mini">
                        <div class="progress-fill ${percentClass}" style="width: ${drive.percent}%"></div>
                    </div>
                </div>
            `;
        }).join('');
    }

    updateProgress(id, percent, text) {
        const valueEl = document.getElementById(`${id}Value`);
        const progressEl = document.getElementById(`${id}Progress`);

        if (valueEl) valueEl.textContent = text || `${percent}%`;
        if (progressEl) {
            progressEl.style.width = `${percent}%`;
            progressEl.className = 'progress-fill';

            if (percent > 90) {
                progressEl.classList.add('critical');
            } else if (percent > 75) {
                progressEl.classList.add('warning');
            }
        }
    }

    updateAlerts(alerts) {
        const container = document.getElementById('alerts');
        if (!container) return;

        if (!alerts || alerts.length === 0) {
            container.innerHTML = '<p class="no-alerts">All systems nominal</p>';
            return;
        }

        container.innerHTML = alerts.map(alert => `
            <div class="alert alert-${alert.level}">
                <span class="alert-icon">${alert.icon}</span>
                <div class="alert-content">
                    <span class="alert-message">${alert.message}</span>
                    <span class="alert-time">${alert.time}</span>
                </div>
            </div>
        `).join('');
    }

    updateActivity(activities) {
        const container = document.getElementById('activity');
        if (!container) return;

        container.innerHTML = activities.map(activity => `
            <div class="activity-item">
                <span class="activity-time">${activity.time}</span>
                <span class="activity-text">${activity.text}</span>
            </div>
        `).join('');
    }

    updateContext(context) {
        const titleEl = document.getElementById('contextTitle');
        const iconEl = document.getElementById('contextIcon');
        const contentEl = document.getElementById('contextContent');

        if (!context) {
            context = this.getDefaultContext();
        }

        if (titleEl) titleEl.textContent = context.title;
        if (iconEl) iconEl.textContent = context.icon;

        if (contentEl) {
            contentEl.innerHTML = `
                <div class="context-actions">
                    ${context.actions.map(action => `
                        <button class="context-btn"
                                ${action.cmd ? `data-cmd="${action.cmd}"` : ''}
                                ${action.url ? `data-url="${action.url}"` : ''}>
                            ${action.label}
                        </button>
                    `).join('')}
                </div>
            `;
        }
    }

    getDefaultContext() {
        return {
            icon: '🎯',
            title: 'Quick Actions',
            actions: [
                { label: 'Full system status', cmd: '/status' },
                { label: 'Check recent logs', cmd: '/logs' },
                { label: 'Knowledge base stats', cmd: '/rag stats' },
                { label: 'Run harvester', cmd: '/harvester run' }
            ]
        };
    }

    getMockData() {
        // Mock data for Week 1 testing
        return {
            services: {
                vllm: { state: 'healthy', value: '⚡ 78% GPU' },
                qdrant: { state: 'healthy', value: '⚡ 1.2M vectors' },
                gpu: { state: 'healthy', value: '🌡️ 68°C' },
                disk: { state: 'healthy', value: '💾 45% used' }
            },
            metrics: {
                gpu: { percent: 78, text: '78%' },
                disk: { percent: 45, text: '842 GB / 1.8 TB' },
                memory: { percent: 44, text: '28.1 GB / 64 GB' }
            },
            alerts: [],
            recent_activity: [
                { time: 'Just now', text: 'Metrics updated' },
                { time: '2m ago', text: 'User query processed' },
                { time: '5m ago', text: 'System health check' }
            ]
        };
    }

    updateDebugTrail(breadcrumb) {
        /**
         * Update debug trail in sidebar (real-time breadcrumb tracking)
         * Only shows when debug mode is enabled (can toggle with console)
         */

        // Check if debug mode is enabled
        if (!window.debugMode) {
            return;
        }

        const activity = document.querySelector('.recent-activity');
        if (!activity) return;

        // Create breadcrumb element
        const item = document.createElement('div');
        item.className = 'activity-item debug-breadcrumb';
        item.style.borderLeft = breadcrumb.confidence < 0.7 ? '3px solid orange' : '3px solid #4ade80';
        item.style.paddingLeft = '8px';

        const time = new Date(breadcrumb.timestamp).toLocaleTimeString();
        const conf = (breadcrumb.confidence * 100).toFixed(0);
        const emoji = breadcrumb.metadata?.risky ? '⚠️' : breadcrumb.metadata?.error ? '❌' : '🔍';

        item.innerHTML = `
            <span class="activity-time">${time}</span>
            <span class="activity-text">${emoji} ${breadcrumb.action} <small>(${conf}%)</small></span>
        `;

        // Add tooltip with reasoning
        item.title = breadcrumb.reasoning;

        // Insert at top
        activity.insertBefore(item, activity.firstChild);

        // Keep only last 10 items
        while (activity.children.length > 10) {
            activity.removeChild(activity.lastChild);
        }
    }
}

// Export for use in app.js
window.Sidebar = Sidebar;
