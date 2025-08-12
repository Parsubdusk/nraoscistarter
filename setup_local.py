#!/usr/bin/env python3
"""
Quick setup script for running NRAO Spectrum Sentinels locally
"""
import subprocess
import sys
import os

def install_packages():
    """Install required Python packages"""
    packages = [
        'flask',
        'flask-sqlalchemy', 
        'waitress',
        'numpy',
        'scipy', 
        'requests',
        'matplotlib',
        'plotly',
        'email-validator',
        'werkzeug',
        'psycopg2-binary',
        'gunicorn'
    ]
    
    print("Installing Python packages...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + packages)
        print("✓ All packages installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install packages: {e}")
        return False
    return True

def set_environment():
    """Set up environment variables"""
    print("\nSetting up environment...")
    
    # Set environment variables for this session
    os.environ['DATABASE_URL'] = 'sqlite:///rf_data.db'
    os.environ['SESSION_SECRET'] = 'spectrum-sentinels-local-key'
    os.environ['SDR_SHARP_PATH'] = r'C:\Users\coraj\OneDrive\Desktop\sdrsharp-x86'
    os.environ['AUDIO_DIRECTORY'] = r'C:\Users\coraj\OneDrive\Desktop\Audio'
    
    print("✓ Environment variables set")

def start_server():
    """Start the Flask application"""
    print("\nStarting NRAO Spectrum Sentinels server...")
    print("Server will be available at: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print("-" * 50)
    
    try:
        # Import and run the Flask app
        from app import app
        from waitress import serve
        
        # Run with Waitress (production server)
        serve(app, host='0.0.0.0', port=5000, threads=4)
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        print("Make sure all project files are in the current directory")
        return False
    except Exception as e:
        print(f"✗ Server error: {e}")
        return False

def main():
    print("NRAO Spectrum Sentinels - Local Setup")
    print("=" * 40)
    
    # Check if we're in the right directory
    required_files = ['app.py', 'routes.py', 'models.py', 'run_server.py']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print("✗ Missing project files:")
        for f in missing_files:
            print(f"  - {f}")
        print("\nPlease download all project files from Replit to this directory first.")
        input("Press Enter to exit...")
        return
    
    print("✓ Project files found")
    
    # Install packages
    if not install_packages():
        input("Press Enter to exit...")
        return
    
    # Set environment
    set_environment()
    
    # Start server
    start_server()

if __name__ == '__main__':
    main()