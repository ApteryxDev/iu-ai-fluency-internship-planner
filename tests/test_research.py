import json
import threading
from internship_planner.research import research_worker, build_prompt
from internship_planner.repository import Store


class FakeClient:
    response=None
    def __init__(self,*args):pass
    def research(self,*args):return self.response


def test_success_preserves_prompt_and_deduplicates(tmp_path):
    store=Store(tmp_path/'data.json')
    FakeClient.response={'status':'completed','output':[{'type':'message','content':[{
        'type':'output_text','text':json.dumps({'advertisements':[
        {'title':'Internship 1','url':'https://example.org/job'},
        {'title':'Internship 1 copy','url':'https://example.org/job'}], 'summary':'Search summary'})}]}]}
    jobs={}
    research_worker('job','advertisements','exact prompt','not-stored-key','fake-model',[],
                    store,threading.RLock(),jobs, FakeClient)
    assert jobs['job']['status']=='completed'
    assert len(store.data['advertisements'])==1
    assert store.data['advertisements'][0]['verified'] is False
    assert store.data['research'][0]['prompt']=='exact prompt'
    assert store.data['research'][0]['raw_response']==FakeClient.response
    assert 'not-stored-key' not in store.path.read_text()


def test_bad_response_preserved(tmp_path):
    store=Store(tmp_path/'data.json')
    FakeClient.response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'not JSON'}]}]}
    jobs={}
    research_worker('job','skills','prompt','secret','test',[],store,threading.RLock(),jobs, FakeClient)
    assert jobs['job']['status']=='failed'
    assert store.data['research'][0]['output']=='not JSON'
    assert store.data['skills']==[]


def test_prompt_from_selected_ads():
    snapshot={'advertisements':[{'title':'Intern', 'selected':True,'requirements':'Docker'}]}
    prompt=build_prompt('skills',{'skills':'Docker','baseline':'Beginner'},snapshot)
    assert 'Docker' in prompt and 'Beginner' in prompt
