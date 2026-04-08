"""
Google Calendar Tools for Scheduling Agent

This module provides calendar integration tools using the Google Calendar API.
These tools allow the scheduling agent to:
- Check for scheduling conflicts
- Find available time slots
- Create delivery events with order details
- View upcoming events

Setup Requirements:
1. Create a Google Cloud project
2. Enable Google Calendar API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download credentials.json to project root
5. First run will open browser for authentication
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# OAuth scopes for Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Get the project root directory (same folder as this file)
PROJECT_ROOT = Path(__file__).parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"


def get_calendar_service():
    """
    Authenticate and return Google Calendar service.

    On first run, opens browser for OAuth consent.
    Subsequent runs use saved token.

    Returns:
        Google Calendar API service object
    """
    creds = None

    # Check for existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}. "
                    "Please download OAuth credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_current_time() -> dict:
    """
    Get the current date and time.

    Returns:
        dict: Current datetime information for calculating delivery windows
    """
    now = datetime.now()
    return {
        "current_time": now.strftime("%I:%M %p"),
        "current_date": now.strftime("%Y-%m-%d"),
        "iso_format": now.isoformat(),
        "day_of_week": now.strftime("%A")
    }


def check_conflicts(start_time: str, end_time: str) -> dict:
    """
    Check if there are any calendar events during the specified time window.

    Args:
        start_time: ISO format datetime string for window start
        end_time: ISO format datetime string for window end

    Returns:
        dict: Conflict information including any overlapping events
    """
    try:
        service = get_calendar_service()

        # Query events in the time range
        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        if not events:
            return {
                "has_conflict": False,
                "message": "No conflicts found in this time window.",
                "conflicting_events": []
            }

        # Build list of conflicting events
        conflicts = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            conflicts.append({
                "title": event.get("summary", "Busy"),
                "start": start,
                "end": end
            })

        return {
            "has_conflict": True,
            "message": f"Found {len(conflicts)} conflicting event(s).",
            "conflicting_events": conflicts
        }

    except HttpError as error:
        return {
            "has_conflict": False,
            "error": str(error),
            "message": "Error checking calendar. Assuming no conflicts."
        }


def get_freebusy(time_min: str, time_max: str) -> dict:
    """
    Get free/busy information for a time range.

    Args:
        time_min: ISO format start time
        time_max: ISO format end time

    Returns:
        dict: Free/busy periods in the specified range
    """
    try:
        service = get_calendar_service()

        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": "primary"}]
        }

        result = service.freebusy().query(body=body).execute()
        busy_periods = result.get("calendars", {}).get("primary", {}).get("busy", [])

        return {
            "time_range": {"start": time_min, "end": time_max},
            "busy_periods": busy_periods,
            "is_completely_free": len(busy_periods) == 0
        }

    except HttpError as error:
        return {"error": str(error)}


def find_next_free_slot(after_time: str, duration_minutes: int = 30) -> dict:
    """
    Find the next available time slot after a given time.

    Args:
        after_time: ISO format datetime to search after
        duration_minutes: Required slot duration in minutes

    Returns:
        dict: Next available time slot information
    """
    try:
        service = get_calendar_service()

        # Parse the start time
        start_dt = datetime.fromisoformat(after_time.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=None)

        # Look ahead up to 8 hours
        end_dt = start_dt + timedelta(hours=8)

        # Get all events in this window
        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        # If no events, the requested time is free
        if not events:
            slot_end = start_dt + timedelta(minutes=duration_minutes)
            return {
                "found": True,
                "slot_start": start_dt.strftime("%I:%M %p"),
                "slot_end": slot_end.strftime("%I:%M %p"),
                "slot_start_iso": start_dt.isoformat(),
                "slot_end_iso": slot_end.isoformat(),
                "message": f"Time slot available from {start_dt.strftime('%I:%M %p')}"
            }

        # Find gaps between events
        current_time = start_dt
        for event in events:
            event_start_str = event["start"].get("dateTime", event["start"].get("date"))
            event_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
            if event_start.tzinfo:
                event_start = event_start.replace(tzinfo=None)

            # Check if there's enough time before this event
            gap = (event_start - current_time).total_seconds() / 60
            if gap >= duration_minutes:
                slot_end = current_time + timedelta(minutes=duration_minutes)
                return {
                    "found": True,
                    "slot_start": current_time.strftime("%I:%M %p"),
                    "slot_end": slot_end.strftime("%I:%M %p"),
                    "slot_start_iso": current_time.isoformat(),
                    "slot_end_iso": slot_end.isoformat(),
                    "message": f"Found available slot from {current_time.strftime('%I:%M %p')}"
                }

            # Move current time to after this event
            event_end_str = event["end"].get("dateTime", event["end"].get("date"))
            event_end = datetime.fromisoformat(event_end_str.replace("Z", "+00:00"))
            if event_end.tzinfo:
                event_end = event_end.replace(tzinfo=None)
            current_time = max(current_time, event_end)

        # Check if there's time after all events
        if current_time < end_dt:
            slot_end = current_time + timedelta(minutes=duration_minutes)
            return {
                "found": True,
                "slot_start": current_time.strftime("%I:%M %p"),
                "slot_end": slot_end.strftime("%I:%M %p"),
                "slot_start_iso": current_time.isoformat(),
                "slot_end_iso": slot_end.isoformat(),
                "message": f"Found available slot after existing events at {current_time.strftime('%I:%M %p')}"
            }

        return {
            "found": False,
            "message": "No available slots found in the next 8 hours."
        }

    except HttpError as error:
        return {"found": False, "error": str(error)}


def create_delivery_event(
    order_id: str,
    pizza_name: str,
    delivery_time: str,
    estimated_arrival: str,
    duration_minutes: int = 30
) -> dict:
    """
    Create a calendar event for pizza delivery.

    Args:
        order_id: The pizza order ID (e.g., "LM-X821B")
        pizza_name: Name of the pizza ordered
        delivery_time: ISO format datetime for delivery window start
        estimated_arrival: Human-readable arrival time (e.g., "1:30 PM")
        duration_minutes: Duration of delivery window

    Returns:
        dict: Created event details or error
    """
    try:
        service = get_calendar_service()

        # Parse delivery time
        start_dt = datetime.fromisoformat(delivery_time.replace("Z", "+00:00"))
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event = {
            "summary": f"Pizza Delivery - {pizza_name}",
            "description": (
                f"Order #{order_id}\n"
                f"Pizza: {pizza_name}\n"
                f"Expected arrival: {estimated_arrival}\n\n"
                "From: Legendary Margherita Pizza"
            ),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Kolkata"  # Adjust to your timezone
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 10}
                ]
            }
        }

        created_event = service.events().insert(
            calendarId="primary",
            body=event
        ).execute()

        return {
            "success": True,
            "event_id": created_event.get("id"),
            "event_link": created_event.get("htmlLink"),
            "summary": created_event.get("summary"),
            "start_time": start_dt.strftime("%I:%M %p"),
            "end_time": end_dt.strftime("%I:%M %p"),
            "message": f"Delivery event created for {estimated_arrival}"
        }

    except HttpError as error:
        return {
            "success": False,
            "error": str(error),
            "message": "Failed to create calendar event"
        }


def list_upcoming_events(hours_ahead: int = 4) -> dict:
    """
    List upcoming calendar events.

    Args:
        hours_ahead: Number of hours to look ahead

    Returns:
        dict: List of upcoming events
    """
    try:
        service = get_calendar_service()

        now = datetime.now()
        time_max = now + timedelta(hours=hours_ahead)

        # Add timezone offset to the ISO string
        # Format: 2024-12-27T13:00:00+05:30 for IST
        time_min_str = now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
        time_max_str = time_max.strftime("%Y-%m-%dT%H:%M:%S+05:30")

        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min_str,
            timeMax=time_max_str,
            maxResults=10,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        if not events:
            return {
                "events": [],
                "message": f"No events in the next {hours_ahead} hours.",
                "is_free": True
            }

        upcoming = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            upcoming.append({
                "title": event.get("summary", "Busy"),
                "start": start,
                "end": end
            })

        return {
            "events": upcoming,
            "message": f"Found {len(upcoming)} event(s) in the next {hours_ahead} hours.",
            "is_free": False
        }

    except HttpError as error:
        return {"events": [], "error": str(error)}


# For testing
if __name__ == "__main__":
    print("Testing Calendar Tools...")
    print("\n1. Current Time:")
    print(get_current_time())

    print("\n2. Upcoming Events (next 4 hours):")
    print(list_upcoming_events(4))
