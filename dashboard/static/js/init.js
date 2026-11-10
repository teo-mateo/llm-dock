function showApp() {
    document.getElementById('app').classList.remove('hidden');
}

// Initialize the dashboard
async function init() {
    const token = getToken();

    if (!token) {
        redirectToLogin();
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/verify`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            clearToken();
            redirectToLogin();
            return;
        }

        showApp();
        // Kick off an HTTP fetch in parallel with the SSE stream. Whichever
        // arrives first paints the services list; the SSE snapshot then takes
        // over for live updates. Without this, a stuck/slow SSE leaves the
        // list empty until ctrl+F5.
        loadServices().catch(() => {});
        startServicesStream();
        startGPUStream();
        loadSystemInfo();
        loadImageMetadata();
        loadGlobalApiKey();
    } catch (error) {
        console.error('Token verification failed:', error);
        clearToken();
        redirectToLogin();
    }
}

// Services are now streamed via SSE in startServicesStream(), no polling needed

// Initialize on page load
init();
