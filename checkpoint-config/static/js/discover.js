// GMDC Checkpoint Config — page 2 (network scan)

let scanInterval = null;
let discoveredDevices = {
    network: [],
    comPorts: [],
    candidates: {
        rfid: [],
        cameras: [],
        modbus: [],
        servers: [],
        all_ips: []
    }
};

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

// ============== Network Scanning ==============
async function startNetworkScan() {
    let startIp, endIp;
    
    // Get IP range from sessionStorage
    const ipRangeData = sessionStorage.getItem('scanIpRange');
    if (ipRangeData) {
        const parsed = JSON.parse(ipRangeData);
        startIp = parsed.startIp;
        endIp = parsed.endIp;
        console.log('[Discover] Using IP range from session:', startIp, '-', endIp);
    } else {
        // Fallback: auto-detect IP range
        console.log('[Discover] No IP range in session, auto-detecting...');
        try {
            const rangeResponse = await fetch('/api/network/ip-range');
            const rangeData = await rangeResponse.json();
            startIp = rangeData.start_ip;
            endIp = rangeData.end_ip;
            console.log('[Discover] Auto-detected IP range:', startIp, '-', endIp);
        } catch (error) {
            console.error('[Discover] Failed to auto-detect IP range:', error);
            showToast('error', 'Error', 'Could not determine IP range. Please go back to checklist.');
            return;
        }
    }
    
    if (!startIp || !endIp) {
        showToast('error', 'Error', 'Invalid IP range. Please go back to checklist.');
        return;
    }
    
    document.getElementById('scanCurrentIp').textContent = `Scanning ${startIp} to ${endIp}...`;
    
    try {
        const response = await fetch('/api/network/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_ip: startIp, end_ip: endIp })
        });
        
        const result = await response.json();
        console.log('[Discover] Scan start result:', result);
        
        if (result.status === 200) {
            document.getElementById('scanTotal').textContent = result.total_ips;
            
            // Start polling for progress
            scanInterval = setInterval(pollScanProgress, 500);
        } else {
            showToast('error', 'Scan Error', result.message || 'Failed to start scan');
        }
    } catch (error) {
        console.error('[Network Scan] Error:', error);
        showToast('error', 'Error', 'Failed to start network scan');
    }
}

async function pollScanProgress() {
    try {
        const response = await fetch('/api/network/status');
        const status = await response.json();
        
        console.log('[Scan Status]', status);
        
        // Update progress UI - API returns 'progress' not 'scanned'
        const scanned = status.progress || 0;
        const total = status.total || 0;
        const found = status.found || 0;
        
        document.getElementById('scanProgress').textContent = scanned;
        document.getElementById('scanFound').textContent = found;
        document.getElementById('scanCurrentIp').textContent = status.current_ip || 'Scanning...';
        
        const progressPercent = total > 0 ? (scanned / total) * 100 : 0;
        document.getElementById('scanProgressBar').style.width = progressPercent + '%';
        
        // Check if scan is complete
        if (!status.running && scanned > 0) {
            clearInterval(scanInterval);
            scanInterval = null;
            
            // Fetch results
            await fetchScanResults();
        }
    } catch (error) {
        console.error('[Scan Progress] Error:', error);
    }
}

async function fetchScanResults() {
    try {
        console.log('[Discover] Fetching scan results...');
        const response = await fetch('/api/network/results');
        const results = await response.json();
        
        console.log('[Discover] Results received:', results);
        
        discoveredDevices.network = results.network_devices || [];
        discoveredDevices.comPorts = results.com_ports || [];
        discoveredDevices.candidates = results.candidates || {};
        
        console.log('[Discover] Discovered devices:', discoveredDevices);
        
        // Store in sessionStorage for devices page
        sessionStorage.setItem('discoveredDevices', JSON.stringify(discoveredDevices));
        
        // Update UI
        displayResults();
    } catch (error) {
        console.error('[Fetch Results] Error:', error);
        showToast('error', 'Error', 'Failed to fetch scan results');
    }
}

function displayResults() {
    // Update summary
    document.getElementById('networkDeviceCount').textContent = discoveredDevices.network.length;
    document.getElementById('comPortCount').textContent = discoveredDevices.comPorts.length;
    
    // Populate network devices table
    const networkBody = document.getElementById('networkDevicesBody');
    networkBody.innerHTML = '';
    
    discoveredDevices.network.forEach(device => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ip-cell">${device.ip}</td>
            <td><span class="device-type-badge">${device.device_type || 'Unknown'}</span></td>
            <td>${(device.open_ports || []).map(p => `<span class="port-badge">${p}</span>`).join(' ')}</td>
        `;
        networkBody.appendChild(row);
    });
    
    // Populate COM ports table
    const comBody = document.getElementById('comPortsBody');
    comBody.innerHTML = '';
    
    discoveredDevices.comPorts.forEach(port => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ip-cell">${port.port}</td>
            <td>${port.description || 'Serial Port'}</td>
        `;
        comBody.appendChild(row);
    });
    
    // Show results section
    document.getElementById('discoveryResults').classList.remove('hidden');
    document.getElementById('scanCurrentIp').textContent = 'Scan complete!';
}

// ============== Navigation ==============
function goBack() {
    window.location.href = '/';
}

function rescan() {
    // Clear results
    document.getElementById('discoveryResults').classList.add('hidden');
    document.getElementById('scanProgress').textContent = '0';
    document.getElementById('scanFound').textContent = '0';
    document.getElementById('scanProgressBar').style.width = '0%';
    
    // Restart scan
    startNetworkScan();
}

function proceedToConfig() {
    sessionStorage.setItem('discoveredDevices', JSON.stringify(discoveredDevices));
    window.location.href = '/devices';
}

// ============== Initialize ==============
document.addEventListener('DOMContentLoaded', function() {
    console.log('[Discover] Page loaded, initializing...');
    initTheme();
    
    // Auto-start scan when page loads
    console.log('[Discover] Starting network scan...');
    startNetworkScan();
});

