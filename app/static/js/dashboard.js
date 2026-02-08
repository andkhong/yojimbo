/**
 * Yojimbo Dashboard - Alpine.js store and WebSocket client.
 */
function dashboardApp() {
    return {
        // Live data
        stats: {
            today_calls: 0,
            active_calls: 0,
            today_appointments: 0,
            total_contacts: 0,
            language_breakdown: {},
            avg_call_duration: 0,
        },
        activeCalls: 0,
        liveTranscripts: [],

        // Toast notifications
        toasts: [],
        toastCounter: 0,

        // WebSocket
        ws: null,
        wsReconnectTimer: null,

        init() {
            this.connectWebSocket();
            this.fetchStats();
            // Refresh stats every 30 seconds
            setInterval(() => this.fetchStats(), 30000);
        },

        connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;

            try {
                this.ws = new WebSocket(wsUrl);

                this.ws.onopen = () => {
                    console.log('Dashboard WebSocket connected');
                    if (this.wsReconnectTimer) {
                        clearTimeout(this.wsReconnectTimer);
                        this.wsReconnectTimer = null;
                    }
                };

                this.ws.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        this.handleWsEvent(msg);
                    } catch (e) {
                        console.error('Failed to parse WS message:', e);
                    }
                };

                this.ws.onclose = () => {
                    console.log('Dashboard WebSocket disconnected, reconnecting...');
                    this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 3000);
                };

                this.ws.onerror = (err) => {
                    console.error('WebSocket error:', err);
                };
            } catch (e) {
                console.error('WebSocket connection failed:', e);
                this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 5000);
            }
        },

        handleWsEvent(msg) {
            const { event, data } = msg;

            switch (event) {
                case 'call.started':
                    this.activeCalls++;
                    this.stats.active_calls = this.activeCalls;
                    this.stats.today_calls++;
                    this.addToast('info', 'New Incoming Call',
                        `From: ${data.caller_number || 'Unknown'} (${data.detected_language || 'en'})`);
                    break;

                case 'call.status_changed':
                    if (data.status === 'completed' || data.status === 'failed') {
                        this.activeCalls = Math.max(0, this.activeCalls - 1);
                        this.stats.active_calls = this.activeCalls;
                    }
                    break;

                case 'call.transcript':
                    this.liveTranscripts.push({
                        id: Date.now() + Math.random(),
                        call_id: data.call_id,
                        role: data.role,
                        original_text: data.original_text,
                        translated_text: data.translated_text,
                        language: data.language,
                    });
                    // Keep only last 50 transcript entries
                    if (this.liveTranscripts.length > 50) {
                        this.liveTranscripts = this.liveTranscripts.slice(-50);
                    }
                    break;

                case 'call.ended':
                    this.activeCalls = Math.max(0, this.activeCalls - 1);
                    this.stats.active_calls = this.activeCalls;
                    this.addToast('success', 'Call Ended',
                        data.summary || `Duration: ${data.duration_seconds || 0}s`);
                    // Clear transcripts for ended call
                    this.liveTranscripts = this.liveTranscripts.filter(t => t.call_id !== data.call_id);
                    break;

                case 'appointment.created':
                    this.stats.today_appointments++;
                    this.addToast('success', 'Appointment Booked',
                        `${data.scheduled_start || ''}`);
                    break;

                case 'appointment.updated':
                    if (data.status === 'cancelled') {
                        this.addToast('warning', 'Appointment Cancelled', `ID: ${data.appointment_id}`);
                    }
                    break;

                case 'sms.received':
                    this.addToast('info', 'SMS Received',
                        `From: ${data.from || 'Unknown'}`);
                    break;

                case 'stats.updated':
                    Object.assign(this.stats, data);
                    this.activeCalls = data.active_calls || 0;
                    break;

                case 'connected':
                    console.log('Dashboard WebSocket ready');
                    break;

                case 'pong':
                    break;

                default:
                    console.log('Unknown WS event:', event, data);
            }
        },

        async fetchStats() {
            try {
                const resp = await fetch('/api/dashboard/stats');
                if (resp.ok) {
                    const data = await resp.json();
                    Object.assign(this.stats, data);
                    this.activeCalls = data.active_calls || 0;
                }
            } catch (e) {
                console.error('Failed to fetch stats:', e);
            }
        },

        addToast(type, title, message) {
            const id = ++this.toastCounter;
            this.toasts.push({ id, type, title, message, visible: true });
            // Auto-remove after 6 seconds
            setTimeout(() => this.removeToast(id), 6000);
        },

        removeToast(id) {
            const toast = this.toasts.find(t => t.id === id);
            if (toast) toast.visible = false;
            setTimeout(() => {
                this.toasts = this.toasts.filter(t => t.id !== id);
            }, 300);
        },
    };
}
