// Dynamically construct API base URL based on hostname
// Use port 3399 only for localhost, otherwise use current hostname without port (assumes reverse proxy)
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? `${window.location.protocol}//${window.location.hostname}:3399/api`
    : `${window.location.protocol}//${window.location.hostname}/api`;
const TOKEN_KEY = 'dashboard_token';

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('API key copied to clipboard');
    }).catch(err => {
        console.error('Failed to copy:', err);
        showToast('Failed to copy to clipboard', true);
    });
}

// Global API key management
let globalApiKey = null;

async function loadGlobalApiKey() {
    try {
        const data = await fetchAPI('/global-api-key');
        if (data.api_key) {
            globalApiKey = data.api_key;
            const displayElement = document.getElementById('global-api-key-display');
            const valueElement = document.getElementById('global-api-key-value');

            // Show first 8 chars + ellipsis
            valueElement.textContent = globalApiKey.substring(0, 8) + '...';
            displayElement.classList.remove('hidden');

            // Show "Use Global" button in modal if it exists
            const useGlobalBtn = document.getElementById('use-global-api-key-btn');
            if (useGlobalBtn) {
                useGlobalBtn.classList.remove('hidden');
            }
        }
    } catch (error) {
        console.error('Failed to load global API key:', error);
    }
}

function copyGlobalApiKey() {
    if (globalApiKey) {
        navigator.clipboard.writeText(globalApiKey).then(() => {
            showToast('Global API key copied to clipboard');
        }).catch(err => {
            console.error('Failed to copy:', err);
            showToast('Failed to copy to clipboard', true);
        });
    }
}

function useGlobalApiKey() {
    if (globalApiKey) {
        const apiKeyInput = document.getElementById('api-key');
        if (apiKeyInput) {
            apiKeyInput.value = globalApiKey;
            showToast('API key set to global key');
        }
    }
}

// Format build date as relative time (e.g., "2 days ago")
function formatBuildDate(isoDateStr) {
    if (!isoDateStr) return null;

    try {
        const buildDate = new Date(isoDateStr);
        const now = new Date();
        const diffMs = now - buildDate;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffDays > 30) {
            return buildDate.toLocaleDateString();
        } else if (diffDays > 1) {
            return `${diffDays} days ago`;
        } else if (diffDays === 1) {
            return 'yesterday';
        } else if (diffHours > 1) {
            return `${diffHours} hours ago`;
        } else if (diffHours === 1) {
            return '1 hour ago';
        } else if (diffMins > 1) {
            return `${diffMins} minutes ago`;
        } else {
            return 'just now';
        }
    } catch (e) {
        console.error('Failed to parse build date:', e);
        return null;
    }
}

// Load and display image metadata in header
async function loadImageMetadata() {
    try {
        const data = await fetchAPI('/images/metadata');
        const container = document.getElementById('image-metadata');

        if (!container) return;

        const parts = [];

        // Format llamacpp info
        if (data.llamacpp && data.llamacpp.exists) {
            const date = formatBuildDate(data.llamacpp.build_date);
            const commit = data.llamacpp.build_commit ? data.llamacpp.build_commit.substring(0, 7) : null;

            let llamaInfo = 'llamacpp';
            if (date || commit) {
                const details = [];
                if (date) details.push(`built ${date}`);
                if (commit) details.push(`<span title="${data.llamacpp.build_commit}">${commit}</span>`);
                llamaInfo += ` (${details.join(', ')})`;
            }
            parts.push(llamaInfo);
        } else if (data.llamacpp && !data.llamacpp.exists) {
            parts.push('<span class="text-gray-600">llamacpp (not built)</span>');
        }

        // Format vllm info
        if (data.vllm && data.vllm.exists) {
            const date = formatBuildDate(data.vllm.build_date);
            const commit = data.vllm.build_commit ? data.vllm.build_commit.substring(0, 7) : null;

            let vllmInfo = 'vllm';
            if (date || commit) {
                const details = [];
                if (date) details.push(`built ${date}`);
                if (commit) details.push(`<span title="${data.vllm.build_commit}">${commit}</span>`);
                vllmInfo += ` (${details.join(', ')})`;
            }
            parts.push(vllmInfo);
        } else if (data.vllm && !data.vllm.exists) {
            parts.push('<span class="text-gray-600">vllm (not built)</span>');
        }

        if (parts.length > 0) {
            container.innerHTML = `<i class="fa-solid fa-cube mr-1"></i>Images: ${parts.join(' · ')}`;
        } else {
            container.innerHTML = '';
        }
    } catch (error) {
        console.error('Failed to load image metadata:', error);
        // Silently fail - this is non-critical UI info
    }
}

function showToast(message, isError = false) {
    // Remove existing toast if any
    const existingToast = document.getElementById('toast');
    if (existingToast) {
        existingToast.remove();
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = `fixed bottom-4 right-4 px-4 py-2 rounded shadow-lg text-sm font-semibold z-50 ${isError ? 'bg-red-600' : 'bg-green-600'} text-white`;
    toast.textContent = message;

    document.body.appendChild(toast);

    // Auto-remove after 2 seconds
    setTimeout(() => {
        toast.remove();
    }, 2000);
}

async function fetchAPI(endpoint, options = {}) {
    const token = getToken();

    if (!token) {
        showLoginModal();
        throw new Error('Not authenticated');
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...options.headers
        }
    });

    if (response.status === 401) {
        clearToken();
        showLoginModal();
        throw new Error('Authentication token is invalid or expired');
    }

    if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        const text = await response.text();
        try {
            const errorData = JSON.parse(text);
            // Handle both {error: "message"} and {error: {message: "message"}} formats
            errorMessage = typeof errorData.error === 'string'
                ? errorData.error
                : errorData.error?.message || errorMessage;
        } catch {
            // Response body is not JSON (e.g. HTML error page)
            if (text) errorMessage = `HTTP ${response.status}: ${text.substring(0, 200)}`;
        }
        throw new Error(errorMessage);
    }

    return response.json();
}

function showLoginModal() {
    document.getElementById('login-modal').classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');
}

function hideLoginModal() {
    document.getElementById('login-modal').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
}

async function handleLogin(event) {
    event.preventDefault();

    const token = document.getElementById('token-input').value.trim();
    const errorEl = document.getElementById('login-error');

    if (!token) {
        errorEl.textContent = 'Token cannot be empty';
        errorEl.classList.remove('hidden');
        return;
    }

    try {
        errorEl.classList.add('hidden');
        // Verify token by calling auth endpoint
        const response = await fetch(`${API_BASE}/auth/verify`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error('Invalid token');
        }

        // Token is valid, save it
        setToken(token);
        document.getElementById('token-input').value = '';
        hideLoginModal();
        loadServices();
        loadGPU();
        loadSystemInfo();
        loadImageMetadata();
    } catch (error) {
        errorEl.textContent = `Login failed: ${error.message}`;
        errorEl.classList.remove('hidden');
    }
}

function logout() {
    clearToken();
    showLoginModal();
}

async function loadServices() {
    try {
        const data = await fetchAPI('/services');

        // Separate open-webui service and other services
        const openWebuiService = data.services.find(service => service.name === 'open-webui');
        const otherServices = data.services.filter(service => service.name !== 'open-webui');

        // Sort other services alphabetically by name
        const sortedOtherServices = otherServices.sort((a, b) => a.name.localeCompare(b.name));

        // Combine: open-webui first, then sorted other services
        const orderedServices = openWebuiService ? [openWebuiService, ...sortedOtherServices] : sortedOtherServices;

        renderServices(orderedServices);
    } catch (error) {
        console.error('Failed to load services:', error);
        document.getElementById('services').innerHTML = `
            <div class="col-span-full bg-red-900 p-4 rounded border border-red-700">
                <p class="text-red-200">Failed to load services: ${error.message}</p>
            </div>
        `;
    }
}

