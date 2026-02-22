/**
 * Command Palette Component
 *
 * VS Code-style command palette with fuzzy search and keyboard navigation.
 * Activated with Cmd+K (or Ctrl+K on Windows).
 *
 * Features:
 * - Fuzzy search filtering
 * - Keyboard navigation (arrows, Enter, Escape)
 * - Categorized actions
 * - Keyboard shortcut hints
 */

class CommandPalette {
    constructor(app) {
        this.app = app;
        this.isOpen = false;
        this.selectedIndex = 0;
        this.filteredActions = [];

        // Define all available actions
        this.actions = [
            // Chat actions
            {
                id: 'chat.new',
                category: 'Chat',
                icon: '💬',
                title: 'New Conversation',
                description: 'Start a fresh conversation',
                shortcut: 'Cmd+L',
                action: () => this.app.chat.clearConversation()
            },
            {
                id: 'chat.clear',
                category: 'Chat',
                icon: '🗑️',
                title: 'Clear Messages',
                description: 'Remove all messages from view',
                action: () => this.app.chat.clearMessages()
            },
            {
                id: 'chat.copy',
                category: 'Chat',
                icon: '📋',
                title: 'Copy Conversation',
                description: 'Copy entire conversation to clipboard',
                action: () => this.copyConversation()
            },
            {
                id: 'chat.export',
                category: 'Chat',
                icon: '💾',
                title: 'Export Conversation',
                description: 'Download conversation as JSON',
                action: () => this.exportConversation()
            },

            // System actions
            {
                id: 'system.status',
                category: 'System',
                icon: '📊',
                title: 'Show System Status',
                description: 'Display full system information',
                action: () => this.showSystemStatus()
            },
            {
                id: 'system.health',
                category: 'System',
                icon: '💚',
                title: 'Check Service Health',
                description: 'Verify all services are running',
                action: () => this.checkHealth()
            },
            {
                id: 'system.refresh',
                category: 'System',
                icon: '🔄',
                title: 'Refresh Metrics',
                description: 'Force sidebar metrics update',
                action: () => this.app.sidebar.updateStatus()
            },

            // Navigation actions
            {
                id: 'nav.sidebar',
                category: 'Navigation',
                icon: '📌',
                title: 'Toggle Sidebar',
                description: 'Show or hide the sidebar',
                shortcut: 'Cmd+B',
                action: () => this.toggleSidebar()
            },
            {
                id: 'nav.focus',
                category: 'Navigation',
                icon: '✏️',
                title: 'Focus Input',
                description: 'Jump to the message input',
                shortcut: 'Cmd+K',
                action: () => this.focusInput()
            },
            {
                id: 'nav.top',
                category: 'Navigation',
                icon: '⬆️',
                title: 'Scroll to Top',
                description: 'Jump to the first message',
                action: () => this.scrollToTop()
            },
            {
                id: 'nav.bottom',
                category: 'Navigation',
                icon: '⬇️',
                title: 'Scroll to Bottom',
                description: 'Jump to the latest message',
                action: () => this.scrollToBottom()
            },

            // Debug actions
            {
                id: 'debug.breadcrumbs',
                category: 'Debug',
                icon: '🍞',
                title: 'Show Breadcrumbs',
                description: 'Display execution trail in console',
                action: () => this.showBreadcrumbs()
            },
            {
                id: 'debug.mode',
                category: 'Debug',
                icon: '🔧',
                title: 'Toggle Debug Mode',
                description: 'Enable verbose logging',
                action: () => this.toggleDebugMode()
            },
            {
                id: 'debug.clear',
                category: 'Debug',
                icon: '🧹',
                title: 'Clear Debug Trail',
                description: 'Reset breadcrumb history',
                action: () => this.clearBreadcrumbs()
            }
        ];

        this.init();
    }

    init() {
        this.createHTML();
        this.attachEventListeners();
    }

