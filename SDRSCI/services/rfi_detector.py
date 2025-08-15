import numpy as np
import scipy.signal
import scipy.io.wavfile
import threading
import logging
from datetime import datetime
import os

from app import db, socketio
from models import Recording, RFIDetection, ProcessingQueue

class RFIDetector:
    def __init__(self):
        self.processing_lock = threading.Lock()
    
    def process_recording_async(self, recording_id):
        """Start RFI detection processing in a background thread"""
        thread = threading.Thread(target=self._process_recording, args=(recording_id,))
        thread.daemon = True
        thread.start()
    
    def _process_recording(self, recording_id):
        """Process a recording for RFI detection with real-time updates"""
        from app import app
        
        with self.processing_lock:
            with app.app_context():
                try:
                    # Update queue status
                    queue_item = ProcessingQueue.query.filter_by(recording_id=recording_id).first()
                    if queue_item:
                        queue_item.status = 'processing'
                        queue_item.started_at = datetime.utcnow()
                        db.session.commit()
                        
                        # Emit real-time update
                        socketio.emit('processing_started', {
                            'recording_id': recording_id,
                            'status': 'processing',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                    
                    recording = Recording.query.get(recording_id)
                    if not recording:
                        raise ValueError(f"Recording {recording_id} not found")
                    
                    logging.info(f"Starting RFI processing for recording {recording_id}")
                    
                    # Load and analyze the audio file
                    detections = self._analyze_audio_file(recording.file_path, recording)
                    
                    # Save detections to database
                    detection_count = 0
                    for detection_data in detections:
                        detection = RFIDetection(
                            recording_id=recording_id,
                            timestamp=detection_data['timestamp'],
                            frequency=detection_data['frequency'],
                            power_level=detection_data['power_level'],
                            bandwidth=detection_data.get('bandwidth'),
                            confidence=detection_data.get('confidence', 0.0),
                            interference_type=detection_data.get('type', 'unknown')
                        )
                        db.session.add(detection)
                        detection_count += 1
                        
                        # Emit real-time detection updates
                        if detection_count % 10 == 0:  # Every 10 detections
                            socketio.emit('detection_progress', {
                                'recording_id': recording_id,
                                'detections_found': detection_count,
                                'latest_detection': {
                                    'frequency': detection_data['frequency'],
                                    'power_level': detection_data['power_level'],
                                    'type': detection_data.get('type', 'unknown')
                                }
                            })
                    
                    # Update recording status
                    recording.processed = True
                    recording.rfi_detected = len(detections) > 0
                    recording.duration = self._get_audio_duration(recording.file_path)
                    recording.processing_completed_at = datetime.utcnow()
                    
                    # Update queue status
                    if queue_item:
                        queue_item.status = 'completed'
                        queue_item.completed_at = datetime.utcnow()
                    
                    db.session.commit()
                    
                    # Emit completion update
                    socketio.emit('processing_completed', {
                        'recording_id': recording_id,
                        'detections_found': detection_count,
                        'rfi_detected': recording.rfi_detected,
                        'duration': recording.duration,
                        'completed_at': recording.processing_completed_at.isoformat()
                    })
                    
                    logging.info(f"RFI processing completed for recording {recording_id}, found {len(detections)} detections")
                    
                except Exception as e:
                    logging.error(f"RFI processing failed for recording {recording_id}: {str(e)}")
                    
                    # Update queue with error
                    queue_item = ProcessingQueue.query.filter_by(recording_id=recording_id).first()
                    if queue_item:
                        queue_item.status = 'failed'
                        queue_item.error_message = str(e)
                        queue_item.completed_at = datetime.utcnow()
                        db.session.commit()
                        
                        # Emit error update
                        socketio.emit('processing_failed', {
                            'recording_id': recording_id,
                            'error': str(e),
                            'timestamp': datetime.utcnow().isoformat()
                        })
    
    def _analyze_audio_file(self, file_path, recording):
        """Fast analyze audio file for RFI patterns"""
        try:
            # Try to read as WAV file first
            if file_path.lower().endswith('.wav'):
                sample_rate, audio_data = scipy.io.wavfile.read(file_path)
            else:
                # For other formats, try to use generic approach
                return self._analyze_raw_data(file_path, recording)
            
            # Convert to mono if stereo
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1)
            
            # Limit data length for fast processing (max 30 seconds)
            max_samples = sample_rate * 30
            if len(audio_data) > max_samples:
                audio_data = audio_data[:max_samples]
            
            # Convert to float32 for faster processing
            audio_data = audio_data.astype(np.float32)
            if np.max(np.abs(audio_data)) > 0:
                audio_data = audio_data / np.max(np.abs(audio_data))
            
            # Update sample rate in recording
            recording.sample_rate = sample_rate
            
            return self._detect_rfi_patterns_fast(audio_data, sample_rate)
            
        except Exception as e:
            logging.error(f"Audio analysis failed: {str(e)}")
            return []
    
    def _analyze_raw_data(self, file_path, recording):
        """Analyze raw/binary data files (common in radio astronomy)"""
        try:
            # Read raw data - assume complex float32 format (common for SDR)
            with open(file_path, 'rb') as f:
                # Read file size to estimate sample count
                file_size = os.path.getsize(file_path)
                sample_count = file_size // 8  # 8 bytes per complex sample (float32 * 2)
                
                # Read data as complex float32
                raw_data = np.fromfile(f, dtype=np.complex64, count=min(sample_count, 1000000))  # Limit to 1M samples
            
            # Use default sample rate if not specified
            sample_rate = recording.sample_rate or 2048000  # 2 MHz default
            
            return self._detect_rfi_patterns_complex(raw_data, sample_rate)
            
        except Exception as e:
            logging.error(f"Raw data analysis failed: {str(e)}")
            return []
    
    def _get_audio_duration(self, file_path):
        """Get audio file duration in seconds"""
        try:
            if file_path.lower().endswith('.wav'):
                sample_rate, audio_data = scipy.io.wavfile.read(file_path)
                return len(audio_data) / sample_rate
            else:
                # For other formats, estimate based on file size
                file_size = os.path.getsize(file_path)
                estimated_duration = file_size / (2048000 * 4)  # Rough estimate
                return estimated_duration
        except:
            return None
    
    def _classify_interference_fast(self, frequency, power_level):
        """Fast classify the type of interference"""
        freq_mhz = frequency / 1e6
        
        # Quick classification based on frequency ranges
        if 88 <= freq_mhz <= 108:
            return 'FM_broadcast'
        elif 174 <= freq_mhz <= 216:
            return 'TV_broadcast'  
        elif 470 <= freq_mhz <= 790:
            return 'UHF_TV'
        elif 2400 <= freq_mhz <= 2500:
            return 'WiFi_ISM'
        elif power_level > -20:
            return 'strong_local'
        elif power_level > -40:
            return 'moderate'
        else:
            return 'weak_signal'
    
    def _detect_rfi_patterns_fast(self, audio_data, sample_rate):
        """Fast detect RFI patterns in real-valued audio data"""
        detections = []
        
        try:
            # Fast parameters for analysis
            window_size = min(2048, len(audio_data) // 4)  # Smaller window for speed
            hop_length = window_size // 4
            
            # Compute spectrogram with reduced resolution
            frequencies, times, spectrogram = scipy.signal.spectrogram(
                audio_data, 
                fs=sample_rate,
                window='hann',
                nperseg=window_size,
                noverlap=hop_length
            )
            
            # Convert to dB with clipping
            spectrogram_db = np.clip(10 * np.log10(spectrogram + 1e-10), -100, 50)
            
            # Fast threshold-based detection
            median_power = np.median(spectrogram_db)
            std_power = np.std(spectrogram_db)
            threshold = median_power + 2 * std_power
            
            # Find peaks above threshold
            peak_indices = np.where(spectrogram_db > threshold)
            
            # Sample detections for speed (every 5th detection)
            for i in range(0, len(peak_indices[0]), 5):
                f_idx = peak_indices[0][i] 
                t_idx = peak_indices[1][i]
                
                power = spectrogram_db[f_idx, t_idx]
                freq = frequencies[f_idx]
                time = times[t_idx]
                
                # Fast interference classification
                interference_type = self._classify_interference_fast(freq, power)
                
                # Simple bandwidth estimation
                bandwidth = sample_rate / window_size
                
                # Confidence based on power level
                confidence = min((power - threshold) / std_power, 1.0)
                
                detections.append({
                    'timestamp': float(time),
                    'frequency': float(freq),
                    'power_level': float(power),
                    'bandwidth': float(bandwidth),
                    'confidence': float(confidence),
                    'type': interference_type
                })
            
            # Limit detections for performance
            if len(detections) > 100:
                detections.sort(key=lambda x: x['power_level'], reverse=True)
                detections = detections[:100]
            
            # Filter out detections that are too close together (avoid duplicates)
            detections = self._filter_nearby_detections(detections)
            
        except Exception as e:
            logging.error(f"RFI pattern detection failed: {str(e)}")
        
        return detections
    
    def _detect_rfi_patterns_complex(self, complex_data, sample_rate):
        """Detect RFI patterns in complex-valued SDR data"""
        detections = []
        
        try:
            # Parameters for analysis
            window_size = 4096
            hop_length = window_size // 4
            
            # Compute FFT-based spectrogram for complex data
            frequencies = np.fft.fftfreq(window_size, 1/sample_rate)
            frequencies = np.fft.fftshift(frequencies)
            
            num_windows = (len(complex_data) - window_size) // hop_length + 1
            spectrogram = np.zeros((window_size, num_windows))
            
            for i in range(num_windows):
                start_idx = i * hop_length
                end_idx = start_idx + window_size
                window_data = complex_data[start_idx:end_idx]
                
                # Apply window and FFT
                windowed_data = window_data * np.hanning(window_size)
                fft_data = np.fft.fft(windowed_data)
                fft_data = np.fft.fftshift(fft_data)
                
                # Store power spectrum
                spectrogram[:, i] = np.abs(fft_data) ** 2
            
            # Convert to dB
            spectrogram_db = 10 * np.log10(spectrogram + 1e-10)
            
            # Create time axis
            times = np.arange(num_windows) * hop_length / sample_rate
            
            # Detect strong signals
            threshold = np.mean(spectrogram_db) + 3 * np.std(spectrogram_db)
            
            detection_count = 0
            for t_idx, time in enumerate(times):
                for f_idx, freq in enumerate(frequencies):
                    power = spectrogram_db[f_idx, t_idx]
                    
                    if power > threshold:
                        # Calculate bandwidth
                        bandwidth = self._estimate_bandwidth(spectrogram_db[:, t_idx], f_idx, frequencies)
                        
                        # Classify interference type
                        interference_type = self._classify_interference(power, bandwidth, freq)
                        
                        # Calculate confidence
                        confidence = min(1.0, (power - threshold) / (np.max(spectrogram_db) - threshold))
                        
                        detections.append({
                            'timestamp': float(time),
                            'frequency': float(freq),
                            'power_level': float(power),
                            'bandwidth': float(bandwidth),
                            'confidence': float(confidence),
                            'type': interference_type
                        })
                        
                        detection_count += 1
                        if detection_count > 200:  # Limit for performance
                            break
                
                if detection_count > 200:
                    break
            
            # Filter nearby detections
            detections = self._filter_nearby_detections(detections)
            
        except Exception as e:
            logging.error(f"Complex RFI pattern detection failed: {str(e)}")
        
        return detections
    
    def _estimate_bandwidth(self, power_spectrum, peak_idx, frequencies):
        """Estimate bandwidth of interference signal"""
        try:
            # Find -3dB points around the peak
            peak_power = power_spectrum[peak_idx]
            threshold = peak_power - 3.0
            
            # Search left and right from peak
            left_idx = peak_idx
            right_idx = peak_idx
            
            while left_idx > 0 and power_spectrum[left_idx] > threshold:
                left_idx -= 1
            
            while right_idx < len(power_spectrum) - 1 and power_spectrum[right_idx] > threshold:
                right_idx += 1
            
            # Calculate bandwidth
            if right_idx > left_idx:
                bandwidth = abs(frequencies[right_idx] - frequencies[left_idx])
            else:
                bandwidth = abs(frequencies[1] - frequencies[0])  # Single bin width
            
            return bandwidth
            
        except Exception:
            # Fallback to single bin bandwidth
            return abs(frequencies[1] - frequencies[0]) if len(frequencies) > 1 else 1000.0
    
    def _classify_interference(self, power_level, bandwidth, frequency):
        """Classify the type of interference based on characteristics"""
        freq_mhz = frequency / 1e6
        bw_khz = bandwidth / 1e3
        
        # FM broadcast
        if 88 <= freq_mhz <= 108 and bw_khz > 150:
            return 'FM_broadcast'
        
        # TV broadcast
        elif 174 <= freq_mhz <= 216:
            return 'TV_broadcast'
        
        # WiFi/ISM band
        elif 2400 <= freq_mhz <= 2500:
            return 'WiFi_ISM'
        
        # Amateur radio bands
        elif freq_mhz in [144, 432, 1296]:  # Near amateur frequencies
            return 'amateur_radio'
        
        # Cellular
        elif 800 <= freq_mhz <= 900 or 1800 <= freq_mhz <= 1900:
            return 'cellular'
        
        # Narrowband vs wideband classification
        elif bw_khz < 25:
            return 'narrowband'
        elif bw_khz > 100:
            return 'wideband'
        else:
            return 'unknown'
    
    def _filter_nearby_detections(self, detections):
        """Filter out detections that are too close in time/frequency"""
        if not detections:
            return detections
        
        # Sort by power level (strongest first)
        detections.sort(key=lambda x: x['power_level'], reverse=True)
        
        filtered = []
        for detection in detections:
            # Check if this detection is too close to existing ones
            too_close = False
            for existing in filtered:
                time_diff = abs(detection['timestamp'] - existing['timestamp'])
                freq_diff = abs(detection['frequency'] - existing['frequency'])
                
                # If within 0.1 seconds and 1 kHz, consider it a duplicate
                if time_diff < 0.1 and freq_diff < 1000:
                    too_close = True
                    break
            
            if not too_close:
                filtered.append(detection)
                
                # Limit total detections
                if len(filtered) >= 50:
                    break
        
        return filtered
