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

function toggleModel(modelIndex) {
    const element = document.getElementById(`model-${modelIndex}`);
    const arrow = document.getElementById(`arrow-${modelIndex}`);
    if (element.classList.contains('hidden')) {
        element.classList.remove('hidden');
        arrow.textContent = '\u25BC';
    } else {
        element.classList.add('hidden');
        arrow.textContent = '\u25B6';
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
                            <span id="arrow-${index}" class="text-xs text-gray-500">\u25B6</span>
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
