// Initialize the dashboard
async function init() {
    const token = getToken();

    if (token) {
        // Token exists, verify it and show dashboard
        try {
            const response = await fetch(`${API_BASE}/auth/verify`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                // Token is valid, show dashboard
                hideLoginModal();
                loadServices();
                loadGPU();
                loadSystemInfo();
                loadImageMetadata();
                loadGlobalApiKey();
            } else {
                // Token is invalid, clear it and show login
                clearToken();
                showLoginModal();
            }
        } catch (error) {
            console.error('Token verification failed:', error);
            clearToken();
            showLoginModal();
        }
    } else {
        // No token, show login
        showLoginModal();
    }
}

// Auto-refresh every 3 seconds (only if logged in)
setInterval(() => {
    if (getToken() && !document.getElementById('app').classList.contains('hidden')) {
        loadServices();
        loadGPU();
    }
}, 3000);

// Initialize on page load
init();
