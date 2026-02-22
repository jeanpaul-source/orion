/**
 * ORION Core - WebSocket Handler
 * Manages WebSocket connection with automatic reconnection
 */

class WebSocketClient {
    constructor(url, options = {}) {
        this.url = url;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.reconnectDelay = options.reconnectDelay || 1000;
        this.maxReconnectDelay = options.maxReconnectDelay || 30000;

        this.handlers = {
            open: [],
            message: [],
            close: [],
            error: [],
            reconnecting: []
        };

        this.isIntentionallyClosed = false;
    }

    /**
     * Connect to WebSocket
     */
    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.warn('WebSocket already connected');
            return;
        }

        this.isIntentionallyClosed = false;

        try {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = (event) => this.handleOpen(event);
            this.ws.onmessage = (event) => this.handleMessage(event);
            this.ws.onclose = (event) => this.handleClose(event);
            this.ws.onerror = (event) => this.handleError(event);

        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.scheduleReconnect();
        }
    }

    /**
     * Disconnect from WebSocket
     */
    disconnect() {
        this.isIntentionallyClosed = true;

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Send message through WebSocket
     */
    send(data) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error('WebSocket not connected');
            return false;
        }

        try {
            const message = typeof data === 'string' ? data : JSON.stringify(data);
            this.ws.send(message);
            return true;
        } catch (error) {
            console.error('Error sending message:', error);
            return false;
        }
    }

    /**
     * Register event handler
     */
    on(event, handler) {
        if (this.handlers[event]) {
            this.handlers[event].push(handler);
        }
    }

    /**
     * Unregister event handler
     */
    off(event, handler) {
        if (this.handlers[event]) {
            this.handlers[event] = this.handlers[event].filter(h => h !== handler);
        }
    }

    /**
     * Trigger event handlers
     */
    trigger(event, data) {
        if (this.handlers[event]) {
            this.handlers[event].forEach(handler => handler(data));
        }
    }

    /**
     * Handle WebSocket open
     */
    handleOpen(event) {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.trigger('open', event);
    }

    /**
     * Handle WebSocket message
     */
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            this.trigger('message', data);
        } catch (error) {
            console.error('Error parsing message:', error);
            this.trigger('message', { error: 'Invalid message format' });
        }
    }

    /**
     * Handle WebSocket close
     */
    handleClose(event) {
        console.log('WebSocket disconnected');
        this.trigger('close', event);

        if (!this.isIntentionallyClosed) {
            this.scheduleReconnect();
        }
    }

    /**
     * Handle WebSocket error
     */
    handleError(event) {
        console.error('WebSocket error:', event);
        this.trigger('error', event);
    }

    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect() {
        if (this.isIntentionallyClosed) {
            return;
        }

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;

        // Exponential backoff with max delay
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        this.trigger('reconnecting', {
            attempt: this.reconnectAttempts,
            maxAttempts: this.maxReconnectAttempts,
            delay
        });

        setTimeout(() => this.connect(), delay);
    }

    /**
     * Get connection state
     */
    getState() {
        if (!this.ws) return 'CLOSED';

        const states = ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'];
        return states[this.ws.readyState] || 'UNKNOWN';
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
}

// Export for use in other modules
window.WebSocketClient = WebSocketClient;
