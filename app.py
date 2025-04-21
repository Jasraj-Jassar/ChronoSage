import streamlit as st
from datetime import datetime
import pytz
from calendar_service import CalendarManager
from config import AppConfig

def render_header():
    """Render the application header with current time display"""
    app_config = AppConfig()
    st.title(app_config.APP_TITLE)
    current_time_mst = datetime.now(pytz.timezone('America/Denver'))
    st.write(f"Current time: {current_time_mst.strftime('%I:%M %p MST on %B %d, %Y')}")

def initialize_calendar():
    """Initialize the calendar manager in session state"""
    if 'calendar' not in st.session_state:
        try:
            st.session_state.calendar = CalendarManager()
        except Exception as e:
            st.error(f"Failed to initialize calendar: {str(e)}")
            return False
    return True

def handle_scheduling(user_input):
    """Process a scheduling request and display the interpreted details"""
    event_details = st.session_state.calendar.process_user_command(user_input)
    
    if event_details:
        with st.container():
            st.write("📅 Interpreted Event Details (Mountain Time):")
            st.write(f"📌 Title: {event_details['title']}")
            st.write(f"📆 Date: {event_details['date']}")
            st.write(f"🕒 Time: {event_details['time']} MST")
            st.write(f"⏱️ Duration: {event_details['duration']} minutes")
            st.write(f"📝 Description: {event_details.get('description', 'No description provided')}")
            
            st.session_state.event_details = event_details
            st.session_state.show_confirm = True

def handle_editing(edit_input):
    """Process an edit request and display the result"""
    result = st.session_state.calendar.process_edit_command(edit_input)
    if result:
        st.success(result)
    else:
        st.error("Failed to process edit request")

def view_calendar():
    """Display upcoming events from the calendar"""
    with st.spinner("Loading calendar..."):
        events = st.session_state.calendar.get_upcoming_events()
        if not events:
            st.info('No upcoming events found')
        else:
            st.write("📅 Upcoming events (Mountain Time):")
            for event in events:
                st.write(f"🗓️ {event}")

def main():
    """Main application function"""
    render_header()
    
    if not initialize_calendar():
        return
    
    # Create tabs for different functionalities
    tab1, tab2, tab3 = st.tabs(["📝 Schedule", "✏️ Edit", "👁️ View"])
    
    # Schedule Tab
    with tab1:
        user_input = st.text_input(
            "Schedule a new event:", 
            placeholder="e.g., Schedule a team meeting tomorrow at 2pm MST for 1 hour",
            key="schedule_input"
        )
        
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("Schedule", type="primary"):
                if user_input:
                    handle_scheduling(user_input)
                else:
                    st.warning("Please enter event details")
        
        # Show confirmation button if needed
        if st.session_state.get('show_confirm', False):
            with col2:
                if st.button("✅ Confirm and Add to Calendar", type="primary"):
                    result = st.session_state.calendar.add_to_calendar(st.session_state.event_details)
                    st.success(result)
                    st.session_state.show_confirm = False

    # Edit Tab
    with tab2:
        edit_input = st.text_input(
            "Edit or reschedule an event:",
            placeholder="e.g., Reschedule my meeting to tomorrow at 3pm",
            key="edit_input"
        )
        
        if st.button("Process Edit", type="primary"):
            if edit_input:
                handle_editing(edit_input)
            else:
                st.warning("Please enter edit details")

    # View Tab
    with tab3:
        if st.button("Refresh Calendar", type="secondary"):
            view_calendar()

    # Add help section at the bottom
    with st.expander("ℹ️ Help & Tips"):
        st.write("""
        ### Quick Guide:
        
        🗓️ **Scheduling Events:**
        - "Schedule a meeting tomorrow at 2pm for 1 hour"
        - "Set up a call with John on Friday at 10am for 30 minutes"
        
        ✏️ **Editing Events:**
        - "Reschedule my meeting to tomorrow at 3pm"
        - "Move my call with John to next week"
        - "Cancel tomorrow's team sync"
        
        👁️ **Viewing Calendar:**
        - Click "Refresh Calendar" to see your upcoming events
        
        ⏰ **Time Format:**
        - Use 12-hour format (e.g., 2pm, 3:30pm)
        - Or 24-hour format (e.g., 14:00, 15:30)
        """)

if __name__ == "__main__":
    main()