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
                const paramCount = Object.keys(config.params || {}).length;
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
        modalManager.lockScroll();
    } catch (error) {
        console.error('Failed to load services:', error);
        alert(`Failed to load services: ${error.message}`);
    }
}

function closeCopyFromModal() {
    document.getElementById('copy-from-modal').classList.add('hidden');
    modalManager.unlockScroll();
}

async function copyParametersFromService(serviceName) {
    try {
        const response = await fetchAPI(`/services/${serviceName}`);
        const config = response.config;

        const params = config.params || {};

        loadServiceParams(params);
        closeCopyFromModal();

        showToast(`Copied ${Object.keys(params).length} parameters from ${serviceName}`);
        updateCommandPreview();
    } catch (error) {
        console.error('Failed to copy parameters:', error);
        alert(`Failed to copy parameters: ${error.message}`);
    }
}
