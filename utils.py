import logging
import re
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import geocoder
import pandas as pd
import pyshorteners
import requests
from icalendar import Alarm, Calendar, Event as ICalEvent
from PIL import Image
from twilio.rest import Client

from config import AppConfig

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
WEATHER_FORECAST_DAYS = 7

def _parse_event_datetime(date: str, time: str) -> Optional[datetime]:
    """Parse event date/time in the expected format."""
    try:
        return datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None

def get_user_location() -> Tuple[Optional[float], Optional[float]]:
    """Attempt to get the user's current location based on IP"""
    try:
        g = geocoder.ip('me')
        if g.ok:
            return g.lat, g.lng
        return None, None
    except Exception as e:
        logger.error(f"Error getting user location: {str(e)}")
        return None, None

def get_weather_for_event(date: str, time: str, location: Optional[str] = None) -> Dict[str, Any]:
    """Get weather forecast for the event date, time and location"""
    config = AppConfig().WEATHER_CONFIG
    if not config.ENABLED or not config.API_KEY:
        return {"status": "disabled"}
    
    try:
        # Parse date and time
        event_datetime = _parse_event_datetime(date, time)
        if not event_datetime:
            return {"status": "invalid_datetime"}
        now = datetime.now()
        
        # Check if event is within the forecast window (typically 7 days)
        if (event_datetime - now).days > WEATHER_FORECAST_DAYS:
            return {"status": "too_far_ahead"}
        
        # Determine location
        lat, lng = None, None
        if location:
            g = geocoder.osm(location)
            if g.ok:
                lat, lng = g.lat, g.lng
        
        if lat is None or lng is None:
            lat, lng = get_user_location()
            
        if lat is None or lng is None:
            return {"status": "no_location"}
            
        # Call weather API
        url = f"https://api.openweathermap.org/data/2.5/forecast"
        params = {
            "lat": lat,
            "lon": lng,
            "appid": config.API_KEY,
            "units": config.UNITS
        }
        
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as e:
            return {"status": "api_error", "error": str(e)}
            
        data = response.json()
        
        # Find the forecast closest to the event time
        forecasts = data.get("list", [])
        closest_forecast = None
        min_diff = float('inf')
        
        for forecast in forecasts:
            forecast_time = datetime.fromtimestamp(forecast["dt"])
            diff = abs((forecast_time - event_datetime).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest_forecast = forecast
                
        if not closest_forecast:
            return {"status": "no_forecast"}
            
        # Format response
        weather = closest_forecast["weather"][0]
        temp = closest_forecast["main"]["temp"]
        
        return {
            "status": "success",
            "description": weather["description"],
            "icon": weather["icon"],
            "temperature": temp,
            "units": config.UNITS,
            "precipitation": closest_forecast.get("pop", 0) * 100,  # Probability of precipitation
            "humidity": closest_forecast["main"]["humidity"],
            "wind_speed": closest_forecast["wind"]["speed"]
        }
    except Exception as e:
        logger.error(f"Error getting weather: {str(e)}")
        return {"status": "error", "error": str(e)}

def send_notification(phone: str, message: str) -> Dict[str, Any]:
    """Send SMS notification via Twilio"""
    config = AppConfig().TWILIO_CONFIG
    if not config.ENABLED or not all([config.ACCOUNT_SID, config.AUTH_TOKEN, config.FROM_NUMBER]):
        return {"status": "disabled"}
    
    try:
        client = Client(config.ACCOUNT_SID, config.AUTH_TOKEN)
        twilio_message = client.messages.create(
            body=message,
            from_=config.FROM_NUMBER,
            to=phone
        )
        return {"status": "success", "sid": twilio_message.sid}
    except Exception as e:
        logger.error(f"Error sending SMS notification: {str(e)}")
        return {"status": "error", "error": str(e)}

def create_ical_event(event_details: Dict[str, Any]) -> bytes:
    """Create an iCalendar file for the event"""
    try:
        cal = Calendar()
        cal.add('prodid', '-//ChronoSage//EN')
        cal.add('version', '2.0')
        
        event = ICalEvent()
        event.add('summary', event_details['title'])
        
        # Parse date and time
        date_str = event_details['date']
        time_str = event_details['time']
        start_datetime = _parse_event_datetime(date_str, time_str)
        if not start_datetime:
            raise ValueError("Invalid date/time format for iCal event.")
        
        # Add timezone information
        config = AppConfig()
        timezone = config.get_timezone_obj()
        start_datetime = timezone.localize(start_datetime)
        
        # Calculate end time
        duration_minutes = int(event_details['duration'])
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        
        event.add('dtstart', start_datetime)
        event.add('dtend', end_datetime)
        
        if 'description' in event_details:
            event.add('description', event_details['description'])
            
        # Add location if available
        if 'location' in event_details:
            event.add('location', event_details['location'])
            
        # Add organizer if available
        if 'organizer' in event_details:
            event.add('organizer', event_details['organizer'])
            
        # Add categories if available
        if 'category' in event_details:
            event.add('categories', [event_details['category']])
            
        # Add alarm/reminder
        reminder_minutes = event_details.get('reminder_minutes')
        if reminder_minutes is not None:
            alarm = Alarm()
            alarm.add('action', 'DISPLAY')
            alarm.add('description', f"Reminder: {event_details['title']}")
            alarm.add('trigger', timedelta(minutes=-int(reminder_minutes)))
            event.add_component(alarm)
            
        cal.add_component(event)
        return cal.to_ical()
    except Exception as e:
        logger.error(f"Error creating iCal event: {str(e)}")
        raise

def shorten_url(url: str) -> str:
    """Shorten a URL using TinyURL service"""
    config = AppConfig()
    if not config.SHORT_URL_SERVICE:
        return url
        
    try:
        s = pyshorteners.Shortener()
        return s.tinyurl.short(url)
    except Exception as e:
        logger.error(f"Error shortening URL: {str(e)}")
        return url

def analyze_calendar_habits(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze calendar usage patterns and return insights"""
    try:
        if not events:
            return {"status": "no_data"}
            
        # Convert to DataFrame for analysis with safer parsing
        categories = []
        start_values = []
        end_values = []
        for event in events:
            if isinstance(event, dict):
                categories.append(event.get('category') or "Uncategorized")
                start = event.get('start', {})
                end = event.get('end', {})
            else:
                categories.append("Uncategorized")
                start = {}
                end = {}
            if isinstance(start, dict):
                start_values.append(start.get('dateTime') or start.get('date'))
            else:
                start_values.append(None)
            if isinstance(end, dict):
                end_values.append(end.get('dateTime') or end.get('date'))
            else:
                end_values.append(None)
                
        df = pd.DataFrame({
            "category": categories,
            "start_dt": pd.to_datetime(start_values, errors='coerce'),
            "end_dt": pd.to_datetime(end_values, errors='coerce')
        })
        
        # Basic stats
        total_events = len(events)
        categories = df['category'].value_counts().to_dict()
        
        # Time analysis
        if df['start_dt'].notna().any():
            df['hour'] = df['start_dt'].dt.hour
            df['day_of_week'] = df['start_dt'].dt.day_name()
            
            busy_hours = df['hour'].value_counts().head(3).to_dict()
            busy_days = df['day_of_week'].value_counts().to_dict()
            
            # Calculate average event duration
            if df['end_dt'].notna().any():
                df['duration_mins'] = (df['end_dt'] - df['start_dt']).dt.total_seconds() / 60
                avg_duration = df['duration_mins'].dropna().mean()
            else:
                avg_duration = None
        else:
            busy_hours = {}
            busy_days = {}
            avg_duration = None
            
        return {
            "status": "success",
            "total_events": total_events,
            "categories": categories,
            "busy_hours": busy_hours,
            "busy_days": busy_days,
            "avg_duration": avg_duration
        }
    except Exception as e:
        logger.error(f"Error analyzing calendar habits: {str(e)}")
        return {"status": "error", "error": str(e)}

def generate_sharing_image(event_details: Dict[str, Any]) -> BytesIO:
    """Generate a shareable image with event details"""
    try:
        # Create a blank image
        width, height = 1200, 630
        image = Image.new('RGB', (width, height), color='white')
        
        # TODO: Add text and styling to the image
        # This is a placeholder - in a real implementation, you would:
        # 1. Use PIL's ImageDraw to add text
        # 2. Add background, logos, etc.
        # 3. Format the event details attractively
        
        # Save to BytesIO
        img_byte_arr = BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        return img_byte_arr
    except Exception as e:
        logger.error(f"Error generating sharing image: {str(e)}")
        raise

def extract_attendees_from_text(text: str) -> List[str]:
    """Extract potential attendees from text using pattern matching"""
    if not text:
        return []

    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    emails = re.findall(email_pattern, text)

    # Common patterns for names in event descriptions
    name_patterns = [
        r'with\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
        r'@\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
        r'invite\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})'
    ]
    
    attendees = []
    for pattern in name_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            attendees.append(match.group(1).strip())
            
    attendees.extend(emails)
    return list(set(attendees))  # Remove duplicates 
