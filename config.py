import os
import pytz
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class CalendarConfig:
    TIMEZONE: str = 'America/Denver'
    SCOPES: List[str] = None
    CREDENTIALS_FILE: str = 'credentials.json'
    TOKEN_FILE: str = 'token.pickle'
    
    def __post_init__(self):
        if self.SCOPES is None:
            self.SCOPES = ['https://www.googleapis.com/auth/calendar']
            
@dataclass
class AppConfig:
    CALENDAR_CONFIG: CalendarConfig = field(default_factory=CalendarConfig)
    APP_TITLE: str = "ChronoSage (MST)"
    DEBUG: bool = False
    MAX_EVENTS: int = 10
    MAX_DAYS_AHEAD: int = 30
