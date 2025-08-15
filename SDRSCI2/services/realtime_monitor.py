import logging
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AudioFileHandler(FileSystemEventHandler):
    """Handle new audio file events"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def on_created(self, event):
        if not event.is_directory:
            self.logger.info(f"New audio file detected: {event.src_path}")
            # Would normally queue for processing

# Global observer instance
_observer = None
_monitor_thread = None

def start_realtime_monitoring():
    """Start real-time file monitoring"""
    global _observer, _monitor_thread
    
    logger = logging.getLogger(__name__)
    
    try:
        if _observer is None:
            _observer = Observer()
            event_handler = AudioFileHandler()
            
            # Monitor audio directory (would be configurable)
            audio_dir = 'audio_recordings'
            if not os.path.exists(audio_dir):
                os.makedirs(audio_dir, exist_ok=True)
                
            _observer.schedule(event_handler, audio_dir, recursive=True)
            _observer.start()
            
            logger.info("Real-time monitoring started")
    except Exception as e:
        logger.error(f"Failed to start real-time monitoring: {e}")

def stop_realtime_monitoring():
    """Stop real-time file monitoring"""
    global _observer
    
    logger = logging.getLogger(__name__)
    
    try:
        if _observer:
            _observer.stop()
            _observer.join()
            _observer = None
            logger.info("Real-time monitoring stopped")
    except Exception as e:
        logger.error(f"Failed to stop real-time monitoring: {e}")

import os  # Add this import