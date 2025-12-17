import streamlit as st
from datetime import datetime, timedelta
import pytz
import logging
from calendar_service import CalendarManager, RecurrenceFrequency
from config import AppConfig, Theme
from streamlit_option_menu import option_menu
import plotly.express as px

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application configuration accessible throughout the module
app_config = AppConfig()

def initialize_session_state():
    """Initialize session state variables"""
    # App Config
    app_config = AppConfig()
    
    # Basic session state vars
    if 'current_timezone' not in st.session_state:
        st.session_state.current_timezone = app_config.CALENDAR_CONFIG.TIMEZONE
    
    if 'dark_mode' not in st.session_state:
        st.session_state.dark_mode = app_config.THEME == Theme.DARK
    
    if 'event_details' not in st.session_state:
        st.session_state.event_details = None
    
    if 'show_confirm' not in st.session_state:
        st.session_state.show_confirm = False
    
    if 'last_schedule_input' not in st.session_state:
        st.session_state.last_schedule_input = ""
    
    if 'last_edit_input' not in st.session_state:
        st.session_state.last_edit_input = ""
    
    if 'selected_tab' not in st.session_state:
        st.session_state.selected_tab = "Schedule"
    
    if 'calendar_stats' not in st.session_state:
        st.session_state.calendar_stats = None

