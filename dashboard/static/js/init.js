// Password visibility toggle for login
function togglePasswordVisibility() {
    const tokenInput = document.getElementById('token-input');
    const toggleBtn = document.getElementById('toggle-password');
    const icon = document.getElementById('password-icon');
    
    if (!tokenInput || !toggleBtn || !icon) return;
    
    const isPassword = tokenInput.type === 'password';
    
    tokenInput.type = isPassword ? 'text' : 'password';
    
    // Toggle icon class and accessibility attributes
    if (isPassword) {
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
        toggleBtn.setAttribute('aria-label', 'Hide password');
        toggleBtn.setAttribute('aria-pressed', 'true');
    } else {
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
        toggleBtn.setAttribute('aria-label', 'Show password');
        toggleBtn.setAttribute('aria-pressed', 'false');
    }
}

// Initialize the dashboard
async function init() {
    // Attach password toggle event listener
    const toggleBtn = document.getElementById('toggle-password');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', togglePasswordVisibility);
    }
	
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
            startServicesStream();
            startGPUStream();
            loadSystemInfo();
            loadImageMetadata();
            loadGlobalApiKey();
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

// Services are now streamed via SSE in startServicesStream(), no polling needed

// Initialize on page load
init();
