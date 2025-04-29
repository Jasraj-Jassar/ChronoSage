from datetime import datetime, timedelta
import pytz
from openai import OpenAI
import json
import streamlit as st
from typing import Dict, List, Any, Optional, Tuple, Set, Union
import re
import logging
import pandas as pd
from config import AppConfig, AIConfig
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from utils import extract_attendees_from_text, get_weather_for_event
from tenacity import retry, stop_after_attempt, wait_exponential

# Set up logging
logger = logging.getLogger(__name__)

# Download NLTK resources if not already available
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)

class EventProcessor:
    def __init__(self, timezone: str, api_key: str = None):
        """Initialize the event processor with timezone and API key"""
        self.timezone = pytz.timezone(timezone)
        self.app_config = AppConfig()
        self.ai_config = self.app_config.AI_CONFIG
        
        # Set up OpenAI client
        try:
            self.api_key = api_key or st.secrets["openai"]["OPENAI_API_KEY"]
            if not self.api_key:
                st.error("OpenAI API key is missing.")
                logger.error("OpenAI API key is missing")
                self.openai_client = None
                return
            
            # Get organization ID if available
            org_id = None
            if "ORGANIZATION_ID" in st.secrets["openai"]:
                org_id = st.secrets["openai"]["ORGANIZATION_ID"]
            
            # Initialize OpenAI client
            client_params = {"api_key": self.api_key}
            if org_id:
                client_params["organization"] = org_id
                
            self.openai_client = OpenAI(**client_params)
            logger.info("EventProcessor initialized successfully")
        except Exception as e:
            error_msg = f"Failed to initialize OpenAI client: {str(e)}"
            logger.error(error_msg)
            st.error(error_msg)
            self.openai_client = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def process_create_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Process natural language commands to create a calendar event"""
        try:
            # Check if client is properly initialized
            if not self.openai_client:
                raise ValueError("OpenAI client not initialized. Check your API key.")
                
            current_date = datetime.now(self.timezone).strftime('%Y-%m-%d')
            
            # Enhanced context for better understanding
            system_prompt = f"""You are a calendar assistant for {self.timezone.zone.replace('_', ' ')}. 
                Convert user requests into structured event details. The current date is {current_date}.
                Be intelligent about inferring meeting locations, attendees, and other details.
                If the input mentions a location like "at office" or "at Starbucks", capture it.
                If attendees are mentioned, extract them as a list.
                If the event repeats (like "every Monday" or "weekly"), indicate it's recurring."""
            
            response = self.openai_client.chat.completions.create(
                model=self.ai_config.MODEL,
                temperature=self.ai_config.TEMPERATURE,
                max_tokens=self.ai_config.MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Convert this request into a calendar event: {user_input}"}
                ],
                functions=[{
                    "name": "create_calendar_event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Title of the event"},
                            "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                            "time": {"type": "string", "description": "Time in HH:MM format (24-hour)"},
                            "duration": {"type": "integer", "description": "Duration in minutes"},
                            "description": {"type": "string", "description": "Description of the event"},
                            "location": {"type": "string", "description": "Location of the event if mentioned"},
                            "attendees": {
                                "type": "array", 
                                "items": {"type": "string"},
                                "description": "List of attendees if mentioned"
                            },
                            "is_recurring": {"type": "boolean", "description": "Whether the event repeats"},
                            "recurrence_pattern": {
                                "type": "string",
                                "enum": ["DAILY", "WEEKLY", "BIWEEKLY", "MONTHLY", "YEARLY"],
                                "description": "How often the event repeats, if it's recurring"
                            },
                            "reminder_minutes": {"type": "integer", "description": "Minutes before event to send reminder"}
                        },
                        "required": ["title", "date", "time", "duration"]
                    }
                }],
                function_call={"name": "create_calendar_event"}
            )
            
            event_details = json.loads(response.choices[0].message.function_call.arguments)
            
            # Add weather information if a location is provided
            if 'location' in event_details and self.app_config.WEATHER_CONFIG.ENABLED:
                weather = get_weather_for_event(
                    event_details['date'], 
                    event_details['time'], 
                    event_details.get('location')
                )
                if weather['status'] == 'success':
                    event_details['weather'] = weather
            
            # Suggest related to-dos if it's a meeting
            if self.ai_config.SUGGESTION_MODE and 'meeting' in event_details['title'].lower():
                suggestions = self._suggest_meeting_preparation(event_details)
                if suggestions:
                    event_details['suggested_todos'] = suggestions
            
            # Set default reminder if not specified
            if 'reminder_minutes' not in event_details:
                event_details['reminder_minutes'] = self.app_config.DEFAULT_NOTIFICATION_LEAD_TIME
                
            return event_details
        except Exception as e:
            logger.error(f"Error processing create request: {str(e)}")
            st.error(f"Error processing request: {str(e)}")
            return None
    
    def _suggest_meeting_preparation(self, event_details: Dict[str, Any]) -> List[str]:
        """Generate suggested to-dos for meeting preparation"""
        try:
            if not self.ai_config.SUGGESTION_MODE:
                return []
            
            # Check if client is properly initialized
            if not self.openai_client:
                logger.error("OpenAI client not initialized. Cannot suggest meeting preparation.")
                return []
                
            response = self.openai_client.chat.completions.create(
                model=self.ai_config.MODEL,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": "You are an assistant that suggests preparation tasks for meetings."},
                    {"role": "user", "content": f"Suggest 3 preparation tasks for this meeting: {json.dumps(event_details)}"}
                ],
                functions=[{
                    "name": "suggest_preparation_tasks",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of preparation tasks"
                            }
                        },
                        "required": ["tasks"]
                    }
                }],
                function_call={"name": "suggest_preparation_tasks"}
            )
            
            return json.loads(response.choices[0].message.function_call.arguments)['tasks']
        except Exception as e:
            logger.error(f"Error suggesting meeting preparation: {str(e)}")
            return []
            
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def process_edit_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Process natural language commands to edit a calendar event"""
        try:
            # Check if client is properly initialized
            if not self.openai_client:
                raise ValueError("OpenAI client not initialized. Check your API key.")
                
            response = self.openai_client.chat.completions.create(
                model=self.ai_config.MODEL,
                temperature=self.ai_config.TEMPERATURE,
                messages=[
                    {"role": "system", "content": """You are a calendar editing assistant. 
                     Convert user edit requests into structured modifications.
                     Identify the event by its title or key terms and specify the changes needed.
                     If the user is trying to move an event, capture both the event identifier 
                     and the new date/time details precisely."""},
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
                                "description": "New date if changing (YYYY-MM-DD format)"
                            },
                            "new_time": {
                                "type": "string",
                                "description": "New time if changing (HH:MM format)"
                            },
                            "new_duration": {
                                "type": "integer",
                                "description": "New duration in minutes if changing"
                            },
                            "new_title": {
                                "type": "string",
                                "description": "New title if changing"
                            },
                            "new_description": {
                                "type": "string",
                                "description": "New description if changing"
                            },
                            "new_location": {
                                "type": "string",
                                "description": "New location if changing"
                            },
                            "add_attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Attendees to add to the event"
                            },
                            "remove_attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Attendees to remove from the event"
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
            logger.error(f"Error processing edit request: {str(e)}")
            st.error(f"Error processing edit request: {str(e)}")
            return None

    def suggest_optimal_meeting_time(self, attendees: List[Dict[str, Any]], 
                               duration: int, priority: str = "earliest") -> List[Dict[str, Any]]:
        """Suggest optimal meeting times based on attendees' availability"""
        try:
            # This is a placeholder. In a real implementation, you'd:
            # 1. Query each attendee's calendar for availability
            # 2. Find common free time slots
            # 3. Rank according to the priority (earliest, latest, most convenient)
            
            # For now, we'll return some dummy suggestions
            now = datetime.now(self.timezone)
            suggestions = []
            
            for i in range(3):
                suggestion_time = now.replace(hour=9+i, minute=0, second=0, microsecond=0) + timedelta(days=1)
                if suggestion_time.weekday() >= 5:  # Skip weekends
                    suggestion_time += timedelta(days=7-suggestion_time.weekday())
                
                suggestions.append({
                    "start": suggestion_time.isoformat(),
                    "end": (suggestion_time + timedelta(minutes=duration)).isoformat(),
                    "confidence": 0.9 - (i * 0.2)
                })
                
            return suggestions
        except Exception as e:
            logger.error(f"Error suggesting meeting times: {str(e)}")
            return []
            
    def generate_event_summary(self, event_details: Dict[str, Any]) -> str:
        """Generate a human-friendly summary of an event"""
        try:
            # Format the datetime in a readable format
            date_obj = datetime.strptime(event_details['date'], '%Y-%m-%d')
            date_str = date_obj.strftime('%A, %B %d, %Y')
            
            # Handle 24-hour time format
            time_obj = datetime.strptime(event_details['time'], '%H:%M')
            time_str = time_obj.strftime('%I:%M %p').lstrip('0')
            
            # Calculate end time
            start_datetime = datetime.strptime(f"{event_details['date']} {event_details['time']}", '%Y-%m-%d %H:%M')
            end_datetime = start_datetime + timedelta(minutes=event_details['duration'])
            end_time_str = end_datetime.strftime('%I:%M %p').lstrip('0')
            
            # Build the summary
            summary = f"{event_details['title']} on {date_str} from {time_str} to {end_time_str}"
            
            if event_details.get('location'):
                summary += f" at {event_details['location']}"
                
            if event_details.get('attendees') and len(event_details['attendees']) > 0:
                attendees_str = ', '.join(event_details['attendees'])
                summary += f" with {attendees_str}"
                
            if event_details.get('is_recurring', False):
                pattern = event_details.get('recurrence_pattern', 'WEEKLY').lower()
                summary += f", recurring {pattern}"
                
            return summary
        except KeyError as e:
            logger.error(f"Missing key in event details: {str(e)}")
            return "Event details incomplete"
        except Exception as e:
            logger.error(f"Error generating event summary: {str(e)}")
            return "Error generating summary"
            
    def analyze_free_time(self, events: List[Dict[str, Any]], 
                          start_date: datetime, end_date: datetime,
                          min_duration: int = 30) -> List[Dict[str, Any]]:
        """Find available free time blocks in a calendar"""
        try:
            # Convert events to a list of busy periods
            busy_periods = []
            for event in events:
                if 'start' in event and 'end' in event:
                    start = event['start'].get('dateTime')
                    end = event['end'].get('dateTime')
                    if start and end:
                        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                        busy_periods.append((start_dt, end_dt))
            
            # Sort busy periods
            busy_periods.sort()
            
            # Find free periods
            free_periods = []
            current_time = max(start_date, datetime.now(self.timezone))
            
            for start_busy, end_busy in busy_periods:
                if current_time < start_busy:
                    duration_mins = (start_busy - current_time).total_seconds() / 60
                    if duration_mins >= min_duration:
                        free_periods.append({
                            "start": current_time.isoformat(),
                            "end": start_busy.isoformat(),
                            "duration_minutes": duration_mins
                        })
                current_time = max(current_time, end_busy)
            
            # Add final free period if needed
            if current_time < end_date:
                duration_mins = (end_date - current_time).total_seconds() / 60
                if duration_mins >= min_duration:
                    free_periods.append({
                        "start": current_time.isoformat(),
                        "end": end_date.isoformat(),
                        "duration_minutes": duration_mins
                    })
            
            return free_periods
        except Exception as e:
            logger.error(f"Error analyzing free time: {str(e)}")
            return []
