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

function escapeAttr(str) {
    return String(str).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
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
