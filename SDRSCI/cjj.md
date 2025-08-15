# NRAO Spectrum Sentinels

## Overview

NRAO Spectrum Sentinels is a citizen science web application for radio astronomy that enables real-time detection and cataloging of radio frequency interference (RFI). The platform allows users to upload SDR (Software Defined Radio) recordings, which are automatically processed using advanced signal processing algorithms to identify RFI patterns. The system features real-time monitoring, interactive visualizations, and seamless integration with external citizen science platforms. Built for radio astronomy research, it helps identify and mitigate interference sources that can affect astronomical observations.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

**Web Framework**: Flask-based web application using SQLAlchemy ORM with declarative base model architecture. The system follows a modular service-oriented design with clear separation between web routes, data models, and processing services. Real-time functionality is provided through Flask-SocketIO for bidirectional WebSocket communication.

**Database Design**: SQLAlchemy-based data layer supporting both SQLite (development) and PostgreSQL (production) through configurable DATABASE_URL. Core entities include:
- Recording: Audio file metadata with processing status and compression metrics
- RFIDetection: Detected interference events with frequency, power level, and confidence scores
- UserSession: Citizen science participant tracking with age verification and consent management
- ProcessingQueue: Asynchronous task management for RFI analysis

**Signal Processing Engine**: Custom RFI detection system utilizing NumPy and SciPy for digital signal processing. Implements multi-threaded background processing to analyze audio recordings without blocking the web interface. The detector uses spectral analysis techniques to identify interference patterns across frequency and time domains.

**Real-time Processing System**: WebSocket-based real-time updates using Flask-SocketIO with automatic file monitoring through the Watchdog library. New audio files are automatically detected, processed, and results are pushed to connected clients in real-time. Includes status indicators and progress tracking for ongoing operations.

**File Management**: Configurable upload system supporting multiple audio formats (WAV, FLAC, OGG, MP3, raw IQ data) with intelligent compression using gzip. Files are processed with size optimization and stored with metadata tracking. Maximum file size of 500MB with automatic directory creation.

**Authentication & Compliance**: Session-based user management with mandatory age verification (18+) and informed consent for research participation. Collects location data for research compliance while maintaining user privacy through session-based anonymization.

**Visualization Framework**: Interactive data visualization using Chart.js and HTML5 Canvas for real-time RFI heatmaps. Features time-frequency domain plotting with zoom capabilities, filtering controls, and live data updates through WebSocket connections.

## External Dependencies

**SciStarter API Integration**: RESTful API integration for logging citizen science contributions with the National Radio Astronomy Observatory. Automatically tracks user activities, file uploads, and RFI detections for research impact measurement. Uses Bearer token authentication with configurable project ID and fallback demo mode.

**SDR Sharp Integration**: Automated SDR Sharp configuration and launcher system that optimizes software-defined radio settings for RFI detection. Pre-configures audio recording parameters (48kHz WAV format, optimal gain settings) and establishes monitored output directories. Includes XML configuration generation for seamless SDR operation.

**Bootstrap & Frontend Libraries**: Responsive web interface built with Bootstrap 5 dark theme, Feather Icons for consistent iconography, and Chart.js for data visualization. Includes Socket.IO client library for real-time communication and custom CSS for radio astronomy themed styling.

**Waitress WSGI Server**: Production-ready WSGI server configuration with multi-threading support for handling concurrent requests and background processing tasks. Configured with connection pooling and automatic reconnection capabilities.

**File System Monitoring**: Watchdog library integration for automatic detection of new audio files in configured directories. Enables hands-free operation where SDR recordings are automatically processed as they are created, supporting continuous monitoring workflows.

**Scientific Computing Stack**: NumPy and SciPy for advanced signal processing algorithms including FFT analysis, spectral density calculations, and statistical interference detection. Provides the mathematical foundation for RFI identification algorithms.