def apply_custom_styles():
    """Apply custom CSS styling to the application"""
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
    }
    
    .time-suggestion {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 10px;
        background-color: #f9f9f9;
    }
    
    .time-suggestion h4 {
        margin-top: 0;
    }
    
    .stButton button {
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

def render_header():
    """Render the application header with current time display"""
    try:
        app_config = AppConfig()
        st.title(app_config.APP_TITLE)
        timezone_name = st.session_state.get('current_timezone', app_config.CALENDAR_CONFIG.TIMEZONE)
        current_time = datetime.now(pytz.timezone(timezone_name))
        timezone_label = timezone_name.replace('_', ' ')
        time_str = current_time.strftime('%I:%M %p')
        date_str = current_time.strftime('%B %d, %Y')
        st.write(f"Current time: {time_str} {timezone_label} on {date_str}")
    except Exception as e:
        logger.error(f"Error in render_header: {str(e)}")
        st.error("Failed to render header. Please refresh the page.")

def initialize_calendar():
    """Initialize the calendar manager in session state"""
    if 'calendar' not in st.session_state:
        try:
            st.session_state.calendar = CalendarManager()
            logger.info("Calendar manager initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize calendar: {str(e)}")
            st.error(f"Failed to initialize calendar: {str(e)}")
            return False
    return True

def handle_scheduling(user_input):
    """Process a scheduling request and store the interpreted details"""
    try:
        event_details = st.session_state.calendar.process_user_command(user_input)
        
        if event_details:
            st.session_state.event_details = event_details
            st.session_state.show_confirm = True
            st.session_state.last_schedule_input = user_input
            logger.info(f"Successfully processed scheduling request: {event_details['title']}")
        else:
            st.warning("Could not interpret the event details. Please try again with clearer information.")
            logger.warning(f"Failed to process scheduling request: {user_input}")
    except Exception as e:
        logger.error(f"Error in handle_scheduling: {str(e)}")
        st.error("An error occurred while processing your request. Please try again.")

def render_event_preview():
    """Render the event preview and confirmation controls."""
    event_details = st.session_state.event_details
    if not event_details:
        return

    with st.container():
        timezone_label = st.session_state.current_timezone.replace("_", " ")
        st.write(f"📅 Interpreted Event Details ({timezone_label}):")
        st.write(f"📌 Title: {event_details['title']}")
        st.write(f"📆 Date: {event_details['date']}")
        st.write(f"🕒 Time: {event_details['time']} {timezone_label}")
        st.write(f"⏱️ Duration: {event_details['duration']} minutes")
        st.write(f"📝 Description: {event_details.get('description', 'No description provided')}")

        # Add recurrence options if needed
        if event_details.get('is_recurring', False):
            recurrence_options = [f.value for f in RecurrenceFrequency]
            default_frequency = event_details.get('recurrence_pattern', recurrence_options[0])
            default_frequency_index = recurrence_options.index(default_frequency) if default_frequency in recurrence_options else 0

            col1, col2, col3 = st.columns(3)
            with col1:
                frequency = st.selectbox(
                    "Recurrence Frequency",
                    recurrence_options,
                    format_func=lambda x: x.capitalize(),
                    index=default_frequency_index,
                    key="recurrence_frequency"
                )
            with col2:
                count = st.number_input(
                    "Number of occurrences",
                    min_value=1,
                    max_value=365,
                    value=event_details.get('recurrence_count', 10),
                    key="recurrence_count"
                )
            with col3:
                interval = st.number_input(
                    "Interval",
                    min_value=1,
                    max_value=12,
                    value=event_details.get('recurrence_interval', 1),
                    key="recurrence_interval"
                )

            event_details['recurrence_pattern'] = frequency
            event_details['recurrence_count'] = count
            event_details['recurrence_interval'] = interval

        # Add category selection
        categories = st.session_state.calendar.get_event_categories()
        default_category = event_details.get('category')
        default_category_index = categories.index(default_category) if default_category in categories else 0
        selected_category = st.selectbox(
            "Event Category",
            categories,
            index=default_category_index,
            key="event_category"
        )
        event_details['category'] = selected_category

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Add to Calendar", type="primary", key="add_to_calendar"):
                try:
                    result = st.session_state.calendar.add_to_calendar(event_details)
                    st.success(result)
                    st.session_state.show_confirm = False
                    st.session_state.event_details = None
                except Exception as e:
                    logger.error(f"Error adding event to calendar: {str(e)}")
                    st.error(f"Failed to add event: {str(e)}")
        with col2:
            if st.button("🗑️ Discard", key="discard_event"):
                st.session_state.show_confirm = False
                st.session_state.event_details = None

def handle_editing(edit_input):
    """Process an edit request and display the result"""
    try:
        result = st.session_state.calendar.process_edit_command(edit_input)
        if result:
            st.success(result)
            st.session_state.last_edit_input = edit_input
            logger.info(f"Successfully processed edit request: {edit_input}")
        else:
            st.error("Failed to process edit request")
            logger.warning(f"Failed to process edit request: {edit_input}")
    except Exception as e:
        logger.error(f"Error in handle_editing: {str(e)}")
        st.error("An error occurred while processing your edit request. Please try again.")

def format_event_label(event, timezone):
    """Format a calendar event for display."""
    if not isinstance(event, dict):
        return str(event)

    summary = event.get('summary', 'Untitled Event')
    start_info = event.get('start') or {}
    if not isinstance(start_info, dict):
        start_info = {}

    start_str = start_info.get('dateTime') or start_info.get('date')
    if not start_str:
        return summary

    try:
        if start_info.get('dateTime'):
            start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            if start_dt.tzinfo:
                start_dt = start_dt.astimezone(timezone)
            formatted_start = start_dt.strftime('%I:%M %p on %B %d, %Y')
        else:
            start_dt = datetime.fromisoformat(start_str)
            formatted_start = start_dt.strftime('%B %d, %Y')
    except ValueError:
        formatted_start = start_str

    return f"{summary} at {formatted_start}"

def handle_calendar_view():
    """Display upcoming events from the calendar"""
    with st.spinner("Loading calendar..."):
        try:
            # Add search functionality
            search_query = st.text_input("🔍 Search events", placeholder="Search by title, description, or category")
            
            # Add date range filter
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", datetime.now())
            with col2:
                end_date = st.date_input("End Date", datetime.now() + timedelta(days=30))
            
            if search_query:
                events = st.session_state.calendar.search_events(
                    search_query,
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date, datetime.max.time())
                )
            else:
                events = st.session_state.calendar.get_upcoming_events()
            
            if not events:
                st.info('No events found')
            else:
                display_timezone = pytz.timezone(st.session_state.current_timezone)
                timezone_label = st.session_state.current_timezone.replace("_", " ")
                st.write(f"📅 Events ({timezone_label}):")
                for event in events:
                    label = format_event_label(event, display_timezone)
                    with st.expander(f"🗓️ {label}"):
                        if isinstance(event, dict):
                            location = event.get('location')
                            if location:
                                st.write(f"📍 Location: {location}")
                            description = event.get('description')
                            if description:
                                st.write(f"📝 Description: {description}")

                        # Add category management
                        if isinstance(event, dict) and 'id' in event:
                            categories = st.session_state.calendar.get_event_categories()
                            selected_category = st.selectbox(
                                "Category",
                                categories,
                                key=f"category_{event['id']}"
                            )
                            if st.button("Update Category", key=f"update_{event['id']}"):
                                result = st.session_state.calendar.add_event_category(
                                    event['id'],
                                    selected_category
                                )
                                st.success(result)
        except Exception as e:
            logger.error(f"Error in handle_calendar_view: {str(e)}")
            st.error("Failed to load calendar events. Please try again.")

