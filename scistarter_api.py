import requests
import logging
import os
import json
from datetime import datetime

class SciStarterAPI:
    def __init__(self):
        self.api_key = os.environ.get('SCISTARTER_API_KEY', 'demo-key')
        self.project_id = os.environ.get('SCISTARTER_PROJECT_ID', 'spectrumx-spectrum-sentinels')
        self.base_url = 'https://api.scistarter.com/v1'
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'SpectrumX-Spectrum-Sentinels/1.0'
        })
    
    def log_contribution(self, user_session_id, activity_type, metadata=None):
        """Log a citizen science contribution to SciStarter"""
        try:
            contribution_data = {
                'project_id': self.project_id,
                'user_id': user_session_id,  # Using session ID as user identifier
                'activity_type': activity_type,
                'timestamp': datetime.utcnow().isoformat(),
                'metadata': metadata or {}
            }
            
            response = self.session.post(
                f'{self.base_url}/contributions',
                json=contribution_data,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                logging.info(f"SciStarter contribution logged: {activity_type}")
                return True
            else:
                logging.warning(f"SciStarter API returned status {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logging.error("SciStarter API timeout")
            return False
        except requests.exceptions.RequestException as e:
            logging.error(f"SciStarter API request failed: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"SciStarter logging error: {str(e)}")
            return False
    
    def log_rfi_detection(self, user_session_id, detection_count, recording_metadata):
        """Log RFI detection results as a contribution"""
        try:
            metadata = {
                'detection_count': detection_count,
                'recording_file': recording_metadata.get('filename'),
                'file_size': recording_metadata.get('file_size'),
                'sample_rate': recording_metadata.get('sample_rate'),
                'frequency_range': recording_metadata.get('frequency_range'),
                'duration': recording_metadata.get('duration')
            }
            
            return self.log_contribution(user_session_id, 'rfi_analysis', metadata)
            
        except Exception as e:
            logging.error(f"RFI detection logging error: {str(e)}")
            return False
    
    def get_user_contributions(self, user_session_id):
        """Get user's contribution history from SciStarter"""
        try:
            response = self.session.get(
                f'{self.base_url}/contributions',
                params={
                    'project_id': self.project_id,
                    'user_id': user_session_id
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.warning(f"Failed to get contributions: {response.status_code}")
                return {'contributions': []}
                
        except Exception as e:
            logging.error(f"Error getting user contributions: {str(e)}")
            return {'contributions': []}
    
    def get_project_stats(self):
        """Get overall project statistics from SciStarter"""
        try:
            response = self.session.get(
                f'{self.base_url}/projects/{self.project_id}/stats',
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.warning(f"Failed to get project stats: {response.status_code}")
                return {
                    'total_contributors': 0,
                    'total_contributions': 0,
                    'active_users': 0
                }
                
        except Exception as e:
            logging.error(f"Error getting project stats: {str(e)}")
            return {
                'total_contributors': 0,
                'total_contributions': 0,
                'active_users': 0
            }
    
    def validate_api_connection(self):
        """Test connection to SciStarter API"""
        try:
            response = self.session.get(
                f'{self.base_url}/projects/{self.project_id}',
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logging.error(f"SciStarter API validation failed: {str(e)}")
            return False
