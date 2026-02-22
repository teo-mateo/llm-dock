// Parameter reference — fetches from backend API (single source of truth)
let serveParamCache = null;

async function fetchServeParamReference() {
    if (serveParamCache) return serveParamCache;
    try {
        const data = await fetchAPI('/flag-metadata/llamacpp');
        const flags = data.optional_flags || {};

        // Transform API format into flat array for rendering
        const CATEGORY_ORDER = [
            'Context', 'GPU', 'Multi-GPU', 'KV Cache', 'Batching',
            'Sampling', 'CPU', 'Memory', 'RoPE', 'LoRA',
            'Speculative', 'Features'
        ];

        const items = Object.entries(flags).map(([key, meta]) => ({
            cat: meta.category || 'Other',
            flag: meta.cli || '',
            desc: meta.description || '',
            def: meta.default || '',
            tip: meta.tip || '',
        }));

        // Sort by category order, then by flag name within category
        items.sort((a, b) => {
            const ai = CATEGORY_ORDER.indexOf(a.cat);
            const bi = CATEGORY_ORDER.indexOf(b.cat);
            const ao = ai === -1 ? 999 : ai;
            const bo = bi === -1 ? 999 : bi;
            if (ao !== bo) return ao - bo;
            return a.flag.localeCompare(b.flag);
        });

        serveParamCache = items;
        return items;
    } catch (e) {
        console.error('Failed to load param reference:', e);
        return [];
    }
}

async function renderServeParamRef(filter = '') {
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

    const params = await fetchServeParamReference();
    const q = filter.toLowerCase();
    let html = '';
    let currentCat = '';
    let hasResults = false;

    params.forEach(p => {
        const searchable = `${p.flag} ${p.desc} ${p.cat}`.toLowerCase();
        if (q && !searchable.includes(q)) return;

        hasResults = true;

        if (p.cat !== currentCat) {
            currentCat = p.cat;
            html += `<div class="text-gray-500 uppercase tracking-wider text-[10px] font-semibold mt-2 mb-1 px-1">${escapeHtml(currentCat)}</div>`;
        }

        const primaryFlag = escapeHtml(p.flag);
        const defBadge = p.def ? `<span class="text-gray-600 ml-auto pl-2 whitespace-nowrap">${escapeHtml(p.def)}</span>` : '';

        const tooltip = p.tip ? `<div class="param-tooltip">${p.tip}</div>` : '';
        html += `
            <div class="param-ref-row group rounded px-2 py-1.5 relative hover:bg-gray-700/50 cursor-pointer transition-colors"
                 onclick="useServeRefParam('${escapeAttr(p.flag)}', '${escapeAttr(p.def)}')">
                <div class="flex items-center gap-1">
                    <span class="text-yellow-400 font-mono font-semibold">${primaryFlag}</span>${defBadge}
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

// Position fixed tooltips relative to their row
(function () {
    document.addEventListener('mouseover', function (e) {
        const row = e.target.closest('.param-ref-row');
        if (!row) return;
        const tip = row.querySelector('.param-tooltip');
        if (!tip) return;
        const rect = row.getBoundingClientRect();
        // Show above the row; if it would go off-screen top, show below
        tip.style.left = rect.left + 'px';
        const tipHeight = tip.offsetHeight || 120;
        if (rect.top - tipHeight - 8 < 0) {
            tip.style.top = (rect.bottom + 8) + 'px';
            tip.style.bottom = 'auto';
        } else {
            tip.style.top = (rect.top - tipHeight - 8) + 'px';
            tip.style.bottom = 'auto';
        }
    });
})();

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
