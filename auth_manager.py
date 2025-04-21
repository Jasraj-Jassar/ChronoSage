import os
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from config import CalendarConfig
import streamlit as st

class GoogleAuthManager:
    def __init__(self, config: CalendarConfig):
        self.config = config
        
    def get_credentials(self):
        """Get and refresh Google OAuth credentials"""
        creds = None
        if os.path.exists(self.config.TOKEN_FILE):
            with open(self.config.TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.config.CREDENTIALS_FILE, 
                        self.config.SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    st.error(f"Authentication error: {str(e)}")
                    raise
                
            with open(self.config.TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
        
        return creds
