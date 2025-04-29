# File: calendar_service.py

import streamlit as st
from datetime import datetime, timedelta
import pytz
import re
import json
import time
import base64
from io import BytesIO
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from auth_manager import GoogleAuthManager
from event_processor import EventProcessor
from config import CalendarConfig, AppConfig, RecurrenceFrequency
from typing import Dict, List, Any, Optional, Union, Tuple
import logging
from utils import create_ical_event, send_notification, analyze_calendar_habits

# Configure logging
logger = logging.getLogger(__name__)

class EventStatus(str):
    """Event status constants"""
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"

class CalendarError(Exception):
    """Custom exception for calendar-related errors"""
    pass

class CalendarManager:
    def __init__(self, config: Optional[CalendarConfig] = None) -> None:
        """Initialize the calendar manager with optional configuration"""
        try:
            self.app_config = AppConfig()
            self.config = config or self.app_config.CALENDAR_CONFIG
            self.timezone = pytz.timezone(self.config.TIMEZONE)
            self.auth_manager = GoogleAuthManager(self.config)
            self.creds = self.auth_manager.get_credentials()
            self.service = build('calendar', 'v3', credentials=self.creds)
            self.event_processor = EventProcessor(self.config.TIMEZONE)
            
            # Cache for frequently accessed data
            self._calendars_cache = None
            self._calendars_cache_expiry = 0
            self._categories_cache = self.app_config.EVENT_CATEGORIES
            
            logger.info("CalendarManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CalendarManager: {str(e)}")
            raise CalendarError(f"Failed to initialize calendar service: {str(e)}")

    def process_user_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Process a natural language command to create an event"""
        try:
            return self.event_processor.process_create_command(user_input)
        except Exception as e:
            logger.error(f"Error processing user command: {str(e)}")
            raise CalendarError(f"Failed to process command: {str(e)}")

    def get_available_calendars(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get list of available calendars for the user"""
        try:
            # Use cached data if available and not expired
            current_time = time.time()
            if not force_refresh and self._calendars_cache and current_time < self._calendars_cache_expiry:
                return self._calendars_cache
                
            # Fetch calendars from API
            calendars_result = self.service.calendarList().list().execute()
            calendars = calendars_result.get('items', [])
            
            # Update cache
            self._calendars_cache = calendars
            self._calendars_cache_expiry = current_time + 3600  # Cache for 1 hour
            
            return calendars
        except HttpError as e:
            logger.error(f"Google Calendar API error: {str(e)}")
            raise CalendarError(f"Failed to get calendars: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting calendars: {str(e)}")
            raise CalendarError(f"An unexpected error occurred: {str(e)}")

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
                raise CalendarError("Could not parse date and time format")

            # Convert to timezone-aware datetime
            start_datetime = self.timezone.localize(start_datetime)
            end_datetime = start_datetime + timedelta(minutes=event_details['duration'])

            # Create event body
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
                'status': EventStatus.CONFIRMED,
            }
            
            # Add location if provided
            if 'location' in event_details and event_details['location']:
                event['location'] = event_details['location']
            
            # Add attendees if provided
            if 'attendees' in event_details and event_details['attendees']:
                event['attendees'] = [{'email': attendee} for attendee in event_details['attendees'] 
                                     if '@' in attendee]
            
            # Add reminders if specified
            if 'reminder_minutes' in event_details:
                event['reminders'] = {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': event_details['reminder_minutes']}
                    ]
                }
            
            # Add transparency (affects busy/free status)
            if event_details.get('category', '').lower() in ['personal', 'social']:
                event['transparency'] = 'transparent'  # Doesn't block time on calendar
            else:
                event['transparency'] = 'opaque'  # Default - blocks time on calendar
                
            # Add visibility
            if event_details.get('private', False):
                event['visibility'] = 'private'
            else:
                event['visibility'] = 'default'

            # Add recurrence if specified
            if event_details.get('is_recurring', False):
                recurrence_pattern = event_details.get('recurrence_pattern', 'WEEKLY')
                try:
                    frequency = RecurrenceFrequency[recurrence_pattern]
                    recurrence = self._create_recurrence_rule(
                        frequency,
                        event_details.get('recurrence_count', 10),  # Default to 10 occurrences
                        event_details.get('recurrence_interval', 1)  # Default interval is 1
                    )
                    event['recurrence'] = [recurrence]
                except (KeyError, ValueError):
                    logger.warning(f"Invalid recurrence pattern: {recurrence_pattern}")

            # Add category as extended property
            if 'category' in event_details:
                event['extendedProperties'] = {
                    'private': {'category': event_details['category']}
                }

            # Create the event
            calendar_id = event_details.get('calendar_id', 'primary')
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendUpdates='all' if event.get('attendees') else 'none'
            ).execute()
            
            event_id = created_event['id']
            created_time = created_event['created']
            
            # Generate human-readable summary
            summary = self.event_processor.generate_event_summary(event_details)
            
            # Send SMS notification if configured
            if self.app_config.TWILIO_CONFIG.ENABLED and event_details.get('send_sms', False) and event_details.get('phone_number'):
                notification_result = send_notification(
                    event_details['phone_number'],
                    f"New event: {summary}"
                )
                if notification_result.get('status') == 'success':
                    logger.info(f"SMS notification sent for event: {event_details['title']}")
            
            logger.info(f"Successfully added event: {event_details['title']} (ID: {event_id})")
            return f"Event '{event_details['title']}' has been added to your calendar"

        except HttpError as e:
            logger.error(f"Google Calendar API error: {str(e)}")
            raise CalendarError(f"Failed to add event to calendar: {str(e)}")
        except Exception as e:
            logger.error(f"Error adding event to calendar: {str(e)}")
            raise CalendarError(f"An unexpected error occurred: {str(e)}")

    def _create_recurrence_rule(self, frequency: RecurrenceFrequency, count: int, interval: int) -> str:
        """Create an RRULE string for recurring events"""
        return f"RRULE:FREQ={frequency.value};COUNT={count};INTERVAL={interval}"

    def get_event_categories(self) -> List[str]:
        """Get list of available event categories"""
        return self._categories_cache
        
    def add_custom_category(self, category_name: str) -> bool:
        """Add a custom category to the list of available categories"""
        if category_name not in self._categories_cache:
            self._categories_cache.append(category_name)
            return True
        return False

    def add_event_category(self, event_id: str, category: str) -> str:
        """Add a category to an existing event"""
        try:
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()

            # Add category to extended properties
            if 'extendedProperties' not in event:
                event['extendedProperties'] = {'private': {}}
            elif 'private' not in event['extendedProperties']:
                event['extendedProperties']['private'] = {}
                
            event['extendedProperties']['private']['category'] = category
            
            # Also add category to description for compatibility
            if 'description' not in event:
                event['description'] = ''
            
            # Remove any existing category line
            description_lines = event['description'].split('\n')
            filtered_lines = [line for line in description_lines if not line.startswith('Category:')]
            filtered_description = '\n'.join(filtered_lines)
            
            # Add new category line
            event['description'] = filtered_description + f"\nCategory: {category}"
            
            # Update event
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event
            ).execute()

            logger.info(f"Added category '{category}' to event: {event['summary']}")
            return f"Category '{category}' added to event: {event['summary']}"

        except HttpError as e:
            logger.error(f"Google Calendar API error: {str(e)}")
            raise CalendarError(f"Failed to add category: {str(e)}")
        except Exception as e:
            logger.error(f"Error adding category: {str(e)}")
            raise CalendarError(f"An unexpected error occurred: {str(e)}")
            
    def get_calendar_stats(self, start_date: Optional[datetime] = None, 
                         end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Get statistics about calendar usage"""
        try:
            if not start_date:
                start_date = datetime.now(self.timezone) - timedelta(days=30)  # Last 30 days
            if not end_date:
                end_date = datetime.now(self.timezone) + timedelta(days=30)  # Next 30 days
                
            events = self.get_events_in_range(start_date, end_date)
            stats = analyze_calendar_habits(events)
            
            return stats
        except Exception as e:
            logger.error(f"Error getting calendar stats: {str(e)}")
            return {"status": "error", "error": str(e)}
            
    def get_events_in_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get all events within a specified date range"""
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_date.isoformat(),
                timeMax=end_date.isoformat(),
                maxResults=250,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            return events_result.get('items', [])
        except Exception as e:
            logger.error(f"Error getting events in range: {str(e)}")
            return []
            
    def get_ical_download(self, event_details: Dict[str, Any]) -> Tuple[bytes, str]:
        """Generate an iCalendar file for the event that can be downloaded"""
        try:
            ical_data = create_ical_event(event_details)
            filename = f"{event_details['title'].replace(' ', '_')}.ics"
            
            return ical_data, filename
        except Exception as e:
            logger.error(f"Error generating iCal file: {str(e)}")
            raise CalendarError(f"Failed to generate iCal file: {str(e)}")
            
    def get_free_busy_times(self, attendees: List[str], start_time: datetime, 
                          end_time: datetime) -> Dict[str, Any]:
        """Get free/busy information for a list of attendees"""
        try:
            if not attendees:
                return {"status": "error", "error": "No attendees provided"}
                
            # Ensure all email addresses are valid
            valid_attendees = []
            for attendee in attendees:
                if '@' in attendee:  # Very basic email validation
                    valid_attendees.append({"id": attendee})
                    
            if not valid_attendees:
                return {"status": "error", "error": "No valid email addresses provided"}
                
            # Format timestamps
            start_time_str = start_time.isoformat()
            end_time_str = end_time.isoformat()
            
            # Make the API request
            query = {
                "timeMin": start_time_str,
                "timeMax": end_time_str,
                "timeZone": self.config.TIMEZONE,
                "items": valid_attendees
            }
            
            response = self.service.freebusy().query(body=query).execute()
            
            # Process the response
            calendars = response.get('calendars', {})
            result = {
                "status": "success",
                "query_time": response.get('kind', ''),
                "attendees": {}
            }
            
            for email, data in calendars.items():
                busy_times = data.get('busy', [])
                result["attendees"][email] = {
                    "busy": busy_times,
                    "errors": data.get('errors', [])
                }
                
            return result
        except Exception as e:
            logger.error(f"Error getting free/busy times: {str(e)}")
            return {"status": "error", "error": str(e)}

    def search_events(self, query: str, start_date: Optional[datetime] = None, 
                     end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Search for events matching the query within a date range"""
        try:
            # Set default date range if not provided
            if not start_date:
                start_date = datetime.now(self.timezone)
            if not end_date:
                end_date = start_date + timedelta(days=30)

            # Get events from the specified date range
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_date.isoformat(),
                timeMax=end_date.isoformat(),
                maxResults=50,
                singleEvents=True,
                orderBy='startTime',
                q=query
            ).execute()

            events = events_result.get('items', [])
            return events

        except HttpError as e:
            logger.error(f"Google Calendar API error: {str(e)}")
            raise CalendarError(f"Failed to search events: {str(e)}")
        except Exception as e:
            logger.error(f"Error searching events: {str(e)}")
            raise CalendarError(f"An unexpected error occurred: {str(e)}")

    def process_edit_command(self, user_input: str) -> str:
        """Process a natural language command to edit an event"""
        try:
            # Get edit details from natural language processor
            edit_details = self.event_processor.process_edit_command(user_input)
            if not edit_details:
                return "Could not understand the edit request. Please try again."
                
            # Find matching events
            search_terms = edit_details['search_terms']
            matching_events = self._find_matching_events(search_terms)
            
            if not matching_events:
                return f"No events found matching '{search_terms}'"
                
            # If multiple matches, use the first one
            # In a real application, you might want to ask the user to choose
            event = matching_events[0]
            event_id = event['id']
            event_summary = event['summary']
            
            # Apply edits based on action type
            if edit_details['action'] == 'cancel':
                result = self.cancel_event(event_id)
                return f"Cancelled event: {event_summary}"
                
            elif edit_details['action'] == 'reschedule':
                # Check if we have new date or time
                updates = {}
                
                if 'new_date' in edit_details or 'new_time' in edit_details:
                    # Get current start time
                    start_dt = self._parse_event_datetime(event['start'])
                    
                    # Apply new date if provided
                    if 'new_date' in edit_details:
                        new_date = datetime.strptime(edit_details['new_date'], '%Y-%m-%d').date()
                        start_dt = start_dt.replace(year=new_date.year, month=new_date.month, day=new_date.day)
                        
                    # Apply new time if provided
                    if 'new_time' in edit_details:
                        new_time = datetime.strptime(edit_details['new_time'], '%H:%M').time()
                        start_dt = start_dt.replace(hour=new_time.hour, minute=new_time.minute)
                        
                    # Calculate new end time based on duration
                    if 'new_duration' in edit_details:
                        duration = edit_details['new_duration']
                    else:
                        # Calculate existing duration
                        end_dt = self._parse_event_datetime(event['end'])
                        duration = int((end_dt - start_dt).total_seconds() / 60)
                        
                    end_dt = start_dt + timedelta(minutes=duration)
                    
                    # Add to updates
                    updates['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': self.config.TIMEZONE}
                    updates['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': self.config.TIMEZONE}
                
                # Other updates
                if 'new_title' in edit_details:
                    updates['summary'] = edit_details['new_title']
                    
                if 'new_description' in edit_details:
                    updates['description'] = edit_details['new_description']
                    
                if 'new_location' in edit_details:
                    updates['location'] = edit_details['new_location']
                
                # Apply the updates
                self.update_event(event_id, updates)
                
                # Handle attendee changes
                if 'add_attendees' in edit_details and edit_details['add_attendees']:
                    self.add_attendees_to_event(event_id, edit_details['add_attendees'])
                    
                if 'remove_attendees' in edit_details and edit_details['remove_attendees']:
                    self.remove_attendees_from_event(event_id, edit_details['remove_attendees'])
                    
                return f"Successfully updated event: {event_summary}"
                
            elif edit_details['action'] == 'modify':
                # Handle other modifications
                updates = {}
                
                if 'new_title' in edit_details:
                    updates['summary'] = edit_details['new_title']
                    
                if 'new_description' in edit_details:
                    updates['description'] = edit_details['new_description']
                    
                if 'new_location' in edit_details:
                    updates['location'] = edit_details['new_location']
                    
                # Apply the updates
                if updates:
                    self.update_event(event_id, updates)
                    
                # Handle attendee changes
                if 'add_attendees' in edit_details and edit_details['add_attendees']:
                    self.add_attendees_to_event(event_id, edit_details['add_attendees'])
                    
                if 'remove_attendees' in edit_details and edit_details['remove_attendees']:
                    self.remove_attendees_from_event(event_id, edit_details['remove_attendees'])
                    
                return f"Successfully modified event: {event_summary}"
                
            else:
                return f"Unsupported action: {edit_details['action']}"
                
        except Exception as e:
            logger.error(f"Error processing edit command: {str(e)}")
            return f"An error occurred while processing your request: {str(e)}"
            
    def update_event(self, event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an event with the specified changes"""
        try:
            # First get the current event
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            # Apply updates
            for key, value in updates.items():
                event[key] = value
                
            # Save the changes
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendUpdates='all' if event.get('attendees') else 'none'
            ).execute()
            
            logger.info(f"Successfully updated event: {event.get('summary', '')}")
            return updated_event
        except Exception as e:
            logger.error(f"Error updating event: {str(e)}")
            raise CalendarError(f"Failed to update event: {str(e)}")
            
    def cancel_event(self, event_id: str) -> Dict[str, Any]:
        """Cancel (delete) an event"""
        try:
            cancelled_event = self.service.events().delete(
                calendarId='primary',
                eventId=event_id,
                sendUpdates='all'
            ).execute()
            
            logger.info(f"Successfully cancelled event with ID: {event_id}")
            return cancelled_event
        except Exception as e:
            logger.error(f"Error cancelling event: {str(e)}")
            raise CalendarError(f"Failed to cancel event: {str(e)}")
            
    def add_attendees_to_event(self, event_id: str, attendees: List[str]) -> Dict[str, Any]:
        """Add attendees to an existing event"""
        try:
            # Get the current event
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            # Prepare attendees list
            current_attendees = event.get('attendees', [])
            current_emails = {attendee.get('email') for attendee in current_attendees}
            
            # Add new attendees that aren't already in the list
            for attendee in attendees:
                if '@' in attendee and attendee not in current_emails:
                    current_attendees.append({'email': attendee})
                    
            # Update the event
            event['attendees'] = current_attendees
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendUpdates='all'
            ).execute()
            
            logger.info(f"Added attendees to event: {event.get('summary', '')}")
            return updated_event
        except Exception as e:
            logger.error(f"Error adding attendees: {str(e)}")
            raise CalendarError(f"Failed to add attendees: {str(e)}")
            
    def remove_attendees_from_event(self, event_id: str, attendees: List[str]) -> Dict[str, Any]:
        """Remove attendees from an existing event"""
        try:
            # Get the current event
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            # Prepare attendees list
            current_attendees = event.get('attendees', [])
            
            # Remove specified attendees
            updated_attendees = [
                attendee for attendee in current_attendees
                if attendee.get('email') not in attendees
            ]
            
            # Update the event
            event['attendees'] = updated_attendees
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendUpdates='all'
            ).execute()
            
            logger.info(f"Removed attendees from event: {event.get('summary', '')}")
            return updated_event
        except Exception as e:
            logger.error(f"Error removing attendees: {str(e)}")
            raise CalendarError(f"Failed to remove attendees: {str(e)}")
            
    def suggest_optimal_meeting_time(self, attendees: List[str], 
                                   duration_minutes: int, 
                                   start_date: Optional[datetime] = None,
                                   end_date: Optional[datetime] = None,
                                   working_hours: Optional[Tuple[int, int]] = None) -> List[Dict[str, Any]]:
        """Find optimal meeting times based on attendees' availability"""
        try:
            if not attendees:
                return []
                
            # Set default dates if not provided
            if not start_date:
                start_date = datetime.now(self.timezone)
            if not end_date:
                end_date = start_date + timedelta(days=7)
                
            # Set default working hours if not provided (9 AM to 5 PM)
            if not working_hours:
                working_hours = (9, 17)
                
            # Get free/busy information for all attendees
            free_busy_info = self.get_free_busy_times(attendees, start_date, end_date)
            
            if free_busy_info.get('status') != 'success':
                logger.error(f"Error getting free/busy info: {free_busy_info.get('error', 'Unknown error')}")
                return []
                
            # Find available slots
            busy_periods = []
            for email, data in free_busy_info.get('attendees', {}).items():
                for busy_time in data.get('busy', []):
                    start = datetime.fromisoformat(busy_time['start'].replace('Z', '+00:00'))
                    end = datetime.fromisoformat(busy_time['end'].replace('Z', '+00:00'))
                    busy_periods.append((start, end))
                    
            # Sort busy periods
            busy_periods.sort()
            
            # Find free periods that are at least as long as the requested duration
            suggestions = []
            current_date = start_date
            
            # Iterate through each day in the range
            while current_date.date() <= end_date.date():
                # Only consider working hours
                day_start = current_date.replace(hour=working_hours[0], minute=0, second=0, microsecond=0)
                day_end = current_date.replace(hour=working_hours[1], minute=0, second=0, microsecond=0)
                
                # If we're looking at the current day and it's already past the start of working hours,
                # adjust day_start to be the current time
                if current_date.date() == datetime.now(self.timezone).date() and datetime.now(self.timezone).hour >= working_hours[0]:
                    day_start = max(day_start, datetime.now(self.timezone).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                
                # Skip if we're already past working hours for the day
                if day_start >= day_end:
                    current_date = current_date + timedelta(days=1)
                    continue
                    
                # Skip weekends (Saturday=5, Sunday=6)
                if current_date.weekday() >= 5:
                    current_date = current_date + timedelta(days=1)
                    continue
                
                # Find free slots in this day
                free_slots = self._find_free_slots(busy_periods, day_start, day_end, duration_minutes)
                suggestions.extend(free_slots)
                
                # Move to next day
                current_date = current_date + timedelta(days=1)
                
            # Return the top suggestions
            return suggestions[:5]  # Limit to 5 suggestions
        except Exception as e:
            logger.error(f"Error suggesting optimal meeting time: {str(e)}")
            return []
            
    def _find_free_slots(self, busy_periods: List[Tuple[datetime, datetime]], 
                        day_start: datetime, day_end: datetime, 
                        duration_minutes: int) -> List[Dict[str, Any]]:
        """Find free time slots in a day given busy periods"""
        free_slots = []
        current_time = day_start
        
        # Filter busy periods to those that overlap with our day
        relevant_busy = [
            (max(start, day_start), min(end, day_end)) 
            for start, end in busy_periods
            if start < day_end and end > day_start
        ]
        
        # Sort by start time
        relevant_busy.sort()
        
        # Find free slots
        for start_busy, end_busy in relevant_busy:
            if current_time < start_busy:
                free_duration = (start_busy - current_time).total_seconds() / 60
                if free_duration >= duration_minutes:
                    free_slots.append({
                        "start": current_time.isoformat(),
                        "end": (current_time + timedelta(minutes=duration_minutes)).isoformat(),
                        "confidence": 0.9
                    })
            current_time = max(current_time, end_busy)
            
        # Add final free slot if needed
        if current_time < day_end:
            free_duration = (day_end - current_time).total_seconds() / 60
            if free_duration >= duration_minutes:
                free_slots.append({
                    "start": current_time.isoformat(),
                    "end": (current_time + timedelta(minutes=duration_minutes)).isoformat(),
                    "confidence": 0.9
                })
                
        return free_slots
    
    def _parse_event_datetime(self, datetime_obj: Dict[str, str]) -> datetime:
        """Parse an event datetime object to a Python datetime"""
        if 'dateTime' in datetime_obj:
            dt_str = datetime_obj['dateTime']
            # Handle various formats including those with Z or timezone offsets
            if dt_str.endswith('Z'):
                dt = datetime.fromisoformat(dt_str[:-1])
                dt = dt.replace(tzinfo=pytz.UTC)
                return dt.astimezone(self.timezone)
            else:
                return datetime.fromisoformat(dt_str)
        elif 'date' in datetime_obj:
            # All-day event
            return datetime.strptime(datetime_obj['date'], '%Y-%m-%d')
        else:
            raise ValueError("Invalid datetime object format")

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