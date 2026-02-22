/**
 * ORION Core - Main Application
 * Initializes and coordinates all components
 */

class ORIONApp {
    constructor() {
        this.ws = null;
        this.chat = null;
        this.sidebar = null;

        this.init();
    }

    init() {
        console.log('🌌 ORION Core initializing...');

        // Initialize components
        this.chat = new Chat();
        this.sidebar = new Sidebar();
        this.commandPalette = new CommandPalette(this);

        // Initialize WebSocket
        this.initializeWebSocket();

        // Setup global event handlers
        this.setupGlobalHandlers();

        console.log('✅ ORION Core initialized');
    }

    initializeWebSocket() {
        const wsUrl = utils.getWebSocketURL('/chat');
        this.ws = new WebSocketClient(wsUrl);

        // On connection open
        this.ws.on('open', () => {
            console.log('✅ Connected to ORION');
            this.hideConnectionToast();
        });

        // On message received
        this.ws.on('message', (data) => {
            this.handleMessage(data);
        });

        // On connection close
        this.ws.on('close', () => {
            console.log('❌ Disconnected from ORION');
            this.showConnectionToast('Connection lost. Attempting to reconnect...');
        });

        // On error
        this.ws.on('error', (error) => {
            console.error('❌ WebSocket error:', error);
        });

        // On reconnecting
        this.ws.on('reconnecting', (data) => {
            console.log(`🔄 Reconnecting (${data.attempt}/${data.maxAttempts})...`);
            this.showConnectionToast(`Reconnecting... (attempt ${data.attempt}/${data.maxAttempts})`);
        });

        // Connect
        this.ws.connect();
    }

    handleMessage(data) {
        const { type, response, metadata } = data;

        switch (type) {
            case 'welcome':
                // Welcome message from server
                this.chat.addMessage('system', response, { isWelcome: true });
                break;

            case 'message':
            case 'response':
                // Regular assistant response
                this.chat.handleAssistantMessage(data);
                break;

            case 'progress':
                // Streaming progress update
                this.chat.handleProgressMessage(data);
                break;

            case 'token':
                // Streaming token (word/char chunk)
                this.chat.handleTokenMessage(data);
                break;

            case 'complete':
                // Streaming complete with metadata
                this.chat.handleCompleteMessage(data);
                break;

            case 'sources':
                // Knowledge sources from RAG
                this.chat.handleSourcesMessage(data);
                break;

            case 'error':
                // Error message
                this.chat.handleAssistantMessage({
                    type: 'error',
                    response: response || 'An error occurred',
                    metadata
                });
                break;

            case 'status':
                // Status update (for sidebar)
                if (metadata && metadata.sidebar) {
                    this.sidebar.updateMetrics();
                }
                break;

            case 'debug_breadcrumb':
                // Debug breadcrumb - show in sidebar if debug panel exists
                this.handleDebugBreadcrumb(data.data);
                break;

            case 'debug_analysis':
                // Error analysis - show in UI
                this.handleDebugAnalysis(data.data);
                break;

            default:
                console.warn('Unknown message type:', type);
                this.chat.handleAssistantMessage(data);
        }
    }

    handleDebugBreadcrumb(breadcrumb) {
        // Log to console for debugging
        console.log('🔍', breadcrumb.action, `(${(breadcrumb.confidence * 100).toFixed(0)}%)`, breadcrumb.reasoning);

        // Update sidebar debug panel if it exists
        if (this.sidebar && typeof this.sidebar.updateDebugTrail === 'function') {
            this.sidebar.updateDebugTrail(breadcrumb);
        }

        // Store breadcrumbs for later display
        if (!this.debugBreadcrumbs) {
            this.debugBreadcrumbs = [];
        }
        this.debugBreadcrumbs.push(breadcrumb);

        // Keep only last 20 breadcrumbs
        if (this.debugBreadcrumbs.length > 20) {
            this.debugBreadcrumbs.shift();
        }
    }

