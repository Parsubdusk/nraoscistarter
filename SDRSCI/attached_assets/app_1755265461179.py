import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "spectrum-sentinels-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///rf_data.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = os.environ.get('RECORDINGS_PATH', './recordings')
app.config['AUDIO_DIRECTORY'] = r'C:\Users\coraj\OneDrive\Desktop\Audio'  # Your SDR recording directory
app.config['SDR_SHARP_PATH'] = os.environ.get('SDR_SHARP_PATH', 'C:\\Users\\coraj\\OneDrive\\Desktop\\sdrsharp-x86')

# Initialize the app with the extension
db.init_app(app)

with app.app_context():
    # Import models to ensure tables are created
    import models
    
    # Create tables if they don't exist
    db.create_all()
    
    logging.info("Database initialized with latest schema")
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Import routes
from routes import *

# Start file monitoring for automatic processing
try:
    from file_monitor import start_file_monitoring
    import threading
    
    def start_monitoring_delayed():
        """Start file monitoring after app initialization"""
        import time
        time.sleep(2)  # Wait for app to fully initialize
        start_file_monitoring()
    
    # Start monitoring in background thread
    monitor_thread = threading.Thread(target=start_monitoring_delayed, daemon=True)
    monitor_thread.start()
    logging.info("Automatic file monitoring enabled")
    
except Exception as e:
    logging.warning(f"File monitoring not available: {str(e)}")
