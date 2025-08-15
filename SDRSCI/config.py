import os

class Config:
    """Application configuration"""
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///spectrum_sentinels.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Security
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'spectrum-sentinels-dev-key')
    
    # File uploads
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB
    
    # SDR Configuration
    SDR_SHARP_PATH = os.environ.get('SDR_SHARP_PATH', r'C:\Users\coraj\OneDrive\Desktop\sdrsharp-x86')
    AUDIO_DIRECTORY = os.environ.get('AUDIO_DIRECTORY', 'audio_recordings')
    
    # External APIs
    SCISTARTER_API_KEY = os.environ.get('SCISTARTER_API_KEY', 'demo-key')
    SCISTARTER_PROJECT_ID = os.environ.get('SCISTARTER_PROJECT_ID', 'spectrumx-spectrum-sentinels')
    
    # File compression
    COMPRESSION_ENABLED = True
    COMPRESSION_LEVEL = 6  # Balance between speed and compression ratio
    
    # Real-time processing
    REALTIME_UPDATES = True
    WEBSOCKET_PING_INTERVAL = 25
    WEBSOCKET_PING_TIMEOUT = 60
