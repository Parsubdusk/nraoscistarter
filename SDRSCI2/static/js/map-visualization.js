/**
 * NRAO Spectrum Sentinels - Map Visualization
 * Real-time RFI detection mapping with Leaflet
 */

let rfiMap = null;
let markersLayer = null;
let socket = null;
let autoRefreshInterval = null;
let currentFilters = {
    timeRange: 24,
    minPower: -100,
    frequencyBand: 'all'
};

/**
 * Initialize the RFI detection map
 */
function initializeRFIMap(options = {}) {
    // Merge options with defaults
    currentFilters = { ...currentFilters, ...options };
    
    // Initialize the map
    rfiMap = L.map('rfi-map', {
        center: [20, 0], // Center on equator
        zoom: 2,
        zoomControl: true,
        attributionControl: true
    });

    // Add dark theme tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(rfiMap);

    // Create markers layer group
    markersLayer = L.layerGroup().addTo(rfiMap);

    // Initialize WebSocket connection
    initializeWebSocket();

    // Load initial data
    loadRFIData();

    // Set up form handlers
    setupFormHandlers();

    // Set up auto-refresh if enabled
    if (options.autoRefresh) {
        startAutoRefresh(options.updateInterval || 30000);
    }

    // Hide loading overlay
    setTimeout(() => {
        document.getElementById('map-loading').style.display = 'none';
    }, 1000);
}

/**
 * Load RFI detection data from the server
 */
