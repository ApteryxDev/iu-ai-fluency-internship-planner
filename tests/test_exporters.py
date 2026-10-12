import csv
import io
import json
import zipfile
from internship_planner.exporters.csv_exporter import csv_bytes
from internship_planner.exporters.calendar_exporter import calendar_bytes
from internship_planner.exporters.obsidian_exporter import obsidian_bytes
from internship_planner.exporters.trello_exporter import trello_bytes
from internship_planner.scheduler import generate_schedule
from internship_planner.models import skill_record


def test_csv_quoted_commas_and_excel_formulas():
    data=csv_bytes([{'title':'Paris, France', 'requirements':'=HYPERLINK("oops")'},
                    {'title':'Line\nBreak','requirements':''}],['title','requirements'])
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assert rows[0]['title']=='Paris, France'
    assert rows[0]['requirements'].startswith("'=HYPERLINK")
    assert rows[1]['title']=='Line\nBreak'


def test_exports():
    option=skill_record({'skill':'PyTorch','certification':'Online course', 'hours':8,
                         'review':'reviewed','url':'https://example.org/course'})
    option['approved']=True
    sessions,summary=generate_schedule([option],{'start_date':'2026-10-19'})
    ics=calendar_bytes(sessions)
    assert b'BEGIN:VCALENDAR' in ics and b'BEGIN:VEVENT' in ics
    assert all(len(line)<=75 for line in ics.split(b'\r\n'))
    rows=list(csv.DictReader(io.StringIO(trello_bytes(sessions).decode('utf-8-sig'))))
    assert len(rows)==len(sessions)
    assert 'PyTorch' in rows[0]['Name']
    state={'advertisements':[], 'skills':[option], 'research':[{'id':'manual-1','kind':'Manual',
             'date':'2026-10-11','prompt':'Question','output':'Response','review':'My decisions'}],
           'schedule':sessions}
    with zipfile.ZipFile(io.BytesIO(obsidian_bytes(state))) as archive:
        files=archive.namelist()
        assert 'Internship-Programme/Programme.md' in files
        assert any(name.endswith('.ics') for name in files)
        assert any(name.endswith('/manual-1.md') for name in files)
