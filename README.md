# ChronoSage - Intelligent Calendar Assistant

ChronoSage is a Streamlit-based web application that provides an intelligent interface for managing your Google Calendar. It uses natural language processing to understand scheduling requests and makes calendar management more intuitive.

## Features

- 📅 Natural language event scheduling
- ✏️ Edit existing events using natural language
- 👁️ View upcoming events
- ⏰ Timezone-aware scheduling (Mountain Time)
- 🔒 Secure Google Calendar integration
- 📱 Responsive web interface

## Prerequisites

- Python 3.8 or higher
- Google Calendar API credentials
- Google account with Calendar access

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ChronoSage.git
cd ChronoSage
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up Google Calendar API:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the Google Calendar API
   - Create OAuth 2.0 credentials
   - Download the credentials and save as `credentials.json` in the project root

## Usage

1. Start the application:
```bash
streamlit run app.py
```

2. Open your browser and navigate to `http://localhost:8501`

3. Use the application:
   - **Schedule Tab**: Enter natural language commands to create events
   - **Edit Tab**: Modify or reschedule existing events
   - **View Tab**: See your upcoming events

## Examples

### Scheduling Events
- "Schedule a team meeting tomorrow at 2pm for 1 hour"
- "Set up a call with John on Friday at 10am for 30 minutes"
- "Create a project review meeting next Monday at 3pm for 2 hours"

### Editing Events
- "Reschedule my meeting to tomorrow at 3pm"
- "Move my call with John to next week"
- "Cancel tomorrow's team sync"

## Development

### Project Structure
```
ChronoSage/
├── app.py                 # Main Streamlit application
├── calendar_service.py    # Google Calendar integration
├── event_processor.py     # Natural language processing
├── auth_manager.py        # Google authentication
├── config.py             # Configuration settings
├── requirements.txt      # Project dependencies
└── README.md            # This file
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Google Calendar API
- Streamlit
- OpenAI 