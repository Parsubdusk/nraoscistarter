from datetime import datetime
from app import db

class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Age verification and consent
    age_verified = db.Column(db.Boolean, default=False)
    consent_given = db.Column(db.Boolean, default=False)
    consent_timestamp = db.Column(db.DateTime)
    
    # Location data for research compliance
    location_country = db.Column(db.String(100))
    location_state = db.Column(db.String(100))
    location_city = db.Column(db.String(100))
    location_latitude = db.Column(db.Float)
    location_longitude = db.Column(db.Float)
    
    # Activity tracking
    recordings_uploaded = db.Column(db.Integer, default=0)
    scistarter_logged = db.Column(db.Boolean, default=False)

class Recording(db.Model):
    __tablename__ = 'recordings'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger)
    compressed_size = db.Column(db.BigInteger)
    compression_ratio = db.Column(db.Float)
    
    # Enhanced audio metadata
    sample_rate = db.Column(db.Integer)
    duration = db.Column(db.Float)
    frequency_range = db.Column(db.String(100))
    center_frequency = db.Column(db.Float)  # Extracted center frequency in Hz
    bandwidth = db.Column(db.Float)  # Extracted bandwidth in Hz
    
    # Processing status
    processed = db.Column(db.Boolean, default=False)
    rfi_detected = db.Column(db.Boolean, default=False)
    processing_started_at = db.Column(db.DateTime)
    processing_completed_at = db.Column(db.DateTime)
    
    # Location information (from user session)
    location_latitude = db.Column(db.Float)
    location_longitude = db.Column(db.Float)
    location_city = db.Column(db.String(100))
    location_country = db.Column(db.String(100))
    
    # Timestamps
    upload_timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    detections = db.relationship('RFIDetection', backref='recording', lazy='dynamic', cascade='all, delete-orphan')

class RFIDetection(db.Model):
    __tablename__ = 'rfi_detections'
    
    id = db.Column(db.Integer, primary_key=True)
    recording_id = db.Column(db.Integer, db.ForeignKey('recordings.id'), nullable=False, index=True)
    
    # Detection data
    timestamp = db.Column(db.Float, nullable=False)  # Time within recording
    frequency = db.Column(db.Float, nullable=False, index=True)  # Hz
    power_level = db.Column(db.Float, nullable=False)  # dB
    bandwidth = db.Column(db.Float)  # Hz
    confidence = db.Column(db.Float, default=0.0)
    interference_type = db.Column(db.String(50), index=True)
    
    # Radio astronomy band identification
    is_radio_astronomy_band = db.Column(db.Boolean, default=False)
    astronomy_band_name = db.Column(db.String(50))  # 'h1_line', 'continuum_l', etc.
    
    # Detection timestamp
    detected_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class ProcessingQueue(db.Model):
    __tablename__ = 'processing_queue'
    
    id = db.Column(db.Integer, primary_key=True)
    recording_id = db.Column(db.Integer, db.ForeignKey('recordings.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, processing, completed, failed
    error_message = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Relationship
    recording = db.relationship('Recording', backref='queue_items')