    handleDebugAnalysis(analysis) {
        console.warn('🚨 Debug Analysis:', analysis);

        // Show error analysis in chat
        if (this.chat) {
            const divergence = analysis.divergence_point;
            const summary = analysis.suggested_fixes || [];

            let analysisText = `**Debug Analysis:**\n\n`;
            analysisText += `**Error:** ${analysis.error_type}: ${analysis.error_message}\n\n`;

            if (divergence) {
                analysisText += `**Likely Issue:** ${divergence.action}\n`;
                analysisText += `*${divergence.reasoning || divergence.reason}*\n\n`;
            }

            if (summary.length > 0) {
                analysisText += `**Suggestions:**\n`;
                summary.forEach((fix, i) => {
                    analysisText += `${i + 1}. ${fix.action}\n`;
                });
            }

            // Show breadcrumb trail summary
            if (analysis.breadcrumb_trail && analysis.breadcrumb_trail.length > 0) {
                analysisText += `\n**Recent Steps (last ${analysis.breadcrumb_trail.length}):**\n`;
                analysis.breadcrumb_trail.slice(-5).forEach((bc, i) => {
                    const conf = (bc.confidence * 100).toFixed(0);
                    analysisText += `${i + 1}. ${bc.action} (${conf}% confident)\n`;
                });
            }

            this.chat.addMessage('system', analysisText, { isDebug: true });
        }
    }

    sendMessage(message, enableStreaming = true) {
        if (!this.ws || !this.ws.isConnected()) {
            this.chat.addMessage('error', 'Not connected to ORION. Please wait for reconnection.');
            this.chat.hideLoading();
            this.chat.isWaitingForResponse = false;
            return false;
        }

        const payload = {
            message,
            stream: enableStreaming,  // Enable streaming by default
            timestamp: Date.now()
        };

        return this.ws.send(payload);
    }

    setupGlobalHandlers() {
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Cmd/Ctrl + K - Open command palette
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                this.commandPalette.toggle();
                return;
            }

            // Cmd/Ctrl + L - Clear chat
            if ((e.metaKey || e.ctrlKey) && e.key === 'l') {
                e.preventDefault();
                if (confirm('Clear chat history?')) {
                    this.chat.clearChat();
                }
            }

            // Cmd/Ctrl + B - Toggle sidebar
            if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
                e.preventDefault();
                this.sidebar.toggleState();
            }

            // Escape - Clear input
            if (e.key === 'Escape') {
                if (this.chat.messageInput === document.activeElement) {
                    this.chat.messageInput.value = '';
                    this.chat.sendBtn.disabled = true;
                }
            }

            // Conversation navigation shortcuts (Alt + Arrow keys)
            if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
                const currentMsg = this.chat.messages.find(m => m.id === this.chat.currentMessageId);
                if (!currentMsg) return;

                // Alt + Left Arrow - Previous sibling
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    const siblings = this.chat.getSiblings(currentMsg.id);
                    const currentIndex = siblings.findIndex(m => m.id === currentMsg.id);
                    if (currentIndex > 0) {
                        this.chat.navigateToMessage(siblings[currentIndex - 1].id);
                    }
                }

                // Alt + Right Arrow - Next sibling
                if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    const siblings = this.chat.getSiblings(currentMsg.id);
                    const currentIndex = siblings.findIndex(m => m.id === currentMsg.id);
                    if (currentIndex < siblings.length - 1) {
                        this.chat.navigateToMessage(siblings[currentIndex + 1].id);
                    }
                }

                // Alt + Up Arrow - Navigate to parent
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    const parent = this.chat.getParent(currentMsg.id);
                    if (parent) {
                        this.chat.navigateToMessage(parent.id);
                    }
                }

                // Alt + Down Arrow - Navigate to first child
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    const children = this.chat.getChildren(currentMsg.id);
                    if (children.length > 0) {
                        this.chat.navigateToMessage(children[0].id);
                    }
                }
            }
        });

        // Visibility change (pause updates when tab hidden)
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                // Pause sidebar updates
                this.sidebar.stopAutoUpdate();
            } else {
                // Resume updates
                this.sidebar.startAutoUpdate();
            }
        });

        // Before unload (clean disconnect)
        window.addEventListener('beforeunload', () => {
            if (this.ws) {
                this.ws.disconnect();
            }
        });
    }

    showConnectionToast(message) {
        const toast = document.getElementById('connectionToast');
        if (toast) {
            toast.querySelector('.toast-text').textContent = message;
            utils.toggleElement(toast, true);
        }
    }

    hideConnectionToast() {
        const toast = document.getElementById('connectionToast');
        if (toast) {
            utils.toggleElement(toast, false);
        }
    }
}

// Initialize app when DOM is ready (with guard to prevent multiple initializations)
document.addEventListener('DOMContentLoaded', () => {
    // Prevent multiple initializations
    if (window.orion) {
        console.warn('⚠️ ORION already initialized, skipping duplicate initialization');
        return;
    }

    window.orion = new ORIONApp();
});

// Expose chat and sidebar for debugging
Object.defineProperty(window, 'chat', {
    get() { return window.orion?.chat; }
});

Object.defineProperty(window, 'sidebar', {
    get() { return window.orion?.sidebar; }
});
