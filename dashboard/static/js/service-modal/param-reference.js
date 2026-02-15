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
