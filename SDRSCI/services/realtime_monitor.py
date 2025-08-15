import os
import time
import threading
import logging
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from flask_socketio import emit
from app import app, db, socketio
from models import Recording, ProcessingQueue
from services.file_processor import FileProcessor
from services.rfi_detector import RFIDetector

class RealtimeFileMonitor(FileSystemEventHandler):
    """Monitor directory for new audio files and process them in real-time"""
    
    def __init__(self):
        self.file_processor = FileProcessor()
        self.rfi_detector = RFIDetector()
        self.processing_lock = threading.Lock()
        
    def on_created(self, event):
        if not event.is_directory:
            self._process_new_file(event.src_path)
    
    def on_modified(self, event):
        if not event.is_directory:
            # Wait a bit to ensure file is completely written
            time.sleep(2)
            self._process_new_file(event.src_path)
    
    def _process_new_file(self, file_path):
        """Process a newly detected file"""
        try:
            if not self._is_audio_file(file_path):
                return
            
            with app.app_context():
                # Check if file already exists in database
                filename = os.path.basename(file_path)
                existing = Recording.query.filter_by(filename=filename).first()
                if existing:
                    return
                
                logging.info(f"Processing new file: {file_path}")
                
                # Emit real-time update
                socketio.emit('file_detected', {
                    'filename': filename,
                    'status': 'processing',
                    'timestamp': datetime.now().isoformat()
                })
                
                # Process file
                file_info = self.file_processor.process_upload(file_path, filename)
                if not file_info:
                    socketio.emit('file_error', {
                        'filename': filename,
                        'error': 'File processing failed'
                    })
                    return
                
                # Create database record
                recording = Recording(
                    filename=filename,
                    original_filename=filename,
                    file_path=file_path,
                    file_size=file_info['original_size'],
                    compressed_size=file_info['compressed_size'],
                    compression_ratio=file_info['compression_ratio']
                )
                
                db.session.add(recording)
                db.session.commit()
                
                # Add to processing queue
                queue_item = ProcessingQueue(recording_id=recording.id)
                db.session.add(queue_item)
                db.session.commit()
                
                # Emit upload complete
                socketio.emit('file_uploaded', {
                    'id': recording.id,
                    'filename': filename,
                    'size': file_info['original_size'],
                    'compressed_size': file_info['compressed_size'],
                    'compression_ratio': file_info['compression_ratio'],
                    'timestamp': recording.upload_timestamp.isoformat()
                })
                
                # Start RFI processing
                self.rfi_detector.process_recording_async(recording.id)
                
        except Exception as e:
            logging.error(f"Real-time file processing failed: {str(e)}")
            socketio.emit('file_error', {
                'filename': os.path.basename(file_path),
                'error': str(e)
            })
    
    def _is_audio_file(self, file_path):
        """Check if file is a supported audio format"""
        audio_extensions = {'.wav', '.flac', '.ogg', '.mp3', '.aiff', '.au', '.raw', '.iq', '.bin'}
        return os.path.splitext(file_path)[1].lower() in audio_extensions

class RealtimeDataBroadcaster:
    """Broadcast real-time updates to connected clients"""
    
    def __init__(self):
        self.update_thread = None
        self.running = False
    
    def start(self):
        """Start real-time data broadcasting"""
        if self.update_thread and self.update_thread.is_alive():
            return
        
        self.running = True
        self.update_thread = threading.Thread(target=self._broadcast_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
        logging.info("Real-time data broadcaster started")
    
    def stop(self):
        """Stop real-time data broadcasting"""
        self.running = False
        if self.update_thread:
            self.update_thread.join()
    
    def _broadcast_loop(self):
        """Main broadcasting loop"""
        while self.running:
            try:
                with app.app_context():
                    # Broadcast current statistics
                    stats = self._get_current_stats()
                    socketio.emit('stats_update', stats)
                    
                    # Broadcast recent activity
                    recent_activity = self._get_recent_activity()
                    socketio.emit('activity_update', recent_activity)
                
                time.sleep(5)  # Update every 5 seconds
                
            except Exception as e:
                logging.error(f"Broadcasting error: {str(e)}")
                time.sleep(10)
    
    def _get_current_stats(self):
        """Get current system statistics"""
        from models import Recording, RFIDetection
        
        total_recordings = Recording.query.count()
        total_detections = RFIDetection.query.count()
        processing_count = ProcessingQueue.query.filter_by(status='processing').count()
        pending_count = ProcessingQueue.query.filter_by(status='pending').count()
        
        return {
            'total_recordings': total_recordings,
            'total_detections': total_detections,
            'processing_count': processing_count,
            'pending_count': pending_count,
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_recent_activity(self):
        """Get recent activity for live updates"""
        from models import Recording, RFIDetection
        
        # Get recent recordings
        recent_recordings = Recording.query.order_by(
            Recording.upload_timestamp.desc()
        ).limit(5).all()
        
        # Get recent detections
        recent_detections = RFIDetection.query.order_by(
            RFIDetection.detected_at.desc()
        ).limit(10).all()
        
        return {
            'recent_recordings': [{
                'id': r.id,
                'filename': r.original_filename,
                'upload_time': r.upload_timestamp.isoformat(),
                'processed': r.processed,
                'rfi_detected': r.rfi_detected
            } for r in recent_recordings],
            'recent_detections': [{
                'id': d.id,
                'recording_id': d.recording_id,
                'frequency': d.frequency,
                'power_level': d.power_level,
                'interference_type': d.interference_type,
                'detected_at': d.detected_at.isoformat()
            } for d in recent_detections]
        }

# Global instances
file_monitor = None
data_broadcaster = None

def start_realtime_monitoring():
    """Start real-time monitoring services"""
    global file_monitor, data_broadcaster
    
    try:
        # Start file monitoring
        audio_dir = app.config['AUDIO_DIRECTORY']
        if os.path.exists(audio_dir):
            file_monitor = RealtimeFileMonitor()
            observer = Observer()
            observer.schedule(file_monitor, audio_dir, recursive=True)
            observer.start()
            logging.info(f"File monitoring started for: {audio_dir}")
        else:
            logging.warning(f"Audio directory not found: {audio_dir}")
        
        # Start data broadcasting
        data_broadcaster = RealtimeDataBroadcaster()
        data_broadcaster.start()
        
    except Exception as e:
        logging.error(f"Failed to start real-time monitoring: {str(e)}")

def stop_realtime_monitoring():
    """Stop real-time monitoring services"""
    global data_broadcaster
    
    if data_broadcaster:
        data_broadcaster.stop()
