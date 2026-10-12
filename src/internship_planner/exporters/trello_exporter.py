"""Prepare Trello card details for copying or importing manually."""

from ..config import CONFIG
from .calendar_exporter import description
from .csv_exporter import csv_bytes


def trello_rows(sessions):
    rows = []
    for session in sessions:
        rows.append({
            'Name': session['title'],
            'Description': description(session),
            'Due': session['end'],
            'Start': session['start'],
            'List': f"{CONFIG['exports']['trello']['list_prefix']} {session['week']}",
        })
    return rows


def trello_bytes(sessions):
    return csv_bytes(trello_rows(sessions), CONFIG['exports']['trello']['columns'])


def trello_card_text(session):
    return f"{session['title']}\n\n{description(session)}\n\nDue: {session['end']}"
