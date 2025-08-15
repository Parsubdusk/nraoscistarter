#!/usr/bin/env python3
"""
Quick start script for NRAO Spectrum Sentinels
"""
import os
import sys

# Set environment variables
env_vars = {
    'DATABASE_URL': 'sqlite:///spectrum_sentinels.db',
    'SESSION_SECRET': 'spectrum-sentinels-dev-key',
    'UPLOAD_FOLDER': 'uploads',
    'AUDIO_DIRECTORY': 'audio_recordings',
    'DEBUG': 'true',
    'HOST': '0.0.0.0',
    'PORT': '5000'
}

for key, value in env_vars.items():
    os.environ[key] = value

# Import and run the application
if __name__ == '__main__':
    from run_server import main
    main()
