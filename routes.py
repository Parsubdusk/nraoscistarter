import os
import subprocess
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import uuid

from app import app, db
from models import Recording, RFIDetection, UserSession, ProcessingQueue
from rfi_detector import RFIDetector
from scistarter_api import SciStarterAPI

# Initialize services
rfi_detector = RFIDetector()
scistarter = SciStarterAPI()

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
    
    return render_template('index.html', 
                         total_recordings=total_recordings,
                         total_rfi=total_rfi,
                         recent_recordings=recent_recordings)



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
                
                # Get file size
                file_size = os.path.getsize(file_path)
                
                # Create database record
                recording = Recording(
                    filename=filename,
                    original_filename=file.filename,
                    file_path=file_path,
                    file_size=file_size,
                    frequency_range=request.form.get('frequency_range', ''),
                    sample_rate=int(request.form.get('sample_rate', 0)) if request.form.get('sample_rate') else None
                )
                
                db.session.add(recording)
                db.session.commit()
                
                # Add to processing queue
                queue_item = ProcessingQueue(recording_id=recording.id)
                db.session.add(queue_item)
                
                # Update user session (ensure it exists)
                if user_session:
                    user_session.recordings_uploaded += 1
                db.session.commit()
                
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
                            'file_size': file_size
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
        
        # Query RFI detections from the last N hours
        cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)
        
        detections = db.session.query(RFIDetection).join(Recording).filter(
            Recording.upload_timestamp >= datetime.fromtimestamp(cutoff_time),
            RFIDetection.power_level >= min_power
        ).all()
        
        # Format data for heatmap
        heatmap_data = []
        for detection in detections:
            heatmap_data.append({
                'frequency': detection.frequency / 1e6,  # Convert to MHz
                'time': detection.recording.upload_timestamp.isoformat(),
                'power': detection.power_level,
                'bandwidth': detection.bandwidth / 1e3 if detection.bandwidth else 1,  # Convert to kHz
                'type': detection.interference_type or 'unknown'
            })
        
        return jsonify({
            'success': True,
            'data': heatmap_data,
            'count': len(heatmap_data)
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
        from sdr_sharp_config import configure_sdr_sharp
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
                    user_session.location_lat = float(request.form.get('latitude'))
                    user_session.location_lon = float(request.form.get('longitude'))
                except ValueError:
                    pass  # Ignore invalid coordinates
            
            db.session.commit()
            
            flash('Welcome to NRAO Spectrum Sentinels! Your participation helps protect radio astronomy research.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            logging.error(f"Age verification error: {str(e)}")
            flash('An error occurred during verification. Please try again.', 'error')
    
    return render_template('age_verification.html')

@app.errorhandler(413)
def too_large(e):
    flash('File too large. Maximum size is 500MB.', 'error')
    return redirect(url_for('upload_file'))

@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', error_message='Page not found'), 404

@app.route('/api/status')
def api_status():
    """API endpoint for real-time status updates"""
    try:
        # Get latest activity timestamp
        latest_recording = Recording.query.order_by(Recording.upload_timestamp.desc()).first()
        latest_detection = RFIDetection.query.order_by(RFIDetection.detection_timestamp.desc()).first()
        
        last_update = 0
        if latest_recording:
            last_update = max(last_update, latest_recording.upload_timestamp.timestamp())
        if latest_detection:
            last_update = max(last_update, latest_detection.detection_timestamp.timestamp())
        
        # Count recent detections (last 5 minutes)
        recent_cutoff = datetime.utcnow().timestamp() - 300
        new_detections = RFIDetection.query.filter(
            RFIDetection.detection_timestamp >= datetime.fromtimestamp(recent_cutoff)
        ).count()
        
        # Processing queue status
        pending_jobs = ProcessingQueue.query.filter_by(status='pending').count()
        processing_jobs = ProcessingQueue.query.filter_by(status='processing').count()
        
        return jsonify({
            'success': True,
            'last_update': last_update,
            'new_detections': new_detections,
            'pending_processing': pending_jobs,
            'currently_processing': processing_jobs,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logging.error(f"Status API error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def api_stats():
    """API endpoint for dashboard statistics"""
    try:
        total_recordings = Recording.query.count()
        total_rfi = RFIDetection.query.count()
        processed_recordings = Recording.query.filter_by(processed=True).count()
        auto_detected_files = Recording.query.filter_by(auto_detected=True).count()
        
        return jsonify({
            'success': True,
            'total_recordings': total_recordings,
            'total_rfi': total_rfi,
            'processed_recordings': processed_recordings,
            'auto_detected_files': auto_detected_files,
            'detection_rate': (total_rfi / total_recordings * 100) if total_recordings > 0 else 0
        })
        
    except Exception as e:
        logging.error(f"Stats API error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.errorhandler(500)
def server_error(e):
    logging.error(f"Server error: {str(e)}")
    return render_template('base.html', error_message='Internal server error'), 500
