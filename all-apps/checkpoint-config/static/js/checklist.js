// E-Rawanna IoT - Checklist Page JavaScript

// ============== Theme Management ==============
function getSystemTheme() {
    // Detect system theme preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
        return 'light';
    }
    // Default to dark if system preference not available
    return 'dark';
}

function initTheme() {
    // Check if user has manually set a theme preference
    const manualTheme = localStorage.getItem('theme_manual');
    
    let theme;
    if (manualTheme) {
        // Use manually set theme
        theme = manualTheme;
    } else {
        // Auto-detect from system theme
        theme = getSystemTheme();
    }
    
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcon(theme);
    
    // Listen for system theme changes (only if no manual override)
    if (!manualTheme && window.matchMedia) {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addEventListener('change', (e) => {
            // Only update if user hasn't manually set a preference
            if (!localStorage.getItem('theme_manual')) {
                const newTheme = e.matches ? 'dark' : 'light';
                document.documentElement.setAttribute('data-theme', newTheme);
                updateThemeIcon(newTheme);
            }
        });
    }
    
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    // Store manual preference
    localStorage.setItem('theme_manual', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
}

// ============== Notification Functions ==============
function showToast(type, title, message) {
    const ribbon = document.getElementById('notificationRibbon');
    const icon = document.getElementById('notifIcon');
    const text = document.getElementById('notifText');
    
    ribbon.className = 'notification-ribbon ' + type;
    icon.className = 'bi ' + (type === 'success' ? 'bi-check-circle-fill' : type === 'error' ? 'bi-x-circle-fill' : 'bi-exclamation-triangle-fill');
    text.textContent = message;
    
    ribbon.classList.add('show');
    
    setTimeout(() => {
        ribbon.classList.remove('show');
    }, 5000);
}

function hideNotification() {
    document.getElementById('notificationRibbon').classList.remove('show');
}

function showLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    if (show) {
        overlay.classList.add('active');
    } else {
        overlay.classList.remove('active');
    }
}

// ============== Checklist Logic ==============
function initChecklist() {
    const checkboxes = document.querySelectorAll('.checklist-item input[type="checkbox"]');
    const proceedBtn = document.getElementById('proceedBtn');

    // Pre-Configuration: always start with all checklist items unchecked
    localStorage.removeItem('checklistState');
    checkboxes.forEach(cb => {
        cb.checked = false;
        cb.addEventListener('change', () => {
            updateProceedButton();
        });
    });

    if (proceedBtn) {
        proceedBtn.disabled = true;
    }
}

/**
 * Explicit wipe only — re-running the checklist must NOT clear iot_configuration.json.
 * Operators reuse existing values + validated flags unless they choose Start fresh.
 */
async function resetAllCheckpointConfig() {
    try {
        sessionStorage.removeItem('scanIpRange');
        sessionStorage.removeItem('discoveredDevices');
        const response = await fetch('/api/config/reset-all', { method: 'POST' });
        const result = await response.json();
        if (!response.ok || result.status !== 200) {
            console.warn('[Checklist] Config reset failed:', result.message || response.status);
            showToast('error', 'Reset', result.message || 'Could not reset checkpoint configuration');
            return false;
        }
        console.log('[Checklist] All checkpoint configuration reset to defaults');
        showToast('success', 'Fresh start', 'Configuration cleared — wizard will start empty');
        return true;
    } catch (err) {
        console.error('[Checklist] Config reset error:', err);
        showToast('error', 'Reset', 'Could not reset checkpoint configuration');
        return false;
    }
}

async function confirmStartFreshConfig() {
    const ok = window.confirm(
        'Start fresh configuration?\n\nThis will wipe the saved iot_configuration.json (all devices and validated flags).\nThis cannot be undone.'
    );
    if (!ok) return;
    showLoading(true);
    try {
        await resetAllCheckpointConfig();
    } finally {
        showLoading(false);
    }
}

async function showExistingConfigHint() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        const cfg = data.config || data || {};
        const hasSomething =
            !!(cfg.rfid && (cfg.rfid.ip || cfg.rfid.validated)) ||
            !!(cfg.digitizer && (cfg.digitizer.host || cfg.digitizer.broker_host || cfg.digitizer.validated)) ||
            !!(cfg.display && (cfg.display.ip || cfg.display.validated)) ||
            !!(cfg.io_controller && cfg.io_controller.validated) ||
            cfg.status === true;
        if (hasSomething) {
            console.log('[Checklist] Reusing existing iot_configuration.json (not wiped)');
        }
    } catch (err) {
        console.warn('[Checklist] Could not inspect existing config:', err);
    }
}

function updateProceedButton() {
    const checkboxes = document.querySelectorAll('.checklist-item input[type="checkbox"]');
    const proceedBtn = document.getElementById('proceedBtn');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    
    proceedBtn.disabled = !allChecked;
    
    // Save state
    const state = {};
    checkboxes.forEach(cb => {
        state[cb.id] = cb.checked;
    });
    localStorage.setItem('checklistState', JSON.stringify(state));
}

// ============== IP Range ==============
async function loadSuggestedIpRange() {
    try {
        const response = await fetch('/api/network/ip-range');
        const data = await response.json();
        
        // Populate IP range fields
        document.getElementById('startIp').value = data.start_ip;
        document.getElementById('endIp').value = data.end_ip;
    } catch (error) {
        console.error('[IP Range] Error:', error);
        // Default values
        document.getElementById('startIp').value = '192.168.1.1';
        document.getElementById('endIp').value = '192.168.1.254';
    }
}

// ============== Proceed to Scan ==============
function proceedToScan() {
    const startIp = document.getElementById('startIp').value.trim();
    const endIp = document.getElementById('endIp').value.trim();
    
    if (!startIp || !endIp) {
        showToast('error', 'Validation Error', 'Please enter IP range');
        return;
    }
    
    // Store IP range in sessionStorage for the discovery page
    sessionStorage.setItem('scanIpRange', JSON.stringify({ startIp, endIp }));
    
    // Navigate to discovery page
    window.location.href = '/discover';
}

// ============== Initialize ==============
document.addEventListener('DOMContentLoaded', async function() {
    initTheme();
    initChecklist();
    // Keep existing config + validated flags on re-run (no automatic reset-all).
    await showExistingConfigHint();
    loadSuggestedIpRange();
});
