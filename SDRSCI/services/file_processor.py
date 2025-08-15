import os
import gzip
import shutil
import logging
from datetime import datetime
from pathlib import Path

class FileProcessor:
    """Enhanced file processing with compression and optimization"""
    
    def __init__(self, compression_level=6):
        self.compression_level = compression_level
        self.supported_formats = {
            '.wav', '.flac', '.ogg', '.mp3', '.aiff', '.au', 
            '.raw', '.iq', '.bin', '.dat'
        }
    
    def process_upload(self, file_path, original_filename):
        """Process uploaded file with compression and optimization"""
        try:
            file_info = {
                'original_size': os.path.getsize(file_path),
                'compressed_size': None,
                'compression_ratio': None,
                'processing_time': None
            }
            
            start_time = datetime.now()
            
            # Determine if file should be compressed
            file_ext = Path(original_filename).suffix.lower()
            
            if self._should_compress_file(file_ext, file_info['original_size']):
                compressed_path = self._compress_file(file_path)
                if compressed_path:
                    # Replace original with compressed version
                    shutil.move(compressed_path, file_path)
                    file_info['compressed_size'] = os.path.getsize(file_path)
                    file_info['compression_ratio'] = file_info['compressed_size'] / file_info['original_size']
                    logging.info(f"File compressed: {original_filename}, ratio: {file_info['compression_ratio']:.2f}")
                else:
                    file_info['compressed_size'] = file_info['original_size']
                    file_info['compression_ratio'] = 1.0
            else:
                file_info['compressed_size'] = file_info['original_size']
                file_info['compression_ratio'] = 1.0
            
            # Calculate processing time
            file_info['processing_time'] = (datetime.now() - start_time).total_seconds()
            
            return file_info
            
        except Exception as e:
            logging.error(f"File processing failed for {original_filename}: {str(e)}")
            return None
    
    def _should_compress_file(self, file_ext, file_size):
        """Determine if a file should be compressed"""
        # Don't compress already compressed formats
        compressed_formats = {'.flac', '.ogg', '.mp3'}
        if file_ext in compressed_formats:
            return False
        
        # Only compress files larger than 1MB
        if file_size < 1024 * 1024:
            return False
        
        # Compress supported audio formats
        return file_ext in self.supported_formats
    
    def _compress_file(self, file_path):
        """Compress file using gzip"""
        try:
            compressed_path = file_path + '.tmp.gz'
            
            with open(file_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb', compresslevel=self.compression_level) as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Decompress back to original format for processing
            decompressed_path = file_path + '.tmp'
            with gzip.open(compressed_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Clean up
            os.remove(compressed_path)
            
            return decompressed_path
            
        except Exception as e:
            logging.error(f"File compression failed: {str(e)}")
            return None
    
    def get_file_metadata(self, file_path):
        """Extract metadata from audio files"""
        try:
            metadata = {
                'size': os.path.getsize(file_path),
                'modified': datetime.fromtimestamp(os.path.getmtime(file_path)),
                'format': Path(file_path).suffix.lower()
            }
            
            # Try to get audio-specific metadata
            try:
                import scipy.io.wavfile
                if metadata['format'] == '.wav':
                    sample_rate, audio_data = scipy.io.wavfile.read(file_path)
                    metadata['sample_rate'] = sample_rate
                    metadata['duration'] = len(audio_data) / sample_rate
                    metadata['channels'] = 1 if len(audio_data.shape) == 1 else audio_data.shape[1]
            except:
                pass
            
            return metadata
            
        except Exception as e:
            logging.error(f"Metadata extraction failed: {str(e)}")
            return {}
