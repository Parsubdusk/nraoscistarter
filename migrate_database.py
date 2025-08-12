#!/usr/bin/env python3
"""
Database migration script to add new columns
"""
import sqlite3
import os
import logging

def migrate_database():
    """Add new columns to existing database"""
    db_path = 'rf_data.db'
    
    if not os.path.exists(db_path):
        print("Database doesn't exist yet - will be created automatically")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(recording)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add missing columns
        if 'processing_completed_at' not in columns:
            cursor.execute("ALTER TABLE recording ADD COLUMN processing_completed_at DATETIME")
            print("✓ Added processing_completed_at column")
        
        if 'file_hash' not in columns:
            cursor.execute("ALTER TABLE recording ADD COLUMN file_hash VARCHAR(64)")
            print("✓ Added file_hash column")
            
        if 'auto_detected' not in columns:
            cursor.execute("ALTER TABLE recording ADD COLUMN auto_detected BOOLEAN DEFAULT 0")
            print("✓ Added auto_detected column")
        
        # Create index for file_hash if it doesn't exist
        try:
            cursor.execute("CREATE INDEX idx_recording_file_hash ON recording(file_hash)")
            print("✓ Added file_hash index")
        except sqlite3.OperationalError:
            pass  # Index might already exist
        
        # Update null values
        cursor.execute("UPDATE recording SET auto_detected = 0 WHERE auto_detected IS NULL")
        
        conn.commit()
        print("✓ Database migration completed successfully")
        
    except Exception as e:
        print(f"✗ Migration error: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()
    
    return True

if __name__ == '__main__':
    migrate_database()