function renderServices(services) {
    const container = document.getElementById('services');

    if (services.length === 0) {
        container.innerHTML = '<div class="col-span-full text-gray-400">No services found</div>';
        return;
    }

    container.innerHTML = services.map(service => {
        const isRunning = service.status === 'running';
        const isNotCreated = service.status === 'not-created';
        const isStopped = service.status === 'exited';

        // Determine border color
        let borderColor = 'border-gray-500';  // default
        if (isRunning) borderColor = 'border-green-500';
        else if (isStopped) borderColor = 'border-yellow-500';
        else if (isNotCreated) borderColor = 'border-gray-600';

        // Determine status color
        let statusColor = 'text-gray-400';
        if (isRunning) statusColor = 'text-green-400';
        else if (isStopped) statusColor = 'text-yellow-400';
        else if (isNotCreated) statusColor = 'text-gray-500';

        // Determine title color - white when running, gray when stopped
        let titleColor = 'text-gray-400';
        if (isRunning) titleColor = 'text-white';

        // Determine card background - brighter for running services
        let cardBg = 'bg-gray-800';
        if (isRunning) cardBg = 'bg-gray-700';

        // Card opacity for non-running services
        let cardOpacity = '';
        if (!isRunning) cardOpacity = 'opacity-75';

        // Determine internal port based on service type
        const internalPort = service.name.startsWith('llamacpp-') ? 8080 :
                            service.name.startsWith('vllm-') ? 8000 : null;

        const portInfo = service.host_port && service.host_port !== 9999
            ? (internalPort ? `<span class="font-bold">${internalPort}</span>:${service.host_port}` : service.host_port)
            : 'N/A';

        // Check if this is an infrastructure service (like open-webui)
        const isInfraService = service.name === 'open-webui';

        return `
            <div class="${cardBg} rounded-lg p-4 border-2 ${borderColor} flex flex-col h-full ${cardOpacity}" data-service="${service.name}" data-status="${service.status}">
                <div class="flex justify-between items-start mb-2">
                    <div class="flex-1 pr-2">
                        <h3 class="text-xl font-bold ${titleColor} inline">${service.name}</h3>
                        <button onclick="copyToClipboard('${service.name}')" class="text-blue-400 hover:text-blue-300 text-sm font-semibold inline-block ml-1 align-middle" title="Copy service name">
                            <i class="fa-solid fa-copy"></i>
                        </button>
                        ${!isInfraService ? `<button onclick="openRenameModal('${service.name}')" class="text-gray-500 hover:text-blue-300 text-sm inline-block ml-1 align-middle" title="Rename service">
                            <i class="fa-solid fa-pen"></i>
                        </button>` : ''}
                    </div>
                    ${!isNotCreated ? `<button onclick="openLogsModal('${service.name}')" class="text-blue-400 hover:text-blue-300 text-sm font-semibold flex-shrink-0">[Logs]</button>` : ''}
                </div>
                <div class="space-y-1 mb-4 text-sm text-gray-300 flex-1">
                    <p>Status: <span class="${statusColor} font-semibold">${service.status}</span>${service.exit_code ? ` <span class="text-red-400">(exit code: ${service.exit_code}${service.exit_code === 139 ? ' - segfault' : service.exit_code === 137 ? ' - OOM killed' : ''})</span>` : ''}</p>
                    <p>Container ID: <span class="text-gray-500 font-mono">${service.container_id || 'N/A'}</span></p>
                    <p>Port: <span class="text-gray-400">${portInfo}</span>${!isInfraService && service.host_port !== 3301 && service.host_port !== 9999 ? ` <button onclick="setPublicPort('${service.name}')" class="text-blue-400 hover:text-blue-300 ml-1" title="Set to public port (3301)"><i class="fa-solid fa-bullseye"></i></button>` : ''}${!isInfraService && service.host_port === 3301 ? ` <span class="text-green-400 ml-1" title="This is the public port"><i class="fa-solid fa-globe"></i></span>` : ''}</p>
                    ${service.api_key ? `<p>API Key: <span class="text-gray-400 font-mono text-xs">${service.api_key.substring(0, 10)}...</span> <button onclick="copyToClipboard('${service.api_key}')" class="text-blue-400 hover:text-blue-300 ml-1" title="Copy API key"><i class="fa-solid fa-copy"></i></button></p>` : ''}
                    ${!isInfraService ? `<p>Open WebUI: ${service.openwebui_registered
                        ? `<span class="text-green-400"><i class="fa-solid fa-check-circle"></i> Registered</span> <button onclick="toggleOpenWebUI('${service.name}', false)" class="text-red-400 hover:text-red-300 ml-2 text-xs" title="Unregister from Open WebUI">[Unregister]</button>`
                        : `<span class="text-gray-500"><i class="fa-solid fa-times-circle"></i> Not registered</span> <button onclick="toggleOpenWebUI('${service.name}', true)" class="text-blue-400 hover:text-blue-300 ml-2 text-xs" title="Register with Open WebUI">[Register]</button>`
                    }</p>` : ''}
                </div>
                <div class="flex gap-2 mt-auto">
                    ${_transitioningServices[service.name]
                        ? `<button disabled class="flex-1 bg-gray-600 px-3 py-2 rounded font-semibold cursor-not-allowed">${_transitioningServices[service.name].charAt(0).toUpperCase() + _transitioningServices[service.name].slice(1)}ing...</button>`
                        : isRunning
                            ? `<button onclick="controlService('${service.name}', 'stop')" class="flex-1 bg-red-600 hover:bg-red-700 px-3 py-2 rounded font-semibold">Stop</button>`
                            : `<button onclick="controlService('${service.name}', 'start')" class="flex-1 bg-green-600 hover:bg-green-700 px-3 py-2 rounded font-semibold">${isNotCreated ? 'Create & Start' : 'Start'}</button>`
                    }
                    ${isInfraService ? `
                        <button onclick="restartOpenWebUI()" class="bg-orange-600 hover:bg-orange-700 px-3 py-2 rounded font-semibold w-10 h-10 flex items-center justify-center" title="Restart Open WebUI">
                            <i class="fa-solid fa-rotate-right"></i>
                        </button>
                    ` : `
                        ${service.name.startsWith('llamacpp-') ? `
                        <a href="/benchmark?service=${service.name}" class="bg-yellow-600 hover:bg-yellow-700 px-3 py-2 rounded font-semibold w-10 h-10 flex items-center justify-center" title="Benchmark">
                            <i class="fa-solid fa-gauge-high"></i>
                        </a>` : ''}
                        <button onclick="previewService('${service.name}')" class="bg-gray-600 hover:bg-gray-700 px-3 py-2 rounded font-semibold w-10 h-10 flex items-center justify-center" title="Preview YAML">
                            <i class="fa-solid fa-code"></i>
                        </button>
                        <button onclick="editService('${service.name}')" class="bg-gray-600 hover:bg-gray-700 px-3 py-2 rounded font-semibold w-10 h-10 flex items-center justify-center" title="Edit service">
                            <i class="fa-solid fa-pen-to-square"></i>
                        </button>
                        <button onclick="deleteService('${service.name}')" class="bg-red-600 hover:bg-red-700 px-3 py-2 rounded font-semibold w-10 h-10 flex items-center justify-center" title="Delete service">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    `}
                </div>
            </div>
        `;
    }).join('');
}

// Track services currently being started/stopped so renders show transitioning state
const _transitioningServices = {};

async function controlService(name, action) {
    try {
        const button = event.target.closest('button');
        button.disabled = true;
        button.textContent = `${action.charAt(0).toUpperCase() + action.slice(1)}ing...`;

        _transitioningServices[name] = action;

        await fetchAPI(`/services/${name}/${action}`, { method: 'POST' });

        // container.stop() is blocking, so the container should be stopped
        // by the time we get here. Poll a few times in case Docker's list
        // query returns stale state.
        const expectedRunning = (action === 'start' || action === 'restart');
        for (let i = 0; i < 5; i++) {
            await loadServices();
            const card = document.querySelector(`[data-service="${name}"]`);
            const isRunning = card?.dataset.status === 'running';
            if (isRunning === expectedRunning) break;
            await new Promise(r => setTimeout(r, 500));
        }
    } catch (error) {
        console.error(`Failed to ${action} service:`, error);
        alert(`Failed to ${action} service: ${error.message}`);
    } finally {
        delete _transitioningServices[name];
        loadServices();
    }
}

async function setPublicPort(serviceName) {
    try {
        const result = await fetchAPI(`/services/${serviceName}/set-public-port`, { method: 'POST' });

        // Show success message
        let message = `${serviceName} now on port 3301`;
        if (result.updates && result.updates.length > 1) {
            const swappedService = result.updates.find(u => u.service !== serviceName);
            if (swappedService) {
                message += ` (${swappedService.service} moved to port ${swappedService.new_port})`;
            }
        }
        showToast(message);

        // Reload services to show updated ports
        loadServices();
    } catch (error) {
        console.error('Failed to set public port:', error);
        showToast(`Failed to set public port: ${error.message}`, true);
    }
}

async function toggleOpenWebUI(serviceName, register) {
    try {
        const endpoint = register ? 'register-openwebui' : 'unregister-openwebui';
        const action = register ? 'Registering' : 'Unregistering';

        showToast(`${action} ${serviceName}...`);

        const result = await fetchAPI(`/services/${serviceName}/${endpoint}`, { method: 'POST' });

        if (result.success) {
            showToast(result.message);

            // Reload services to show updated status
            loadServices();

            // Ask user if they want to restart Open WebUI
            const restart = confirm(
                'Open WebUI must be restarted for changes to take effect.\n\n' +
                'Do you want to restart Open WebUI now?'
            );

            if (restart) {
                await restartOpenWebUI();
            }
        } else {
            showToast(result.error || `Failed to ${register ? 'register' : 'unregister'}`, true);
        }
    } catch (error) {
        console.error(`Failed to ${register ? 'register' : 'unregister'} with Open WebUI:`, error);
        showToast(`Failed: ${error.message}`, true);
    }
}

async function restartOpenWebUI() {
    try {
        showToast('Restarting Open WebUI...');

        const result = await fetchAPI('/openwebui/restart', { method: 'POST' });

        if (result.success) {
            showToast('Open WebUI restarted successfully');
        } else {
            showToast(result.error || 'Failed to restart Open WebUI', true);
        }
    } catch (error) {
        console.error('Failed to restart Open WebUI:', error);
        showToast(`Failed to restart: ${error.message}`, true);
    }
}

let serviceToDelete = null;

function deleteService(name) {
    serviceToDelete = name;
    document.getElementById('delete-service-name').textContent = name;
    document.getElementById('delete-service-modal').classList.remove('hidden');
}

