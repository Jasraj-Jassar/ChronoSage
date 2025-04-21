from datetime import datetime, timedelta
import pytz
from openai import OpenAI
import json
import streamlit as st
from typing import Dict, Any, Optional, List
import re

class EventProcessor:
    def __init__(self, timezone: str, api_key: str = None):
        """Initialize the event processor with timezone and API key"""
        self.timezone = pytz.timezone(timezone)
        self.api_key = api_key or st.secrets.get("OPENAI_API_KEY")
        if not self.api_key:
            st.error("OpenAI API key is missing.")
        self.openai_client = OpenAI(api_key=self.api_key)

    def process_create_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Process natural language commands to create a calendar event"""
        try:
            current_date = datetime.now(self.timezone).strftime('%Y-%m-%d')
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"""You are a calendar assistant for Mountain Time (MST/MDT). 
                     Convert user requests into structured event details. The current date is {current_date}."""},
                    {"role": "user", "content": f"Convert this request into a calendar event: {user_input}"}
                ],
                functions=[{
                    "name": "create_calendar_event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "date": {"type": "string"},
                            "time": {"type": "string"},
                            "duration": {"type": "integer"},
                            "description": {"type": "string"}
                        },
                        "required": ["title", "date", "time", "duration"]
                    }
                }],
                function_call={"name": "create_calendar_event"}
            )
            
            return json.loads(response.choices[0].message.function_call.arguments)
        except Exception as e:
            st.error(f"Error processing request: {str(e)}")
            return None
            
    def process_edit_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Process natural language commands to edit a calendar event"""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """You are a calendar editing assistant. 
                     Convert user edit requests into structured modifications.
                     Identify the event by its title or key terms and specify the changes needed."""},
                    {"role": "user", "content": f"Process this calendar edit request: {user_input}"}
                ],
                functions=[{
                    "name": "edit_calendar_event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_terms": {
                                "type": "string",
                                "description": "Keywords to identify the event"
                            },
                            "new_date": {
                                "type": "string",
                                "description": "New date if changing"
                            },
                            "new_time": {
                                "type": "string",
                                "description": "New time if changing"
                            },
                            "new_duration": {
                                "type": "integer",
                                "description": "New duration in minutes if changing"
                            },
                            "new_title": {
                                "type": "string",
                                "description": "New title if changing"
                            },
                            "action": {
                                "type": "string",
                                "enum": ["reschedule", "modify", "cancel"],
                                "description": "Type of edit action"
                            }
                        },
                        "required": ["search_terms", "action"]
                    }
                }],
                function_call={"name": "edit_calendar_event"}
            )
            
            return json.loads(response.choices[0].message.function_call.arguments)
        except Exception as e:
            st.error(f"Error processing edit request: {str(e)}")
            return None