async function loadRFIData() {
    try {
        const params = new URLSearchParams({
            hours: currentFilters.timeRange,
            min_power: currentFilters.minPower,
            frequency_band: currentFilters.frequencyBand
        });

        const response = await fetch(`/api/heatmap_data?${params}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Clear existing markers
        markersLayer.clearLayers();
        
        // Update statistics
        updateStatistics(data.statistics || {});
        
        // Add new markers
        if (data.detections && data.detections.length > 0) {
            addDetectionMarkers(data.detections);
        } else {
            console.log('No RFI detections found for current filters');
        }
        
    } catch (error) {
        console.error('Error loading RFI data:', error);
        showErrorMessage('Failed to load RFI detection data. Please try again.');
    }
}

/**
 * Add detection markers to the map
 */
function addDetectionMarkers(detections) {
    detections.forEach(detection => {
        if (!detection.latitude || !detection.longitude) {
            return; // Skip detections without valid coordinates
        }

        const lat = parseFloat(detection.latitude);
        const lng = parseFloat(detection.longitude);
        
        if (isNaN(lat) || isNaN(lng)) {
            return; // Skip invalid coordinates
        }

        // Determine marker color based on power level and astronomy band
        const color = getMarkerColor(detection.power_level, detection.is_radio_astronomy_band);
        const size = getMarkerSize(detection.power_level);
        
        // Create marker
        const marker = L.circleMarker([lat, lng], {
            radius: size,
            fillColor: color,
            color: '#ffffff',
            weight: 1,
            opacity: 0.8,
            fillOpacity: 0.6
        });

        // Create popup content
        const popupContent = createPopupContent(detection);
        marker.bindPopup(popupContent);

        // Add marker to layer
        markersLayer.addLayer(marker);
    });
}

/**
 * Get marker color based on power level and astronomy band
 */
function getMarkerColor(powerLevel, isAstronomyBand) {
    if (isAstronomyBand) {
        return '#6f42c1'; // Purple for critical astronomy bands
    }
    
    if (powerLevel >= -60) {
        return '#dc3545'; // Red for high power
    } else if (powerLevel >= -80) {
        return '#ffc107'; // Yellow for medium power
    } else {
        return '#28a745'; // Green for low power
    }
}

/**
 * Get marker size based on power level
 */
function getMarkerSize(powerLevel) {
    if (powerLevel >= -60) {
        return 10;
    } else if (powerLevel >= -80) {
        return 8;
    } else {
        return 6;
    }
}

/**
 * Create popup content for detection marker
 */
function createPopupContent(detection) {
    const frequency = detection.frequency ? (detection.frequency / 1e6).toFixed(3) + ' MHz' : 'Unknown';
    const powerLevel = detection.power_level ? detection.power_level.toFixed(1) + ' dB' : 'Unknown';
    const location = detection.location_city || 'Unknown Location';
    const timestamp = detection.detected_at ? new Date(detection.detected_at).toLocaleString() : 'Unknown Time';
    const astronomyBand = detection.astronomy_band_name || 'N/A';
    
    return `
        <div class="popup-content">
            <h6 class="mb-2 text-primary">RFI Detection</h6>
            <div class="small">
                <div><strong>Location:</strong> ${location}</div>
                <div><strong>Frequency:</strong> ${frequency}</div>
                <div><strong>Power Level:</strong> ${powerLevel}</div>
                <div><strong>Astronomy Band:</strong> ${astronomyBand}</div>
                <div><strong>Detected:</strong> ${timestamp}</div>
                ${detection.interference_type ? `<div><strong>Type:</strong> ${detection.interference_type}</div>` : ''}
            </div>
        </div>
    `;
}

/**
 * Update statistics display
 */
function updateStatistics(stats) {
    document.getElementById('total-detections').textContent = stats.total_detections || 0;
    document.getElementById('active-locations').textContent = stats.active_locations || 0;
    document.getElementById('critical-band-alerts').textContent = stats.critical_band_alerts || 0;
    
    const avgPower = stats.avg_power_level;
    document.getElementById('avg-power-level').textContent = avgPower ? avgPower.toFixed(1) : 'N/A';
}

/**
 * Initialize WebSocket connection for real-time updates
 */
function initializeWebSocket() {
    socket = io();
    
    socket.on('connect', function() {
        console.log('Connected to real-time updates');
    });
    
    socket.on('rfi_detected', function(data) {
        console.log('New RFI detection received:', data);
        
        // Add new marker if it matches current filters
        if (shouldIncludeDetection(data)) {
            addDetectionMarkers([data]);
            
            // Update statistics
            updateStatisticsIncremental();
        }
    });
    
    socket.on('file_uploaded', function(data) {
        console.log('New file uploaded:', data);
        
        // Refresh data to include potential new detections
        setTimeout(() => {
            loadRFIData();
        }, 2000); // Wait 2 seconds for processing
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from real-time updates');
    });
}

/**
 * Check if detection should be included based on current filters
 */
function shouldIncludeDetection(detection) {
    // Check power level
    if (detection.power_level < currentFilters.minPower) {
        return false;
    }
    
    // Check frequency band
    if (currentFilters.frequencyBand !== 'all') {
        // Implementation would check against specific frequency ranges
        // For now, include all detections
    }
    
    // Check time range
    const detectionTime = new Date(detection.detected_at);
    const cutoffTime = new Date(Date.now() - currentFilters.timeRange * 60 * 60 * 1000);
    
    return detectionTime >= cutoffTime;
}

/**
 * Update statistics incrementally
 */
function updateStatisticsIncremental() {
    const currentTotal = parseInt(document.getElementById('total-detections').textContent) || 0;
    document.getElementById('total-detections').textContent = currentTotal + 1;
}

/**
 * Set up form event handlers
 */
function setupFormHandlers() {
    const filterForm = document.getElementById('filter-form');
    const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
    
    // Filter form submission
    filterForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Update filters
        currentFilters.timeRange = parseInt(document.getElementById('time-range').value);
        currentFilters.minPower = parseFloat(document.getElementById('min-power').value);
        currentFilters.frequencyBand = document.getElementById('frequency-band').value;
        
        // Reload data
        loadRFIData();
    });
    
    // Auto-refresh toggle
    let isAutoRefreshActive = false;
    autoRefreshToggle.addEventListener('click', function() {
        isAutoRefreshActive = !isAutoRefreshActive;
        
        if (isAutoRefreshActive) {
            startAutoRefresh();
            this.innerHTML = '<i data-feather="pause" class="me-1"></i>Stop Auto-refresh';
            this.classList.remove('btn-outline-secondary');
            this.classList.add('btn-outline-danger');
        } else {
            stopAutoRefresh();
            this.innerHTML = '<i data-feather="play" class="me-1"></i>Auto-refresh';
            this.classList.remove('btn-outline-danger');
            this.classList.add('btn-outline-secondary');
        }
        
        feather.replace(); // Update feather icons
    });
    
    // Map view toggles
    document.querySelectorAll('input[name="map-view"]').forEach(radio => {
        radio.addEventListener('change', function() {
            filterMarkersBasedOnView(this.id);
        });
    });
}

/**
 * Filter markers based on selected view
 */
function filterMarkersBasedOnView(viewId) {
    markersLayer.eachLayer(function(layer) {
        switch(viewId) {
            case 'view-all':
                layer.setStyle({ opacity: 0.8, fillOpacity: 0.6 });
                break;
            case 'view-critical':
                const isCritical = layer.options.fillColor === '#6f42c1' || layer.options.fillColor === '#dc3545';
                layer.setStyle({ 
                    opacity: isCritical ? 0.8 : 0.2, 
                    fillOpacity: isCritical ? 0.6 : 0.1 
                });
                break;
            case 'view-clusters':
                // For clusters view, we could implement marker clustering
                // For now, just show all markers
                layer.setStyle({ opacity: 0.8, fillOpacity: 0.6 });
                break;
        }
    });
}

/**
 * Start auto-refresh functionality
 */
function startAutoRefresh(interval = 30000) {
    stopAutoRefresh(); // Clear any existing interval
    
    autoRefreshInterval = setInterval(() => {
        loadRFIData();
        updateLastUpdateTime();
    }, interval);
}

/**
 * Stop auto-refresh functionality
 */
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

/**
 * Update the last update time display
 */
function updateLastUpdateTime() {
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString('en-US', {
        timeZone: 'UTC',
        hour12: false
    }) + ' UTC';
}

/**
 * Show error message to user
 */
function showErrorMessage(message) {
    // Create a temporary alert
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger alert-dismissible fade show position-fixed';
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alertDiv.innerHTML = `
        <i data-feather="alert-circle" class="me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    feather.replace();
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// Export functions for global access
window.initializeRFIMap = initializeRFIMap;
window.loadRFIData = loadRFIData;
