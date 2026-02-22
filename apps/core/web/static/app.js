/**
 * ORION Web UI - WebSocket Client
 *
 * Handles real-time communication with ORION Core via WebSocket.
 */

class ORIONClient {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.messagesContainer = document.getElementById('messages');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.loadingIndicator = document.getElementById('loadingIndicator');

        this.setupEventListeners();
        this.connect();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/chat`;

        this.updateStatus('connecting', 'Connecting...');

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => this.onOpen();
            this.ws.onmessage = (event) => this.onMessage(event);
            this.ws.onclose = () => this.onClose();
            this.ws.onerror = (error) => this.onError(error);

        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.scheduleReconnect();
        }
    }

    onOpen() {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.updateStatus('connected', 'Connected');
        this.sendButton.disabled = false;
        this.messageInput.disabled = false;
        this.messageInput.focus();
    }

    onMessage(event) {
        const data = JSON.parse(event.data);
        console.log('Received:', data);

        const { response, type } = data;

        if (type === 'welcome') {
            this.addMessage('assistant', response, true);
        } else if (type === 'message') {
            this.addMessage('assistant', response);
            this.hideLoading();
        } else if (type === 'error') {
            this.addMessage('error', response);
            this.hideLoading();
        }
    }

    onClose() {
        console.log('WebSocket disconnected');
        this.updateStatus('disconnected', 'Disconnected');
        this.sendButton.disabled = true;
        this.scheduleReconnect();
    }

    onError(error) {
        console.error('WebSocket error:', error);
        this.updateStatus('error', 'Connection Error');
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

            this.updateStatus('reconnecting', `Reconnecting in ${delay/1000}s...`);

            setTimeout(() => this.connect(), delay);
        } else {
            this.updateStatus('failed', 'Connection Failed');
            this.addMessage('error', 'Failed to connect to ORION. Please refresh the page.');
        }
    }

    updateStatus(status, text) {
        this.statusDot.className = `status-dot status-${status}`;
        this.statusText.textContent = text;
    }

    setupEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());

        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    sendMessage() {
        const message = this.messageInput.value.trim();

        if (!message || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        // Add user message to UI
        this.addMessage('user', message);

        // Send to server
        this.ws.send(JSON.stringify({ message }));

        // Clear input
        this.messageInput.value = '';

        // Show loading indicator
        this.showLoading();
    }

    addMessage(role, content, isWelcome = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message message-${role}`;

        if (isWelcome) {
            messageDiv.classList.add('message-welcome');
        }

        // Add avatar
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.textContent = role === 'user' ? '👤' : '🌌';

        // Add content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Parse markdown-like formatting
        const formattedContent = this.formatContent(content);
        contentDiv.innerHTML = formattedContent;

        // Add timestamp
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = new Date().toLocaleTimeString();

        // Assemble message
        messageDiv.appendChild(avatarDiv);
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper';
        wrapper.appendChild(contentDiv);
        wrapper.appendChild(timeDiv);
        messageDiv.appendChild(wrapper);

        // Add to container
        this.messagesContainer.appendChild(messageDiv);

        // Scroll to bottom
        this.scrollToBottom();
    }

    formatContent(content) {
        // Convert markdown-like syntax to HTML
        return content
            // Bold (**text**)
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic (*text*)
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Code blocks (```code```)
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            // Inline code (`code`)
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // Links ([text](url))
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            // Newlines
            .replace(/\n/g, '<br>');
    }

    showLoading() {
        this.loadingIndicator.classList.remove('hidden');
    }

    hideLoading() {
        this.loadingIndicator.classList.add('hidden');
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
}

// Initialize client when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.orionClient = new ORIONClient();
});
