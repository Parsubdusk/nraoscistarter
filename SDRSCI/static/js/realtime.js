// NRAO Spectrum Sentinels - Real-time WebSocket Client
class RealtimeClient {
    constructor() {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.isConnected = false;
        
        this.init();
    }
    
    init() {
        // Initialize Socket.IO connection
        this.socket = io({
            transports: ['websocket', 'polling'],
            upgrade: true,
            rememberUpgrade: true
        });
        
        this.setupEventHandlers();
        this.setupConnectionStatusIndicator();
    }
    
    setupEventHandlers() {
        // Connection events
        this.socket.on('connect', () => {
            console.log('Connected to real-time server');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus(true);
            this.joinRooms();
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from real-time server');
            this.isConnected = false;
            this.updateConnectionStatus(false);
            this.scheduleReconnect();
        });
        
        this.socket.on('connect_error', (error) => {
            console.error('Connection error:', error);
            this.updateConnectionStatus(false);
        });
        
        // Data update events
        this.socket.on('stats_update', (data) => {
            this.updateStatistics(data);
        });
        
        this.socket.on('activity_update', (data) => {
            this.updateActivityFeed(data);
        });
        
        this.socket.on('file_uploaded', (data) => {
            this.handleFileUploaded(data);
        });
        
        this.socket.on('file_detected', (data) => {
            this.handleFileDetected(data);
        });
        
        this.socket.on('processing_started', (data) => {
            this.handleProcessingStarted(data);
        });
        
        this.socket.on('processing_completed', (data) => {
            this.handleProcessingCompleted(data);
        });
        
        this.socket.on('processing_failed', (data) => {
            this.handleProcessingFailed(data);
        });
        
        this.socket.on('detection_progress', (data) => {
            this.handleDetectionProgress(data);
        });
    }
    
    joinRooms() {
        // Join relevant rooms for different types of updates
        this.socket.emit('join_room', { room: 'processing_updates' });
        this.socket.emit('join_room', { room: 'detection_updates' });
        this.socket.emit('join_room', { room: 'stats_updates' });
    }
    
    updateConnectionStatus(connected) {
        const indicator = document.getElementById('connection-status');
        if (indicator) {
            indicator.className = `connection-status ${connected ? 'connected' : 'disconnected'}`;
            indicator.innerHTML = `
                <span class="status-indicator ${connected ? 'status-online' : 'status-offline'}"></span>
                ${connected ? 'Connected' : 'Disconnected'}
            `;
        }
    }
    
    setupConnectionStatusIndicator() {
        // Create connection status indicator if it doesn't exist
        if (!document.getElementById('connection-status')) {
            const indicator = document.createElement('div');
            indicator.id = 'connection-status';
            indicator.className = 'connection-status disconnected';
            indicator.innerHTML = `
                <span class="status-indicator status-offline"></span>
                Connecting...
            `;
            document.body.appendChild(indicator);
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * this.reconnectAttempts;
            
            console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
            
            setTimeout(() => {
                if (!this.isConnected) {
                    this.socket.connect();
                }
            }, delay);
        } else {
            console.error('Max reconnection attempts reached');
            this.updateConnectionStatus(false);
        }
    }
    
    updateStatistics(data) {
        // Update statistics cards with animation
        const stats = [
            { id: 'total-recordings', value: data.total_recordings },
            { id: 'total-detections', value: data.total_detections },
            { id: 'processing-count', value: data.processing_count },
            { id: 'pending-count', value: data.pending_count }
        ];
        
        stats.forEach(stat => {
            const element = document.getElementById(stat.id);
            if (element) {
                const currentValue = parseInt(element.textContent) || 0;
                if (currentValue !== stat.value) {
                    this.animateStatUpdate(element, stat.value);
                }
            }
        });
    }
    
    animateStatUpdate(element, newValue) {
        // Add update animation class
        const card = element.closest('.stats-card');
        if (card) {
            card.classList.add('updated');
            setTimeout(() => {
                card.classList.remove('updated');
            }, 800);
        }
        
        // Animate number change
        const currentValue = parseInt(element.textContent) || 0;
        const increment = newValue > currentValue ? 1 : -1;
        const duration = 500;
        const steps = Math.abs(newValue - currentValue);
        const stepDuration = duration / Math.max(steps, 1);
        
        let current = currentValue;
        const timer = setInterval(() => {
            current += increment;
            element.textContent = current.toLocaleString();
            
            if (current === newValue) {
                clearInterval(timer);
            }
        }, stepDuration);
    }
    
    updateActivityFeed(data) {
        const feedContainer = document.getElementById('activity-feed');
        if (!feedContainer) return;
        
        // Update recent recordings
        if (data.recent_recordings) {
            this.updateRecentRecordings(data.recent_recordings);
        }
        
        // Update recent detections
        if (data.recent_detections) {
            this.updateRecentDetections(data.recent_detections);
        }
    }
    
    updateRecentRecordings(recordings) {
        const container = document.getElementById('recent-recordings');
        if (!container) return;
        
        recordings.forEach(recording => {
            if (!document.querySelector(`[data-recording-id="${recording.id}"]`)) {
                this.addActivityItem(container, {
                    type: 'recording',
                    id: recording.id,
                    title: `New Recording: ${recording.filename}`,
                    timestamp: recording.upload_time,
                    status: recording.processed ? 'completed' : 'processing'
                });
            }
        });
    }
    
    updateRecentDetections(detections) {
        const container = document.getElementById('recent-detections');
        if (!container) return;
        
        detections.slice(0, 5).forEach(detection => {
            if (!document.querySelector(`[data-detection-id="${detection.id}"]`)) {
                this.addActivityItem(container, {
                    type: 'detection',
                    id: detection.id,
                    title: `RFI Detected: ${(detection.frequency / 1e6).toFixed(2)} MHz`,
                    timestamp: detection.detected_at,
                    details: `${detection.power_level.toFixed(1)} dB (${detection.interference_type})`
                });
            }
        });
    }
    
