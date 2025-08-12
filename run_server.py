#!/usr/bin/env python3
"""
SpectrumX Spectrum Sentinels Server Runner
Uses Waitress WSGI server as specified in requirements
"""

import os
import sys
import logging
from waitress import serve
from app import app

def main():
    """Main server runner function"""
    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('spectrum_sentinels.log')
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    # Configuration
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    threads = int(os.environ.get('THREADS', 4))
    
    logger.info("="*50)
    logger.info("SpectrumX Spectrum Sentinels Server Starting")
    logger.info("="*50)
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"Threads: {threads}")
    logger.info(f"Database: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured')}")
    logger.info(f"Upload Directory: {app.config.get('UPLOAD_FOLDER', 'Not configured')}")
    logger.info(f"SDR Sharp Path: {app.config.get('SDR_SHARP_PATH', 'Not configured')}")
    logger.info("="*50)
    
    # Validate configuration
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        logger.warning(f"Upload directory does not exist: {app.config['UPLOAD_FOLDER']}")
        try:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            logger.info(f"Created upload directory: {app.config['UPLOAD_FOLDER']}")
        except OSError as e:
            logger.error(f"Failed to create upload directory: {e}")
            sys.exit(1)
    
    # Check SDR Sharp path (warn but don't exit if missing)
    if not os.path.exists(app.config['SDR_SHARP_PATH']):
        logger.warning(f"SDR Sharp not found at: {app.config['SDR_SHARP_PATH']}")
        logger.warning("SDR Sharp launch functionality will not work")
    
    try:
        # Test database connection
        with app.app_context():
            from models import Recording
            recording_count = Recording.query.count()
            logger.info(f"Database connection successful. Total recordings: {recording_count}")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.warning("Server will start but database functionality may not work")
    
    try:
        logger.info("Starting Waitress WSGI server...")
        logger.info("Press Ctrl+C to stop the server")
        
        # Serve the application using Waitress
        serve(
            app,
            host=host,
            port=port,
            threads=threads,
            url_scheme='https' if os.environ.get('USE_HTTPS') == 'true' else 'http',
            # Performance settings
            connection_limit=1000,
            cleanup_interval=30,
            channel_timeout=120,
            # Security settings
            max_request_header_size=262144,  # 256KB
            max_request_body_size=524288000,  # 500MB (matches Flask config)
            # Logging
            ident='SpectrumSentinels'
        )
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
    finally:
        logger.info("Server shutdown complete")

if __name__ == '__main__':
    main()

