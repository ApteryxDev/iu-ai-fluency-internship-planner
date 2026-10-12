from collections import defaultdict
from datetime import datetime
import pytest
from internship_planner.scheduler import generate_schedule
from internship_planner.models import skill_record


def option(hours):
    entry=skill_record({'skill':'Python', 'certification':'Course','jobs':'AI Engineer',
                        'hours':hours, 'url':'https://example.org/c','review':'checked'})
    entry['approved']=True
    return entry


def test_weekly_capacity_and_overflow():
    sessions,summary=generate_schedule([option(100)],{'start_date':'2026-10-19','days':[0,2,5], 'weekly_hours':6})
    assert summary['weeks']==12
    assert summary['capacity_hours']==72
    assert summary['allocated_hours']==72
    assert summary['overflow'][0]['remaining_hours']==28
    weekly=defaultdict(float)
    for session in sessions:
        weekly[session['week']]+=session['hours']
        assert datetime.fromisoformat(session['end'])>datetime.fromisoformat(session['start'])
    assert max(weekly.values())<=6.001


def test_dst_paris_time_shift():
    sessions,_=generate_schedule([option(15)],{'start_date':'2026-10-19','days':[0], 'weekly_hours':6,
                      'timezone':'Europe/Paris','start_time':'18:00'})
    assert sessions[0]['start'].endswith('16:00:00+00:00')
    assert sessions[1]['start'].endswith('17:00:00+00:00')


def test_no_approval_or_invalid_times():
    entry=option(3)
    entry['approved']=False
    with pytest.raises(ValueError):generate_schedule([entry],{'start_date':'2026-10-19'})
    with pytest.raises(ValueError):generate_schedule([option(3)],{'start_date':'2026-10-19','weekly_hours':20})
    with pytest.raises(ValueError):generate_schedule([option(3)],{'start_date':'2026-10-19','days':[]})
    with pytest.raises(ValueError):generate_schedule([option(0)],{'start_date':'2026-10-19'})
