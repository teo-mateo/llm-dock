// Modal scroll lock manager
// Uses reference counting to handle stacked modals (e.g. "Copy from" inside "Create Service")

(function() {
    let modalCount = 0;
    let originalBodyOverflow = '';
    let originalHtmlOverflow = '';

    function lockScroll() {
        if (modalCount === 0) {
            originalBodyOverflow = document.body.style.overflow;
            originalHtmlOverflow = document.documentElement.style.overflow;
            document.body.style.overflow = 'hidden';
            document.documentElement.style.overflow = 'hidden';
        }
        modalCount++;
    }

    function unlockScroll() {
        if (modalCount > 0) {
            modalCount--;
        }
        if (modalCount === 0) {
            document.body.style.overflow = originalBodyOverflow;
            document.documentElement.style.overflow = originalHtmlOverflow;
        }
    }

    window.modalManager = { lockScroll, unlockScroll };

    // Login modal is visible on page load (no 'hidden' class), so lock immediately
    lockScroll();
})();
