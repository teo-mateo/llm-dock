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
                        <a href="${window.location.protocol}//${window.location.hostname}:${service.host_port}" target="_blank" class="flex-1 bg-blue-600 hover:bg-blue-700 px-3 py-2 rounded font-semibold text-center" title="Open WebUI">
                            <i class="fa-solid fa-arrow-up-right-from-square mr-1"></i>Open
                        </a>
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
    modalManager.lockScroll();
}

function closeDeleteModal() {
    document.getElementById('delete-service-modal').classList.add('hidden');
    serviceToDelete = null;
    modalManager.unlockScroll();

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
    modalManager.lockScroll();

    // Focus and select the input text
    setTimeout(() => {
        input.focus();
        input.select();
    }, 50);
}

function closeRenameModal() {
    document.getElementById('rename-service-modal').classList.add('hidden');
    serviceToRename = null;
    modalManager.unlockScroll();

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
        modalManager.lockScroll();
    } catch (error) {
        console.error('Failed to preview service:', error);
        alert(`Failed to preview service: ${error.message}`);
    }
}

function closePreviewModal() {
    document.getElementById('preview-service-modal').classList.add('hidden');
    currentPreviewYaml = '';
    modalManager.unlockScroll();
}

function copyPreviewYaml() {
    copyToClipboard(currentPreviewYaml, 'YAML');
}
