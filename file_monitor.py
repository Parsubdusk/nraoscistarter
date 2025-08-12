"""
Automatic file monitoring for SDR recordings
Watches the audio directory and automatically processes new files
"""
import os
import time
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from werkzeug.utils import secure_filename
from datetime import datetime
import hashlib
from app import app, db
from models import Recording, ProcessingQueue
from rfi_detector import RFIDetector

class AudioFileHandler(FileSystemEventHandler):
    """Handle new audio files in the monitoring directory"""
    
    def __init__(self):
        self.processing_extensions = {'.wav', '.flac', '.ogg', '.mp3', '.raw', '.iq', '.dat'}
        self.min_file_age = 5  # Wait 5 seconds after file creation to ensure it's complete
        
    def on_created(self, event):
        """Handle new file creation"""
        if event.is_directory:
            return
            
        file_path = event.src_path
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext in self.processing_extensions:
            logging.info(f"New audio file detected: {filename}")
            # Wait a bit to ensure file is completely written
            threading.Timer(self.min_file_age, self.process_new_file, args=[file_path]).start()
    
    def process_new_file(self, file_path):
        """Process newly detected audio file"""
        try:
            if not os.path.exists(file_path):
                logging.warning(f"File disappeared before processing: {file_path}")
                return
                
            filename = os.path.basename(file_path)
            secure_name = secure_filename(filename)
            
            # Get file stats
            file_size = os.path.getsize(file_path)
            file_mtime = os.path.getmtime(file_path)
            
            # Calculate file hash to avoid duplicates
            file_hash = self.calculate_file_hash(file_path)
            
            with app.app_context():
                # Check if file already processed
                existing = Recording.query.filter_by(file_hash=file_hash).first()
                if existing:
                    logging.info(f"File already processed: {filename}")
                    return
                
                # Create new recording entry
                recording = Recording(
                    filename=filename,
                    original_filename=filename,
                    file_path=file_path,
                    file_size=file_size,
                    file_hash=file_hash,
                    upload_timestamp=datetime.fromtimestamp(file_mtime),
                    processed=False,
                    auto_detected=True
                )
                
                db.session.add(recording)
                db.session.commit()
                
                # Add to processing queue
                queue_item = ProcessingQueue(
                    recording_id=recording.id,
                    status='pending'
                )
                db.session.add(queue_item)
                db.session.commit()
                
                logging.info(f"Auto-processing started for: {filename}")
                
                # Start async processing
                detector = RFIDetector()
                detector.process_recording_async(recording.id)
                
        except Exception as e:
            logging.error(f"Error processing new file {file_path}: {str(e)}")
    
    def calculate_file_hash(self, file_path):
        """Calculate SHA-256 hash of file for duplicate detection"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logging.error(f"Error calculating hash for {file_path}: {str(e)}")
            return None

class FileMonitor:
    """Main file monitoring service"""
    
    def __init__(self, watch_directory=None):
        self.watch_directory = watch_directory or app.config.get('AUDIO_DIRECTORY', './recordings')
        self.observer = None
        self.running = False
        
    def start_monitoring(self):
        """Start monitoring the audio directory"""
        try:
            # Ensure watch directory exists
            os.makedirs(self.watch_directory, exist_ok=True)
            
            # Set up file system observer
            self.observer = Observer()
            event_handler = AudioFileHandler()
            self.observer.schedule(event_handler, self.watch_directory, recursive=True)
            
            self.observer.start()
            self.running = True
            
            logging.info(f"File monitoring started for: {self.watch_directory}")
            
            # Process any existing files on startup
            self.process_existing_files()
            
        except Exception as e:
            logging.error(f"Failed to start file monitoring: {str(e)}")
    
    def stop_monitoring(self):
        """Stop file monitoring"""
        if self.observer and self.running:
            self.observer.stop()
            self.observer.join()
            self.running = False
            logging.info("File monitoring stopped")
    
    def process_existing_files(self):
        """Process any existing files in the directory on startup"""
        try:
            handler = AudioFileHandler()
            for root, dirs, files in os.walk(self.watch_directory):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    file_ext = os.path.splitext(filename)[1].lower()
                    
                    if file_ext in handler.processing_extensions:
                        # Check if file is recent (within last hour)
                        file_age = time.time() - os.path.getmtime(file_path)
                        if file_age < 3600:  # 1 hour
                            logging.info(f"Processing existing file: {filename}")
                            threading.Timer(2, handler.process_new_file, args=[file_path]).start()
                            
        except Exception as e:
            logging.error(f"Error processing existing files: {str(e)}")

# Global monitor instance
file_monitor = FileMonitor()

def start_file_monitoring():
    """Start the file monitoring service"""
    if not file_monitor.running:
        file_monitor.start_monitoring()

def stop_file_monitoring():
    """Stop the file monitoring service"""
    file_monitor.stop_monitoring()