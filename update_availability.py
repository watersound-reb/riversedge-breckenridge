#!/usr/bin/env python3
"""
Fetches Airbnb AND VRBO iCal calendars and generates availability.json
for the Rivers Edge Breckenridge website.
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, date

AIRBNB_ICAL_URL = os.environ.get('AIRBNB_ICAL_URL', '')
VRBO_ICAL_URL = os.environ.get('VRBO_ICAL_URL', '')
OUTPUT_FILE = 'availability.json'
LOOKAHEAD_DAYS = 180
MIN_NIGHTS = 2


def fetch_ical(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8')


def extract_date(event_text, field):
    """Extract a date from an iCal field, handling all common formats."""
    match = re.search(rf'{field};VALUE=DATE:(\d{{8}})', event_text)
    if match:
        return datetime.strptime(match.group(1), '%Y%m%d').date()

    match = re.search(rf'{field};TZID=[^:]+:(\d{{8}})', event_text)
    if match:
        return datetime.strptime(match.group(1), '%Y%m%d').date()

    match = re.search(rf'{field}:(\d{{8}})', event_text)
    if match:
        return datetime.strptime(match.group(1), '%Y%m%d').date()

    return None


def parse_booked_dates(ical_text, source_name):
    booked = []
    skipped = 0
    events = ical_text.split('BEGIN:VEVENT')

    print(f"  Raw VEVENT blocks found: {len(events) - 1}")

    for i, event in enumerate(events[1:], 1):
        start = extract_date(event, 'DTSTART')
        end = extract_date(event, 'DTEND')

        if start and not end:
            dur_match = re.search(r'DURATION:P(\d+)D', event)
            if dur_match:
                end = start + timedelta(days=int(dur_match.group(1)))
            else:
                end = start + timedelta(days=1)

        summary_match = re.search(r'SUMMARY:(.*)', event)
        summary = summary_match.group(1).strip() if summary_match else '(no summary)'

        if start and end:
            booked.append((start, end))
            print(f"  [{source_name}] Event {i}: {start} to {end} — {summary}")
        else:
            skipped += 1
            preview = event.strip()[:200].replace('\n', ' | ')
            print(f"  [{source_name}] Event {i} SKIPPED: {preview}")

    if skipped:
        print(f"  [{source_name}] WARNING: {skipped} events could not be parsed")

    return booked


def find_available_windows(booked_dates):
    today = date.today()
    end_window = today + timedelta(days=LOOKAHEAD_DAYS)

    relevant = []
    for start, end in booked_dates:
        if end > today and start < end_window:
            relevant.append((max(start, today), min(end, end_window)))

    relevant.sort(key=lambda x: x[0])

    if not relevant:
        return [(today + timedelta(days=1), end_window)]

    merged = [relevant[0]]
    for start, end in relevant[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    print(f"\n  Merged blocked ranges (both calendars combined):")
    for s, e in merged:
        print(f"    BLOCKED: {s} to {e} ({(e - s).days} nights)")

    available = []

    if merged[0][0] > today + timedelta(days=1):
        available.append((today + timedelta(days=1), merged[0][0]))

    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        if (gap_end - gap_start).days >= MIN_NIGHTS:
            available.append((gap_start, gap_end))

    if merged[-1][1] < end_window:
        available.append((merged[-1][1], end_window))

    available = [(s, e) for s, e in available if (e - s).days >= MIN_NIGHTS]

    print(f"\n  Available windows:")
    for s, e in available:
        print(f"    OPEN: {s} to {e} ({(e - s).days} nights)")

    return available


def get_season_info(d):
    month = d.month
    if month in (12, 1, 2, 3):
        return {"title": "Ski Season Availability", "subtitle": "Book Your Mountain Getaway", "theme": "ski"}
    elif month in (4, 5):
        return {"title": "Spring Season Availability", "subtitle": "Enjoy the Mountain Transition", "theme": "spring"}
    elif month in (6, 7, 8):
        return {"title": "Summer Season Availability", "subtitle": "Alpine Adventures Await", "theme": "summer"}
    else:
        return {"title": "Fall Season Availability", "subtitle": "Experience Peak Foliage", "theme": "fall"}


def get_description(start):
    month = start.month
    if month in (12, 1, 2, 3):
        options = [
            "Prime ski season with exceptional powder conditions and stunning mountain views",
            "World-class skiing with easy access to all five peaks",
            "Perfect powder days and cozy evenings by the fireplace"
        ]
    elif month in (4, 5):
        options = [
            "Spring skiing combined with early summer mountain activities",
            "Longer days, sunshine, and spring snow conditions",
            "The best of both seasons as the mountain transitions"
        ]
    elif month in (6, 7, 8):
        options = [
            "Hiking, biking, and river activities in the Rocky Mountains",
            "Summer festivals, wildflowers, and endless mountain activities",
            "Perfect weather for outdoor adventures and exploring Main Street"
        ]
    else:
        options = [
            "Stunning fall foliage and crisp mountain air with fewer crowds",
            "Golden aspens and world-class mountain biking before ski season",
            "Peaceful autumn retreat with breathtaking Colorado colors"
        ]
    return options[start.day % len(options)]


def format_dates(start, end):
    if start.month == end.month and start.year == end.year:
        return f"{start.strftime('%B')} {start.day}\u2013{end.day}, {start.year}"
    elif start.year == end.year:
        return f"{start.strftime('%B')} {start.day} \u2013 {end.strftime('%B')} {end.day}, {start.year}"
    else:
        return f"{start.strftime('%B')} {start.day}, {start.year} \u2013 {end.strftime('%B')} {end.day}, {end.year}"


def format_title(start, end):
    nights = (end - start).days
    if nights <= 10:
        return f"{start.strftime('%B')} Week"
    elif start.day <= 15:
        return f"Early {start.strftime('%B')}"
    else:
        return f"Late {start.strftime('%B')}"


def main():
    if not AIRBNB_ICAL_URL:
        print("Error: AIRBNB_ICAL_URL environment variable not set")
        return

    # Fetch Airbnb calendar
    print("=== AIRBNB CALENDAR ===")
    print("Fetching iCal from Airbnb...")
    airbnb_text = fetch_ical(AIRBNB_ICAL_URL)
    print(f"Received {len(airbnb_text)} bytes\n")
    print("Parsing Airbnb bookings...")
    all_booked = parse_booked_dates(airbnb_text, "Airbnb")
    print(f"Airbnb entries: {len(all_booked)}")

    # Fetch VRBO calendar if available
    if VRBO_ICAL_URL:
        print(f"\n=== VRBO CALENDAR ===")
        print("Fetching iCal from VRBO...")
        vrbo_text = fetch_ical(VRBO_ICAL_URL)
        print(f"Received {len(vrbo_text)} bytes\n")
        print("Parsing VRBO bookings...")
        vrbo_booked = parse_booked_dates(vrbo_text, "VRBO")
        print(f"VRBO entries: {len(vrbo_booked)}")
        all_booked.extend(vrbo_booked)
        print(f"\nCombined total: {len(all_booked)} entries from both calendars")
    else:
        print("\nVRBO_ICAL_URL not set — using Airbnb calendar only")

    # Sort all bookings by start date
    all_booked.sort(key=lambda x: x[0])

    print(f"\n=== FINDING AVAILABILITY ===")
    available = find_available_windows(all_booked)
    print(f"\nTotal available: {len(available)} windows")

    blocks = []
    for start, end in available[:3]:
        nights = (end - start).days
        blocks.append({
            "title": format_title(start, end),
            "dates": format_dates(start, end),
            "description": get_description(start),
            "nights": nights
        })

    today = date.today()
    data = {
        "last_updated": today.isoformat() + "T00:00:00",
        "season": get_season_info(today),
        "availability": blocks,
        "meta": {
            "listing_id": "1286116063774289661",
            "airbnb_url": "https://www.airbnb.com/rooms/1286116063774289661"
        }
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n=== FINAL OUTPUT ===")
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
