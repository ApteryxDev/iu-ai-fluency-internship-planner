import json
import pytest

from internship_planner.models import Advertisement, LearningOption, ad_record, skill_record, valid_hours
from internship_planner.repository import Store
from internship_planner import app


def test_dataclasses_and_creation():
    advert = Advertisement.from_dict(ad_record({'title': 'Fictional AI internship', 'requirements': 'Python\nSQL'}))
    assert advert.title == 'Fictional AI internship'
    assert advert.requirement_lines == ['Python', 'SQL']
    assert advert.selected is False and advert.verified is False
    option = LearningOption.from_dict(skill_record({'skill': 'Docker', 'hours': 5}))
    assert option.approved is False and option.hours == 5
    with pytest.raises(ValueError):
        ad_record({'employer':'No title'})
    with pytest.raises(ValueError):
        skill_record({'skill':''})
    with pytest.raises(ValueError):
        valid_hours(float('nan'))


def test_empty_json_and_persistence(tmp_path):
    path = tmp_path/'project.json'
    path.write_text('{}')
    store = Store(path)
    assert store.data['advertisements'] == [] and store.data['events'] == []
    record = ad_record({'title':'Test'})
    store.data['advertisements'].append(record)
    store.save('Added ad')
    again = Store(path)
    assert again.data['advertisements'][0]['id'] == record['id']
    assert again.data['revision'] == 1
    assert again.data['events'][-1]['action'] == 'Added ad'


def test_invalid_json_shape(tmp_path):
    path=tmp_path/'project.json'
    path.write_text('[]')
    with pytest.raises(ValueError):Store(path)


def test_updates_are_atomic_and_selection_limit(tmp_path,monkeypatch):
    store=Store(tmp_path/'project.json')
    store.data['advertisements']=[ad_record({'title':f'Job {i}', 'url':f'https://example.org/{i}'}) for i in range(6)]
    monkeypatch.setattr(app,'STORE',store)
    handler=object.__new__(app.Handler)
    for ad in store.data['advertisements'][:5]:
        handler.action('/api/advertisements/update', {'id':ad['id'],'selected':True})
    sixth=store.data['advertisements'][-1]
    with pytest.raises(ValueError,match='selection limit'):
        handler.action('/api/advertisements/update', {'id':sixth['id'],'selected':True})
    assert not sixth['selected']
    with pytest.raises(ValueError,match='source URL'):
        handler.action('/api/advertisements/update',{'id':sixth['id'],'url':'https://example.org/0','title':'CHANGED'})
    assert sixth['title']!='CHANGED'
    assert len(store.data['events']) >= 10


def test_learning_option_requires_checked_resource(tmp_path,monkeypatch):
    store=Store(tmp_path/'project.json')
    ad=ad_record({'title':'Sample ad','url':'https://example.org/ad'})
    store.data['advertisements'].append(ad)
    monkeypatch.setattr(app,'STORE',store)
    handler=object.__new__(app.Handler)
    handler.action('/api/skills/add',{'skill':'Python', 'related_advertisement_ids':[ad['id']]})
    item=store.data['skills'][0]
    assert item['related_advertisement_ids']==[ad['id']]
    with pytest.raises(ValueError):
        handler.action('/api/skills/update',{'id':item['id'],'approved':True})
    assert item['approved'] is False
    handler.action('/api/skills/update',{'id':item['id'],'approved':True,'hours':12,'url':'https://example.org/course','review':'Manually checked course page'})
    assert item['approved'] is True
    with pytest.raises(ValueError):
        handler.action('/api/skills/update',{'id':item['id'],'hours':0})
    assert item['hours']==12
