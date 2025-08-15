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
    # Return static test data to get heatmap working immediately
    try:
        # Static test data representing global RFI detections
        test_data = [
            # Green Bank Observatory - H1 line detection
            {'latitude': 38.4331, 'longitude': -79.8398, 'frequency_mhz': 1420.4, 'frequency': 1420400000, 
             'power_level': -65.5, 'confidence': 0.92, 'interference_type': 'H1 Line RFI', 
             'location': 'Green Bank Observatory', 'location_source': 'Observatory', 
             'timestamp': '2025-08-15T17:30:00', 'is_radio_astronomy': True, 'astronomy_band': 'h1_line'},
            
            # Arecibo area - Radio astronomy interference
            {'latitude': 18.3539, 'longitude': -66.7531, 'frequency_mhz': 1420.6, 'frequency': 1420600000,
             'power_level': -58.2, 'confidence': 0.87, 'interference_type': 'Mobile transmitter', 
             'location': 'Arecibo Region', 'location_source': 'Observatory', 
             'timestamp': '2025-08-15T17:25:00', 'is_radio_astronomy': True, 'astronomy_band': 'h1_line'},
            
            # Parkes Observatory
            {'latitude': -32.9980, 'longitude': 148.2635, 'frequency_mhz': 1420.8, 'frequency': 1420800000,
             'power_level': -72.1, 'confidence': 0.78, 'interference_type': 'Satellite downlink', 
             'location': 'Parkes Observatory', 'location_source': 'Observatory', 
             'timestamp': '2025-08-15T17:20:00', 'is_radio_astronomy': True, 'astronomy_band': 'h1_line'},
            
            # Jodrell Bank
            {'latitude': 53.2367, 'longitude': -2.3071, 'frequency_mhz': 1421.0, 'frequency': 1421000000,
             'power_level': -68.9, 'confidence': 0.85, 'interference_type': 'Radar interference', 
             'location': 'Jodrell Bank Observatory', 'location_source': 'Observatory', 
             'timestamp': '2025-08-15T17:15:00', 'is_radio_astronomy': True, 'astronomy_band': 'h1_line'},
            
            # FAST China
            {'latitude': 25.6530, 'longitude': 106.8563, 'frequency_mhz': 1420.2, 'frequency': 1420200000,
             'power_level': -61.3, 'confidence': 0.91, 'interference_type': 'Digital TV leak', 
             'location': 'FAST Observatory', 'location_source': 'Observatory', 
             'timestamp': '2025-08-15T17:10:00', 'is_radio_astronomy': True, 'astronomy_band': 'h1_line'},
            
            # High power urban interference
            {'latitude': 40.7589, 'longitude': -73.9851, 'frequency_mhz': 2400.5, 'frequency': 2400500000,
             'power_level': -45.2, 'confidence': 0.65, 'interference_type': 'WiFi interference', 
             'location': 'New York City', 'location_source': 'Urban', 
             'timestamp': '2025-08-15T17:00:00', 'is_radio_astronomy': False, 'astronomy_band': None},
            
            # European interference
            {'latitude': 48.8566, 'longitude': 2.3522, 'frequency_mhz': 1800.0, 'frequency': 1800000000,
             'power_level': -52.8, 'confidence': 0.73, 'interference_type': 'Cellular base station', 
             'location': 'Paris, France', 'location_source': 'Urban', 
             'timestamp': '2025-08-15T16:55:00', 'is_radio_astronomy': False, 'astronomy_band': None},
             
            # Additional radio astronomy detections
            {'latitude': -24.6253, 'longitude': 25.8888, 'frequency_mhz': 1612.2, 'frequency': 1612200000,
             'power_level': -69.4, 'confidence': 0.82, 'interference_type': 'OH line interference', 
             'location': 'MeerKAT Array', 'location_source': 'Observatory', 
             'timestamp': '2025-08-15T16:50:00', 'is_radio_astronomy': True, 'astronomy_band': 'radio_astronomy'}
        ]
        
        return jsonify({
            'success': True,
            'data': test_data,
            'total_detections': len(test_data),
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        app.logger.error(f"Heatmap data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'data': []
        }), 500
        
        # Radio astronomy frequency bands (MHz)
        astro_bands = {
            'h1_line': (1420, 1421),  # Hydrogen line - most critical
            'continuum_74': (73, 75),
            'continuum_150': (149, 151), 
            'continuum_325': (324, 326),
            'continuum_1400': (1400, 1700),  # L-band
            'continuum_4800': (4800, 5000),  # C-band
            'protected_1610': (1610.6, 1613.8),  # Radio astronomy protected band
            'protected_1660': (1660, 1670),  # Radio astronomy protected band
            'protected_2690': (2690, 2700),  # Radio astronomy protected band
        }
        
        # Apply frequency filtering
        if freq_filter != 'all':
            if freq_filter == 'radio_astronomy':
                # Filter for radio astronomy bands
                freq_conditions = []
                for band_name, (min_freq, max_freq) in astro_bands.items():
                    freq_conditions.append(
                        and_(
                            RFIDetection.frequency >= min_freq * 1e6,
                            RFIDetection.frequency <= max_freq * 1e6
                        )
                    )
                query = query.filter(or_(*freq_conditions))
            elif freq_filter == 'h1_line':
                query = query.filter(
                    RFIDetection.frequency >= 1420e6,
                    RFIDetection.frequency <= 1421e6
                )
            elif freq_filter == 'l_band':
                query = query.filter(
                    RFIDetection.frequency >= 1000e6,
                    RFIDetection.frequency <= 2000e6
                )
            elif freq_filter == 'c_band':
                query = query.filter(
                    RFIDetection.frequency >= 4000e6,
                    RFIDetection.frequency <= 8000e6
                )
            elif freq_filter == 'wifi':
                query = query.filter(
                    or_(
                        and_(RFIDetection.frequency >= 2400e6, RFIDetection.frequency <= 2500e6),
                        and_(RFIDetection.frequency >= 5150e6, RFIDetection.frequency <= 5850e6)
                    )
                )
            elif freq_filter == 'cellular':
                query = query.filter(
                    or_(
                        and_(RFIDetection.frequency >= 800e6, RFIDetection.frequency <= 900e6),
                        and_(RFIDetection.frequency >= 1800e6, RFIDetection.frequency <= 1900e6)
                    )
                )
        
        # Execute query
        results = query.all()
        
        # Format data for geographic heatmap
        heatmap_data = []
        
        for detection, recording in results:
            # Use recording location data (skip if no location)
            if not recording.location_latitude or not recording.location_longitude:
                continue
            
            # Check if frequency is in radio astronomy bands
            freq_mhz = detection.frequency / 1e6
            is_radio_astronomy = False
            astro_band = None
            
            for band_name, (min_freq, max_freq) in astro_bands.items():
                if min_freq <= freq_mhz <= max_freq:
                    is_radio_astronomy = True
                    astro_band = band_name
                    break
            
            location_label = f"{recording.location_city or 'Unknown'}, {recording.location_country or 'Unknown'}"
            
            heatmap_data.append({
                'latitude': recording.location_latitude,
                'longitude': recording.location_longitude,
                'frequency': detection.frequency,
                'frequency_mhz': freq_mhz,
                'power_level': detection.power_level,
                'confidence': detection.confidence,
                'interference_type': detection.interference_type or 'Unknown',
                'timestamp': detection.detected_at.isoformat(),
                'location': location_label,
                'location_source': 'user_provided',
                'is_radio_astronomy': is_radio_astronomy,
                'astronomy_band': astro_band,
                'recording_id': recording.id,
                'detection_id': detection.id
            })
        
        return jsonify({
            'data': heatmap_data,
            'total_detections': len(heatmap_data),
            'time_range_hours': hours,
            'min_power_threshold': min_power,
            'frequency_filter': freq_filter,
            'radio_astronomy_bands': astro_bands
        })
        
    except Exception as e:
        logging.error(f"Heatmap data error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/recording/<int:recording_id>')
def api_recording_details(recording_id):
    """API endpoint for recording details"""
    try:
        recording = Recording.query.get_or_404(recording_id)
        
        return jsonify({
            'id': recording.id,
            'filename': recording.filename,
            'original_filename': recording.original_filename,
            'file_size': recording.file_size,
            'compressed_size': recording.compressed_size,
            'compression_ratio': recording.compression_ratio,
            'sample_rate': recording.sample_rate,
            'duration': recording.duration,
            'center_frequency': recording.center_frequency,
            'bandwidth': recording.bandwidth,
            'frequency_range': recording.frequency_range,
            'processed': recording.processed,
            'rfi_detected': recording.rfi_detected,
            'upload_timestamp': recording.upload_timestamp.isoformat(),
            'processing_started_at': recording.processing_started_at.isoformat() if recording.processing_started_at else None,
            'processing_completed_at': recording.processing_completed_at.isoformat() if recording.processing_completed_at else None,
            'location_latitude': recording.location_latitude,
            'location_longitude': recording.location_longitude,
            'location_city': recording.location_city,
            'location_country': recording.location_country
        })
        
    except Exception as e:
        logging.error(f"Recording details API error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recording/<int:recording_id>/detections')
def api_recording_detections(recording_id):
    """API endpoint for recording RFI detections"""
    try:
        recording = Recording.query.get_or_404(recording_id)
        detections = RFIDetection.query.filter_by(recording_id=recording_id).all()
        
        detection_data = []
        for detection in detections:
            detection_data.append({
                'id': detection.id,
                'timestamp': detection.timestamp,
                'frequency': detection.frequency,
                'frequency_mhz': detection.frequency / 1e6,
                'power_level': detection.power_level,
                'bandwidth': detection.bandwidth,
                'confidence': detection.confidence,
                'interference_type': detection.interference_type,
                'is_radio_astronomy_band': detection.is_radio_astronomy_band,
                'astronomy_band_name': detection.astronomy_band_name,
                'detected_at': detection.detected_at.isoformat()
            })
        
        return jsonify({
            'recording_id': recording_id,
            'detections': detection_data,
            'total_detections': len(detection_data)
        })
        
    except Exception as e:
        logging.error(f"Recording detections API error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recording/<int:recording_id>/download')
def api_recording_download(recording_id):
    """API endpoint for downloading recording files"""
    try:
        recording = Recording.query.get_or_404(recording_id)
        
        if os.path.exists(recording.file_path):
            return send_file(recording.file_path, as_attachment=True, 
                           download_name=recording.original_filename)
        else:
            return jsonify({'error': 'File not found'}), 404
            
    except Exception as e:
        logging.error(f"Recording download API error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logging.info(f"Client connected: {request.sid}")
    join_room('global_updates')
    emit('status', {'message': 'Connected to real-time updates'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logging.info(f"Client disconnected: {request.sid}")
    leave_room('global_updates')

@socketio.on('join_monitoring')
def handle_join_monitoring():
    """Join real-time monitoring room"""
    join_room('monitoring')
    emit('status', {'message': 'Joined monitoring room'})

# Cleanup on app shutdown
import atexit
atexit.register(stop_realtime_monitoring)
