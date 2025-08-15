#!/usr/bin/env python3
"""
NRAO Spectrum Sentinels - Production Server Runner
Enhanced with real-time monitoring and file compression
"""

import os
import sys
import logging
from waitress import serve
from app import app, socketio

def setup_logging():
    """Configure application logging"""
    log_level = logging.DEBUG if os.environ.get('DEBUG') == 'true' else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('spectrum_sentinels.log', mode='a')
        ]
    )
    
    # Reduce noise from some libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('matplotlib').setLevel(logging.WARNING)

def validate_environment():
    """Validate required environment variables and directories"""
    logger = logging.getLogger(__name__)
    
    # Check required directories
    required_dirs = [
        app.config['UPLOAD_FOLDER'],
        app.config['AUDIO_DIRECTORY']
    ]
    
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.info(f"Creating directory: {directory}")
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create directory {directory}: {e}")
                return False
    
    # Test database connection
    try:
        with app.app_context():
            from models import Recording
            count = Recording.query.count()
            logger.info(f"Database connection successful. Total recordings: {count}")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.warning("Server will start but database functionality may not work")
    
    # Check SDR Sharp path (optional)
    sdr_path = app.config.get('SDR_SHARP_PATH')
    if sdr_path and not os.path.exists(sdr_path):
        logger.warning(f"SDR Sharp not found at: {sdr_path}")
        logger.warning("SDR Sharp launch functionality will not work")
    
    return True

def print_startup_info():
    """Print startup information"""
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("NRAO Spectrum Sentinels - Real-time RFI Detection")
    logger.info("=" * 60)
    logger.info(f"Version: Enhanced with real-time monitoring")
    logger.info(f"Host: {os.environ.get('HOST', '0.0.0.0')}")
    logger.info(f"Port: {os.environ.get('PORT', 5000)}")
    logger.info(f"Debug Mode: {os.environ.get('DEBUG', 'false')}")
    logger.info(f"Database: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured')}")
    logger.info(f"Upload Directory: {app.config['UPLOAD_FOLDER']}")
    logger.info(f"Audio Directory: {app.config['AUDIO_DIRECTORY']}")
    logger.info(f"SDR Sharp Path: {app.config.get('SDR_SHARP_PATH', 'Not configured')}")
    
    # Feature status
    logger.info("Features:")
    logger.info(f"  - Real-time Updates: {'Enabled' if app.config.get('REALTIME_UPDATES') else 'Disabled'}")
    logger.info(f"  - File Compression: {'Enabled' if app.config.get('COMPRESSION_ENABLED') else 'Disabled'}")
    logger.info(f"  - WebSocket Support: Enabled")
    logger.info(f"  - Background Processing: Enabled")
    logger.info(f"  - SciStarter Integration: {'Enabled' if os.environ.get('SCISTARTER_API_KEY') else 'Disabled'}")
    
    logger.info("=" * 60)

def main():
    """Main server entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    print_startup_info()
    
    # Validate environment
    if not validate_environment():
        logger.error("Environment validation failed")
        sys.exit(1)
    
    # Configuration
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    threads = int(os.environ.get('THREADS', 4))
    
    logger.info("Starting NRAO Spectrum Sentinels server...")
    logger.info("Press Ctrl+C to stop the server")
    logger.info("-" * 40)
    
    try:
        if debug:
            # Development mode with Flask's built-in server and Socket.IO
            logger.info("Running in DEBUG mode with Flask development server")
            socketio.run(
                app,
                host=host,
                port=port,
                debug=True,
                use_reloader=False  # Disable reloader to prevent issues with threading
            )
        else:
            # Production mode with Waitress
            logger.info("Running in PRODUCTION mode with Waitress WSGI server")
            serve(
                app,
                host=host,
                port=port,
                threads=threads,
                url_scheme='https' if os.environ.get('USE_HTTPS') == 'true' else 'http',
                connection_limit=1000,
                cleanup_interval=30,
                channel_timeout=120,
                max_request_header_size=262144,  # 256KB
                max_request_body_size=524288000,  # 500MB
                ident='NRAO-SpectrumSentinels'
            )
    
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        try:
            from services.realtime_monitor import stop_realtime_monitoring
            stop_realtime_monitoring()
            logger.info("Real-time monitoring stopped")
        except:
            pass
        
        logger.info("Server shutdown complete")

if __name__ == '__main__':
    main()
