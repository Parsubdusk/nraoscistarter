#!/usr/bin/env python3
"""
Local Setup Script for NRAO Spectrum Sentinels
Automated installation and configuration for localhost development
"""

import subprocess
import sys
import os
import json
from pathlib import Path

def print_banner():
    print("=" * 60)
    print("NRAO Spectrum Sentinels - Localhost Setup")
    print("Real-time RFI Detection with File Compression")
    print("=" * 60)
    print()

def check_python_version():
    """Check if Python version is sufficient"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {sys.version}")
        return False
    
    print(f"✓ Python version: {sys.version.split()[0]}")
    return True

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    
    # Core packages that are definitely needed
    core_packages = [
        'flask>=3.0.0',
        'flask-sqlalchemy>=3.1.0',
        'flask-socketio>=5.3.0',
        'waitress>=3.0.0',
        'numpy>=1.21.0',
        'scipy>=1.7.0',
        'requests>=2.25.0',
        'werkzeug>=3.0.0',
        'email-validator>=2.0.0',
        'watchdog>=3.0.0',
        'python-socketio[client]>=5.8.0'
    ]
    
    # Optional packages for enhanced functionality
    optional_packages = [
        'matplotlib>=3.5.0',
        'plotly>=5.0.0',
        'psycopg2-binary>=2.9.0',  # For PostgreSQL support
        'gunicorn>=21.0.0'  # Alternative WSGI server
    ]
    
    try:
        # Install core packages
        print("   Installing core packages...")
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'
        ], stdout=subprocess.DEVNULL)
        
        for package in core_packages:
            try:
                subprocess.check_call([
                    sys.executable, '-m', 'pip', 'install', package
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"   ✓ {package.split('>=')[0]}")
            except subprocess.CalledProcessError:
                print(f"   ⚠ Failed to install {package}")
        
        # Install optional packages (best effort)
        print("   Installing optional packages...")
        for package in optional_packages:
            try:
                subprocess.check_call([
                    sys.executable, '-m', 'pip', 'install', package
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"   ✓ {package.split('>=')[0]}")
            except subprocess.CalledProcessError:
                print(f"   - Skipped {package.split('>=')[0]} (optional)")
        
        print("✓ Dependencies installed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")
    
    directories = [
        'uploads',
        'audio_recordings',
        'logs',
        'static/css',
        'static/js',
        'templates',
        'services'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"   ✓ {directory}")
    
    print("✓ Directories created")
    return True

def setup_environment():
    """Set up environment variables"""
    print("🔧 Configuring environment...")
    
    # Default environment variables
    env_vars = {
        'DATABASE_URL': 'sqlite:///spectrum_sentinels.db',
        'SESSION_SECRET': 'spectrum-sentinels-dev-key-' + os.urandom(16).hex(),
        'UPLOAD_FOLDER': 'uploads',
        'AUDIO_DIRECTORY': 'audio_recordings',
        'SDR_SHARP_PATH': r'C:\Users\coraj\OneDrive\Desktop\sdrsharp-x86',
        'SCISTARTER_API_KEY': 'demo-key',
        'SCISTARTER_PROJECT_ID': 'spectrumx-spectrum-sentinels',
        'DEBUG': 'true',
        'HOST': '0.0.0.0',
        'PORT': '5000',
        'THREADS': '4'
    }
    
    # Set environment variables for this session
    for key, value in env_vars.items():
        os.environ[key] = value
        print(f"   ✓ {key}")
    
    # Create .env file for future reference
    try:
        with open('.env', 'w') as f:
            f.write("# NRAO Spectrum Sentinels Environment Variables\n")
            f.write("# Copy these to your shell or use a .env loader\n\n")
            for key, value in env_vars.items():
                f.write(f'export {key}="{value}"\n')
        
        print("✓ Environment configured (.env file created)")
    except Exception as e:
        print(f"⚠ Could not create .env file: {e}")
    
    return True

def check_project_files():
    """Check if all project files are present"""
    print("📋 Checking project files...")
    
    required_files = [
        'app.py',
        'models.py',
        'routes.py',
        'config.py',
        'main.py',
        'run_server.py',
        'templates/base.html',
        'templates/index.html',
        'templates/upload.html',
        'templates/results.html',
        'templates/heatmap.html',
        'templates/age_verification.html',
        'static/css/styles.css',
        'static/js/realtime.js',
        'services/file_processor.py',
        'services/rfi_detector.py',
        'services/realtime_monitor.py',
        'services/scistarter_api.py',
        'services/sdr_sharp_config.py'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
        else:
            print(f"   ✓ {file_path}")
    
    if missing_files:
        print(f"❌ Missing files: {len(missing_files)}")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    print("✓ All project files present")
    return True

def initialize_database():
    """Initialize the database"""
    print("🗄️ Initializing database...")
    
    try:
        # Import and initialize the Flask app to create tables
        sys.path.insert(0, os.getcwd())
        from app import app, db
        
        with app.app_context():
            db.create_all()
            
            # Check if database is working
            from models import Recording
            count = Recording.query.count()
            print(f"   ✓ Database initialized (current recordings: {count})")
        
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def create_run_script():
    """Create a simple run script for easy startup"""
    print("🚀 Creating run script...")
    
    script_content = '''#!/usr/bin/env python3
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
'''
    
    try:
        with open('start_server.py', 'w') as f:
            f.write(script_content)
        
        # Make executable on Unix-like systems
        if os.name != 'nt':
            os.chmod('start_server.py', 0o755)
        
        print("   ✓ start_server.py created")
        return True
    
    except Exception as e:
        print(f"❌ Failed to create run script: {e}")
        return False

def print_usage_instructions():
    """Print usage instructions"""
    print("\n" + "=" * 70)
    print("🎉 NRAO Spectrum Sentinels - Setup Complete!")
    print("=" * 70)
    print()
    print("📋 STEP-BY-STEP INSTRUCTIONS TO RUN LOCALLY:")
    print()
    print("1️⃣  START THE SERVER (Choose one method):")
    print("   • Quick Start:     python start_server.py")
    print("   • Direct Launch:   python run_server.py")
    print("   • Development:     python main.py")
    print()
    print("2️⃣  OPEN YOUR WEB BROWSER:")
    print("   Go to: http://localhost:5000")
    print()
    print("3️⃣  VERIFY THE WEBSITE WORKS:")
    print("   • Check age verification page loads")
    print("   • Try uploading an audio file")
    print("   • View the real-time heatmap")
    print()
    print("4️⃣  OPTIONAL SDR SHARP INTEGRATION:")
    print("   • Edit .env file and set SDR_SHARP_PATH to your SDR Sharp folder")
    print("   • Example: SDR_SHARP_PATH=C:\\SDRSharp")
    print()
    print("✅ FEATURES ENABLED:")
    print("  ✓ Real-time US geographic RFI heatmap")
    print("  ✓ Automatic file compression on upload")
    print("  ✓ Background RFI processing and detection")
    print("  ✓ Live WebSocket updates")
    print("  ✓ Radio astronomy frequency filtering")
    print("  ✓ SDR Sharp auto-configuration (if path set)")
    print()
    print("📁 IMPORTANT FILES & FOLDERS:")
    print(f"  ├── uploads/           → User uploaded audio files")
    print(f"  ├── audio_recordings/  → SDR Sharp monitoring folder")
    print(f"  ├── .env               → Configuration settings")
    print(f"  └── spectrum_sentinels.db → Local database")
    print()
    print("🔧 CONFIGURATION OPTIONS:")
    print("  Edit the .env file to customize:")
    print("  • DATABASE_URL        → Change to PostgreSQL if needed")
    print("  • SDR_SHARP_PATH      → Path to SDR Sharp installation")
    print("  • SCISTARTER_API_KEY  → Enable SciStarter integration")
    print("  • UPLOAD_FOLDER       → Change upload directory")
    print()
    print("🆘 TROUBLESHOOTING:")
    print("  • Port 5000 busy?     → Change PORT in .env file")
    print("  • Missing packages?   → Run 'python setup_local.py' again")
    print("  • Database errors?    → Delete spectrum_sentinels.db and restart")
    print("="*70)

def main():
    """Main setup function"""
    print_banner()
    
    # Check prerequisites
    if not check_python_version():
        sys.exit(1)
    
    # Setup steps
    steps = [
        ("Installing dependencies", install_dependencies),
        ("Creating directories", create_directories),
        ("Setting up environment", setup_environment),
        ("Checking project files", check_project_files),
        ("Initializing database", initialize_database),
        ("Creating run script", create_run_script)
    ]
    
    for step_name, step_func in steps:
        print(f"\n🔄 {step_name}...")
        if not step_func():
            print(f"\n❌ Setup failed at: {step_name}")
            sys.exit(1)
    
    print_usage_instructions()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during setup: {e}")
        sys.exit(1)
