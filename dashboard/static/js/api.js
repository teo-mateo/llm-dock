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

let redirecting = false;

function redirectToLogin() {
    if (redirecting) return;
    redirecting = true;
    const target = window.location.pathname + window.location.search;
    window.location.replace(`/login?redirect=${encodeURIComponent(target)}`);
}

async function fetchAPI(endpoint, options = {}) {
    const token = getToken();

    if (!token) {
        redirectToLogin();
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
        redirectToLogin();
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

async function logout() {
    stopGPUStream();
    stopServicesStream();
    const token = getToken();
    clearToken();
    try {
        await fetch(`${API_BASE}/auth/logout`, {
            method: 'POST',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
    } catch (error) {
        // Navigate anyway; the guard/login page handles a stale cookie.
    }
    window.location.replace(`/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`);
}