    createHTML() {
        const html = `
            <div class="command-palette-overlay" id="commandPaletteOverlay">
                <div class="command-palette-modal">
                    <div class="command-palette-search">
                        <input type="text"
                               id="commandPaletteInput"
                               placeholder="Type a command or search..."
                               autocomplete="off"
                               spellcheck="false">
                    </div>
                    <div class="command-palette-results" id="commandPaletteResults">
                        <!-- Results will be populated dynamically -->
                    </div>
                    <div class="command-palette-footer">
                        <div class="command-palette-footer-hint">
                            <span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span>
                            <span><kbd>↵</kbd> Select</span>
                            <span><kbd>Esc</kbd> Close</span>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', html);

        this.overlay = document.getElementById('commandPaletteOverlay');
        this.input = document.getElementById('commandPaletteInput');
        this.results = document.getElementById('commandPaletteResults');
    }

    attachEventListeners() {
        // Click outside to close
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });

        // Search input
        this.input.addEventListener('input', (e) => {
            this.filter(e.target.value);
        });

        // Keyboard navigation
        this.input.addEventListener('keydown', (e) => {
            switch (e.key) {
                case 'Escape':
                    e.preventDefault();
                    this.close();
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    this.selectNext();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.selectPrevious();
                    break;
                case 'Enter':
                    e.preventDefault();
                    this.executeSelected();
                    break;
            }
        });

        // Click on item
        this.results.addEventListener('click', (e) => {
            const item = e.target.closest('.command-palette-item');
            if (item) {
                const index = parseInt(item.dataset.index);
                this.selectedIndex = index;
                this.executeSelected();
            }
        });
    }

    open() {
        this.isOpen = true;
        this.overlay.classList.add('active');
        this.input.value = '';
        this.input.focus();
        this.filter(''); // Show all actions
    }

    close() {
        this.isOpen = false;
        this.overlay.classList.remove('active');
        this.selectedIndex = 0;
    }

    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    filter(query) {
        if (!query) {
            // Show all actions grouped by category
            this.filteredActions = this.actions;
        } else {
            // Fuzzy search
            const lowerQuery = query.toLowerCase();
            this.filteredActions = this.actions.filter(action => {
                const searchText = `${action.title} ${action.description} ${action.category}`.toLowerCase();
                return searchText.includes(lowerQuery);
            });
        }

        this.selectedIndex = 0;
        this.render();
    }

    render() {
        if (this.filteredActions.length === 0) {
            this.results.innerHTML = `
                <div class="command-palette-empty">
                    <div class="command-palette-empty-icon">🔍</div>
                    <div class="command-palette-empty-text">No commands found</div>
                </div>
            `;
            return;
        }

        // Group by category
        const categories = {};
        this.filteredActions.forEach(action => {
            if (!categories[action.category]) {
                categories[action.category] = [];
            }
            categories[action.category].push(action);
        });

        // Render grouped results
        let html = '';
        let itemIndex = 0;

        for (const [category, actions] of Object.entries(categories)) {
            html += `<div class="command-palette-category">${category}</div>`;

            actions.forEach(action => {
                const isSelected = itemIndex === this.selectedIndex;
                const shortcut = action.shortcut
                    ? `<span class="command-palette-item-shortcut">${action.shortcut}</span>`
                    : '';

                html += `
                    <div class="command-palette-item ${isSelected ? 'selected' : ''}" data-index="${itemIndex}">
                        <div class="command-palette-item-main">
                            <div class="command-palette-item-icon">${action.icon}</div>
                            <div class="command-palette-item-text">
                                <div class="command-palette-item-title">${action.title}</div>
                                <div class="command-palette-item-description">${action.description}</div>
                            </div>
                        </div>
                        ${shortcut}
                    </div>
                `;
                itemIndex++;
            });
        }

        this.results.innerHTML = html;

        // Scroll selected item into view
        const selectedElement = this.results.querySelector('.command-palette-item.selected');
        if (selectedElement) {
            selectedElement.scrollIntoView({ block: 'nearest' });
        }
    }

    selectNext() {
        if (this.selectedIndex < this.filteredActions.length - 1) {
            this.selectedIndex++;
            this.render();
        }
    }

    selectPrevious() {
        if (this.selectedIndex > 0) {
            this.selectedIndex--;
            this.render();
        }
    }

    executeSelected() {
        if (this.filteredActions.length === 0) return;

        const action = this.filteredActions[this.selectedIndex];
        if (action && action.action) {
            this.close();
            action.action();
        }
    }

    // Action implementations
    copyConversation() {
        const messages = this.app.chat.messages;
        const text = messages.map(msg => `${msg.type === 'user' ? 'You' : 'ORION'}: ${msg.content}`).join('\n\n');
        navigator.clipboard.writeText(text);
        this.app.showNotification('Conversation copied to clipboard');
    }

    exportConversation() {
        const messages = this.app.chat.messages;
        const data = JSON.stringify(messages, null, 2);
        const blob = new Blob([data], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `orion-conversation-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        this.app.showNotification('Conversation exported');
    }

    showSystemStatus() {
        const message = "Show me full system status";
        this.app.chat.sendMessage(message);
    }

    checkHealth() {
        const message = "Check all service health";
        this.app.chat.sendMessage(message);
    }

    toggleSidebar() {
        this.app.sidebar.toggle();
    }

    focusInput() {
        this.app.chat.focusInput();
    }

    scrollToTop() {
        const messagesContainer = document.getElementById('chatMessages');
        if (messagesContainer) {
            messagesContainer.scrollTop = 0;
        }
    }

    scrollToBottom() {
        const messagesContainer = document.getElementById('chatMessages');
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    showBreadcrumbs() {
        console.log('=== ORION Debug Breadcrumbs ===');
        console.log(this.app.breadcrumbs);
        this.app.showNotification('Breadcrumbs logged to console');
    }

    toggleDebugMode() {
        window.debugMode = !window.debugMode;
        const status = window.debugMode ? 'enabled' : 'disabled';
        this.app.showNotification(`Debug mode ${status}`);
        console.log(`Debug mode ${status}`);
    }

    clearBreadcrumbs() {
        if (this.app.breadcrumbs) {
            this.app.breadcrumbs.length = 0;
            this.app.showNotification('Breadcrumbs cleared');
        }
    }
}

// Export for use in app.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CommandPalette;
}
