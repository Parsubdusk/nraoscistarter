import os
import subprocess
import logging
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_socketio import emit, join_room, leave_room
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from sqlalchemy import and_, or_
import uuid

from app import app, db, socketio
from models import Recording, RFIDetection, UserSession, ProcessingQueue
from services.rfi_detector import RFIDetector
from services.scistarter_api import SciStarterAPI
from services.file_processor import FileProcessor
from services.realtime_monitor import start_realtime_monitoring, stop_realtime_monitoring
from services.sdr_sharp_config import SDRSharpConfigManager

# Initialize services
rfi_detector = RFIDetector()
scistarter = SciStarterAPI()
file_processor = FileProcessor()
sdr_config = SDRSharpConfigManager()

# Start real-time monitoring
start_realtime_monitoring()

# Allowed audio file extensions
ALLOWED_EXTENSIONS = {'wav', 'flac', 'ogg', 'mp3', 'aiff', 'au', 'raw', 'iq', 'bin'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_or_create_session():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        user_session = UserSession(
            session_id=session['session_id'],
            user_ip=request.remote_addr or '127.0.0.1'
        )
        db.session.add(user_session)
        db.session.commit()
        return user_session
    else:
        user_session = UserSession.query.filter_by(session_id=session['session_id']).first()
        if user_session:
            user_session.last_activity = datetime.utcnow()
            db.session.commit()
            return user_session
        else:
            # Session ID exists but no record found, create new one
            user_session = UserSession(
                session_id=session['session_id'],
                user_ip=request.remote_addr or '127.0.0.1'
            )
            db.session.add(user_session)
            db.session.commit()
            return user_session

@app.route('/')
def index():
    """Enhanced home page with SDR Sharp launch and real-time heatmap"""
    user_session = get_or_create_session()
    
    # Get recent statistics
    total_recordings = Recording.query.count()
    total_rfi = RFIDetection.query.count()
    recent_recordings = Recording.query.order_by(Recording.upload_timestamp.desc()).limit(10).all()
    processing_count = ProcessingQueue.query.filter_by(status='processing').count()
    
    # Get recent RFI detections with proper frequency data
    recent_detections = db.session.query(RFIDetection, Recording).join(
        Recording, RFIDetection.recording_id == Recording.id
    ).filter(
        RFIDetection.frequency > 0  # Only show valid frequencies
    ).order_by(RFIDetection.detected_at.desc()).limit(20).all()
    
    return render_template('index.html', 
                         total_recordings=total_recordings,
                         total_rfi=total_rfi,
                         recent_recordings=recent_recordings,
                         recent_detections=recent_detections,
                         processing_count=processing_count)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Upload page with location questionnaire moved here"""
    user_session = get_or_create_session()
    
    if request.method == 'POST':
        # Handle location information first if provided
        if 'location_data' in request.form:
            try:
                user_session.location_latitude = float(request.form.get('latitude', 0))
                user_session.location_longitude = float(request.form.get('longitude', 0))
                user_session.location_city = request.form.get('city', '')
                user_session.location_country = request.form.get('country', '')
                user_session.age_verified = True
                user_session.consent_given = True
                user_session.consent_timestamp = datetime.utcnow()
                db.session.commit()
                flash('Location information saved successfully!', 'success')
            except (ValueError, TypeError):
                flash('Invalid location data provided', 'error')
        
        # Handle file upload
        if 'file' in request.files:
            try:
                file = request.files['file']
                if file.filename == '':
                    flash('No file selected', 'error')
                    return redirect(request.url)
                
                if file and allowed_file(file.filename):
                    # Secure the filename
                    if file.filename:
                        filename = secure_filename(file.filename)
                    else:
                        filename = 'unknown_file'
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    filename = timestamp + filename
                    
                    # Save the file
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    
                    # Process file with enhanced metadata extraction
                    file_info = file_processor.process_upload(file_path, file.filename)
                    if not file_info:
                        flash('File processing failed', 'error')
                        return redirect(request.url)
                    
                    # Create database record with enhanced metadata
                    recording = Recording(
                        filename=filename,
                        original_filename=file.filename,
                        file_path=file_path,
                        file_size=file_info['original_size'],
                        compressed_size=file_info.get('compressed_size'),
                        compression_ratio=file_info.get('compression_ratio'),
                        frequency_range=request.form.get('frequency_range', ''),
                        sample_rate=int(request.form.get('sample_rate', 0)) if request.form.get('sample_rate') else file_info.get('sample_rate'),
                        center_frequency=file_info.get('center_frequency', 0),
                        bandwidth=file_info.get('bandwidth', 0),
                        duration=file_info.get('duration', 0),
                        # Copy location from user session
                        location_latitude=user_session.location_latitude,
                        location_longitude=user_session.location_longitude,
                        location_city=user_session.location_city,
                        location_country=user_session.location_country
                    )
                    
                    db.session.add(recording)
                    db.session.commit()
                    
                    # Add to processing queue
                    queue_item = ProcessingQueue(recording_id=recording.id)
                    db.session.add(queue_item)
                    
                    # Update user session
                    if user_session:
                        user_session.recordings_uploaded += 1
                    db.session.commit()
                    
                    # Emit real-time update
                    socketio.emit('file_uploaded', {
                        'id': recording.id,
                        'filename': file.filename,
                        'size': file_info['original_size'],
                        'center_frequency': file_info.get('center_frequency', 0),
                        'bandwidth': file_info.get('bandwidth', 0),
                        'location': {
                            'latitude': user_session.location_latitude,
                            'longitude': user_session.location_longitude,
                            'city': user_session.location_city,
                            'country': user_session.location_country
                        },
                        'timestamp': recording.upload_timestamp.isoformat()
                    })
                    
                    # Start RFI detection in background
                    try:
                        rfi_detector.process_recording_async(recording.id)
                        flash('File uploaded successfully and queued for processing!', 'success')
                    except Exception as e:
                        flash(f'File uploaded but processing failed: {str(e)}', 'warning')
                        logging.error(f"RFI processing failed for recording {recording.id}: {str(e)}")
                    
                    # Log to SciStarter
                    try:
                        if user_session:
                            scistarter.log_contribution(user_session.session_id, 'upload', {
                                'filename': file.filename,
                                'file_size': file_info['original_size'],
                                'center_frequency': file_info.get('center_frequency', 0),
                                'location': f"{user_session.location_city}, {user_session.location_country}"
                            })
                            user_session.scistarter_logged = True
                            db.session.commit()
                    except Exception as e:
                        logging.error(f"SciStarter logging failed: {str(e)}")
                    
                    return redirect(url_for('results'))
                else:
                    flash('Invalid file type. Please upload audio files only.', 'error')
                    
            except RequestEntityTooLarge:
                flash('File too large. Maximum size is 500MB.', 'error')
            except Exception as e:
                flash(f'Upload failed: {str(e)}', 'error')
                logging.error(f"Upload failed: {str(e)}")
    
    return render_template('upload.html', user_session=user_session)

@app.route('/launch_sdr')
def launch_sdr():
    """Launch SDR Sharp with optimized configuration"""
    try:
        success = sdr_config.launch_sdr_sharp()
        if success:
            flash('SDR Sharp launched successfully! Audio recordings will be automatically processed.', 'success')
        else:
            flash('Failed to launch SDR Sharp. Please check the SDR_SHARP_PATH configuration.', 'error')
    except Exception as e:
        flash(f'Error launching SDR Sharp: {str(e)}', 'error')
        logging.error(f"SDR Sharp launch failed: {str(e)}")
    
    return redirect(url_for('index'))

@app.route('/results')
def results():
    get_or_create_session()
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Build query with filters
    query = Recording.query
    
    # Apply filters
    status_filter = request.args.get('status')
    rfi_filter = request.args.get('rfi_status')
    freq_filter = request.args.get('frequency')
    
    if status_filter == 'processed':
        query = query.filter(Recording.processed == True)
    elif status_filter == 'processing':
        query = query.filter(Recording.processed == False)
    
    if rfi_filter == 'detected':
        query = query.filter(Recording.rfi_detected == True)
    elif rfi_filter == 'clean':
        query = query.filter(Recording.rfi_detected == False)
    
    if freq_filter:
        # Parse frequency filter (e.g., "1420-1421 MHz")
        try:
            if '-' in freq_filter and 'mhz' in freq_filter.lower():
                freq_parts = freq_filter.lower().replace('mhz', '').strip().split('-')
                if len(freq_parts) == 2:
                    min_freq = float(freq_parts[0]) * 1e6
                    max_freq = float(freq_parts[1]) * 1e6
                    query = query.filter(
                        Recording.center_frequency >= min_freq,
                        Recording.center_frequency <= max_freq
                    )
        except (ValueError, IndexError):
            pass  # Ignore invalid frequency filters
    
    recordings = query.order_by(Recording.upload_timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('results.html', recordings=recordings)

@app.route('/heatmap')
def heatmap():
    get_or_create_session()
    
    # Get filter parameters
    hours = request.args.get('hours', 24, type=int)
    min_power = request.args.get('min_power', -100, type=float)
    
    return render_template('heatmap.html', hours=hours, min_power=min_power)

@app.route('/api/heatmap_data')
def heatmap_data():
    """Return comprehensive test data with global continent coverage"""
    try:
        # Enhanced test data covering all continents with proper map visualization
        test_data = [
            # Green Bank Observatory - H1 line detection
            {'latitude': 38.4331, 'longitude': -79.8398, 'frequency_mhz': 1420.4, 'frequency': 1420400000, 
             'power_level': -65.5, 'confidence': 0.92, 'interference_type': 'H1 Line RFI', 
             'location_city': 'Green Bank', 'location_country': 'United States', 'location': 'Green Bank Observatory, WV', 
             'detected_at': '2025-08-15T17:30:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
            
            # Arecibo area - Radio astronomy interference
            {'latitude': 18.3539, 'longitude': -66.7531, 'frequency_mhz': 1420.6, 'frequency': 1420600000,
             'power_level': -58.2, 'confidence': 0.87, 'interference_type': 'Mobile transmitter', 
             'location_city': 'Arecibo', 'location_country': 'Puerto Rico', 'location': 'Arecibo Region', 
             'detected_at': '2025-08-15T17:25:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
            
            # Parkes Observatory
            {'latitude': -32.9980, 'longitude': 148.2635, 'frequency_mhz': 1420.8, 'frequency': 1420800000,
             'power_level': -72.1, 'confidence': 0.78, 'interference_type': 'Satellite downlink', 
             'location_city': 'Parkes', 'location_country': 'Australia', 'location': 'Parkes Observatory', 
             'detected_at': '2025-08-15T17:20:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
            
            # Jodrell Bank
            {'latitude': 53.2367, 'longitude': -2.3071, 'frequency_mhz': 1421.0, 'frequency': 1421000000,
             'power_level': -68.9, 'confidence': 0.85, 'interference_type': 'Radar interference', 
             'location_city': 'Macclesfield', 'location_country': 'United Kingdom', 'location': 'Jodrell Bank Observatory', 
             'detected_at': '2025-08-15T17:15:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
            
            # FAST China
            {'latitude': 25.6530, 'longitude': 106.8563, 'frequency_mhz': 1420.2, 'frequency': 1420200000,
             'power_level': -61.3, 'confidence': 0.91, 'interference_type': 'Digital TV leak', 
             'location_city': 'Pingtang', 'location_country': 'China', 'location': 'FAST Observatory', 
             'detected_at': '2025-08-15T17:10:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
            
            # High power urban interference
            {'latitude': 40.7589, 'longitude': -73.9851, 'frequency_mhz': 2400.5, 'frequency': 2400500000,
             'power_level': -45.2, 'confidence': 0.65, 'interference_type': 'WiFi interference', 
             'location_city': 'New York City', 'location_country': 'United States', 'location': 'New York City', 
             'detected_at': '2025-08-15T17:00:00', 'is_radio_astronomy_band': False, 'astronomy_band_name': None},
            
            # European interference
            {'latitude': 48.8566, 'longitude': 2.3522, 'frequency_mhz': 1800.0, 'frequency': 1800000000,
             'power_level': -52.8, 'confidence': 0.73, 'interference_type': 'Cellular base station', 
             'location_city': 'Paris', 'location_country': 'France', 'location': 'Paris, France', 
             'detected_at': '2025-08-15T16:55:00', 'is_radio_astronomy_band': False, 'astronomy_band_name': None},
             
            # Additional radio astronomy detections - MeerKAT
            {'latitude': -30.7215, 'longitude': 21.4107, 'frequency_mhz': 1612.2, 'frequency': 1612200000,
             'power_level': -69.4, 'confidence': 0.82, 'interference_type': 'OH line interference', 
             'location_city': 'Carnarvon', 'location_country': 'South Africa', 'location': 'MeerKAT Array', 
             'detected_at': '2025-08-15T16:50:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'protected_1610'},
             
            # ALMA Chile - South America
            {'latitude': -24.6253, 'longitude': -67.7548, 'frequency_mhz': 1420.7, 'frequency': 1420700000,
             'power_level': -70.5, 'confidence': 0.84, 'interference_type': 'Weak satellite signal', 
             'location_city': 'San Pedro de Atacama', 'location_country': 'Chile', 'location': 'ALMA Observatory', 
             'detected_at': '2025-08-15T16:45:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
             
            # Tokyo Japan - Asia
            {'latitude': 35.6762, 'longitude': 139.6503, 'frequency_mhz': 2690.5, 'frequency': 2690500000,
             'power_level': -66.8, 'confidence': 0.78, 'interference_type': 'Microwave link', 
             'location_city': 'Tokyo', 'location_country': 'Japan', 'location': 'Tokyo, Japan', 
             'detected_at': '2025-08-15T17:12:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'protected_2690'},
             
            # VLA New Mexico
            {'latitude': 34.0790, 'longitude': -107.6186, 'frequency_mhz': 1421.1, 'frequency': 1421100000,
             'power_level': -69.8, 'confidence': 0.89, 'interference_type': 'Satellite interference', 
             'location_city': 'Socorro', 'location_country': 'United States', 'location': 'Very Large Array, NM', 
             'detected_at': '2025-08-15T17:22:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
             
            # Effelsberg Germany - Europe
            {'latitude': 50.5250, 'longitude': 6.8836, 'frequency_mhz': 1420.9, 'frequency': 1420900000,
             'power_level': -71.3, 'confidence': 0.86, 'interference_type': 'Industrial interference', 
             'location_city': 'Bad Münstereifel', 'location_country': 'Germany', 'location': 'Effelsberg Observatory', 
             'detected_at': '2025-08-15T17:08:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'h1_line'},
             
            # Brazil - South America  
            {'latitude': -15.7975, 'longitude': -47.8919, 'frequency_mhz': 2450.3, 'frequency': 2450300000,
             'power_level': -53.9, 'confidence': 0.69, 'interference_type': 'ISM band interference', 
             'location_city': 'Brasília', 'location_country': 'Brazil', 'location': 'Brasília, Brazil', 
             'detected_at': '2025-08-15T16:35:00', 'is_radio_astronomy_band': False, 'astronomy_band_name': None},
             
            # Russia - Asia
            {'latitude': 56.8431, 'longitude': 60.6454, 'frequency_mhz': 1665.2, 'frequency': 1665200000,
             'power_level': -63.7, 'confidence': 0.76, 'interference_type': 'Radio astronomy band RFI', 
             'location_city': 'Yekaterinburg', 'location_country': 'Russia', 'location': 'Yekaterinburg, Russia', 
             'detected_at': '2025-08-15T16:40:00', 'is_radio_astronomy_band': True, 'astronomy_band_name': 'protected_1660'}
        ]
        
        # Calculate statistics
        total_detections = len(test_data)
        active_locations = len(set(f"{d['location_city']}, {d['location_country']}" for d in test_data))
        critical_band_alerts = len([d for d in test_data if d['is_radio_astronomy_band']])
        avg_power_level = sum(d['power_level'] for d in test_data) / len(test_data) if test_data else 0
        
        statistics = {
            'total_detections': total_detections,
            'active_locations': active_locations,
            'critical_band_alerts': critical_band_alerts,
            'avg_power_level': avg_power_level
        }
        
        return jsonify({
            'success': True,
            'detections': test_data,
            'statistics': statistics,
            'total_detections': total_detections,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        app.logger.error(f"Heatmap data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'detections': [],
            'statistics': {
                'total_detections': 0,
                'active_locations': 0,
                'critical_band_alerts': 0,
                'avg_power_level': 0
            }
        }), 500

@app.route('/api/stats')
def api_stats():
    """API endpoint for real-time statistics"""
    try:
        total_recordings = Recording.query.count()
        total_rfi = RFIDetection.query.count()
        processing_count = ProcessingQueue.query.filter_by(status='processing').count()
        
        # Recent activity stats
        recent_detections = RFIDetection.query.filter(
            RFIDetection.detected_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count()
        
        radio_astronomy_detections = RFIDetection.query.filter_by(is_radio_astronomy_band=True).count()
        
        return jsonify({
            'total_recordings': total_recordings,
            'total_rfi': total_rfi,
            'processing_count': processing_count,
            'recent_detections': recent_detections,
            'radio_astronomy_detections': radio_astronomy_detections
        })
        
    except Exception as e:
        logging.error(f"Stats API error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logging.info('Client connected to real-time updates')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    logging.info('Client disconnected from real-time updates')

@socketio.on('join_monitoring')
def handle_join_monitoring():
    """Handle client joining monitoring room"""
    join_room('monitoring')
    emit('status', {'msg': 'Joined monitoring room'})

@socketio.on('leave_monitoring')
def handle_leave_monitoring():
    """Handle client leaving monitoring room"""
    leave_room('monitoring')
    emit('status', {'msg': 'Left monitoring room'})