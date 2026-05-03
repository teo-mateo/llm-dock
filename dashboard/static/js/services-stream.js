// Services streaming state
let servicesStreamCtrl = null;
let servicesReconnectTimer = null;
let servicesState = { services: [], total: 0, running: 0, stopped: 0 };

// Start the SSE stream for services
async function startServicesStream() {
    if (servicesStreamCtrl) return;
    const token = getToken();
    if (!token) return;

    if (servicesReconnectTimer) {
        clearTimeout(servicesReconnectTimer);
        servicesReconnectTimer = null;
    }

    servicesStreamCtrl = new AbortController();
    const ctrl = servicesStreamCtrl;
    let aborted = false;

    try {
        const response = await fetch(`${API_BASE}/services/stream`, {
            method: 'GET',
            headers: { 'Authorization': `Bearer ${token}` },
            signal: ctrl.signal,
        });
        if (response.status === 401) {
            clearToken();
            showLoginModal();
            return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleServicesEvent(data);
                    } catch {
                        // ignore malformed line
                    }
                }
                // Keepalive messages are ignored
            }
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            aborted = true;
            return;
        }
        console.error('Services stream error:', err);
    } finally {
        if (servicesStreamCtrl === ctrl) servicesStreamCtrl = null;
        if (!aborted && getToken()) {
            servicesReconnectTimer = setTimeout(startServicesStream, 3000);
        }
    }
}

// Stop the SSE stream for services
function stopServicesStream() {
    if (servicesReconnectTimer) {
        clearTimeout(servicesReconnectTimer);
        servicesReconnectTimer = null;
    }
    if (servicesStreamCtrl) {
        servicesStreamCtrl.abort();
        servicesStreamCtrl = null;
    }
}

// Handle incoming SSE events
function handleServicesEvent(data) {
    switch (data.type) {
        case 'snapshot':
            servicesState = data.data;
            processServicesData({ services: servicesState.services, total: servicesState.total, running: servicesState.running, stopped: servicesState.stopped });
            break;
        case 'delta':
            applyDelta(data);
            break;
        case 'error':
            console.error('Services stream error:', data.message);
            break;
    }
}

// Apply a delta update to the services state
function applyDelta(delta) {
    const serviceIndex = servicesState.services.findIndex(s => s.name === delta.service_name);
    
    if (delta.action === 'remove') {
        if (serviceIndex !== -1) {
            servicesState.services.splice(serviceIndex, 1);
            servicesState.total = servicesState.services.length;
            updateServiceCounts();
        }
    } else {
        const updatedService = {
            ...(serviceIndex !== -1 ? servicesState.services[serviceIndex] : {}),
            name: delta.service_name,
            status: delta.status,
            container_id: delta.container_id,
        };
        
        if (serviceIndex !== -1) {
            servicesState.services[serviceIndex] = updatedService;
        } else {
            servicesState.services.push(updatedService);
            servicesState.total = servicesState.services.length;
        }
        
        updateServiceCounts();
    }
    
    // Re-process and render the updated services
    processServicesData({ services: servicesState.services, total: servicesState.total, running: servicesState.running, stopped: servicesState.stopped });
}

// Update running/stopped counts based on current state
function updateServiceCounts() {
    servicesState.running = servicesState.services.filter(s => s.status === 'running').length;
    servicesState.stopped = servicesState.services.filter(s => s.status === 'exited' || s.status === 'not-created').length;
}

// Handle page visibility changes
function setupVisibilityHandler() {
    if (!document.visibilityState) return;
    
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            // Reconnect if we were disconnected
            if (!servicesStreamCtrl && getToken()) {
                startServicesStream();
            }
        } else {
            // Optionally disconnect when tab is hidden to save resources
            // stopServicesStream();
        }
    });
}

// Initialize visibility handling
setupVisibilityHandler();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopServicesStream();
});