function closeDeleteModal() {
    document.getElementById('delete-service-modal').classList.add('hidden');
    serviceToDelete = null;

    // Reset button state
    const confirmBtn = document.getElementById('delete-service-confirm');
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = '<i class="fa-solid fa-trash mr-2"></i>Delete';
}

async function confirmDelete() {
    if (!serviceToDelete) return;

    const modal = document.getElementById('delete-service-modal');
    const confirmBtn = document.getElementById('delete-service-confirm');
    const originalHTML = confirmBtn.innerHTML;

    try {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Deleting...';

        await fetchAPI(`/services/${serviceToDelete}`, { method: 'DELETE' });

        // Close modal and reload
        closeDeleteModal();
        loadServices();
    } catch (error) {
        console.error('Failed to delete service:', error);
        alert(`Failed to delete service: ${error.message}`);
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = originalHTML;
    }
}

// Rename Service Modal
let serviceToRename = null;

function openRenameModal(serviceName) {
    serviceToRename = serviceName;
    const input = document.getElementById('rename-service-input');
    const errorEl = document.getElementById('rename-service-error');
    document.getElementById('rename-service-old-name').textContent = serviceName;
    input.value = serviceName;
    errorEl.classList.add('hidden');
    document.getElementById('rename-service-modal').classList.remove('hidden');

    // Focus and select the input text
    setTimeout(() => {
        input.focus();
        input.select();
    }, 50);
}

function closeRenameModal() {
    document.getElementById('rename-service-modal').classList.add('hidden');
    serviceToRename = null;

    // Reset button state
    const confirmBtn = document.getElementById('rename-service-confirm');
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = '<i class="fa-solid fa-pen mr-2"></i>Rename';
}

async function confirmRename() {
    if (!serviceToRename) return;

    const input = document.getElementById('rename-service-input');
    const errorEl = document.getElementById('rename-service-error');
    const confirmBtn = document.getElementById('rename-service-confirm');
    const newName = input.value.trim();

    // Client-side validation
    if (!newName) {
        errorEl.textContent = 'Service name cannot be empty';
        errorEl.classList.remove('hidden');
        return;
    }
    if (newName === serviceToRename) {
        closeRenameModal();
        return;
    }
    if (newName.length > 63) {
        errorEl.textContent = 'Name too long (max 63 characters)';
        errorEl.classList.remove('hidden');
        return;
    }
    if (!newName.replace(/-/g, '').replace(/_/g, '').match(/^[a-zA-Z0-9]+$/)) {
        errorEl.textContent = 'Only alphanumeric characters, hyphens, and underscores allowed';
        errorEl.classList.remove('hidden');
        return;
    }

    try {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Renaming...';
        errorEl.classList.add('hidden');

        const result = await fetchAPI(`/services/${serviceToRename}/rename`, {
            method: 'POST',
            body: JSON.stringify({ new_name: newName })
        });

        closeRenameModal();
        showToast(result.message);
        loadServices();
    } catch (error) {
        console.error('Failed to rename service:', error);
        errorEl.textContent = error.message;
        errorEl.classList.remove('hidden');
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fa-solid fa-pen mr-2"></i>Rename';
    }
}

// Close modal on ESC key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const deleteModal = document.getElementById('delete-service-modal');
        if (!deleteModal.classList.contains('hidden')) {
            closeDeleteModal();
        }
        const previewModal = document.getElementById('preview-service-modal');
        if (!previewModal.classList.contains('hidden')) {
            closePreviewModal();
        }
        // param-browser-modal removed (replaced by inline reference panel)
        const renameModal = document.getElementById('rename-service-modal');
        if (renameModal && !renameModal.classList.contains('hidden')) {
            closeRenameModal();
        }
        const copyFromModal = document.getElementById('copy-from-modal');
        if (copyFromModal && !copyFromModal.classList.contains('hidden')) {
            closeCopyFromModal();
        }
    }
});

// Preview Service Modal
let currentPreviewYaml = '';

async function previewService(serviceName) {
    try {
        const data = await fetchAPI(`/services/${serviceName}/preview`);
        currentPreviewYaml = data.yaml;

        document.getElementById('preview-service-name').textContent = serviceName;
        document.getElementById('preview-yaml').textContent = data.yaml;
        document.getElementById('preview-service-modal').classList.remove('hidden');
    } catch (error) {
        console.error('Failed to preview service:', error);
        alert(`Failed to preview service: ${error.message}`);
    }
}

function closePreviewModal() {
    document.getElementById('preview-service-modal').classList.add('hidden');
    currentPreviewYaml = '';
}

