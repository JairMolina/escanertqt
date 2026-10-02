/**
 * ws_client.js - Cliente WebSocket Robusto con Reconexión y Heartbeat
 * Escaner TQT - Comunicación en tiempo real móvil <-> monitor PC
 */

class TQTWebSocketClient {
    constructor(clientType = 'operador_movil') {
        this.clientType = clientType;
        this.socket = null;
        this.listeners = new Map();
        this.statusListeners = new Set();
        this.reconnectAttempts = 0;
        this.maxReconnectDelay = 8000;
        this.reconnectTimer = null;
        this.heartbeatTimer = null;
        this.isExplicitClose = false;
        this.isConnected = false;
        this.lastMessageAt = 0;

        // Reconectar de inmediato al volver la red o al reactivar la pestaña (sin esperar el backoff).
        window.addEventListener('online', () => this.reconnectNow());
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) this.reconnectNow();
        });
    }

    /** Fuerza un reintento inmediato si no hay conexión viva. */
    reconnectNow() {
        if (this.isExplicitClose) return;
        const s = this.socket;
        if (s && s.readyState === WebSocket.OPEN && Date.now() - this.lastMessageAt < 60000) return;
        if (s && s.readyState === WebSocket.CONNECTING) return;
        if (s) { try { s.onclose = null; s.close(); } catch (e) { /* ya cerrado */ } }
        this.socket = null;
        this.isConnected = false;
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.connect();
    }

    /**
     * Inicia conexión WebSocket
     */
    connect() {
        if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
            return;
        }

        this.isExplicitClose = false;
        this._notifyStatus('connecting');

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const url = `${protocol}//${host}/ws?client_type=${encodeURIComponent(this.clientType)}`;

        console.log(`[WS] Conectando a ${url}...`);

        try {
            this.socket = new WebSocket(url);
        } catch (err) {
            console.error('[WS] Error al crear instancia WebSocket:', err);
            this._scheduleReconnect();
            return;
        }

        this.socket.onopen = () => {
            console.log('[WS] Conexión establecida.');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.lastMessageAt = Date.now();
            this._notifyStatus('connected');
            this._startHeartbeat();
        };

        this.socket.onmessage = (event) => {
            this.lastMessageAt = Date.now();
            try {
                const message = JSON.parse(event.data);
                const eventType = message.evento || message.action || 'MESSAGE';
                this._dispatch(eventType, message.data !== undefined ? message.data : message);
            } catch (err) {
                // Mensaje no JSON (ej. string simple PONG)
                if (event.data === 'PONG') {
                    this._dispatch('PONG', {});
                } else {
                    console.debug('[WS] Mensaje no JSON:', event.data);
                }
            }
        };

        this.socket.onerror = (err) => {
            console.warn('[WS] Error en socket:', err);
            this._notifyStatus('error');
        };

        this.socket.onclose = (event) => {
            this.isConnected = false;
            this._stopHeartbeat();
            console.log(`[WS] Desconectado (código: ${event.code})`);
            this._notifyStatus('disconnected');

            if (!this.isExplicitClose) {
                this._scheduleReconnect();
            }
        };
    }

    /**
     * Programa reconexión exponencial con jitter
     */
    _scheduleReconnect() {
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay) + Math.random() * 500;
        console.log(`[WS] Reintentando conexión en ${(delay / 1000).toFixed(1)}s (intento #${this.reconnectAttempts})...`);
        this.reconnectTimer = setTimeout(() => {
            this.connect();
        }, delay);
    }

    /**
     * Heartbeat continuo para evitar timeouts en proxies / WiFi
     */
    _startHeartbeat() {
        this._stopHeartbeat();
        this.heartbeatTimer = setInterval(() => {
            // Sin respuesta en ~60 s (WiFi caído sin cierre limpio): tratar como desconexión.
            if (this.isConnected && Date.now() - this.lastMessageAt > 60000) {
                this.reconnectNow();
                return;
            }
            if (this.isConnected && this.socket && this.socket.readyState === WebSocket.OPEN) {
                try {
                    this.socket.send(JSON.stringify({ action: 'PING' }));
                } catch (e) {
                    console.warn('[WS] Fallo al enviar heartbeat PING:', e);
                }
            }
        }, 25000);
    }

    _stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    /**
     * Envía una acción con datos al servidor
     */
    send(action, data = {}) {
        if (!this.isConnected || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
            console.warn('[WS] No se puede enviar, socket no conectado');
            return false;
        }
        try {
            this.socket.send(JSON.stringify({ action, data }));
            return true;
        } catch (e) {
            console.error('[WS] Error al enviar mensaje:', e);
            return false;
        }
    }

    /**
     * Suscripción a eventos
     */
    on(event, handler) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(handler);
        return () => this.off(event, handler);
    }

    off(event, handler) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).delete(handler);
        }
    }

    _dispatch(event, data) {
        if (this.listeners.has(event)) {
            for (const handler of this.listeners.get(event)) {
                try {
                    handler(data);
                } catch (err) {
                    console.error(`[WS] Error en listener para ${event}:`, err);
                }
            }
        }
    }

    /**
     * Suscripción al estado de conexión
     */
    onStatus(handler) {
        this.statusListeners.add(handler);
        // Notificar estado actual de inmediato
        handler(this.isConnected ? 'connected' : 'disconnected');
        return () => this.statusListeners.delete(handler);
    }

    _notifyStatus(status) {
        for (const handler of this.statusListeners) {
            try {
                handler(status);
            } catch (e) {
                console.error('[WS] Error en status listener:', e);
            }
        }
    }

    /**
     * Cierra explícitamente la conexión
     */
    disconnect() {
        this.isExplicitClose = true;
        this._stopHeartbeat();
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }
}

window.TQTWebSocketClient = TQTWebSocketClient;
