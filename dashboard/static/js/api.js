// Dynamically construct API base URL based on hostname
// Use port 3399 only for localhost, otherwise use current hostname without port (assumes reverse proxy)
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.hostname === 'z440'
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

    // Auto-extract X-TOTP-Token from response headers for token refresh
    const newToken = response.headers.get('X-TOTP-Token');
    if (newToken) {
        setToken(newToken);
    }

    if (response.status === 401) {
        clearToken();
        showLoginModal();
        throw new Error('Authentication failed');
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
    // Reset password visibility state
    const tokenInput = document.getElementById('token-input');
    const toggleBtn = document.getElementById('toggle-password');
    const icon = document.getElementById('password-icon');
    
    if (tokenInput) tokenInput.type = 'password';
    if (icon) {
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
    if (toggleBtn) {
        toggleBtn.setAttribute('aria-label', 'Show password');
        toggleBtn.setAttribute('aria-pressed', 'false');
    }
    
    const loginModal = document.getElementById('login-modal');
    const wasHidden = loginModal.classList.contains('hidden');
    loginModal.classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');
    if (wasHidden) modalManager.lockScroll();
}

function hideLoginModal() {
    document.getElementById('login-modal').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    modalManager.unlockScroll();
}

async function handleLogin(event) {
    event.preventDefault();

    const token = document.getElementById('token-input').value.trim();
    const errorEl = document.getElementById('login-error');

    if (!token) {
        errorEl.textContent = 'Password cannot be empty';
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
            throw new Error('Invalid password');
        }

        // Token is valid, save it
        setToken(token);
        document.getElementById('token-input').value = '';
        hideLoginModal();
        startServicesStream();
        startGPUStream();
        loadSystemInfo();
        loadImageMetadata();
    } catch (error) {
        errorEl.textContent = `Login failed: ${error.message}`;
        errorEl.classList.remove('hidden');
    }
}

function logout() {
    stopGPUStream();
    stopServicesStream();
    clearToken();
    showLoginModal();
}

function switchLoginTab(tab) {
    const passwordTab = document.getElementById('login-tab-password');
    const totpTab = document.getElementById('login-tab-totp');
    const passwordPanel = document.getElementById('login-password-panel');
    const totpPanel = document.getElementById('login-totp-panel');
    const errorEl = document.getElementById('login-error');

    // Reset error message when switching tabs
    if (errorEl) {
        errorEl.textContent = '';
        errorEl.classList.add('hidden');
    }

    if (tab === 'password') {
        passwordTab.className = 'flex-1 pb-2 text-sm font-medium text-white border-b-2 border-blue-500';
        totpTab.className = 'flex-1 pb-2 text-sm font-medium text-gray-400 border-b-2 border-transparent';
        passwordPanel.classList.remove('hidden');
        totpPanel.classList.add('hidden');
    } else {
        totpTab.className = 'flex-1 pb-2 text-sm font-medium text-white border-b-2 border-blue-500';
        passwordTab.className = 'flex-1 pb-2 text-sm font-medium text-gray-400 border-b-2 border-transparent';
        totpPanel.classList.remove('hidden');
        passwordPanel.classList.add('hidden');
    }
}

async function handleTOTPLogin() {
    const totpInput = document.getElementById('totp-input');
    const errorEl = document.getElementById('login-error');
    const code = totpInput ? totpInput.value.trim() : '';

    if (!code || code.length !== 6) {
        if (errorEl) {
            errorEl.textContent = 'Please enter a 6-digit code';
            errorEl.classList.remove('hidden');
        }
        return;
    }

    try {
        if (errorEl) errorEl.classList.add('hidden');
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: {
                'X-TOTP-Code': code,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Authentication failed');
        }

        const data = await response.json();
        if (data.token) {
            setToken(data.token);
            totpInput.value = '';
            hideLoginModal();
            loadServices().catch(() => {});
            startServicesStream();
            startGPUStream();
            loadSystemInfo();
            loadImageMetadata();
        }
    } catch (error) {
        if (errorEl) {
            errorEl.textContent = `Login failed: ${error.message}`;
            errorEl.classList.remove('hidden');
        }
    }
}
