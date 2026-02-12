#!/usr/bin/env python3
"""
Fetches Airbnb iCal calendar and generates availability.json
for the Rivers Edge Breckenridge website.
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, date

ICAL_URL = os.environ.get('AIRBNB_ICAL_URL', '')
OUTPUT_FILE = 'availability.json'
LOOKAHEAD_DAYS = 180
MIN_NIGHTS = 2


def fetch_ical(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8')


def parse_booked_dates(ical_text):
    booked = []
    events = ical_text.split('BEGIN:VEVENT')
    for event in events[1:]:
        dtstart = re.search(r'DTSTART;VALUE=DATE:(\d{8})', event)
        if not dtstart:
            dtstart = re.search(r'DTSTART:(\d{8})', event)
        dtend = re.search(r'DTEND;VALUE=DATE:(\d{8})', event)
        if not dtend:
            dtend = re.search(r'DTEND:(\d{8})', event)
        if dtstart and dtend:
            start = datetime.strptime(dtstart.group(1), '%Y%m%d').date()
            end = datetime.strptime(dtend.group(1), '%Y%m%d').date()
            booked.append((start, end))
    booked.sort(key=lambda x: x[0])
    return booked


def find_available_windows(booked_dates):
    today = date.today()
    end_window = today + timedelta(days=LOOKAHEAD_DAYS)

    relevant = []
    for start, end in booked_dates:
        if end > today and start < end_window:
            relevant.append((max(start, today), min(end, end_window)))

    if not relevant:
        return [(today + timedelta(days=1), end_window)]

    merged = [relevant[0]]
    for start, end in relevant[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

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
    if not ICAL_URL:
        print("Error: AIRBNB_ICAL_URL environment variable not set")
        return

    print("Fetching iCal from Airbnb...")
    ical_text = fetch_ical(ICAL_URL)

    print("Parsing booked dates...")
    booked = parse_booked_dates(ical_text)
    print(f"Found {len(booked)} booking entries")

    print("Finding available windows...")
    available = find_available_windows(booked)
    print(f"Found {len(available)} available windows")

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

    print(f"Updated {OUTPUT_FILE} with {len(blocks)} availability windows")


if __name__ == '__main__':
    main()