    addActivityItem(container, item) {
        const itemElement = document.createElement('div');
        itemElement.className = 'activity-item new';
        itemElement.setAttribute(`data-${item.type}-id`, item.id);
        
        itemElement.innerHTML = `
            <div class="d-flex justify-content-between align-items-start">
                <div>
                    <strong>${item.title}</strong>
                    ${item.details ? `<div class="text-muted small">${item.details}</div>` : ''}
                </div>
                <span class="activity-timestamp">${this.formatTimestamp(item.timestamp)}</span>
            </div>
            ${item.status ? `<div class="processing-status ${item.status} mt-2">
                <span class="status-indicator status-${item.status === 'completed' ? 'online' : 'processing'}"></span>
                ${item.status}
            </div>` : ''}
        `;
        
        // Insert at the top
        container.insertBefore(itemElement, container.firstChild);
        
        // Remove old items if too many
        const items = container.querySelectorAll('.activity-item');
        if (items.length > 10) {
            items[items.length - 1].remove();
        }
        
        // Remove 'new' class after animation
        setTimeout(() => {
            itemElement.classList.remove('new');
        }, 600);
    }
    
    handleFileUploaded(data) {
        console.log('File uploaded:', data);
        
        // Show notification
        this.showNotification('success', `File uploaded: ${data.filename}`);
        
        // Update compression info if available
        if (data.compression_ratio && data.compression_ratio < 1) {
            const compressionSaved = ((1 - data.compression_ratio) * 100).toFixed(1);
            this.showNotification('info', `File compressed: ${compressionSaved}% size reduction`);
        }
        
        // Refresh page data if on results page
        if (window.location.pathname === '/results') {
            setTimeout(() => {
                location.reload();
            }, 1000);
        }
    }
    
    handleFileDetected(data) {
        console.log('File detected:', data);
        this.showNotification('info', `New file detected: ${data.filename}`);
    }
    
    handleProcessingStarted(data) {
        console.log('Processing started:', data);
        this.updateProcessingStatus(data.recording_id, 'processing');
        this.showNotification('info', `Processing started for recording ${data.recording_id}`);
    }
    
    handleProcessingCompleted(data) {
        console.log('Processing completed:', data);
        this.updateProcessingStatus(data.recording_id, 'completed');
        
        const message = data.rfi_detected 
            ? `Processing complete: ${data.detections_found} RFI detections found`
            : 'Processing complete: No RFI detected';
            
        this.showNotification('success', message);
    }
    
    handleProcessingFailed(data) {
        console.log('Processing failed:', data);
        this.updateProcessingStatus(data.recording_id, 'failed');
        this.showNotification('error', `Processing failed: ${data.error}`);
    }
    
    handleDetectionProgress(data) {
        console.log('Detection progress:', data);
        
        // Update progress indicator if visible
        const progressElement = document.getElementById(`progress-${data.recording_id}`);
        if (progressElement) {
            progressElement.textContent = `${data.detections_found} detections found...`;
        }
    }
    
    updateProcessingStatus(recordingId, status) {
        const statusElement = document.querySelector(`[data-recording-id="${recordingId}"] .processing-status`);
        if (statusElement) {
            statusElement.className = `processing-status ${status}`;
            statusElement.innerHTML = `
                <span class="status-indicator status-${status === 'completed' ? 'online' : status === 'processing' ? 'processing' : 'offline'}"></span>
                ${status}
            `;
        }
    }
    
    showNotification(type, message) {
        // Create notification using Bootstrap toast or simple alert
        const toast = document.createElement('div');
        toast.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
        toast.style.cssText = 'top: 80px; right: 20px; z-index: 1060; max-width: 300px;';
        
        toast.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(toast);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 5000);
    }
    
    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60000) { // Less than 1 minute
            return 'Just now';
        } else if (diff < 3600000) { // Less than 1 hour
            const minutes = Math.floor(diff / 60000);
            return `${minutes}m ago`;
        } else if (diff < 86400000) { // Less than 1 day
            const hours = Math.floor(diff / 3600000);
            return `${hours}h ago`;
        } else {
            return date.toLocaleDateString();
        }
    }
    
    // Public methods for external use
    emit(event, data) {
        if (this.socket && this.isConnected) {
            this.socket.emit(event, data);
        }
    }
    
    on(event, callback) {
        if (this.socket) {
            this.socket.on(event, callback);
        }
    }
}

// Initialize real-time client when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.realtimeClient = new RealtimeClient();
    
    // Setup drag and drop for file uploads
    setupDragAndDrop();
    
    // Setup auto-refresh for heatmap
    if (window.location.pathname === '/heatmap') {
        setupHeatmapAutoRefresh();
    }
});

function setupDragAndDrop() {
    const uploadZone = document.querySelector('.upload-zone');
    if (!uploadZone) return;
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadZone.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadZone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadZone.addEventListener(eventName, unhighlight, false);
    });
    
    uploadZone.addEventListener('drop', handleDrop, false);
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight(e) {
        uploadZone.classList.add('dragover');
    }
    
    function unhighlight(e) {
        uploadZone.classList.remove('dragover');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            const fileInput = document.getElementById('file');
            if (fileInput) {
                fileInput.files = files;
                // Trigger change event to show selected file
                fileInput.dispatchEvent(new Event('change'));
            }
        }
    }
}

function setupHeatmapAutoRefresh() {
    // Auto-refresh heatmap data every 30 seconds
    setInterval(() => {
        if (typeof refreshHeatmapData === 'function') {
            refreshHeatmapData();
        }
    }, 30000);
}
