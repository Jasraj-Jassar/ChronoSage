import os
import pytz
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum, auto

class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"

class NotificationMethod(Enum):
    EMAIL = auto()
    SMS = auto()
    PUSH = auto()
    NONE = auto()

class RecurrenceFrequency(Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"

@dataclass
class TwilioConfig:
    ENABLED: bool = False
    ACCOUNT_SID: Optional[str] = None
    AUTH_TOKEN: Optional[str] = None
    FROM_NUMBER: Optional[str] = None

@dataclass
class WeatherConfig:
    ENABLED: bool = True
    API_KEY: Optional[str] = None
    UNITS: str = "metric"  # metric or imperial

@dataclass
class CalendarConfig:
    TIMEZONE: str = 'America/Denver'
    SCOPES: List[str] = None
    CREDENTIALS_FILE: str = 'credentials.json'
    TOKEN_FILE: str = 'token.pickle'
    PRIMARY_CALENDAR_ID: str = 'primary'
    MAX_RECURRING_EVENTS: int = 365
    SUPPORTED_TIMEZONES: List[str] = field(default_factory=lambda: [
        'America/Denver', 'America/New_York', 'America/Los_Angeles', 
        'America/Chicago', 'Europe/London', 'Europe/Paris', 'Asia/Tokyo',
        'Asia/Singapore', 'Australia/Sydney', 'Pacific/Auckland'
    ])
    
    def __post_init__(self):
        if self.SCOPES is None:
            self.SCOPES = ['https://www.googleapis.com/auth/calendar']
            
@dataclass
class AIConfig:
    MODEL: str = "gpt-4o-mini"
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 1024
    SUGGESTION_MODE: bool = True  # Suggests improvements for event descriptions
    SMART_SCHEDULING: bool = True  # Finds optimal meeting times
    SUMMARY_ENABLED: bool = True   # Generates summaries of past events
            
@dataclass
class AppConfig:
    CALENDAR_CONFIG: CalendarConfig = field(default_factory=CalendarConfig)
    TWILIO_CONFIG: TwilioConfig = field(default_factory=TwilioConfig)
    WEATHER_CONFIG: WeatherConfig = field(default_factory=WeatherConfig)
    AI_CONFIG: AIConfig = field(default_factory=AIConfig)
    APP_TITLE: str = "ChronoSage"
    APP_SUBTITLE: str = "Intelligent Calendar Assistant"
    VERSION: str = "2.0.0"
    DEBUG: bool = False
    MAX_EVENTS: int = 20
    MAX_DAYS_AHEAD: int = 60
    THEME: Theme = Theme.AUTO
    USER_PREFERENCES: Dict[str, Any] = field(default_factory=dict)
    DEFAULT_NOTIFICATION_LEAD_TIME: int = 15  # minutes
    NOTIFICATION_METHODS: List[NotificationMethod] = field(
        default_factory=lambda: [NotificationMethod.EMAIL]
    )
    SHORT_URL_SERVICE: bool = True
    EVENT_CATEGORIES: List[str] = field(default_factory=lambda: [
        "Meeting", "Appointment", "Task", "Reminder", "Personal", 
        "Work", "Health", "Education", "Social", "Family", "Travel", "Other"
    ])
    ENABLE_ANALYTICS: bool = True
    
    def get_timezone_obj(self) -> pytz.timezone:
        """Get the timezone object for the configured timezone"""
        return pytz.timezone(self.CALENDAR_CONFIG.TIMEZONE)
    
    def get_all_timezone_choices(self) -> List[Dict[str, str]]:
        """Get a list of timezone choices for the UI"""
        return [
            {"label": tz.replace('_', ' '), "value": tz} 
            for tz in self.CALENDAR_CONFIG.SUPPORTED_TIMEZONES
        ]
