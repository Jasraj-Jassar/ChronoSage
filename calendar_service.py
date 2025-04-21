# File: calendar_service.py

import streamlit as st
from datetime import datetime, timedelta
import pytz
import re
from googleapiclient.discovery import build
from auth_manager import GoogleAuthManager
from event_processor import EventProcessor
from config import CalendarConfig, AppConfig
from typing import Dict, List, Any, Optional

class CalendarManager:
    def __init__(self, config: CalendarConfig = None):
        """Initialize the calendar manager with optional configuration"""
        self.config = config or CalendarConfig()
        self.timezone = pytz.timezone(self.config.TIMEZONE)
        self.auth_manager = GoogleAuthManager(self.config)
        self.creds = self.auth_manager.get_credentials()
        self.service = build('calendar', 'v3', credentials=self.creds)
        self.event_processor = EventProcessor(self.config.TIMEZONE)

    def process_user_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Process a natural language command to create an event"""
        return self.event_processor.process_create_command(user_input)

    def add_to_calendar(self, event_details: Dict[str, Any]) -> str:
        """Add an event to the calendar with the provided details"""
        try:
            # Parse date and time
            date_str = event_details['date']
            time_str = event_details['time']
            
            # Combine date and time
            datetime_str = f"{date_str} {time_str}"
            
            # Try different formats to handle various inputs
            formats = ['%Y-%m-%d %H:%M', '%Y-%m-%d %I:%M %p']
            start_datetime = None
            
            for fmt in formats:
                try:
                    start_datetime = datetime.strptime(datetime_str, fmt)
                    break
                except ValueError:
                    continue
            
            if not start_datetime:
                return "Error: Could not parse date and time format."
            
            # Localize the datetime to MST
            start_datetime = self.timezone.localize(start_datetime)
            
            # Calculate end time
            end_datetime = start_datetime + timedelta(minutes=int(event_details['duration']))
            
            # Create event
            event = {
                'summary': event_details['title'],
                'description': event_details.get('description', ''),
                'start': {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': self.config.TIMEZONE,
                },
                'end': {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': self.config.TIMEZONE,
                },
                'reminders': {
                    'useDefault': True,
                },
            }
            
            event = self.service.events().insert(calendarId='primary', body=event).execute()
            
            return f"Event created successfully! View it here: {event.get('htmlLink')}"
            
        except Exception as e:
            return f"Failed to create event: {str(e)}"

    def process_edit_command(self, user_input: str) -> str:
        """Process a natural language command to edit an event"""
        edit_details = self.event_processor.process_edit_command(user_input)
        
        if not edit_details:
            return "Failed to process edit request"
        
        # Find matching events
        events = self._find_matching_events(edit_details['search_terms'])
        
        if not events:
            return "No matching events found."

        # If multiple events found, let user select
        if len(events) > 1:
            st.write("Multiple matching events found:")
            for i, event in enumerate(events):
                start = datetime.fromisoformat(event['start'].get('dateTime')).astimezone(self.timezone)
                st.write(f"{i+1}. {event['summary']} on {start.strftime('%B %d at %I:%M %p')}")
            
            event_index = st.selectbox(
                "Select the event to modify:",
                range(len(events)),
                format_func=lambda x: f"Event {x+1}"
            )
            selected_event = events[event_index]
        else:
            selected_event = events[0]

        # Handle cancellation
        if edit_details['action'] == 'cancel':
            self.service.events().delete(
                calendarId='primary',
                eventId=selected_event['id']
            ).execute()
            return f"Successfully cancelled: {selected_event['summary']}"

        # Handle rescheduling/modification
        event = selected_event
        start_time = datetime.fromisoformat(event['start']['dateTime'])
        
        # Update title if provided
        if edit_details.get('new_title'):
            event['summary'] = edit_details['new_title']
        
        # Update event details based on edit_details
        if edit_details.get('new_date') or edit_details.get('new_time'):
            new_start = start_time
            
            if edit_details.get('new_date'):
                new_date = datetime.strptime(edit_details['new_date'], '%Y-%m-%d').date()
                new_start = new_start.replace(year=new_date.year, 
                                            month=new_date.month, 
                                            day=new_date.day)
            
            if edit_details.get('new_time'):
                new_time = datetime.strptime(edit_details['new_time'], '%H:%M').time()
                new_start = new_start.replace(hour=new_time.hour, 
                                            minute=new_time.minute)
            
            # Calculate duration
            old_duration = (datetime.fromisoformat(event['end']['dateTime']) - 
                          datetime.fromisoformat(event['start']['dateTime'])).total_seconds() / 60
            duration = edit_details.get('new_duration', old_duration)
            
            # Update times
            new_start = self.timezone.localize(new_start)
            new_end = new_start + timedelta(minutes=int(duration))
            
            event['start']['dateTime'] = new_start.isoformat()
            event['end']['dateTime'] = new_end.isoformat()

        # Update event
        updated_event = self.service.events().update(
            calendarId='primary',
            eventId=event['id'],
            body=event
        ).execute()
        
        return f"Event updated successfully! View it here: {updated_event.get('htmlLink')}"

    def _find_matching_events(self, search_terms: str, max_results: int = 5):
        """Find events matching the search terms"""
        try:
            # Get events from the next 30 days
            time_min = datetime.now(self.timezone).isoformat()
            time_max = (datetime.now(self.timezone) + timedelta(days=30)).isoformat()
            
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results * 2,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Create search pattern from terms
            search_pattern = re.compile(search_terms, re.IGNORECASE)
            
            # Filter events matching search terms
            matching_events = [
                event for event in events
                if search_pattern.search(event.get('summary', '')) 
                or search_pattern.search(event.get('description', ''))
            ]
            
            return matching_events[:max_results]
            
        except Exception as e:
            st.error(f"Error finding events: {str(e)}")
            return []

    def get_upcoming_events(self, max_results: int = 10) -> List[str]:
        """Get a list of upcoming events formatted for display"""
        try:
            now = datetime.now(self.timezone).isoformat()
            future = (datetime.now(self.timezone) + timedelta(days=30)).isoformat()
            
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=future,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return []
                
            # Format events for display
            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                start_dt = datetime.fromisoformat(start).astimezone(self.timezone)
                
                formatted_start = start_dt.strftime('%I:%M %p on %B %d, %Y')
                formatted_events.append(f"{event['summary']} at {formatted_start}")
                
            return formatted_events
            
        except Exception as e:
            st.error(f"Error retrieving events: {str(e)}")
            return []