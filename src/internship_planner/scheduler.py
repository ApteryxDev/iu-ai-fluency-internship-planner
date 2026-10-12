"""Turn approved courses into study sessions without exceeding the weekly limit."""

from datetime import date, datetime, time, timedelta, timezone
from string import Template
from zoneinfo import ZoneInfo

from .config import CONFIG
from .models import identifier, valid_hours


# Tiny remaining-hour values are just floating-point rounding errors.
EPSILON = 0.00001


def generate_schedule(skills, options):
    """Fill study days in priority order and report anything that does not fit."""
    approved = [skill for skill in skills if skill.get('approved')]
    if not approved:
        raise ValueError('Approve at least one researched learning option first.')

    settings = CONFIG['schedule']
    weekly_hours = valid_hours(
        options.get('weekly_hours', settings['default_weekly_hours'])
    )
    minimum = settings['minimum_weekly_hours']
    maximum = settings['maximum_weekly_hours']
    if not minimum <= weekly_hours <= maximum:
        raise ValueError(f'Choose between {minimum:g} and {maximum:g} study hours per week.')

    start_date = date.fromisoformat(options['start_date'])
    start_time = time.fromisoformat(options.get('start_time', settings['start_time']))
    study_days = sorted(set(int(day) for day in options.get('days', settings['days'])))
    if not study_days or any(day < 0 or day > 6 for day in study_days):
        raise ValueError('Choose at least one study day.')

    local_timezone = ZoneInfo(options.get('timezone', settings['timezone']))
    hours_left = [valid_hours(skill.get('hours')) for skill in approved]
    total_requested = sum(hours_left)
    hours_per_day = weekly_hours / len(study_days)

    sessions = []
    skill_index = 0

    for week in range(settings['weeks']):
        for day_offset in range(7):
            study_date = start_date + timedelta(days=7 * week + day_offset)
            if study_date.weekday() not in study_days:
                continue

            # Start in the chosen timezone, then save UTC for calendar exports.
            current_time = datetime.combine(
                study_date, start_time, local_timezone
            ).astimezone(timezone.utc)
            available_today = hours_per_day

            while available_today > EPSILON and skill_index < len(approved):
                if hours_left[skill_index] < EPSILON:
                    skill_index += 1
                    continue

                skill = approved[skill_index]
                session_hours = min(available_today, hours_left[skill_index])
                end_time = current_time + timedelta(hours=session_hours)
                title = Template(settings['title_template']).substitute(
                    skill=skill['skill'], certification=skill['certification']
                )

                sessions.append({
                    'id': identifier(),
                    'skill_id': skill['id'],
                    'week': week + 1,
                    'title': title,
                    'jobs': skill['jobs'],
                    'skill': skill['skill'],
                    'certification': skill['certification'],
                    'difficulty': skill['difficulty'],
                    'resource': skill['url'],
                    'start': current_time.isoformat(),
                    'end': end_time.isoformat(),
                    'hours': round(session_hours, 4),
                    'evidence': settings['evidence_requirement'],
                    'rationale': skill['rationale'],
                    'status': settings['session_status'],
                })

                current_time = end_time
                available_today -= session_hours
                hours_left[skill_index] -= session_hours

    overflow = [
        {'skill': skill['skill'], 'remaining_hours': round(remaining, 2)}
        for skill, remaining in zip(approved, hours_left)
        if remaining > EPSILON
    ]
    summary = {
        'allocated_hours': round(total_requested - sum(hours_left), 2),
        'weeks': settings['weeks'],
        'capacity_hours': weekly_hours * settings['weeks'],
        'overflow': overflow,
        'note': 'Preparation estimates are not guarantees of certification. Unused time remains free.',
    }
    return sessions, summary
