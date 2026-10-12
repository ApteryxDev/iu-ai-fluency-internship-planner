"""Create calendar files that can be imported into Apple or Google Calendar."""

from datetime import datetime, timezone
from string import Template

from ..config import CONFIG
from ..models import now


def escape_ics(value):
    """Escape characters that have special meaning in calendar text fields."""
    return (
        str(value)
        .replace('\\', '\\\\')
        .replace('\r', '')
        .replace('\n', '\\n')
        .replace(';', '\\;')
        .replace(',', '\\,')
    )


def fold_ics(line):
    """Calendar lines should be no longer than 75 bytes, not 75 characters."""
    parts = []
    current_line = ''
    byte_count = 0

    for character in line:
        character_bytes = len(character.encode('utf-8'))
        if byte_count + character_bytes > 75:
            parts.append(current_line)
            current_line = ' '
            byte_count = 1
        current_line += character
        byte_count += character_bytes

    parts.append(current_line)
    return '\r\n'.join(parts)


def description(session):
    return Template(CONFIG['exports']['description_template']).substitute(session)


def calendar_bytes(sessions):
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:' + escape_ics(CONFIG['exports']['calendar']['product_id']),
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
    ]

    def calendar_time(iso_date):
        return datetime.fromisoformat(iso_date).astimezone(timezone.utc).strftime(
            '%Y%m%dT%H%M%SZ'
        )

    for session in sessions:
        lines.extend([
            'BEGIN:VEVENT',
            'UID:' + session['id'] + '@internship-studio.local',
            'DTSTAMP:' + calendar_time(now()),
            'DTSTART:' + calendar_time(session['start']),
            'DTEND:' + calendar_time(session['end']),
            'SUMMARY:' + escape_ics(session['title']),
            'DESCRIPTION:' + escape_ics(description(session)),
            'END:VEVENT',
        ])

    lines.append('END:VCALENDAR')
    return ('\r\n'.join(fold_ics(line) for line in lines) + '\r\n').encode('utf-8')
