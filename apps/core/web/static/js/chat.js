/**
 * ORION Core - Chat Component
 * Handles chat UI, messages, and user input
 */

class Chat {
    constructor() {
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.messagesContainer = document.getElementById('messages');
        this.quickStart = document.getElementById('quickStart');
        this.loadingIndicator = document.getElementById('loadingIndicator');
        this.suggestions = document.getElementById('suggestions');

        // Tree-based conversation storage
        this.messages = [];  // Array of all messages in the tree
        this.currentMessageId = null;  // Current position in conversation tree
        this.rootMessageId = null;  // Root of conversation tree
        this.isWaitingForResponse = false;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadHistory();
    }

    setupEventListeners() {
        // Send button
        this.sendBtn.addEventListener('click', () => this.handleSend());

        // Enter key in input
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSend();
            }
        });

        // Enable send button when text entered
        this.messageInput.addEventListener('input', () => {
            this.sendBtn.disabled = !this.messageInput.value.trim();
        });

        // Quick start hint buttons
        document.querySelectorAll('.hint-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const cmd = btn.dataset.cmd;
                if (cmd) {
                    this.messageInput.value = cmd;
                    this.handleSend();
                }
            });
        });
    }

    handleSend() {
        const message = this.messageInput.value.trim();

        if (!message || this.isWaitingForResponse) {
            return;
        }

        // Add user message to UI
        this.addMessage('user', message);

        // Clear input
        this.messageInput.value = '';
        this.sendBtn.disabled = true;

        // Send message via WebSocket (handled by app.js)
        if (window.orion && window.orion.ws) {
            window.orion.sendMessage(message);
            this.showLoading();
            this.isWaitingForResponse = true;
        } else {
            this.addMessage('error', 'Connection error. Please refresh the page.');
        }
    }

    addMessage(role, content, metadata = {}) {
        const messageId = this.generateMessageId();
        const message = {
            id: messageId,
            parentId: this.currentMessageId,
            role,
            content,
            timestamp: Date.now(),
            ...metadata
        };

        this.messages.push(message);
        this.currentMessageId = messageId;

        // Set root if this is the first message
        if (!this.rootMessageId) {
            this.rootMessageId = messageId;
        }

        this.renderConversation();
        this.saveHistory();

        // Hide quick start if messages exist
        if (this.messages.length > 0) {
            utils.toggleElement(this.quickStart, false);
        }

        // Auto-scroll to bottom
        utils.scrollToBottom(this.messagesContainer);
    }

    generateMessageId() {
        return `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }

    renderMessage(message, isCurrent = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message message-${message.role}`;
        messageDiv.dataset.messageId = message.id;

        if (isCurrent) {
            messageDiv.classList.add('message-current');
        }

        // Avatar
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';

        const avatars = {
            user: '👤',
            assistant: '🌌',
            system: 'ℹ️',
            error: '⚠️'
        };
        avatarDiv.textContent = avatars[message.role] || '💬';

        // Wrapper
        const wrapperDiv = document.createElement('div');
        wrapperDiv.className = 'message-wrapper';

        // Content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Format content (markdown support via marked.js)
        if (window.marked) {
            try {
                contentDiv.innerHTML = marked.parse(message.content);
            } catch (e) {
                contentDiv.textContent = message.content;
            }
        } else {
            contentDiv.textContent = message.content;
        }

        // Timestamp
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = utils.getTimestamp();

        // Branch navigation controls
        const siblings = this.getSiblings(message.id);
        const children = this.getChildren(message.id);

        // Only show navigation if there are multiple siblings OR it's the last message in this branch
        const isLastInBranch = children.length === 0 && message.id === this.currentMessageId;
        if (siblings.length > 1 || isLastInBranch) {
            const navDiv = this.createNavigationControls(message, siblings, children);
            wrapperDiv.appendChild(navDiv);
        }

        // Assemble
        wrapperDiv.appendChild(contentDiv);
        wrapperDiv.appendChild(timeDiv);
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(wrapperDiv);

        return messageDiv;
    }

    createNavigationControls(message, siblings, children) {
        const navDiv = document.createElement('div');
        navDiv.className = 'message-navigation';

        // Sibling navigation (alternate responses)
        if (siblings.length > 1) {
            const siblingIndex = siblings.findIndex(s => s.id === message.id);
            const branchDiv = document.createElement('div');
            branchDiv.className = 'branch-indicator';
            branchDiv.innerHTML = `
                <button class="nav-btn nav-prev" data-message-id="${message.id}" ${siblingIndex === 0 ? 'disabled' : ''}>
                    ←
                </button>
                <span class="branch-count">${siblingIndex + 1} / ${siblings.length}</span>
                <button class="nav-btn nav-next" data-message-id="${message.id}" ${siblingIndex === siblings.length - 1 ? 'disabled' : ''}>
                    →
                </button>
            `;
            navDiv.appendChild(branchDiv);

            // Add event listeners
            branchDiv.querySelector('.nav-prev').addEventListener('click', () => {
                if (siblingIndex > 0) {
                    this.navigateToMessage(siblings[siblingIndex - 1].id);
                }
            });
            branchDiv.querySelector('.nav-next').addEventListener('click', () => {
                if (siblingIndex < siblings.length - 1) {
                    this.navigateToMessage(siblings[siblingIndex + 1].id);
                }
            });
        }

        // Action buttons (only for assistant messages at the end of the branch)
        const isLastInBranch = children.length === 0 && message.id === this.currentMessageId;
        if (message.role === 'assistant' && isLastInBranch) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';

            // Check if we can go back to parent
            const parent = this.getParent(message.id);
            const parentBtn = parent ? `
                <button class="action-btn parent-btn" data-message-id="${parent.id}" title="Go back to previous checkpoint">
                    ⏮️ Back
                </button>
            ` : '';

            actionsDiv.innerHTML = `
                ${parentBtn}
                <button class="action-btn regenerate-btn" data-message-id="${message.id}" title="Create alternate response at this checkpoint">
                    🔄 Alternate
                </button>
                <button class="action-btn edit-btn" data-message-id="${message.id}" title="Edit your original prompt and branch from there">
                    ✏️ Edit Prompt
                </button>
            `;
            navDiv.appendChild(actionsDiv);

            // Add event listeners
            if (parent) {
                actionsDiv.querySelector('.parent-btn').addEventListener('click', () => {
                    this.navigateToMessage(parent.id);
                });
            }
            actionsDiv.querySelector('.regenerate-btn').addEventListener('click', () => {
                this.regenerateResponse(message.parentId);
            });
            actionsDiv.querySelector('.edit-btn').addEventListener('click', () => {
                this.editMessage(message.id);
            });
        }

        // For user messages, show continuation option
        if (message.role === 'user') {
            const children = this.getChildren(message.id);
            if (children.length > 0) {
                const continueDiv = document.createElement('div');
                continueDiv.className = 'message-actions';
                continueDiv.innerHTML = `
                    <button class="action-btn continue-btn" title="Continue from this checkpoint">
                        ▶️ Continue (${children.length} response${children.length > 1 ? 's' : ''})
                    </button>
                `;
                navDiv.appendChild(continueDiv);

                continueDiv.querySelector('.continue-btn').addEventListener('click', () => {
                    this.navigateToMessage(children[0].id);
                });
            }
        }

        return navDiv;
    }

    renderConversation() {
        // Clear existing messages
        this.messagesContainer.innerHTML = '';

        // Get path from root to current message
        const messagePath = this.getMessagePath(this.currentMessageId);

        // Render each message in the path
        messagePath.forEach((message, index) => {
            const isCurrent = (index === messagePath.length - 1);
            const messageEl = this.renderMessage(message, isCurrent);

            // Add checkpoint/rewind button for user messages
            if (message.role === 'user' && index < messagePath.length - 1) {
                const checkpointBtn = this.createCheckpointButton(message, index);
                messageEl.querySelector('.message-wrapper').appendChild(checkpointBtn);
            }

            this.messagesContainer.appendChild(messageEl);
        });
    }

    createCheckpointButton(message, index) {
        const children = this.getChildren(message.id);
        const checkpointDiv = document.createElement('div');
        checkpointDiv.className = 'checkpoint-controls';

        const branchCount = children.length;
        const branchText = branchCount > 1 ? ` (${branchCount} branches)` : '';

        checkpointDiv.innerHTML = `
            <button class="checkpoint-btn" data-message-id="${message.id}" title="Rewind to this checkpoint">
                ⏮️ Rewind to checkpoint #${index + 1}${branchText}
            </button>
        `;

        checkpointDiv.querySelector('.checkpoint-btn').addEventListener('click', () => {
            this.rewindToCheckpoint(message.id);
        });

        return checkpointDiv;
    }

    rewindToCheckpoint(messageId) {
        // Find the first assistant response after this user message
        const children = this.getChildren(messageId);
        if (children.length > 0) {
            // Navigate to the first response (or currently selected one)
            const currentPath = this.getMessagePath(this.currentMessageId);
            const targetChild = currentPath.find(m => m.parentId === messageId) || children[0];
            this.navigateToMessage(targetChild.id);
        } else {
            // No responses yet, just navigate to this message
            this.navigateToMessage(messageId);
        }
    }

    handleAssistantMessage(data) {
        this.hideLoading();
        this.isWaitingForResponse = false;

        const { response, type, metadata } = data;

        if (type === 'error') {
            this.addMessage('error', response, metadata);
        } else {
            this.addMessage('assistant', response, metadata);
        }

        // Update suggestions if provided
        if (metadata && metadata.suggestions) {
            this.updateSuggestions(metadata.suggestions);
        }
    }

    // ========================================
    // Streaming message handlers
    // ========================================

    /**
     * Handle streaming progress message
     * Shows progress indicator above streaming message
     */
    handleProgressMessage(data) {
        const { message, stage } = data;

        // Hide default loading, show custom progress
        this.hideLoading();

        // Get or create streaming message container
        let streamingDiv = this.messagesContainer.querySelector('.message-streaming');
        if (!streamingDiv) {
            streamingDiv = this.createStreamingMessage();
            this.messagesContainer.appendChild(streamingDiv);
            utils.scrollToBottom(this.messagesContainer);
        }

        // Update progress indicator
        const progressDiv = streamingDiv.querySelector('.streaming-progress');
        if (progressDiv) {
            progressDiv.textContent = message;
            progressDiv.dataset.stage = stage || '';
        }
    }

    /**
     * Handle streaming token (content chunk)
     * Appends to existing streaming message
     */
    handleTokenMessage(data) {
        const { content } = data;

        // Get or create streaming message container
        let streamingDiv = this.messagesContainer.querySelector('.message-streaming');
        if (!streamingDiv) {
            streamingDiv = this.createStreamingMessage();
            this.messagesContainer.appendChild(streamingDiv);
        }

        // Hide progress indicator once tokens start arriving
        const progressDiv = streamingDiv.querySelector('.streaming-progress');
        if (progressDiv && !progressDiv.classList.contains('hidden')) {
            progressDiv.classList.add('hidden');
        }

        // Append token to content area
        const contentDiv = streamingDiv.querySelector('.streaming-content');
        if (contentDiv) {
            // Accumulate text content
            if (!contentDiv.dataset.text) {
                contentDiv.dataset.text = '';
            }
            contentDiv.dataset.text += content;

            // Render markdown if available (with throttling for performance)
            if (window.marked) {
                this.throttledRenderStreamingContent(contentDiv);
            } else {
                // Fallback: plain text
                contentDiv.textContent = contentDiv.dataset.text;
            }

            // Auto-scroll during streaming
            utils.scrollToBottom(this.messagesContainer);
        }
    }

    /**
     * Handle streaming complete message
     * Finalizes streaming and converts to permanent message
     */
    handleCompleteMessage(data) {
        const { intent, confidence, latency_ms } = data;

        this.hideLoading();
        this.isWaitingForResponse = false;

        // Get streaming message
        const streamingDiv = this.messagesContainer.querySelector('.message-streaming');
        if (streamingDiv) {
            const contentDiv = streamingDiv.querySelector('.streaming-content');
            const finalContent = contentDiv ? contentDiv.dataset.text : '';

            // Remove streaming message
            streamingDiv.remove();

            // Add as permanent message
            if (finalContent) {
                this.addMessage('assistant', finalContent, {
                    intent,
                    confidence,
                    latency_ms
                });
            }
        }
    }

    /**
     * Handle sources from RAG knowledge system
     * Appends expandable sources section
     */
    handleSourcesMessage(data) {
        const { sources, count } = data;

        if (!sources || sources.length === 0) {
            return;
        }

        // Get the last assistant message
        const messages = this.messagesContainer.querySelectorAll('.message-assistant');
        const lastMessage = messages[messages.length - 1];

        if (!lastMessage) {
            return;
        }

        // Create sources section
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'message-sources';
        sourcesDiv.innerHTML = `
            <details>
                <summary>📚 Sources (${count})</summary>
                <div class="sources-list">
                    ${sources.map((source, idx) => `
                        <div class="source-item">
                            <span class="source-number">[${idx + 1}]</span>
                            <span class="source-title">${this.escapeHtml(source.title || 'Untitled')}</span>
                            ${source.score !== undefined ? `<span class="source-score">${(source.score * 100).toFixed(0)}%</span>` : ''}
                        </div>
                    `).join('')}
                </div>
            </details>
        `;

        lastMessage.querySelector('.message-wrapper').appendChild(sourcesDiv);
    }

    /**
     * Create streaming message container
     */
    createStreamingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message message-assistant message-streaming';

        // Avatar
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.textContent = '🌌';

        // Wrapper
        const wrapperDiv = document.createElement('div');
        wrapperDiv.className = 'message-wrapper';

        // Progress indicator
        const progressDiv = document.createElement('div');
        progressDiv.className = 'streaming-progress';
        progressDiv.textContent = '⏳ Processing...';

        // Content area
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content streaming-content';
        contentDiv.dataset.text = '';

        // Cursor indicator
        const cursorSpan = document.createElement('span');
        cursorSpan.className = 'streaming-cursor';
        cursorSpan.textContent = '▋';

        wrapperDiv.appendChild(progressDiv);
        wrapperDiv.appendChild(contentDiv);
        contentDiv.appendChild(cursorSpan);

        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(wrapperDiv);

        return messageDiv;
    }

    /**
     * Throttled markdown rendering for streaming
     * Renders every 100ms to avoid performance issues
     */
    throttledRenderStreamingContent(contentDiv) {
        if (!this._renderThrottle) {
            this._renderThrottle = null;
        }

        if (this._renderThrottle) {
            clearTimeout(this._renderThrottle);
        }

        this._renderThrottle = setTimeout(() => {
            try {
                const cursor = contentDiv.querySelector('.streaming-cursor');
                const text = contentDiv.dataset.text || '';
                contentDiv.innerHTML = marked.parse(text);

                // Re-add cursor
                if (cursor) {
                    contentDiv.appendChild(cursor);
                }
            } catch (e) {
                console.warn('Markdown rendering error:', e);
                contentDiv.textContent = contentDiv.dataset.text;
            }
        }, 100);
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    updateSuggestions(suggestions) {
        if (!suggestions || suggestions.length === 0) {
            utils.toggleElement(this.suggestions, false);
            return;
        }

        this.suggestions.innerHTML = suggestions.map(suggestion => `
            <button class="suggestion-btn" data-cmd="${suggestion}">
                ${suggestion}
            </button>
        `).join('');

        // Add click handlers
        this.suggestions.querySelectorAll('.suggestion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.messageInput.value = btn.dataset.cmd;
                this.handleSend();
            });
        });

        utils.toggleElement(this.suggestions, true);
    }

    showLoading() {
        utils.toggleElement(this.loadingIndicator, true);
    }

    hideLoading() {
        utils.toggleElement(this.loadingIndicator, false);
    }

    // Tree navigation helper methods
    getMessagePath(messageId) {
        const path = [];
        let currentId = messageId;

        while (currentId) {
            const message = this.messages.find(m => m.id === currentId);
            if (!message) break;
            path.unshift(message);
            currentId = message.parentId;
        }

        return path;
    }

    getSiblings(messageId) {
        const message = this.messages.find(m => m.id === messageId);
        if (!message) return [];

        return this.messages.filter(m => m.parentId === message.parentId);
    }

    getChildren(messageId) {
        return this.messages.filter(m => m.parentId === messageId);
    }

    getParent(messageId) {
        const message = this.messages.find(m => m.id === messageId);
        return message ? this.messages.find(m => m.id === message.parentId) : null;
    }

    navigateToMessage(messageId) {
        this.currentMessageId = messageId;
        this.renderConversation();
        this.saveHistory();
        utils.scrollToBottom(this.messagesContainer);
    }

    regenerateResponse(parentMessageId) {
        // Navigate to the parent (user message)
        this.navigateToMessage(parentMessageId);

        // Find the user message content
        const parentMessage = this.messages.find(m => m.id === parentMessageId);
        if (!parentMessage || parentMessage.role !== 'user') {
            console.error('Cannot regenerate: parent is not a user message');
            return;
        }

        // Send the same message again via WebSocket
        if (window.orion && window.orion.ws) {
            window.orion.sendMessage(parentMessage.content);
            this.showLoading();
            this.isWaitingForResponse = true;
        }
    }

    editMessage(messageId) {
        const message = this.messages.find(m => m.id === messageId);
        if (!message) return;

        // For assistant messages, edit the parent user prompt instead
        if (message.role === 'assistant') {
            const parentMessage = this.getParent(messageId);
            if (!parentMessage || parentMessage.role !== 'user') {
                alert('Cannot find the original prompt to edit');
                return;
            }

            // Prompt to edit the user's original message
            const newContent = prompt('Edit your original prompt and create new branch:', parentMessage.content);
            if (newContent && newContent.trim() && newContent !== parentMessage.content) {
                // Navigate to the parent's parent (the message before the user prompt)
                this.navigateToMessage(parentMessage.parentId || parentMessage.id);

                // Send the edited prompt as a new message
                if (window.orion && window.orion.ws) {
                    window.orion.sendMessage(newContent.trim());
                    this.showLoading();
                    this.isWaitingForResponse = true;
                }
            }
        } else {
            // For user messages, allow direct editing
            const newContent = prompt('Edit your prompt:', message.content);
            if (newContent && newContent.trim() && newContent !== message.content) {
                // Create a new sibling message with edited content
                const editedMessageId = this.generateMessageId();
                const editedMessage = {
                    id: editedMessageId,
                    parentId: message.parentId,
                    role: message.role,
                    content: newContent.trim(),
                    timestamp: Date.now(),
                    edited: true
                };

                this.messages.push(editedMessage);
                this.navigateToMessage(editedMessageId);

                // If this was a user message, we might want to get a response
                if (window.orion && window.orion.ws) {
                    window.orion.sendMessage(newContent.trim());
                    this.showLoading();
                    this.isWaitingForResponse = true;
                }
            }
        }
    }

    clearChat() {
        this.messages = [];
        this.currentMessageId = null;
        this.rootMessageId = null;
        this.messagesContainer.innerHTML = '';
        this.saveHistory();
        utils.toggleElement(this.quickStart, true);
        utils.toggleElement(this.suggestions, false);
    }

    saveHistory() {
        // Save conversation tree structure
        const conversationData = {
            messages: this.messages,
            currentMessageId: this.currentMessageId,
            rootMessageId: this.rootMessageId,
            timestamp: Date.now()
        };
        utils.storage.set('chat-history', conversationData);
    }

    loadHistory() {
        // Don't auto-load old conversations - start fresh each time
        // Users can manually load history if needed via export/import
        return;
    }

    exportHistory() {
        // Export the current conversation path
        const messagePath = this.getMessagePath(this.currentMessageId);
        const markdown = messagePath.map(msg => {
            const time = new Date(msg.timestamp).toLocaleString();
            const role = msg.role === 'user' ? 'You' : 'ORION';
            const siblings = this.getSiblings(msg.id);
            const branchInfo = siblings.length > 1 ?
                ` [Branch ${siblings.findIndex(s => s.id === msg.id) + 1}/${siblings.length}]` : '';
            return `**${role}** (${time})${branchInfo}:\n${msg.content}\n`;
        }).join('\n---\n\n');

        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `orion-chat-${Date.now()}.md`;
        a.click();
        URL.revokeObjectURL(url);
    }
}

// Export for use in app.js
window.Chat = Chat;
