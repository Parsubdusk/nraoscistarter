from app import db
from datetime import datetime
from sqlalchemy import Text, Float, Integer, String, DateTime, Boolean

class Recording(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, default='')
    original_filename = db.Column(db.String(255), nullable=False, default='')
    file_path = db.Column(db.String(500), nullable=False, default='')
    file_size = db.Column(db.Integer, nullable=False, default=0)
    upload_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sample_rate = db.Column(db.Integer, nullable=True)
    duration = db.Column(db.Float, nullable=True)
    frequency_range = db.Column(db.String(100), nullable=True)
    processed = db.Column(db.Boolean, default=False)
    rfi_detected = db.Column(db.Boolean, default=False)
    processing_completed_at = db.Column(db.DateTime, nullable=True)
    file_hash = db.Column(db.String(64), nullable=True, index=True)
    auto_detected = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationship to RFI detections
    rfi_detections = db.relationship('RFIDetection', backref='recording', lazy=True, cascade='all, delete-orphan')

class RFIDetection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recording_id = db.Column(db.Integer, db.ForeignKey('recording.id'), nullable=False)
    timestamp = db.Column(db.Float, nullable=False)  # Time in seconds from start of recording
    frequency = db.Column(db.Float, nullable=False)  # Frequency in Hz
    power_level = db.Column(db.Float, nullable=False)  # Power level in dB
    bandwidth = db.Column(db.Float)  # Bandwidth of interference in Hz
    confidence = db.Column(db.Float, default=0.0)  # Confidence level 0-1
    interference_type = db.Column(db.String(50))  # Type of interference detected
    detection_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class UserSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), unique=True, nullable=False)
    user_ip = db.Column(db.String(45))
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    recordings_uploaded = db.Column(db.Integer, default=0)
    scistarter_logged = db.Column(db.Boolean, default=False)
    
    # Age verification and location data
    age_verified = db.Column(db.Boolean, default=False)
    location_country = db.Column(db.String(100))
    location_state = db.Column(db.String(100))
    location_city = db.Column(db.String(100))
    location_lat = db.Column(db.Float)
    location_lon = db.Column(db.Float)
    consent_given = db.Column(db.Boolean, default=False)
    consent_timestamp = db.Column(db.DateTime)

class ProcessingQueue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recording_id = db.Column(db.Integer, db.ForeignKey('recording.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
