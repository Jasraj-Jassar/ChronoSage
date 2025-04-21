# ChronoSage

An intelligent calendar assistant that uses natural language processing to schedule, edit, and view calendar events in Google Calendar. Specialized for Mountain Time zone users.

## Features

- **Natural Language Processing**: Use everyday language to schedule and manage your calendar events
- **Google Calendar Integration**: Seamlessly connects with your Google Calendar
- **Multiple Views**: Schedule, edit, and view your calendar in one application
- **Time Zone Support**: Designed for Mountain Time (MST/MDT) users

## Setup and Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/ChronoSage.git
   cd ChronoSage
   ```

2. Create a Python virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   ```

3. Install required packages:
   ```
   pip install -r requirements.txt
   ```

4. Set up Google Calendar API:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the Google Calendar API
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials JSON file and save it as `credentials.json` in the project root

5. Set up OpenAI API:
   - Get an API key from [OpenAI](https://platform.openai.com/)
   - Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   - Add your OpenAI API key to this file

## Running the Application

After setting up the project, run the application with:

```
streamlit run app.py
```

On first run, you'll need to authorize the application to access your Google Calendar.

## Usage

### Schedule Events
Enter natural language commands like:
- "Schedule a team meeting tomorrow at 2pm for 1 hour"
- "Set up a doctor's appointment on July 15 at 9:30am for 45 minutes"

### Edit Events
Modify existing events with commands like:
- "Reschedule my team meeting to Friday at 3pm"
- "Cancel my doctor's appointment"

### View Calendar
See your upcoming events in a user-friendly format.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 