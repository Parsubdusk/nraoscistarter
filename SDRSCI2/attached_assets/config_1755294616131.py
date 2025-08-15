import os

class Config:
    """Enhanced application configuration"""
    
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
    
    # Enhanced audio processing
    SUPPORTED_SAMPLE_RATES = [8000, 16000, 22050, 44100, 48000, 96000, 192000]
    DEFAULT_SAMPLE_RATE = 48000
    
    # RFI Detection settings
    RFI_DETECTION_THRESHOLD = -80  # dB
    RFI_CONFIDENCE_THRESHOLD = 0.7
    
    # Radio Astronomy Bands (MHz)
    RADIO_ASTRONOMY_BANDS = {
        'h1_line': {'min': 1420, 'max': 1421, 'name': 'Hydrogen Line', 'priority': 'critical'},
        'continuum_74': {'min': 73, 'max': 75, 'name': '74 MHz Continuum', 'priority': 'high'},
        'continuum_150': {'min': 149, 'max': 151, 'name': '150 MHz Continuum', 'priority': 'high'},
        'continuum_325': {'min': 324, 'max': 326, 'name': '325 MHz Continuum', 'priority': 'high'},
        'l_band': {'min': 1400, 'max': 1700, 'name': 'L-band', 'priority': 'medium'},
        'c_band': {'min': 4800, 'max': 5000, 'name': 'C-band', 'priority': 'medium'},
        'protected_1610': {'min': 1610.6, 'max': 1613.8, 'name': 'Protected 1610', 'priority': 'critical'},
        'protected_1660': {'min': 1660, 'max': 1670, 'name': 'Protected 1660', 'priority': 'critical'},
        'protected_2690': {'min': 2690, 'max': 2700, 'name': 'Protected 2690', 'priority': 'critical'},
    }
