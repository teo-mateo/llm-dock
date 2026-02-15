// Logs modal state
let logsPollingInterval = null;
let currentLogsService = null;

function openLogsModal(serviceName) {
    console.log('openLogsModal called with:', serviceName);
    currentLogsService = serviceName;
    document.getElementById('logs-modal-title').textContent = `${serviceName} - Logs`;
    document.getElementById('logs-modal').classList.remove('hidden');
    document.getElementById('logs-content').textContent = 'Loading logs...';
    modalManager.lockScroll();

    // Add ESC key listener
    document.addEventListener('keydown', handleEscapeKey);

    // Load logs immediately
    loadLogs();

    // Start polling every 3 seconds
    logsPollingInterval = setInterval(loadLogs, 3000);
}

function closeLogsModal() {
    document.getElementById('logs-modal').classList.add('hidden');
    currentLogsService = null;
    modalManager.unlockScroll();

    // Remove ESC key listener
    document.removeEventListener('keydown', handleEscapeKey);

    // Stop polling
    if (logsPollingInterval) {
        clearInterval(logsPollingInterval);
        logsPollingInterval = null;
    }
}

function handleEscapeKey(event) {
    if (event.key === 'Escape') {
        closeLogsModal();
    }
}

// Make functions globally accessible
window.openLogsModal = openLogsModal;
window.closeLogsModal = closeLogsModal;

async function loadLogs() {
    if (!currentLogsService) return;

    try {
        // Flash the polling indicator
        const indicator = document.getElementById('logs-polling-indicator');
        indicator.style.opacity = '1';
        setTimeout(() => indicator.style.opacity = '0', 200);

        const data = await fetchAPI(`/services/${currentLogsService}/logs?tail=200`);

        const logsContent = document.getElementById('logs-content');

        // Skip DOM update if user has text selected in the logs to avoid losing selection
        const selection = window.getSelection();
        const hasSelection = selection && selection.toString().length > 0 &&
            logsContent.contains(selection.anchorNode);
        if (hasSelection) return;

        const wasScrolledToBottom = logsContent.scrollHeight - logsContent.scrollTop <= logsContent.clientHeight + 50;

        logsContent.textContent = data.logs || 'No logs available';

        // Auto-scroll to bottom if user was already at bottom
        if (wasScrolledToBottom) {
            logsContent.scrollTop = logsContent.scrollHeight;
        }

        // Update timestamp
        const now = new Date();
        document.getElementById('logs-info').textContent =
            `Last updated: ${now.toLocaleTimeString()} | ${data.lines} lines`;

    } catch (error) {
        console.error('Failed to load logs:', error);
        document.getElementById('logs-content').textContent = `Error loading logs: ${error.message}`;
    }
}