# Handler function for analytics view
def handle_analytics():
    """Display analytics and insights about calendar usage"""
    try:
        # Date range selector for analytics
        st.subheader("📊 Calendar Analytics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            start_date = st.date_input(
                "From",
                value=(datetime.now() - timedelta(days=30)).date(),
                key="analytics_start_date"
            )
        
        with col2:
            end_date = st.date_input(
                "To",
                value=datetime.now().date(),
                key="analytics_end_date"
            )
        
        # Button to generate analytics
        if st.button("Generate Analytics", type="primary"):
            with st.spinner("Analyzing your calendar..."):
                # Convert to datetime objects with timezone
                timezone = pytz.timezone(st.session_state.current_timezone)
                start_datetime = timezone.localize(datetime.combine(start_date, datetime.min.time()))
                end_datetime = timezone.localize(datetime.combine(end_date, datetime.max.time()))
                
                # Get calendar stats
                stats = st.session_state.calendar.get_calendar_stats(start_datetime, end_datetime)
                
                # Store in session state
                st.session_state.calendar_stats = stats
        
        # Display stats if available
        if st.session_state.calendar_stats:
            stats = st.session_state.calendar_stats
            
            if stats.get('status') == 'success':
                # Create tabs for different analytics views
                tab1, tab2, tab3 = st.tabs(["📈 Overview", "⏰ Time Analysis", "🏷️ Categories"])
                
                # Overview tab
                with tab1:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.metric("Total Events", stats.get('total_events', 0))
                        
                        # Add some overall stats
                        if stats.get('avg_duration') is not None:
                            avg_duration = stats.get('avg_duration')
                            hours = int(avg_duration // 60)
                            minutes = int(avg_duration % 60)
                            duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                            st.metric("Average Event Duration", duration_str)
                            
                    with col2:
                        # Add a date range summary
                        days_analyzed = (end_date - start_date).days
                        events_per_day = stats.get('total_events', 0) / max(1, days_analyzed)
                        st.metric("Days Analyzed", days_analyzed)
                        st.metric("Events per Day", f"{events_per_day:.1f}")
                
                # Time Analysis tab
                with tab2:
                    # Create busy hours chart
                    if stats.get('busy_hours'):
                        st.subheader("Busiest Hours")
                        
                        busy_hours = stats.get('busy_hours', {})
                        hours = list(busy_hours.keys())
                        counts = list(busy_hours.values())
                        
                        # Convert hour numbers to formatted time
                        hour_labels = [f"{int(h)}:00" for h in hours]
                        
                        fig = px.bar(
                            x=hour_labels,
                            y=counts,
                            labels={'x': 'Hour of Day', 'y': 'Number of Events'},
                            color=counts,
                            color_continuous_scale='Viridis'
                        )
                        
                        fig.update_layout(
                            title="Events by Hour of Day",
                            xaxis_title="Hour of Day",
                            yaxis_title="Number of Events"
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Create busy days chart
                    if stats.get('busy_days'):
                        st.subheader("Events by Day of Week")
                        
                        busy_days = stats.get('busy_days', {})
                        
                        # Order days of week properly
                        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        ordered_days = []
                        ordered_counts = []
                        
                        for day in day_order:
                            if day in busy_days:
                                ordered_days.append(day)
                                ordered_counts.append(busy_days[day])
                        
                        fig = px.bar(
                            x=ordered_days,
                            y=ordered_counts,
                            labels={'x': 'Day of Week', 'y': 'Number of Events'},
                            color=ordered_counts,
                            color_continuous_scale='Viridis'
                        )
                        
                        fig.update_layout(
                            title="Events by Day of Week",
                            xaxis_title="Day of Week",
                            yaxis_title="Number of Events"
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                
                # Categories tab
                with tab3:
                    if stats.get('categories'):
                        st.subheader("Events by Category")
                        
                        categories = stats.get('categories', {})
                        category_names = list(categories.keys())
                        category_counts = list(categories.values())
                        
                        # Create pie chart for categories
                        fig = px.pie(
                            names=category_names,
                            values=category_counts,
                            title="Event Categories Distribution"
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Create a bar chart for better readability
                        fig2 = px.bar(
                            x=category_names,
                            y=category_counts,
                            labels={'x': 'Category', 'y': 'Number of Events'},
                            color=category_names
                        )
                        
                        fig2.update_layout(
                            title="Events by Category",
                            xaxis_title="Category",
                            yaxis_title="Number of Events"
                        )
                        
                        st.plotly_chart(fig2, use_container_width=True)
                    else:
                        st.info("No category data available. Try categorizing your events to see analytics.")
            elif stats.get('status') == 'no_data':
                st.info("No events found in the selected date range for analysis.")
            else:
                st.error(f"Error analyzing calendar: {stats.get('error', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Error in handle_analytics: {str(e)}")
        st.error(f"Error generating analytics: {str(e)}")

# Handler function for settings
def handle_settings():
    """Display and manage application settings"""
    try:
        st.subheader("⚙️ Settings")
        
        # Create columns for different settings categories
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Display Settings")
            
            # Theme selection
            dark_mode = st.toggle(
                "Dark Mode",
                value=st.session_state.dark_mode,
                key="dark_mode_toggle"
            )
            
            if dark_mode != st.session_state.dark_mode:
                st.session_state.dark_mode = dark_mode
                # In a real app, you'd save this preference to a database
                st.info("Theme preference updated. Refresh to see changes.")
            
            # Timezone selection
            st.markdown("### Timezone Settings")
            
            timezone_options = app_config.get_all_timezone_choices()
            timezone_values = [tz["value"] for tz in timezone_options]
            timezone_labels = [tz["label"] for tz in timezone_options]
            
            current_index = timezone_values.index(st.session_state.current_timezone) if st.session_state.current_timezone in timezone_values else 0
            
            selected_timezone = st.selectbox(
                "Timezone",
                options=timezone_values,
                format_func=lambda x: x.replace("_", " "),
                index=current_index,
                key="timezone_select"
            )
            
            if selected_timezone != st.session_state.current_timezone:
                st.session_state.current_timezone = selected_timezone
                if 'calendar' in st.session_state:
                    st.session_state.calendar.config.TIMEZONE = selected_timezone
                    st.session_state.calendar.timezone = pytz.timezone(selected_timezone)
                    st.session_state.calendar.event_processor.timezone = pytz.timezone(selected_timezone)
                # In a real app, you'd save this preference to a database
                st.info("Timezone updated. The app will use this timezone for all dates and times.")
                
        with col2:
            st.markdown("### Notification Settings")
            
            # Notification settings
            default_reminder = st.number_input(
                "Default reminder time (minutes before event)",
                min_value=0,
                max_value=1440,  # 24 hours
                value=app_config.DEFAULT_NOTIFICATION_LEAD_TIME,
                key="default_reminder"
            )
            
            # In a real app, you'd save this preference
            if default_reminder != app_config.DEFAULT_NOTIFICATION_LEAD_TIME:
                st.info("Default reminder time updated.")
            
            # SMS settings if Twilio is configured
            if app_config.TWILIO_CONFIG.ENABLED:
                st.markdown("### SMS Notifications")
                
                enable_sms = st.checkbox(
                    "Enable SMS notifications",
                    value=app_config.TWILIO_CONFIG.ENABLED,
                    key="enable_sms"
                )
                
                if enable_sms:
                    phone_number = st.text_input(
                        "Your phone number",
                        key="sms_phone_number"
                    )
                    
                    # Save settings button
                    if st.button("Save SMS Settings"):
                        # In a real app, you'd save these settings
                        st.success("SMS settings saved.")
            
        # Advanced settings
        with st.expander("Advanced Settings"):
            st.markdown("### Calendar Settings")
            
            max_events = st.slider(
                "Maximum events to display",
                min_value=10,
                max_value=100,
                value=app_config.MAX_EVENTS,
                step=10,
                key="max_events"
            )
            
            max_days = st.slider(
                "Maximum days ahead to display",
                min_value=7,
                max_value=365,
                value=app_config.MAX_DAYS_AHEAD,
                step=7,
                key="max_days"
            )
            
            # AI model settings
            st.markdown("### AI Settings")
            
            ai_model = st.selectbox(
                "AI Model",
                options=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
                index=0,
                key="ai_model"
            )
            
            # Save settings button
            if st.button("Save Advanced Settings"):
                # In a real app, you'd save these settings
                st.success("Advanced settings saved.")
    except Exception as e:
        logger.error(f"Error in handle_settings: {str(e)}")
        st.error(f"Error displaying settings: {str(e)}")

# Handler for smart scheduler
def handle_smart_scheduler():
    """Smart meeting scheduler that finds optimal meeting times"""
    try:
        st.subheader("🧠 Smart Meeting Scheduler")
        
        with st.form("smart_scheduler_form"):
            # Meeting details
            st.markdown("### Meeting Details")
            
            meeting_title = st.text_input("Meeting title", key="smart_title")
            meeting_duration = st.slider("Duration (minutes)", 15, 180, 30, 15, key="smart_duration")
            
            # Attendees
            st.markdown("### Attendees")
            
            attendees = st.text_area(
                "Enter attendee email addresses (one per line)",
                key="smart_attendees"
            )
            
            # Parse attendees
            attendee_list = [email.strip() for email in attendees.split("\n") if email.strip()]
            
            # Date range
            st.markdown("### Date Range")
            
            col1, col2 = st.columns(2)
            
            with col1:
                start_date = st.date_input(
                    "Earliest date",
                    value=datetime.now().date(),
                    key="smart_start_date"
                )
            
            with col2:
                end_date = st.date_input(
                    "Latest date",
                    value=(datetime.now() + timedelta(days=7)).date(),
                    key="smart_end_date"
                )
            
            # Work hours
            st.markdown("### Work Hours")
            
            col1, col2 = st.columns(2)
            
            with col1:
                start_hour = st.selectbox(
                    "Start time",
                    options=range(6, 21),
                    format_func=lambda h: f"{h}:00",
                    index=3,  # Default to 9 AM
                    key="smart_start_hour"
                )
            
            with col2:
                end_hour = st.selectbox(
                    "End time",
                    options=range(7, 22),
                    format_func=lambda h: f"{h}:00",
                    index=10,  # Default to 5 PM
                    key="smart_end_hour"
                )
            
            # Submit button
            submitted = st.form_submit_button("Find Optimal Meeting Times")
        
        # Process form submission
        if submitted:
            if not meeting_title:
                st.warning("Please enter a meeting title.")
            elif not attendee_list:
                st.warning("Please add at least one attendee.")
            elif start_hour >= end_hour:
                st.warning("End time must be after start time.")
            elif start_date > end_date:
                st.warning("End date must be after start date.")
            else:
                with st.spinner("Finding optimal meeting times..."):
                    # Convert to datetime objects with timezone
                    timezone = pytz.timezone(st.session_state.current_timezone)
                    start_datetime = timezone.localize(datetime.combine(start_date, datetime.min.time()))
                    end_datetime = timezone.localize(datetime.combine(end_date, datetime.max.time()))
                    
                    # Get suggested times
                    suggested_times = st.session_state.calendar.suggest_optimal_meeting_time(
                        attendees=attendee_list,
                        duration_minutes=meeting_duration,
                        start_date=start_datetime,
                        end_date=end_datetime,
                        working_hours=(start_hour, end_hour)
                    )
                    
                    if not suggested_times:
                        st.warning("No suitable meeting times found. Try adjusting your parameters.")
                    else:
                        st.success(f"Found {len(suggested_times)} optimal meeting times!")
                        
                        # Display suggestions
                        st.markdown("### Suggested Meeting Times")
                        
                        for i, suggestion in enumerate(suggested_times):
                            # Parse times
                            start_time = datetime.fromisoformat(suggestion['start'].replace('Z', '+00:00'))
                            end_time = datetime.fromisoformat(suggestion['end'].replace('Z', '+00:00'))
                            
                            # Format for display
                            date_str = start_time.strftime('%A, %B %d, %Y')
                            time_str = f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
                            
                            # Confidence indicator
                            confidence = suggestion.get('confidence', 0.5)
                            confidence_emoji = "🟢" if confidence > 0.7 else "🟡" if confidence > 0.4 else "🔴"
                            
                            # Create interactive card
                            with st.container():
                                st.markdown(f"""
                                <div class="time-suggestion">
                                    <h4>{confidence_emoji} Option {i+1}: {date_str}</h4>
                                    <p>{time_str}</p>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Schedule button
                                if st.button(f"Schedule This Time", key=f"schedule_{i}"):
                                    # Create event details
                                    event_details = {
                                        'title': meeting_title,
                                        'date': start_time.strftime('%Y-%m-%d'),
                                        'time': start_time.strftime('%H:%M'),
                                        'duration': meeting_duration,
                                        'attendees': attendee_list,
                                        'category': 'Meeting'
                                    }
                                    
                                    # Store in session state and switch to Schedule tab
                                    st.session_state.event_details = event_details
                                    st.session_state.show_confirm = True
                                    st.session_state.selected_tab = "Schedule"
                                    st.experimental_rerun()
    except Exception as e:
        logger.error(f"Error in handle_smart_scheduler: {str(e)}")
        st.error(f"Error using smart scheduler: {str(e)}")

# Main application function
def main():
    """Main application function"""
    # Initialize session state
    initialize_session_state()
    
    # Apply custom styles
    apply_custom_styles()
    
    # Render header
    render_header()

    # Initialize calendar manager
    if not initialize_calendar():
        st.stop()
    
    # Sidebar menu
    with st.sidebar:
        selected_tab = option_menu(
            "Menu",
            ["Schedule", "Edit", "View", "Smart Scheduler", "Analytics", "Settings"],
            icons=['calendar-plus', 'pencil', 'calendar-week', 'lightbulb', 'graph-up', 'gear'],
            menu_icon="bars",
            default_index=0,
            key="main_menu"
        )
        
        # Update session state
        st.session_state.selected_tab = selected_tab
        
        # Show app version
        st.markdown(f"<div style='text-align: center; color: gray; font-size: 0.8em;'>Version {app_config.VERSION}</div>", unsafe_allow_html=True)
    
    # Main content area
    if selected_tab == "Schedule":
        st.subheader("📝 Schedule a New Event")
        
        # User input
        user_input = st.text_input(
            "Describe your event in natural language:",
            value=st.session_state.last_schedule_input,
            placeholder="e.g., Schedule a team meeting tomorrow at 2pm for 1 hour",
            key="schedule_input"
        )
        
        # Process button
        if st.button("🔍 Interpret Request", type="primary", key="schedule_button"):
            if user_input:
                handle_scheduling(user_input)
            else:
                st.warning("Please enter event details")
        
        # Show confirmation section if needed
        if st.session_state.show_confirm and st.session_state.event_details:
            render_event_preview()
    
    elif selected_tab == "Edit":
        st.subheader("✏️ Edit or Reschedule an Event")
        
        # User input
        edit_input = st.text_input(
            "Describe what you want to change:",
            value=st.session_state.last_edit_input,
            placeholder="e.g., Reschedule my team meeting to tomorrow at 3pm",
            key="edit_input"
        )
        
        # Process button
        if st.button("🔄 Process Edit", type="primary", key="edit_button"):
            if edit_input:
                handle_editing(edit_input)
            else:
                st.warning("Please enter edit details")
    
    elif selected_tab == "View":
        st.subheader("👁️ View Calendar")
        handle_calendar_view()
    
    elif selected_tab == "Smart Scheduler":
        handle_smart_scheduler()
    
    elif selected_tab == "Analytics":
        handle_analytics()
    
    elif selected_tab == "Settings":
        handle_settings()
        
    # Add help section at the bottom of every page
    with st.expander("ℹ️ Help & Tips"):
        st.markdown("""
        ### Quick Guide:
        
        🗓️ **Scheduling Events:**
        - "Schedule a meeting tomorrow at 2pm for 1 hour"
        - "Set up a call with John at john@example.com on Friday at 10am for 30 minutes"
        - "Create a weekly team meeting every Monday at 9am"
        - "Add a doctor's appointment at City Clinic on June 15th at 3pm"
        
        ✏️ **Editing Events:**
        - "Reschedule my meeting to tomorrow at 3pm"
        - "Move my call with John to next week"
        - "Cancel tomorrow's team sync"
        - "Add Jane to my project review meeting"
        
        🧠 **Smart Scheduler:**
        - Finds optimal meeting times based on attendees' availability
        - Considers working hours and preferred time ranges
        - Lets you select and schedule the best option with one click
        
        📊 **Analytics:**
        - See patterns in your calendar usage
        - Identify your busiest days and times
        - Analyze time spent by category
        
        ⚙️ **Settings:**
        - Change timezone settings
        - Customize notification preferences
        - Adjust display options
        """)

if __name__ == "__main__":
    main()
