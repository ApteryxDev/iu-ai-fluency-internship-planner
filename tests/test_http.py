"""Offline, end-to-end smoke test for the browser-facing API."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import pytest
from internship_planner import app
from internship_planner.repository import Store


@pytest.fixture
def server(tmp_path,monkeypatch):
    store=Store(tmp_path/'project.json')
    monkeypatch.setattr(app,'STORE',store)
    httpd=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    thread=threading.Thread(target=httpd.serve_forever,daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}', store
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def post(base,endpoint,payload,token=app.TOKEN):
    req=urllib.request.Request(base+endpoint, data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-App-Token':token},method='POST')
    with urllib.request.urlopen(req,timeout=4) as response:
        return json.load(response)


def test_manual_browser_workflow(server):
    base,store=server
    with urllib.request.urlopen(base+'/',timeout=4) as response:
        page=response.read()
        assert b'Internship' in page
        # The three wireframe panels and both review boxes are on one page.
        for element in (b'id="ads"',b'id="skills"',b'id="exports"',b'id="adReview"',b'id="skillReview"',b'id="gantt"'):
            assert element in page
    with urllib.request.urlopen(base+'/app.js',timeout=4) as response:
        assert b'linkedAdvertisement' in response.read()
    with urllib.request.urlopen(base+'/api/state',timeout=4) as response:
        assert json.load(response)['data']['advertisements']==[]
    with pytest.raises(urllib.error.HTTPError) as err:
        post(base,'/api/advertisements/add',{'title':'Bad token'},token='wrong')
    assert err.value.code==403
    post(base,'/api/advertisements/add',{'title':'Fictional internship','url':'https://example.org/ad',
                                         'requirements':'Python, SQL','selection_reason':'Relevant to AI'})
    ad=store.data['advertisements'][0]
    post(base,'/api/advertisements/update',{'id':ad['id'],'verified':True,'selected':True})
    post(base,'/api/skills/add',{'skill':'PyTorch','hours':8,'url':'https://example.org/course',
                                 'review':'Source checked', 'related_advertisement_ids':[ad['id']]})
    skill=store.data['skills'][0]
    post(base,'/api/skills/update',{'id':skill['id'],'approved':True})
    result=post(base,'/api/schedule',{'start_date':'2026-10-19','weekly_hours':6})
    assert result['summary']['allocated_hours']==8
    for kind in ('advertisements','skills','trello','calendar','obsidian','evidence'):
        with urllib.request.urlopen(base+'/export/'+kind,timeout=4) as response:
            assert response.status==200 and len(response.read())>15
    assert Store(store.path).data['advertisements'][0]['selected'] is True


def test_csv_import_with_quoted_fields_and_duplicates(server):
    base,store=server
    source='title,employer,url,requirements\n"Data, AI",Example,https://example.org/a,"Python, SQL"\nDuplicate,Example,https://example.org/a,SQL\nMinimal,,,\n'
    result=post(base,'/api/advertisements/import',{'csv':source})
    assert 'Imported 2 records' in result['message']
    assert len(store.data['advertisements'])==2
    assert store.data['advertisements'][0]['title']=='Data, AI'
    assert store.data['advertisements'][1]['employer']==''