function copyPreviewYaml() {
    navigator.clipboard.writeText(currentPreviewYaml).then(() => {
        showToast('YAML copied to clipboard');
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
}

// GPU History for graph
const gpuHistory = {
    memory: [],
    compute: [],
    maxPoints: 20  // 20 points at 3s intervals = 60 seconds
};

async function loadGPU() {
    try {
        const data = await fetchAPI('/gpu');
        renderGPU(data.gpus);
        updateGPUHistory(data.gpus);
        drawGPUGraph();
    } catch (error) {
        console.error('Failed to load GPU stats:', error);
        document.getElementById('gpu-stats').innerHTML = `
            <div class="bg-red-900 p-4 rounded border border-red-700">
                <p class="text-red-200">Failed to load GPU stats: ${error.message}</p>
            </div>
        `;
    }
}

function updateGPUHistory(gpus) {
    if (!gpus || gpus.length === 0) return;

    // Use first GPU's stats
    const gpu = gpus[0];
    const memoryPercent = Math.round((gpu.memory.used / gpu.memory.total) * 100);
    const computePercent = gpu.utilization.gpu_percent;

    // Add to history
    gpuHistory.memory.push(memoryPercent);
    gpuHistory.compute.push(computePercent);

    // Trim to max points
    if (gpuHistory.memory.length > gpuHistory.maxPoints) {
        gpuHistory.memory.shift();
        gpuHistory.compute.shift();
    }

    // Show graph container once we have data
    document.getElementById('gpu-graph-container').classList.remove('hidden');
}

function drawGPUGraph() {
    const canvas = document.getElementById('gpu-graph');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();

    // Set canvas size for high DPI
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = 80 * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = 80;
    const padding = 2;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Draw grid lines
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const y = padding + (height - 2 * padding) * (i / 4);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }

    if (gpuHistory.memory.length < 2) return;

    const pointWidth = (width - 2 * padding) / (gpuHistory.maxPoints - 1);
    const dataLen = gpuHistory.memory.length;

    // Draw memory line (blue) - right to left flow
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.beginPath();
    gpuHistory.memory.forEach((value, i) => {
        // Position from right: newest value at right edge
        const x = width - padding - (dataLen - 1 - i) * pointWidth;
        const y = height - padding - (value / 100) * (height - 2 * padding);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw compute line (green) - right to left flow
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = 2;
    ctx.beginPath();
    gpuHistory.compute.forEach((value, i) => {
        // Position from right: newest value at right edge
        const x = width - padding - (dataLen - 1 - i) * pointWidth;
        const y = height - padding - (value / 100) * (height - 2 * padding);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw current values
    const lastMem = gpuHistory.memory[gpuHistory.memory.length - 1];
    const lastComp = gpuHistory.compute[gpuHistory.compute.length - 1];

    ctx.font = '10px monospace';
    ctx.fillStyle = '#3b82f6';
    ctx.fillText(`${lastMem}%`, width - 30, 12);
    ctx.fillStyle = '#22c55e';
    ctx.fillText(`${lastComp}%`, width - 30, 24);
}

function renderGPU(gpus) {
    const container = document.getElementById('gpu-stats');

    if (!gpus || gpus.length === 0) {
        container.innerHTML = '<div class="text-gray-400">No GPU information available</div>';
        return;
    }

    container.innerHTML = gpus.map((gpu, idx) => {
        const memoryPercent = Math.round((gpu.memory.used / gpu.memory.total) * 100);
        const memoryBar = `
            <div class="w-full bg-gray-700 rounded h-2 mt-1">
                <div class="bg-blue-600 h-2 rounded" style="width: ${memoryPercent}%"></div>
            </div>
        `;

        return `
            <div class="bg-gray-800 p-4 rounded border border-gray-700">
                <p class="font-bold text-lg mb-2">${gpu.name}</p>
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <p class="text-gray-400">Memory</p>
                        <p class="text-white font-mono">${gpu.memory.used}/${gpu.memory.total} MiB</p>
                        ${memoryBar}
                    </div>
                    <div>
                        <p class="text-gray-400">Temperature</p>
                        <p class="text-white font-mono">${gpu.temperature.current}°C</p>
                    </div>
                    <div>
                        <p class="text-gray-400">GPU Utilization</p>
                        <p class="text-white font-mono">${gpu.utilization.gpu_percent}%</p>
                    </div>
                    <div>
                        <p class="text-gray-400">Power</p>
                        <p class="text-white font-mono">${gpu.power.draw.toFixed(1)}/${gpu.power.limit.current.toFixed(0)} W</p>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Initialize the dashboard
async function init() {
    const token = getToken();

    if (token) {
        // Token exists, verify it and show dashboard
        try {
            const response = await fetch(`${API_BASE}/auth/verify`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                // Token is valid, show dashboard
                hideLoginModal();
                loadServices();
                loadGPU();
                loadSystemInfo();
                loadImageMetadata();
                loadGlobalApiKey();
            } else {
                // Token is invalid, clear it and show login
                clearToken();
                showLoginModal();
            }
        } catch (error) {
            console.error('Token verification failed:', error);
            clearToken();
            showLoginModal();
        }
    } else {
        // No token, show login
        showLoginModal();
    }
}

// Logs modal state
let logsPollingInterval = null;
let currentLogsService = null;

function openLogsModal(serviceName) {
    console.log('openLogsModal called with:', serviceName);
    currentLogsService = serviceName;
    document.getElementById('logs-modal-title').textContent = `${serviceName} - Logs`;
    document.getElementById('logs-modal').classList.remove('hidden');
    document.getElementById('logs-content').textContent = 'Loading logs...';

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

async function loadSystemInfo() {
    try {
        const data = await fetchAPI('/system/info');
        renderSystemInfo(data);
    } catch (error) {
        console.error('Failed to load system info:', error);
        document.getElementById('system-info').innerHTML = `
            <div class="bg-red-900 p-4 rounded border border-red-700">
                <p class="text-red-200">Failed to load system information: ${error.message}</p>
            </div>
        `;
    }
}

function formatBytes(bytes) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }
    return `${size.toFixed(2)} ${units[unitIndex]}`;
}

function toggleModel(modelIndex) {
    const element = document.getElementById(`model-${modelIndex}`);
    const arrow = document.getElementById(`arrow-${modelIndex}`);
    if (element.classList.contains('hidden')) {
        element.classList.remove('hidden');
        arrow.textContent = '▼';
    } else {
        element.classList.add('hidden');
        arrow.textContent = '▶';
    }
}

function renderSystemInfo(data) {
    const container = document.getElementById('system-info');
    const disk = data.disk;
    const models = data.models || [];

    // Store models globally for filtering
    allModels = models;

    const diskPercentColor = disk.percent > 90 ? 'bg-red-600' : disk.percent > 75 ? 'bg-yellow-600' : 'bg-green-600';

    container.innerHTML = `
        <div class="space-y-6">
            <!-- Disk Usage -->
            <div>
                <h3 class="text-lg font-bold mb-3 flex items-center gap-2">
                    <i class="fa-solid fa-hard-drive"></i>
                    <span>Disk Usage</span>
                </h3>
                <div class="space-y-2">
                    <div class="flex justify-between text-sm">
                        <span class="text-gray-400">Total:</span>
                        <span class="font-mono">${disk.total_str}</span>
                    </div>
                    <div class="flex justify-between text-sm">
                        <span class="text-gray-400">Used:</span>
                        <span class="font-mono">${disk.used_str} (${disk.percent}%)</span>
                    </div>
                    <div class="flex justify-between text-sm">
                        <span class="text-gray-400">Free:</span>
                        <span class="font-mono text-green-400">${disk.free_str}</span>
                    </div>
                    <div class="w-full bg-gray-700 rounded-full h-3 mt-2">
                        <div class="${diskPercentColor} h-3 rounded-full transition-all" style="width: ${disk.percent}%"></div>
                    </div>
                </div>
            </div>

            <!-- Models -->
            <div>
                <h3 id="models-count" class="text-lg font-bold mb-3 flex items-center gap-2">
                    <i class="fa-solid fa-brain"></i>
                    <span>Models (${models.length})</span>
                </h3>
                <div class="text-sm mb-3 text-gray-400">
                    Total size: ${formatBytes(data.total_model_size || 0)}
                </div>
                <div class="mb-3">
                    <input
                        type="text"
                        id="model-search"
                        placeholder="Search models..."
                        class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm focus:outline-none focus:border-blue-500"
                        oninput="filterModels(this.value)"
                    >
                </div>
                <div id="models-list" class="max-h-96 overflow-y-auto border border-gray-700 rounded p-3 bg-gray-900">
                    ${renderModelsList(models)}
                </div>
            </div>
        </div>
    `;
}

// Store models globally for filtering
let allModels = [];

function filterModels(searchTerm) {
    const term = searchTerm.toLowerCase();
    const filtered = term
        ? allModels.filter(m =>
            (m.full_name || m.name).toLowerCase().includes(term) ||
            (m.quantization && m.quantization.toLowerCase().includes(term))
        )
        : allModels;

    const container = document.getElementById('models-list');
    if (container) {
        container.innerHTML = renderModelsList(filtered);
    }

    // Update count
    const countEl = document.getElementById('models-count');
    if (countEl) {
        countEl.textContent = `Models (${filtered.length}${term ? ` / ${allModels.length}` : ''})`;
    }
}

function renderModelsList(models) {
    if (models.length === 0) {
        return '<p class="text-gray-400 text-sm">No models found</p>';
    }

    return models.map((model, index) => {
        const hasFiles = model.files && model.files.length > 0;
        const filesHtml = hasFiles
            ? model.files.map(file => {
                const related = file.related ? ' <span class="text-yellow-400">(related)</span>' : '';
                return `
                    <div class="ml-4 text-xs text-gray-400 font-mono mt-1">
                        <div class="flex items-start gap-2 truncate" title="${file.path}">
                            <i class="fa-solid fa-file flex-shrink-0 mt-0.5"></i>
                            <span class="truncate">${file.path}</span>
                        </div>
                        <div class="ml-6 text-gray-500">Size: ${file.size_str}${related}</div>
                    </div>
                `;
            }).join('')
            : '';

        return `
            <div class="border-b border-gray-700 pb-2 mb-2 last:border-0">
                <div class="flex justify-between items-start">
                    <div class="flex-1 cursor-pointer hover:bg-gray-750" onclick="toggleModel(${index})">
                        <div class="flex items-center gap-2">
                            <span id="arrow-${index}" class="text-xs text-gray-500">▶</span>
                            <span class="px-1.5 py-0.5 text-xs rounded ${model.type === 'huggingface' ? 'bg-yellow-600' : 'bg-green-600'}">${model.type === 'huggingface' ? 'HF' : 'LOCAL'}</span>
                            <span class="font-semibold text-sm">${model.full_name || model.name}</span>
                        </div>
                        ${model.quantization ? `<div class="ml-6 text-xs text-gray-500">Quantization: ${model.quantization} (${model.quantization_type})</div>` : ''}
                    </div>
                    <div class="flex items-center gap-3">
                        <div class="text-sm text-gray-400">${model.size_str}</div>
                        <button
                            onclick="event.stopPropagation(); openCreateServiceModal(${JSON.stringify(model).replace(/"/g, '&quot;')})"
                            class="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs font-semibold whitespace-nowrap"
                            title="Create service from this model"
                        >
                            <i class="fa-solid fa-plus mr-1"></i>Create Service
                        </button>
                    </div>
                </div>
                <div id="model-${index}" class="hidden mt-2 ml-6">
                    ${hasFiles ? `
                        <div class="text-xs text-gray-500 mb-1">Files: ${model.file_count}</div>
                        ${filesHtml}
                    ` : '<p class="text-xs text-gray-500">No file information available</p>'}
                </div>
            </div>
        `;
    }).join('');
}

// Create Service Modal Functions
let currentModelData = null;
let modalMode = 'create'; // 'create' or 'update'
let currentServiceName = null; // For update mode
let availableFlags = {}; // Cache for flag metadata by engine
let gpuInfo = null; // Cached GPU info

function escapeAttr(str) {
    return String(str).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Serve parameter reference data (llama-server flags only)
const SERVE_PARAM_REFERENCE = [
    { cat: 'Context', flag: '-c', long: '--ctx-size', desc: 'Context length in tokens', def: '128000',
      tip: 'Sets the <b>maximum context length</b> in tokens. Determines how much text the model can process at once. Higher values require more VRAM for the KV cache.' },
    { cat: 'GPU', flag: '-ngl', long: '--n-gpu-layers', desc: 'Number of layers to offload to GPU', def: '999',
      tip: 'Controls how many model layers are stored in VRAM. Use <code>999</code> to offload everything. <b>Higher values = faster inference but more VRAM.</b>' },
    { cat: 'Batching', flag: '-b', long: '--batch-size', desc: 'Logical batch size for prompt processing', def: '256',
      tip: '<b>Logical batch size</b> for prompt processing. Controls how many tokens are processed per iteration. Larger values speed up prompt processing but require more VRAM.' },
    { cat: 'Batching', flag: '-ub', long: '--ubatch-size', desc: 'Physical micro-batch size', def: '256',
      tip: '<b>Physical micro-batch size</b> at the hardware level. When <code>batch > ubatch</code>, processing is pipelined. Must satisfy: <code>batch >= ubatch</code>.' },
    { cat: 'Memory', flag: '-fa', long: '--flash-attn', desc: 'Enable flash attention', def: '',
      tip: 'Enables flash attention for reduced memory bandwidth and improved GPU performance. <b>Enable when using GPU</b> for up to ~15% throughput gains. Required for KV cache quantization.' },
    { cat: 'Memory', flag: '-ctk', long: '--cache-type-k', desc: 'KV cache type for K', def: 'f16',
      tip: 'Data type for the <b>key</b> component of the KV cache. Options: <code>f16</code>, <code>f32</code>, <code>q8_0</code>, <code>q4_0</code>. Use <code>q8_0</code> to halve KV cache VRAM. Requires <code>-fa</code>.' },
    { cat: 'Memory', flag: '-ctv', long: '--cache-type-v', desc: 'KV cache type for V', def: 'f16',
      tip: 'Data type for the <b>value</b> component of the KV cache. Options: <code>f16</code>, <code>f32</code>, <code>q8_0</code>, <code>q4_0</code>. Should match <code>-ctk</code>. Requires <code>-fa</code>.' },
    { cat: 'Memory', flag: '', long: '--no-mmap', desc: 'Disable memory-mapped model loading', def: '',
      tip: 'Disables memory-mapped file loading, forcing the model to be loaded fully into RAM. Use when model is larger than available RAM or for consistent performance.' },
    { cat: 'GPU', flag: '-sm', long: '--split-mode', desc: 'Multi-GPU split mode (none|layer|row)', def: 'layer',
      tip: 'How models distribute across multiple GPUs. <code>layer</code> = sequential; <code>row</code> = parallel tensor splitting. <b>Use row for better multi-GPU utilization.</b>' },
    { cat: 'GPU', flag: '-mg', long: '--main-gpu', desc: 'Primary GPU index', def: '0',
      tip: 'Which GPU handles primary processing. <b>Set to your fastest GPU.</b>' },
    { cat: 'GPU', flag: '-ts', long: '--tensor-split', desc: 'Fraction of work per GPU (comma-separated)', def: '',
      tip: 'Custom proportions for distributing model weights across GPUs (e.g., <code>3,1</code> = 75%/25% split). <b>Use when GPUs have different VRAM.</b>' },
    { cat: 'Sampling', flag: '', long: '--repeat-penalty', desc: 'Penalty for repeating tokens', def: '1.3',
      tip: 'Penalizes repeated token sequences. Values > 1.0 discourage repetition. <b>1.0 = no penalty, 1.5 = strong penalty.</b>' },
    { cat: 'Sampling', flag: '', long: '--top-p', desc: 'Top-p (nucleus) sampling', def: '0.95',
      tip: 'Limits token choices to the smallest set with cumulative probability >= p. <b>Lower values = more focused, higher = more diverse.</b>' },
    { cat: 'Sampling', flag: '', long: '--top-k', desc: 'Top-k sampling', def: '40',
      tip: 'Limits choices to top K most likely tokens. <b>Lower = more focused, higher = more diverse.</b>' },
    { cat: 'Sampling', flag: '-t', long: '--temp', desc: 'Temperature for sampling', def: '1.0',
      tip: 'Controls randomness. <b>0.0 = deterministic, 1.0 = normal, >1.0 = more random.</b>' },
    { cat: 'CPU', flag: '', long: '--threads', desc: 'Number of threads for computation', def: 'auto',
      tip: 'Number of CPU threads for computation. <b>Higher values improve performance on multi-core systems.</b>' },
    { cat: 'Features', flag: '', long: '--jinja', desc: 'Enable Jinja template parsing', def: '',
      tip: 'Enables <b>Jinja template parsing</b> for chat templates. Required for some models with custom chat formats.' },
    { cat: 'Features', flag: '-v', long: '--verbose', desc: 'Enable verbose logging', def: '',
      tip: 'Enables <b>detailed diagnostic logging</b> with maximum verbosity.' },
    { cat: 'Features', flag: '', long: '--log-verbosity', desc: 'Set verbosity threshold level', def: '',
      tip: 'Sets the verbosity threshold for logging output.' },
    { cat: 'Features', flag: '', long: '--reasoning-format', desc: 'Reasoning format (auto, cot, etc.)', def: '',
      tip: 'Sets the reasoning output format. Use <code>auto</code> for automatic detection.' },
    { cat: 'Features', flag: '', long: '--mmproj', desc: 'Path to multi-modal projector', def: '',
      tip: 'Path to the multi-modal projector file for vision models.' },
    { cat: 'RoPE', flag: '', long: '--rope-freq-base', desc: 'RoPE frequency base', def: '',
      tip: 'Base frequency for RoPE positional encoding.' },
    { cat: 'RoPE', flag: '', long: '--rope-freq-scale', desc: 'RoPE frequency scaling factor', def: '',
      tip: 'Scaling factor for RoPE positional encoding frequencies.' },
];

// Fetch and display GPU info in modal
async function loadGPUInfo() {
    const gpuNameEl = document.getElementById('modal-gpu-name');
    const gpuVramEl = document.getElementById('modal-gpu-vram');

    try {
        const result = await fetchAPI('/gpu');
        if (result.gpus && result.gpus.length > 0) {
            const gpu = result.gpus[0];
            gpuInfo = gpu;

            const totalGB = (gpu.memory.total / 1024).toFixed(1);
            const freeGB = (gpu.memory.free / 1024).toFixed(1);

            gpuNameEl.textContent = gpu.name;
            gpuVramEl.innerHTML = `VRAM: <span class="text-green-400">${freeGB} GB free</span> / ${totalGB} GB total`;
        } else {
            gpuNameEl.textContent = 'No GPU detected';
            gpuVramEl.textContent = '';
            gpuInfo = null;
        }
    } catch (error) {
        console.error('Failed to load GPU info:', error);
        gpuNameEl.textContent = 'GPU info unavailable';
        gpuVramEl.textContent = '';
        gpuInfo = null;
    }
}

// Get the next available port in the 3301-3399 range
async function getNextAvailablePort() {
    try {
        const data = await fetchAPI('/services');
        const usedPorts = new Set(
            data.services
                .filter(s => s.host_port)
                .map(s => s.host_port)
        );

        for (let port = 3301; port <= 3399; port++) {
            if (!usedPorts.has(port)) {
                return port;
            }
        }
        return null;
    } catch (error) {
        console.error('Failed to get available port:', error);
        return null;
    }
}

// Calculate smart defaults based on GPU VRAM and model size (returns CLI-keyed params)
function getSmartDefaults(engine, modelSizeGB, vramTotalMB) {
    const vramGB = vramTotalMB / 1024;
    const params = {};

    if (engine === 'llamacpp') {
        params['-ngl'] = '999';

        const headroomGB = vramGB - (modelSizeGB * 1.2);
        let contextLength;
        if (headroomGB >= 12) contextLength = '32768';
        else if (headroomGB >= 8) contextLength = '16384';
        else if (headroomGB >= 4) contextLength = '8192';
        else if (headroomGB >= 2) contextLength = '4096';
        else contextLength = '2048';
        params['-c'] = contextLength;

        if (headroomGB < 6) {
            params['-fa'] = '';
        }
    } else if (engine === 'vllm') {
        params['--gpu-memory-utilization'] = '0.90';
        if (vramGB >= 24) params['--max-model-len'] = '8192';
        else if (vramGB >= 16) params['--max-model-len'] = '4096';
        else params['--max-model-len'] = '2048';
    }

    return params;
}

// Apply smart defaults to service parameter rows
function applySmartDefaults() {
    if (!gpuInfo || !currentModelData) return;

    const engine = document.querySelector('input[name="engine"]:checked')?.value;
    if (!engine) return;

    const sizeMatch = currentModelData.size_str?.match(/([\d.]+)\s*(GB|MB)/i);
    let modelSizeGB = 0;
    if (sizeMatch) {
        modelSizeGB = parseFloat(sizeMatch[1]);
        if (sizeMatch[2].toUpperCase() === 'MB') modelSizeGB /= 1024;
    }

    const defaults = getSmartDefaults(engine, modelSizeGB, gpuInfo.memory.total);
    loadServiceParams(defaults);
}

// Update the params count display
function updateParamsCount() {
    const countEl = document.getElementById('params-count');
    if (!countEl) return;

    const rows = document.querySelectorAll('#dynamic-params-container .param-row:not([data-empty="1"])');
    let configuredCount = 0;
    rows.forEach(row => {
        const flagInput = row.querySelector('input');
        if (flagInput && flagInput.value.trim()) configuredCount++;
    });

    countEl.textContent = `(${configuredCount} configured)`;
}

// Transform host path to container path
function transformToContainerPath(hostPath) {
    // Replace common host cache paths with container path
    // ~/.cache/huggingface -> /hf-cache
    // ~/.cache/models -> /local-models (separate volume mount)
    let containerPath = hostPath
        .replace(/^\/home\/[^/]+\/\.cache\/huggingface/, '/hf-cache')
        .replace(/^\/home\/[^/]+\/\.cache\/models/, '/local-models');
    return containerPath;
}

// Populate GGUF file selector
function populateGGUFFileSelector(files) {
    const selector = document.getElementById('gguf-file-selector');
    const fileList = document.getElementById('gguf-file-list');
    const hint = document.getElementById('model-path-hint');

    // Filter for GGUF files only
    const ggufFiles = files ? files.filter(f => f.name && f.name.endsWith('.gguf')) : [];

    if (ggufFiles.length === 0) {
        selector.classList.add('hidden');
        hint.classList.remove('hidden');
        return;
    }

    // Show selector, hide hint
    selector.classList.remove('hidden');
    hint.classList.add('hidden');

    // Populate file list
    fileList.innerHTML = ggufFiles.map((file, index) => {
        const containerPath = transformToContainerPath(file.path);
        const fileName = file.name || file.path.split('/').pop();
        const size = file.size_str || '';
        return `
            <div class="px-3 py-2 hover:bg-gray-700 cursor-pointer border-b border-gray-700 last:border-0 flex items-center gap-2"
                 onclick="selectGGUFFile('${containerPath.replace(/'/g, "\\'")}')">
                <input type="radio" name="gguf-file" id="gguf-file-${index}" class="flex-shrink-0">
                <label for="gguf-file-${index}" class="flex-1 cursor-pointer">
                    <div class="text-sm font-mono truncate" title="${containerPath}">${fileName}</div>
                    <div class="text-xs text-gray-500">${size}</div>
                </label>
            </div>
        `;
    }).join('');

    // Auto-select if only one file
    if (ggufFiles.length === 1) {
        const containerPath = transformToContainerPath(ggufFiles[0].path);
        selectGGUFFile(containerPath);
        document.querySelector('input[name="gguf-file"]').checked = true;
    }
}

// Handle GGUF file selection
function selectGGUFFile(containerPath) {
    document.getElementById('model-path').value = containerPath;

    // Update radio button state
    const radios = document.querySelectorAll('input[name="gguf-file"]');
    radios.forEach(radio => {
        const div = radio.closest('div');
        const pathInDiv = div.querySelector('.font-mono').getAttribute('title');
        radio.checked = (pathInDiv === containerPath);
    });
}

// Flag Metadata Functions (kept for vllm backward compat)
async function loadFlagMetadata(templateType) {
    if (availableFlags[templateType]) {
        return availableFlags[templateType];
    }

    try {
        const data = await fetchAPI(`/flag-metadata/${templateType}`);
        availableFlags[templateType] = data.optional_flags || {};
        return availableFlags[templateType];
    } catch (error) {
        console.error('Failed to load flag metadata:', error);
        return {};
    }
}

// ── Unified Parameter Row Management (benchmark-style) ──

function addServiceParamRow(flag, value, isEmpty = false) {
    const container = document.getElementById('dynamic-params-container');
    const row = document.createElement('div');
    row.className = 'flex gap-2 items-center param-row';
    if (isEmpty) row.dataset.empty = '1';
    row.innerHTML = `
        <input type="text" value="${escapeAttr(flag)}" placeholder="-flag"
            class="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm w-28 font-mono focus:outline-none focus:border-blue-500"
            oninput="onServiceParamInput(this); updateCommandPreview(); updateParamsCount()">
        <input type="text" value="${escapeAttr(value)}" placeholder="value (empty = boolean flag)"
            class="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm flex-1 font-mono focus:outline-none focus:border-blue-500"
            oninput="onServiceParamInput(this); updateCommandPreview()">
        <button type="button" onclick="removeServiceParamRow(this)" class="text-red-400 hover:text-red-300 px-2 py-1 ${isEmpty ? 'invisible' : ''}" title="Remove">
            <i class="fa-solid fa-xmark"></i>
        </button>
    `;
    const emptyRow = container.querySelector('.param-row[data-empty="1"]');
    if (emptyRow && !isEmpty) {
        container.insertBefore(row, emptyRow);
    } else {
        container.appendChild(row);
    }
    updateCommandPreview();
    return row;
}

function ensureEmptyServiceRow() {
    const container = document.getElementById('dynamic-params-container');
    const emptyRow = container.querySelector('.param-row[data-empty="1"]');
    if (!emptyRow) {
        addServiceParamRow('', '', true);
    }
}

function onServiceParamInput(input) {
    const row = input.closest('.param-row');
    if (row.dataset.empty === '1') {
        delete row.dataset.empty;
        row.querySelector('button').classList.remove('invisible');
        ensureEmptyServiceRow();
    }
}

function removeServiceParamRow(btn) {
    const row = btn.closest('.param-row');
    if (row.dataset.empty === '1') return;
    row.remove();
    updateCommandPreview();
    updateParamsCount();
    ensureEmptyServiceRow();
}

function getServiceParams() {
    const rows = document.querySelectorAll('#dynamic-params-container .param-row:not([data-empty="1"])');
    const params = {};
    rows.forEach(row => {
        const inputs = row.querySelectorAll('input');
        const flag = inputs[0].value.trim();
        const value = inputs[1].value.trim();
        if (flag) {
            params[flag] = value;
        }
    });
    return params;
}

function getServiceParamsArray() {
    const rows = document.querySelectorAll('#dynamic-params-container .param-row:not([data-empty="1"])');
    const params = [];
    rows.forEach(row => {
        const inputs = row.querySelectorAll('input');
        const flag = inputs[0].value.trim();
        const value = inputs[1].value.trim();
        if (flag) {
            params.push({ flag, value });
        }
    });
    return params;
}

function loadServiceParams(params) {
    document.getElementById('dynamic-params-container').innerHTML = '';
    Object.entries(params).forEach(([flag, value]) => addServiceParamRow(flag, String(value)));
    ensureEmptyServiceRow();
    updateParamsCount();
}

function resetServiceParams() {
    const engine = document.querySelector('input[name="engine"]:checked')?.value;
    if (engine === 'llamacpp') {
        loadServiceParams({ '-ngl': '999', '-c': '8192' });
    } else {
        loadServiceParams({});
    }
    showToast('Parameters reset');
    updateCommandPreview();
}

// ── Parameter Reference Panel ──

function renderServeParamRef(filter = '') {
    const engine = document.querySelector('input[name="engine"]:checked')?.value;
    const list = document.getElementById('serve-param-ref-list');
    const empty = document.getElementById('serve-param-ref-empty');
    if (!list) return;

    // For vllm, we don't show the reference panel (different flags)
    if (engine !== 'llamacpp') {
        list.innerHTML = '<div class="text-gray-500 text-xs py-2">Reference available for llama.cpp only.</div>';
        empty.classList.add('hidden');
        return;
    }

    const q = filter.toLowerCase();
    let html = '';
    let currentCat = '';
    let hasResults = false;

    SERVE_PARAM_REFERENCE.forEach(p => {
        const flagText = p.flag || p.long;
        const searchable = `${p.flag} ${p.long} ${p.desc} ${p.cat}`.toLowerCase();
        if (q && !searchable.includes(q)) return;

        hasResults = true;

        if (p.cat !== currentCat) {
            currentCat = p.cat;
            html += `<div class="text-gray-500 uppercase tracking-wider text-[10px] font-semibold mt-2 mb-1 px-1">${escapeHtml(currentCat)}</div>`;
        }

        const primaryFlag = escapeHtml(p.flag || p.long);
        const secondaryFlag = p.flag && p.long ? ` <span class="text-gray-600">${escapeHtml(p.long)}</span>` : '';
        const defBadge = p.def ? `<span class="text-gray-600 ml-auto pl-2 whitespace-nowrap">${escapeHtml(p.def)}</span>` : '';

        const tooltip = p.tip ? `<div class="param-tooltip">${p.tip}</div>` : '';
        html += `
            <div class="param-ref-row group rounded px-2 py-1.5 relative hover:bg-gray-700/50 cursor-pointer transition-colors"
                 onclick="useServeRefParam('${escapeAttr(p.flag || p.long)}', '${escapeAttr(p.def)}')">
                <div class="flex items-center gap-1">
                    <span class="text-yellow-400 font-mono font-semibold">${primaryFlag}</span>${secondaryFlag}${defBadge}
                </div>
                <div class="text-gray-400 leading-snug mt-0.5">${escapeHtml(p.desc)}</div>
                ${tooltip}
            </div>`;
    });

    list.innerHTML = html;
    empty.classList.toggle('hidden', hasResults);
}

function filterServeParamRef() {
    const q = document.getElementById('serve-param-search').value.trim();
    renderServeParamRef(q);
}

function useServeRefParam(flag, defaultValue) {
    // Check if this flag already exists in the param rows
    const rows = document.querySelectorAll('#dynamic-params-container .param-row');
    for (const row of rows) {
        const flagInput = row.querySelector('input');
        if (flagInput && flagInput.value.trim() === flag) {
            flagInput.focus();
            showToast(`${flag} is already in your parameters`);
            return;
        }
    }
    addServiceParamRow(flag, defaultValue);
    updateParamsCount();
    showToast(`Added ${flag}`);
}

// ── Copy From Modal ──

async function openCopyFromModal() {
    const engine = document.querySelector('input[name="engine"]:checked')?.value;
    if (!engine) {
        alert('Please select an engine first');
        return;
    }

    try {
        // GET /api/services returns Docker status array, not DB configs.
        // Fetch the status list to get service names, then fetch each config individually.
        const data = await fetchAPI('/services');
        const serviceNames = (data.services || [])
            .map(s => s.name)
            .filter(name => name && name !== 'open-webui');

        // Fetch configs in parallel
        const configs = await Promise.all(
            serviceNames.map(async name => {
                try {
                    const resp = await fetchAPI(`/services/${name}`);
                    return { name, config: resp.config };
                } catch {
                    return null;
                }
            })
        );

        const filteredServices = configs.filter(entry => {
            if (!entry || !entry.config) return false;
            if (entry.config.template_type !== engine) return false;
            if (modalMode === 'update' && entry.name === currentServiceName) return false;
            return true;
        });

        const listContainer = document.getElementById('copy-from-list');
        const emptyMessage = document.getElementById('copy-from-empty');

        if (filteredServices.length === 0) {
            listContainer.classList.add('hidden');
            emptyMessage.classList.remove('hidden');
        } else {
            listContainer.classList.remove('hidden');
            emptyMessage.classList.add('hidden');

            listContainer.innerHTML = filteredServices.map(({ name, config }) => {
                const paramCount = Object.keys(config.params || config.optional_flags || {}).length;
                return `
                    <button
                        type="button"
                        onclick="copyParametersFromService('${name}')"
                        class="w-full text-left px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded border border-gray-600 transition"
                    >
                        <div class="font-semibold">${name}</div>
                        <div class="text-xs text-gray-400 mt-1">${paramCount} parameter${paramCount !== 1 ? 's' : ''}</div>
                    </button>
                `;
            }).join('');
        }

        document.getElementById('copy-from-modal').classList.remove('hidden');
    } catch (error) {
        console.error('Failed to load services:', error);
        alert(`Failed to load services: ${error.message}`);
    }
}

function closeCopyFromModal() {
    document.getElementById('copy-from-modal').classList.add('hidden');
}

async function copyParametersFromService(serviceName) {
    try {
        const response = await fetchAPI(`/services/${serviceName}`);
        const config = response.config;

        // Support both new (params) and legacy (optional_flags + custom_flags) formats
        let params = config.params;
        if (!params || Object.keys(params).length === 0) {
            // Convert legacy format
            params = {};
            const metadata = availableFlags[config.template_type] || {};
            const optFlags = config.optional_flags || {};
            for (const [name, value] of Object.entries(optFlags)) {
                if (metadata[name]) {
                    params[metadata[name].cli] = String(value);
                }
            }
            const customFlags = config.custom_flags || {};
            for (const [name, value] of Object.entries(customFlags)) {
                params[name] = String(value);
            }
        }

        loadServiceParams(params);
        closeCopyFromModal();

        showToast(`Copied ${Object.keys(params).length} parameters from ${serviceName}`);
        updateCommandPreview();
    } catch (error) {
        console.error('Failed to copy parameters:', error);
        alert(`Failed to copy parameters: ${error.message}`);
    }
}

function hasInvalidCustomFlags() {
    // Validate all param rows have valid flag names
    const rows = document.querySelectorAll('#dynamic-params-container .param-row:not([data-empty="1"])');
    for (const row of rows) {
        const flagInput = row.querySelector('input');
        const flagName = flagInput?.value?.trim() || '';
        if (flagName && !flagName.startsWith('-')) return true;
    }
    return false;
}

// Command Preview Generator
function generateCommandPreview() {
    const engine = document.querySelector('input[name="engine"]:checked')?.value;
    if (!engine) {
        return 'Select an engine to see command preview';
    }

    const modelPath = document.getElementById('model-path')?.value || '';
    const modelName = document.getElementById('model-hf-name')?.value || '';
    const alias = document.getElementById('service-name')?.value || 'model-alias';
    const apiKey = document.getElementById('api-key')?.value || 'your-api-key';

    // Get unified params from rows (CLI-keyed)
    const paramsArray = getServiceParamsArray();

    let preview = '';

    if (engine === 'llamacpp') {
        preview = '/llama.cpp/build/bin/llama-server\n';
        preview += `-m ${modelPath || '/path/to/model.gguf'}\n`;
        preview += `--alias ${alias}\n`;
        preview += `--host "0.0.0.0"\n`;
        preview += `--port 8080\n`;
        preview += `--api-key ${apiKey}\n`;

        paramsArray.forEach(p => {
            if (p.value) {
                preview += `${p.flag} ${p.value}\n`;
            } else {
                preview += `${p.flag}\n`;
            }
        });
    } else if (engine === 'vllm') {
        // vllm still uses old approach for now - render params as CLI flags
        preview = 'vllm serve ';
        preview += `${modelName || 'org/model-name'}\n`;
        preview += `--host 0.0.0.0\n`;
        preview += `--port 8000\n`;
        preview += `--trust-remote-code\n`;
        preview += `--served-model-name ${alias}\n`;
        preview += `--api-key ${apiKey}\n`;

        paramsArray.forEach(p => {
            if (p.value) {
                preview += `${p.flag} ${p.value}\n`;
            } else {
                preview += `${p.flag}\n`;
            }
        });
    }

    return preview;
}

function updateCommandPreview() {
    const previewEl = document.getElementById('command-preview');
    if (previewEl) {
        previewEl.textContent = generateCommandPreview();
    }
}

function openCreateServiceModal(modelData) {
    modalMode = 'create';
    currentModelData = modelData;
    currentServiceName = null;

    // Set modal title and button
    document.getElementById('modal-title').textContent = 'Create New Service';
    const submitBtn = document.getElementById('create-service-submit');
    submitBtn.innerHTML = '<i class="fa-solid fa-plus mr-2"></i>Create Service';

    // Enable service name and engine fields
    document.getElementById('service-name').disabled = false;
    document.querySelectorAll('input[name="engine"]').forEach(radio => radio.disabled = false);

    // Set model info
    document.getElementById('modal-model-name').textContent = modelData.full_name || modelData.name;
    document.getElementById('modal-model-size').textContent = `Size: ${modelData.size_str}${modelData.quantization ? ' | Quantization: ' + modelData.quantization : ''}`;

    // Reset parameters count
    document.getElementById('params-count').textContent = '(0 configured)';

    // Auto-select engine based on model format
    const hasGGUF = modelData.files && modelData.files.some(f => f.name.endsWith('.gguf'));
    const llamacppRadio = document.querySelector('input[name="engine"][value="llamacpp"]');
    const vllmRadio = document.querySelector('input[name="engine"][value="vllm"]');

    if (hasGGUF) {
        llamacppRadio.checked = true;
        vllmRadio.checked = false;
    } else {
        llamacppRadio.checked = false;
        vllmRadio.checked = true;
    }

    // Trigger engine change to show/hide appropriate fields
    handleEngineChange();

    // Auto-fill fields
    const suggestedName = generateServiceName(modelData.name, llamacppRadio.checked ? 'llamacpp' : 'vllm', modelData.quantization);
    document.getElementById('service-name').value = suggestedName;

    // Set HuggingFace model name for vllm
    document.getElementById('model-hf-name').value = modelData.name;

    // Clear previous values
    document.getElementById('service-port').value = '';
    document.getElementById('model-path').value = '';
    document.getElementById('api-key').value = '';
    document.getElementById('create-service-error').classList.add('hidden');

    // Populate GGUF file selector if model has GGUF files
    populateGGUFFileSelector(modelData.files);

    // Load flag metadata, GPU info, and next available port
    const engine = llamacppRadio.checked ? 'llamacpp' : 'vllm';
    Promise.all([
        loadFlagMetadata(engine),
        loadGPUInfo(),
        getNextAvailablePort()
    ]).then(([_, __, nextPort]) => {
        applySmartDefaults();
        renderServeParamRef();
        if (nextPort) {
            document.getElementById('service-port').value = nextPort;
        }
    });

    // Show modal
    document.getElementById('create-service-modal').classList.remove('hidden');

    // Add engine change listeners with flag reload
    document.querySelectorAll('input[name="engine"]').forEach(radio => {
        radio.addEventListener('change', async () => {
            await handleEngineChange();
            const newEngine = document.querySelector('input[name="engine"]:checked')?.value;
            if (newEngine) {
                await loadFlagMetadata(newEngine);
                applySmartDefaults();
                renderServeParamRef();

                if (newEngine === 'llamacpp' && currentModelData) {
                    populateGGUFFileSelector(currentModelData.files);
                }
            }
        });
    });

    // Add form submit listener
    const form = document.getElementById('create-service-form');
    form.onsubmit = handleCreateServiceSubmit;

    // Add ESC key listener
    document.addEventListener('keydown', handleCreateServiceEscapeKey);

    // Add input listeners for real-time preview
    document.getElementById('service-name').addEventListener('input', updateCommandPreview);
    document.getElementById('model-path').addEventListener('input', updateCommandPreview);
    document.getElementById('model-hf-name').addEventListener('input', updateCommandPreview);
    document.getElementById('api-key').addEventListener('input', updateCommandPreview);

    // Initialize drag functionality
    initModalDrag();
}

function initModalDrag() {
    const modal = document.getElementById('create-service-modal-content');
    const header = document.getElementById('create-service-modal-header');

    let isDragging = false;
    let currentX;
    let currentY;
    let initialX;
    let initialY;
    let xOffset = 0;
    let yOffset = 0;

    header.addEventListener('mousedown', dragStart);
    document.addEventListener('mousemove', drag);
    document.addEventListener('mouseup', dragEnd);

    function dragStart(e) {
        initialX = e.clientX - xOffset;
        initialY = e.clientY - yOffset;

        if (e.target === header || header.contains(e.target)) {
            // Don't drag if clicking the close button
            if (!e.target.closest('button')) {
                isDragging = true;
            }
        }
    }

    function drag(e) {
        if (isDragging) {
            e.preventDefault();

            currentX = e.clientX - initialX;
            currentY = e.clientY - initialY;

            xOffset = currentX;
            yOffset = currentY;

            setTranslate(currentX, currentY, modal);
        }
    }

    function dragEnd(e) {
        initialX = currentX;
        initialY = currentY;
        isDragging = false;
    }

    function setTranslate(xPos, yPos, el) {
        el.style.transform = `translate3d(${xPos}px, ${yPos}px, 0)`;
    }
}

function closeCreateServiceModal() {
    document.getElementById('create-service-modal').classList.add('hidden');
    currentModelData = null;

    // Reset modal position
    const modal = document.getElementById('create-service-modal-content');
    if (modal) {
        modal.style.transform = 'translate3d(0px, 0px, 0)';
    }

    // Remove ESC key listener
    document.removeEventListener('keydown', handleCreateServiceEscapeKey);
}

function handleCreateServiceEscapeKey(event) {
    if (event.key === 'Escape') {
        closeCreateServiceModal();
    }
}

// Edit Service Functions
function editService(serviceName) {
    openUpdateServiceModal(serviceName);
}

async function openUpdateServiceModal(serviceName) {
    try {
        modalMode = 'update';
        currentServiceName = serviceName;
        currentModelData = null;

        // Fetch service configuration
        const response = await fetchAPI(`/services/${serviceName}`);
        const config = response.config;

        // Set modal title and button
        document.getElementById('modal-title').textContent = `Update Service: ${serviceName}`;
        const submitBtn = document.getElementById('create-service-submit');
        submitBtn.innerHTML = '<i class="fa-solid fa-save mr-2"></i>Update Service';

        // Disable service name and engine fields (cannot change)
        document.getElementById('service-name').value = serviceName;
        document.getElementById('service-name').disabled = true;

        // Set engine based on template_type and disable it
        const engine = config.template_type;
        const llamacppRadio = document.querySelector('input[name="engine"][value="llamacpp"]');
        const vllmRadio = document.querySelector('input[name="engine"][value="vllm"]');

        if (engine === 'llamacpp') {
            llamacppRadio.checked = true;
            vllmRadio.checked = false;
        } else {
            llamacppRadio.checked = false;
            vllmRadio.checked = true;
        }

        // Disable engine radios
        llamacppRadio.disabled = true;
        vllmRadio.disabled = true;

        // Trigger engine change to show/hide appropriate fields
        handleEngineChange();

        // Hide model info (not applicable for update)
        document.getElementById('modal-model-name').textContent = `Editing: ${serviceName}`;
        document.getElementById('modal-model-size').textContent = `Engine: ${config.template_type}`;

        // Populate fields
        document.getElementById('service-port').value = config.port || '';
        document.getElementById('api-key').value = config.api_key || '';

        // Engine-specific fields
        if (engine === 'llamacpp') {
            document.getElementById('model-path').value = config.model_path || '';
            // Hide file selector in update mode (no model data available)
            document.getElementById('gguf-file-selector').classList.add('hidden');
        } else {
            document.getElementById('model-hf-name').value = config.model_name || '';
        }

        // Load flag metadata and populate parameter rows from existing config
        await loadFlagMetadata(engine);

        // Load params: prefer new format, fall back to legacy conversion
        let params = config.params;
        if (!params || Object.keys(params).length === 0) {
            // Convert legacy optional_flags + custom_flags to unified params
            params = {};
            const metadata = availableFlags[engine] || {};
            const optFlags = config.optional_flags || {};
            for (const [name, value] of Object.entries(optFlags)) {
                if (metadata[name]) {
                    params[metadata[name].cli] = String(value);
                }
            }
            const customFlags = config.custom_flags || {};
            for (const [name, value] of Object.entries(customFlags)) {
                params[name] = String(value);
            }
        }
        loadServiceParams(params);
        renderServeParamRef();

        // Clear error
        document.getElementById('create-service-error').classList.add('hidden');

        // Load GPU info for display
        await loadGPUInfo();

        // Show modal
        document.getElementById('create-service-modal').classList.remove('hidden');

        // Add engine change listeners (but they won't work since radios are disabled)
        document.querySelectorAll('input[name="engine"]').forEach(radio => {
            radio.addEventListener('change', handleEngineChange);
        });

        // Add form submit listener
        const form = document.getElementById('create-service-form');
        form.onsubmit = handleCreateServiceSubmit;

        // Add ESC key listener
        document.addEventListener('keydown', handleCreateServiceEscapeKey);

        // Add input listeners for real-time preview
        document.getElementById('service-name').addEventListener('input', updateCommandPreview);
        document.getElementById('model-path').addEventListener('input', updateCommandPreview);
        document.getElementById('model-hf-name').addEventListener('input', updateCommandPreview);
        document.getElementById('api-key').addEventListener('input', updateCommandPreview);

        // Initialize drag functionality
        initModalDrag();

    } catch (error) {
        console.error('Failed to load service config:', error);
        alert(`Failed to load service configuration: ${error.message}`);
    }
}

function handleEngineChange() {
    const engine = document.querySelector('input[name="engine"]:checked')?.value;

    const modelPathGroup = document.getElementById('model-path-group');
    const modelNameGroup = document.getElementById('model-name-group');
    const modelPathInput = document.getElementById('model-path');
    const paramsSection = document.getElementById('params-section');

    if (engine === 'llamacpp') {
        modelPathGroup.classList.remove('hidden');
        modelNameGroup.classList.add('hidden');
        modelPathInput.required = true;
    } else if (engine === 'vllm') {
        modelPathGroup.classList.add('hidden');
        modelNameGroup.classList.remove('hidden');
        modelPathInput.required = false;
    }

    // Show params section once engine is selected
    if (paramsSection && engine) {
        paramsSection.classList.remove('hidden');
    }

    updateCommandPreview();
}

async function handleCreateServiceSubmit(event) {
    event.preventDefault();

    const errorEl = document.getElementById('create-service-error');
    const submitBtn = document.getElementById('create-service-submit');
    const originalBtnText = submitBtn.innerHTML;

    try {
        // Check for invalid custom flags before submitting
        if (hasInvalidCustomFlags()) {
            errorEl.textContent = 'Please fix invalid custom flag names before saving.';
            errorEl.classList.remove('hidden');
            return;
        }

        // Disable button and show loading
        submitBtn.disabled = true;
        const loadingText = modalMode === 'create'
            ? '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Creating...'
            : '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Updating...';
        submitBtn.innerHTML = loadingText;
        errorEl.classList.add('hidden');

        const engine = document.querySelector('input[name="engine"]:checked').value;

        if (modalMode === 'create') {
            // CREATE MODE
            const serviceName = document.getElementById('service-name').value;
            const port = document.getElementById('service-port').value;
            const apiKey = document.getElementById('api-key').value.trim();

            const requestBody = {
                template_type: engine,
                alias: serviceName
            };

            if (port) requestBody.port = parseInt(port);
            if (apiKey) requestBody.api_key = apiKey;

            if (engine === 'llamacpp') {
                requestBody.model_path = document.getElementById('model-path').value;
            } else {
                requestBody.model_name = document.getElementById('model-hf-name').value;
            }

            // Send unified params (CLI-keyed)
            requestBody.params = getServiceParams();

            const response = await fetchAPI('/services', {
                method: 'POST',
                body: JSON.stringify(requestBody)
            });

            closeCreateServiceModal();
            await loadServices();

            alert(`Service "${response.service_name}" created successfully on port ${response.port}!\n\nAPI Key: ${response.api_key}\n\nThe service is stopped. Use the Start button to run it.`);

        } else {
            // UPDATE MODE
            const port = document.getElementById('service-port').value;
            const apiKey = document.getElementById('api-key').value.trim();

            const requestBody = {
                alias: currentServiceName
            };

            if (port) requestBody.port = parseInt(port);
            if (apiKey) requestBody.api_key = apiKey;

            if (engine === 'llamacpp') {
                requestBody.model_path = document.getElementById('model-path').value;
            } else {
                requestBody.model_name = document.getElementById('model-hf-name').value;
            }

            // Send unified params (CLI-keyed)
            requestBody.params = getServiceParams();

            const response = await fetchAPI(`/services/${currentServiceName}`, {
                method: 'PUT',
                body: JSON.stringify(requestBody)
            });

            closeCreateServiceModal();
            await loadServices();

            // Show simple success notification
            alert(`Service "${currentServiceName}" updated successfully!`);
        }

    } catch (error) {
        // Show error
        const action = modalMode === 'create' ? 'create' : 'update';
        errorEl.textContent = error.message || `Failed to ${action} service`;
        errorEl.classList.remove('hidden');
    } finally {
        // Re-enable button
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalBtnText;
    }
}

function generateServiceName(modelName, engine, quantization) {
    // Generate alias only - backend will prepend engine prefix
    let baseName = modelName.split('/').pop();  // Get part after /
    baseName = baseName.replace(/-GGUF$/i, '').replace(/-Instruct$/i, '').replace(/-FP8-Dynamic$/i, '');

    if (quantization) {
        const shortQuant = quantization.replace(/UD-/g, '').replace(/_K_XL/g, '').replace(/_/g, '').toLowerCase();
        baseName += `-${shortQuant}`;
    }

    baseName = baseName.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');

    // Return alias without engine prefix - backend adds it via gen_service_name()
    return baseName;
}

// Auto-refresh every 3 seconds (only if logged in)
setInterval(() => {
    if (getToken() && !document.getElementById('app').classList.contains('hidden')) {
        loadServices();
        loadGPU();
    }
}, 3000);

// Initialize on page load
init();
