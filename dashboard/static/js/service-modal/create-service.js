// Create/Update Service Modal
let currentModelData = null;
let modalMode = 'create'; // 'create' or 'update'
let currentServiceName = null; // For update mode
let availableFlags = {}; // Cache for flag metadata by engine
let gpuInfo = null; // Cached GPU info

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
