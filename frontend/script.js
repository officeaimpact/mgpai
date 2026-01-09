/**
 * MGP Chat Widget - JavaScript
 * Сеть Магазинов Горящих Путевок
 */

(function() {
    'use strict';

    // ============================================
    // CONFIGURATION
    // ============================================
    const CONFIG = {
        apiUrl: 'http://localhost:8000/api/v1/chat',
        botName: 'MGP AI',
        typingDelay: 500,
        messageDelay: 100
    };

    // ============================================
    // STATE
    // ============================================
    let conversationId = null;
    let isTyping = false;

    // ============================================
    // DOM ELEMENTS
    // ============================================
    const elements = {
        launcher: document.getElementById('chatLauncher'),
        widget: document.getElementById('chatWidget'),
        closeBtn: document.getElementById('chatClose'),
        messages: document.getElementById('chatMessages'),
        form: document.getElementById('chatForm'),
        input: document.getElementById('chatInput'),
        sendBtn: document.getElementById('chatSend'),
        typingIndicator: document.getElementById('typingIndicator')
    };

    // ============================================
    // UTILITIES
    // ============================================
    
    /**
     * Generate UUID v4
     */
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    /**
     * Format price with spaces
     */
    function formatPrice(price) {
        if (!price) return '—';
        return price.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    }

    /**
     * Format date from ISO string
     */
    function formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('ru-RU', { 
            day: '2-digit', 
            month: '2-digit', 
            year: 'numeric' 
        });
    }

    /**
     * Generate star rating
     */
    function generateStars(count) {
        return '★'.repeat(count || 0);
    }

    /**
     * Scroll messages to bottom
     */
    function scrollToBottom() {
        setTimeout(() => {
            elements.messages.scrollTop = elements.messages.scrollHeight;
        }, CONFIG.messageDelay);
    }

    /**
     * Escape HTML
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Parse markdown-like formatting
     */
    function parseFormatting(text) {
        return text
            // Bold: **text** or __text__
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/__(.*?)__/g, '<strong>$1</strong>')
            // Italic: *text* or _text_
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/_(.*?)_/g, '<em>$1</em>')
            // Line breaks
            .replace(/\n/g, '<br>');
    }

    // ============================================
    // CHAT TOGGLE
    // ============================================
    
    function toggleChat() {
        const isOpen = elements.widget.classList.contains('open');
        
        if (isOpen) {
            closeChat();
        } else {
            openChat();
        }
    }

    function openChat() {
        elements.widget.classList.add('open');
        elements.launcher.classList.add('active');
        elements.input.focus();
        
        // Generate conversation ID if not exists
        if (!conversationId) {
            conversationId = generateUUID();
            console.log('New conversation:', conversationId);
        }
    }

    function closeChat() {
        elements.widget.classList.remove('open');
        elements.launcher.classList.remove('active');
    }

    // ============================================
    // MESSAGE RENDERING
    // ============================================

    /**
     * Create message bubble HTML
     */
    function createMessageHTML(role, content) {
        const isBot = role === 'bot' || role === 'assistant';
        const messageClass = isBot ? 'bot-message' : 'user-message';
        
        const avatarSvg = isBot 
            ? `<svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
               </svg>`
            : `<svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
               </svg>`;

        const formattedContent = parseFormatting(content);

        return `
            <div class="message ${messageClass}">
                <div class="message-avatar">${avatarSvg}</div>
                <div class="message-content">
                    <div class="message-bubble">${formattedContent}</div>
                </div>
            </div>
        `;
    }

    /**
     * Add message to chat
     */
    function addMessage(role, content) {
        const html = createMessageHTML(role, content);
        elements.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
    }

    /**
     * Create tour card HTML
     */
    function createTourCardHTML(tour) {
        const imageUrl = tour.hotel_photo || '';
        const hasImage = imageUrl && imageUrl.length > 0;
        
        const imageHtml = hasImage 
            ? `<img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(tour.hotel_name)}" class="tour-card-image" onerror="this.classList.add('placeholder'); this.innerHTML='🏨';">`
            : `<div class="tour-card-image placeholder">🏨</div>`;

        const stars = generateStars(tour.hotel_stars);
        const price = formatPrice(tour.price);
        const pricePerPerson = tour.price_per_person ? formatPrice(tour.price_per_person) : null;
        const dateFrom = formatDate(tour.date_from);
        
        const location = [tour.country, tour.resort].filter(Boolean).join(', ');
        const hotelLink = tour.hotel_link || '#';

        return `
            <div class="tour-card">
                ${imageHtml}
                <div class="tour-card-body">
                    <div class="tour-card-price">
                        ${price} ₽ 
                        ${pricePerPerson ? `<span>/ ${pricePerPerson} ₽ за чел.</span>` : '<span>за номер</span>'}
                    </div>
                    <ul class="tour-card-details">
                        <li>
                            <span class="icon">📍</span>
                            <span class="text">${escapeHtml(location)}</span>
                        </li>
                        <li>
                            <span class="icon">📅</span>
                            <span class="text">${dateFrom}, <strong>${tour.nights || 7} ночей</strong></span>
                        </li>
                        <li>
                            <span class="icon">🏨</span>
                            <span class="text"><strong>${escapeHtml(tour.hotel_name)}</strong> ${stars}</span>
                        </li>
                        <li>
                            <span class="icon">🛏</span>
                            <span class="text">${escapeHtml(tour.room_type || 'Standard')}</span>
                        </li>
                        <li>
                            <span class="icon">🍽</span>
                            <span class="text">${escapeHtml(tour.food_type || 'AI')}</span>
                        </li>
                    </ul>
                    <div class="tour-card-actions">
                        <a href="${escapeHtml(hotelLink)}" class="btn-book" target="_blank" rel="noopener">
                            Оформить тур
                        </a>
                        <button class="btn-details" onclick="window.MGPChat.bookTour('${escapeHtml(tour.id || '')}')">
                            Забронировать
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Render tour cards carousel
     */
    function renderTourCards(cards) {
        if (!cards || cards.length === 0) return;

        const cardsHtml = cards.map(card => createTourCardHTML(card)).join('');
        
        const containerHtml = `
            <div class="message bot-message">
                <div class="message-avatar">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                    </svg>
                </div>
                <div class="message-content">
                    <div class="tour-cards-container">
                        <div class="tour-cards-wrapper">
                            ${cardsHtml}
                        </div>
                        ${cards.length > 1 ? `
                            <div class="tour-cards-nav">
                                <span>← Листайте для просмотра всех ${cards.length} предложений →</span>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;

        elements.messages.insertAdjacentHTML('beforeend', containerHtml);
        scrollToBottom();
    }

    // ============================================
    // TYPING INDICATOR
    // ============================================

    function showTyping() {
        isTyping = true;
        elements.typingIndicator.classList.add('show');
        scrollToBottom();
    }

    function hideTyping() {
        isTyping = false;
        elements.typingIndicator.classList.remove('show');
    }

    // ============================================
    // API COMMUNICATION
    // ============================================

    /**
     * Send message to API
     */
    async function sendMessage(text) {
        if (!text.trim() || isTyping) return;

        // Add user message to chat
        addMessage('user', text);
        
        // Clear input
        elements.input.value = '';
        elements.sendBtn.disabled = true;

        // Show typing indicator
        showTyping();

        try {
            const response = await fetch(CONFIG.apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: text,
                    conversation_id: conversationId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            // Update conversation ID from response
            if (data.conversation_id) {
                conversationId = data.conversation_id;
            }

            // Hide typing indicator
            hideTyping();

            // Add bot response
            if (data.reply) {
                addMessage('bot', data.reply);
            }

            // Render tour cards if present
            if (data.tour_cards && data.tour_cards.length > 0) {
                setTimeout(() => {
                    renderTourCards(data.tour_cards);
                }, CONFIG.typingDelay);
            }

        } catch (error) {
            console.error('Chat error:', error);
            hideTyping();
            addMessage('bot', '😔 Извините, произошла ошибка соединения. Пожалуйста, попробуйте позже или позвоните нам по телефону.');
        } finally {
            elements.sendBtn.disabled = false;
            elements.input.focus();
        }
    }

    /**
     * Book tour action
     */
    function bookTour(tourId) {
        const message = tourId 
            ? `Хочу забронировать тур ${tourId}`
            : 'Хочу забронировать тур';
        sendMessage(message);
    }

    // ============================================
    // EVENT HANDLERS
    // ============================================

    function handleSubmit(e) {
        e.preventDefault();
        const text = elements.input.value.trim();
        if (text) {
            sendMessage(text);
        }
    }

    function handleKeyPress(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    }

    // ============================================
    // INITIALIZATION
    // ============================================

    function init() {
        // Check if all elements exist
        if (!elements.launcher || !elements.widget) {
            console.error('MGP Chat: Required elements not found');
            return;
        }

        // Event listeners
        elements.launcher.addEventListener('click', toggleChat);
        elements.closeBtn.addEventListener('click', closeChat);
        elements.form.addEventListener('submit', handleSubmit);
        elements.input.addEventListener('keypress', handleKeyPress);

        // Close on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && elements.widget.classList.contains('open')) {
                closeChat();
            }
        });

        // Generate initial conversation ID
        conversationId = generateUUID();

        console.log('MGP Chat Widget initialized');
        console.log('Conversation ID:', conversationId);
    }

    // ============================================
    // PUBLIC API
    // ============================================
    
    window.MGPChat = {
        open: openChat,
        close: closeChat,
        toggle: toggleChat,
        send: sendMessage,
        bookTour: bookTour,
        getConversationId: () => conversationId
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
