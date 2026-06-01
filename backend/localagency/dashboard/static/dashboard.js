/*
 * LocalAgency Kits — Exception Dashboard
 * Client-side JavaScript for HTMX enhancements.
 */

(function () {
    'use strict';

    // ── Auto-refresh indicator ───────────────────────────────────────
    // Shows a subtle "refreshing" state on HTMX-triggered fragments
    document.addEventListener('htmx:beforeRequest', function (e) {
        const target = e.detail.target;
        if (target) {
            target.classList.add('opacity-50', 'transition-opacity', 'duration-150');
        }
    });

    document.addEventListener('htmx:afterRequest', function (e) {
        const target = e.detail.target;
        if (target) {
            target.classList.remove('opacity-50', 'transition-opacity', 'duration-150');
        }
    });

    // ── Error handling ───────────────────────────────────────────────
    // Show a toast when an HTMX request fails
    document.addEventListener('htmx:responseError', function (e) {
        console.warn('[Dashboard] HTMX request failed:', e.detail.pathInfo.requestPath, e.detail.xhr.status);
    });

    // ── Live clock (backup: set by inline script in base.html) ───────
    // Already handled in base.html inline script.

    // ── Keyboard shortcuts ───────────────────────────────────────────
    document.addEventListener('keydown', function (e) {
        // Don't interfere with input fields
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
            return;
        }

        switch (e.key) {
            case '1': case '2': case '3': case '4': case '5': case '6':
                const links = [
                    '/',            // 1 - Overview
                    '/alerts',      // 2 - Alerts
                    '/missed-calls',// 3 - Missed Calls
                    '/bookings',    // 4 - Bookings
                    '/errors',      // 5 - Error Log
                    '/circuit-breakers', // 6 - Systems
                ];
                const idx = parseInt(e.key, 10) - 1;
                if (idx >= 0 && idx < links.length) {
                    window.location.href = links[idx];
                }
                break;
            case 'r':
            case 'R':
                // Refresh HTMX fragments on the page
                document.querySelectorAll('[hx-get]').forEach(function (el) {
                    htmx.trigger(el, 'htmx:load');
                });
                break;
        }
    });

    // ── Tab visibility ───────────────────────────────────────────────
    // Pause HTMX polling when tab is hidden, resume when visible
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            document.querySelectorAll('[hx-trigger*="every"]').forEach(function (el) {
                el.setAttribute('data-hx-trigger', el.getAttribute('hx-trigger'));
                el.setAttribute('hx-trigger', 'none');
            });
        } else {
            document.querySelectorAll('[data-hx-trigger]').forEach(function (el) {
                el.setAttribute('hx-trigger', el.getAttribute('data-hx-trigger'));
                el.removeAttribute('data-hx-trigger');
                htmx.process(el);
            });
        }
    });

})();
