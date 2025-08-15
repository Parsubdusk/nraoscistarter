import os
import subprocess
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, session
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
from services.realtime_monitor import start_realtime_monitoring

# Initialize services
rfi_detector = RFIDetector()
scistarter = SciStarterAPI()
file_processor = FileProcessor()

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

def check_age_verification():
    """Check if user has completed age verification"""
    user_session = get_or_create_session()
    return user_session.age_verified and user_session.consent_given

@app.route('/')
def index():
    user_session = get_or_create_session()
    
    # Check if age verification is required
    if not check_age_verification():
        return redirect(url_for('verify_age'))
    
    # Get recent statistics
    total_recordings = Recording.query.count()
    total_rfi = RFIDetection.query.count()
    recent_recordings = Recording.query.order_by(Recording.upload_timestamp.desc()).limit(5).all()
    processing_count = ProcessingQueue.query.filter_by(status='processing').count()
    
    return render_template('index.html', 
                         total_recordings=total_recordings,
                         total_rfi=total_rfi,
                         recent_recordings=recent_recordings,
                         processing_count=processing_count)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    user_session = get_or_create_session()
    
    # Check age verification
    if not check_age_verification():
        return redirect(url_for('verify_age'))
    
    if request.method == 'POST':
        try:
            # Check if file was uploaded
            if 'file' not in request.files:
                flash('No file selected', 'error')
                return redirect(request.url)
            
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
                
                # Process file with compression
                file_info = file_processor.process_upload(file_path, file.filename)
                if not file_info:
                    flash('File processing failed', 'error')
                    return redirect(request.url)
                
                # Create database record
                recording = Recording(
                    filename=filename,
                    original_filename=file.filename,
                    file_path=file_path,
                    file_size=file_info['original_size'],
                    compressed_size=file_info.get('compressed_size'),
                    compression_ratio=file_info.get('compression_ratio'),
                    frequency_range=request.form.get('frequency_range', ''),
                    sample_rate=int(request.form.get('sample_rate', 0)) if request.form.get('sample_rate') else None
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
                    'compressed_size': file_info.get('compressed_size'),
                    'compression_ratio': file_info.get('compression_ratio'),
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
                            'compressed_size': file_info.get('compressed_size'),
                            'compression_ratio': file_info.get('compression_ratio')
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
    
    return render_template('upload.html')

@app.route('/results')
def results():
    get_or_create_session()
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    recordings = Recording.query.order_by(Recording.upload_timestamp.desc()).paginate(
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
    try:
        hours = request.args.get('hours', 24, type=int)
        min_power = request.args.get('min_power', -100, type=float)
        freq_filter = request.args.get('freq_filter', 'all')
        astro_only = request.args.get('astro_only', 'false').lower() == 'true'
        
        # Query RFI detections from the last N hours with location data
        cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)
        
        query = db.session.query(RFIDetection, Recording, UserSession).join(
            Recording, RFIDetection.recording_id == Recording.id
        ).outerjoin(
            UserSession, UserSession.session_id == session.get('session_id')
        ).filter(
            Recording.upload_timestamp >= datetime.fromtimestamp(cutoff_time),
            RFIDetection.power_level >= min_power
        )
        
        # Radio astronomy frequency bands (MHz)
        astro_bands = {
            'hi_line': (1420, 1421),  # Hydrogen line - most critical
            'continuum_74': (73, 75),
            'continuum_150': (149, 151), 
            'continuum_325': (324, 326),
            'continuum_1400': (1400, 1700),  # L-band
            'continuum_4800': (4800, 5000),  # C-band
            'seti': (1420, 1720),  # SETI frequencies
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
            elif freq_filter == 'vhf':
                query = query.filter(
                    RFIDetection.frequency >= 30e6,
                    RFIDetection.frequency <= 300e6
                )
            elif freq_filter == 'uhf':
                query = query.filter(
                    RFIDetection.frequency >= 300e6,
                    RFIDetection.frequency <= 1000e6
                )
            elif freq_filter == 'l_band':
                query = query.filter(
                    RFIDetection.frequency >= 1000e6,
                    RFIDetection.frequency <= 2000e6
                )
            elif freq_filter == 'wifi':
                query = query.filter(
                    or_(
                        and_(RFIDetection.frequency >= 2400e6, RFIDetection.frequency <= 2500e6),
                        and_(RFIDetection.frequency >= 5150e6, RFIDetection.frequency <= 5850e6)
                    )
                )
        
        # Execute query
        results = query.all()
        
        # Format data for geographic heatmap
        heatmap_data = []
        default_locations = {
            'latitude': 39.8283,  # Center of continental US
            'longitude': -98.5795
        }
        
        for detection, recording, user_session in results:
            # Use user location if available, otherwise use default US center
            latitude = default_locations['latitude']
            longitude = default_locations['longitude']
            location_source = 'default'
            
            if user_session and user_session.location_latitude and user_session.location_longitude:
                latitude = user_session.location_latitude
                longitude = user_session.location_longitude
                location_source = 'user_provided'
            
            # Check if frequency is in radio astronomy bands
            freq_mhz = detection.frequency / 1e6
            is_radio_astronomy = False
            astro_band = None
            
            for band_name, (min_freq, max_freq) in astro_bands.items():
                if min_freq <= freq_mhz <= max_freq:
                    is_radio_astronomy = True
                    astro_band = band_name
                    break
            
            # Skip non-radio astronomy frequencies if astro_only filter is enabled
            if astro_only and not is_radio_astronomy:
                continue
                
            data_point = {
                'id': detection.id,
                'recording_id': recording.id,
                'latitude': latitude,
                'longitude': longitude,
                'location_source': location_source,
                'frequency': freq_mhz,
                'power': detection.power_level,
                'bandwidth': detection.bandwidth / 1e3 if detection.bandwidth else 1,
                'type': detection.interference_type or 'unknown',
                'confidence': detection.confidence,
                'timestamp': detection.detected_at.isoformat(),
                'upload_time': recording.upload_timestamp.isoformat(),
                'is_radio_astronomy': is_radio_astronomy,
                'astro_band': astro_band,
                'location_info': {
                    'country': user_session.location_country if user_session else 'USA',
                    'state': user_session.location_state if user_session else None,
                    'city': user_session.location_city if user_session else None
                }
            }
            heatmap_data.append(data_point)
        
        # Summary statistics
        total_detections = len(heatmap_data)
        radio_astronomy_detections = sum(1 for d in heatmap_data if d['is_radio_astronomy'])
        unique_bands = len(set(d['astro_band'] for d in heatmap_data if d['astro_band']))
        avg_power = sum(d['power'] for d in heatmap_data) / total_detections if total_detections > 0 else 0
        
        return jsonify({
            'success': True,
            'data': heatmap_data,
            'summary': {
                'total_detections': total_detections,
                'radio_astronomy_detections': radio_astronomy_detections,
                'interference_detections': total_detections - radio_astronomy_detections,
                'unique_astro_bands': unique_bands,
                'average_power': round(avg_power, 2),
                'time_range_hours': hours
            },
            'radio_astronomy_bands': {k: {'min': v[0], 'max': v[1]} for k, v in astro_bands.items()}
        })
        
    except Exception as e:
        logging.error(f"Heatmap data error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/recording/<int:recording_id>')
def recording_details(recording_id):
    try:
        recording = Recording.query.get_or_404(recording_id)
        detections = RFIDetection.query.filter_by(recording_id=recording_id).all()
        
        detection_data = []
        for d in detections:
            detection_data.append({
                'timestamp': d.timestamp,
                'frequency': d.frequency,
                'power_level': d.power_level,
                'bandwidth': d.bandwidth,
                'confidence': d.confidence,
                'type': d.interference_type
            })
        
        return jsonify({
            'success': True,
            'recording': {
                'id': recording.id,
                'filename': recording.original_filename,
                'upload_time': recording.upload_timestamp.isoformat(),
                'file_size': recording.file_size,
                'compressed_size': recording.compressed_size,
                'compression_ratio': recording.compression_ratio,
                'sample_rate': recording.sample_rate,
                'duration': recording.duration,
                'frequency_range': recording.frequency_range,
                'processed': recording.processed,
                'rfi_detected': recording.rfi_detected
            },
            'detections': detection_data
        })
        
    except Exception as e:
        logging.error(f"Recording details error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/launch_sdr')
def launch_sdr():
    """Launch SDR Sharp with auto-configured RFI detection settings"""
    # Check age verification
    if not check_age_verification():
        return redirect(url_for('verify_age'))
    
    try:
        sdr_dir = app.config['SDR_SHARP_PATH']
        audio_dir = app.config['AUDIO_DIRECTORY']
        
        # Auto-configure SDR Sharp before launching
        from services.sdr_sharp_config import configure_sdr_sharp
        config_success = configure_sdr_sharp(sdr_dir, audio_dir)
        
        if config_success:
            flash('SDR Sharp auto-configured for optimal RFI detection!', 'info')
        
        # Look for common SDR Sharp executables in the directory
        possible_exes = [
            'SDRSharp.dotnet8.exe',
            'SDRSharp.exe', 
            'sdrsharp.exe'
        ]
        
        sdr_exe = None
        if os.path.exists(sdr_dir):
            for exe in possible_exes:
                exe_path = os.path.join(sdr_dir, exe)
                if os.path.exists(exe_path):
                    sdr_exe = exe_path
                    break
        
        if sdr_exe:
            # Launch SDR Sharp
            subprocess.Popen([sdr_exe], cwd=sdr_dir)
            flash('SDR Sharp launched with RFI detection settings!', 'success')
        else:
            logging.error(f"SDR Sharp executable not found in: {sdr_dir}")
            flash(f'SDR Sharp not found in {sdr_dir}. Please check the path.', 'error')
            
    except Exception as e:
        logging.error(f"Failed to launch SDR Sharp: {str(e)}")
        flash(f'Failed to launch SDR Sharp: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/verify_age', methods=['GET', 'POST'])
def verify_age():
    """Age verification and consent page"""
    if request.method == 'POST':
        try:
            user_session = get_or_create_session()
            
            # Check age confirmation
            age_confirmed = request.form.get('age_confirmation') == 'on'
            data_consent = request.form.get('data_consent') == 'on'
            
            if not age_confirmed or not data_consent:
                flash('Age verification and data consent are required to participate.', 'error')
                return render_template('age_verification.html')
            
            # Update user session with verification data
            user_session.age_verified = True
            user_session.consent_given = True
            user_session.consent_timestamp = datetime.utcnow()
            
            # Location data
            user_session.location_country = request.form.get('country', '').strip()
            user_session.location_state = request.form.get('state', '').strip()
            user_session.location_city = request.form.get('city', '').strip()
            
            # GPS coordinates if provided
            if request.form.get('latitude') and request.form.get('longitude'):
                try:
                    user_session.location_latitude = float(request.form.get('latitude'))
                    user_session.location_longitude = float(request.form.get('longitude'))
                except ValueError:
                    pass
            
            db.session.commit()
            
            # Log to SciStarter
            try:
                scistarter.log_contribution(user_session.session_id, 'registration', {
                    'country': user_session.location_country,
                    'state': user_session.location_state,
                    'city': user_session.location_city
                })
            except Exception as e:
                logging.error(f"SciStarter registration logging failed: {str(e)}")
            
            flash('Age verification completed. Welcome to NRAO Spectrum Sentinels!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            logging.error(f"Age verification failed: {str(e)}")
            flash('Verification failed. Please try again.', 'error')
    
    return render_template('age_verification.html')

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    user_session = get_or_create_session()
    join_room('realtime_updates')
    emit('connected', {'status': 'connected', 'session_id': user_session.session_id})
    logging.info(f"Client connected: {user_session.session_id}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    leave_room('realtime_updates')
    logging.info("Client disconnected")

@socketio.on('join_room')
def handle_join_room(data):
    """Handle room joining for specific updates"""
    room = data.get('room')
    if room in ['processing_updates', 'detection_updates', 'stats_updates']:
        join_room(room)
        emit('joined_room', {'room': room})

@socketio.on('leave_room')
def handle_leave_room(data):
    """Handle room leaving"""
    room = data.get('room')
    leave_room(room)
    emit('left_room', {'room': room})

# Start real-time monitoring when the app starts
if app.config.get('REALTIME_UPDATES', True):
    start_realtime_monitoring()
