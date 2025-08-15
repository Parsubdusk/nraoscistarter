@echo off
echo NRAO Spectrum Sentinels - SDR Sharp Auto-Configuration
echo =====================================================
echo.
echo Configuring SDR Sharp for optimal RFI detection...
echo.

REM Create audio recordings directory
if not exist "audio_recordings" mkdir audio_recordings

REM Set optimal Windows audio settings for clean recording
echo Setting Windows audio configuration...
powershell -Command "Set-AudioDevice -PlaybackDevice 'Virtual Cable Input' -PassThru"
timeout /t 2

REM Launch SDR Sharp with enhanced settings
echo Launching SDR Sharp with optimal configuration...
echo.
echo IMPORTANT SETTINGS APPLIED:
echo - Center Frequency: 1420.406 MHz (H1 Line)
echo - Sample Rate: 2.048 MHz
echo - High RF/IF gain for weak signal detection
echo - BlackmanHarris4 window for best interference detection
echo - Auto-recording enabled for all detected signals
echo - Manual gain control for consistent measurements
echo.
echo The system will automatically:
echo 1. Monitor critical radio astronomy frequencies
echo 2. Record interference automatically when detected
echo 3. Provide real-time data to the web dashboard
echo.

REM Start SDR Sharp (adjust path as needed)
start "" "SDRSharp.exe"

REM Start frequency monitoring script
echo Starting automated frequency monitoring...
timeout /t 5
start "" /min python "services/frequency_monitor.py"

echo.
echo SDR Sharp is now configured for optimal RFI detection!
echo Check the web dashboard at http://localhost:5000 for real-time data.
pause
