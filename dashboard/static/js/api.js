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
