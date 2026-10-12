"""Run the local web app and connect buttons to the planner functions."""
import copy
import csv
import io
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .config import CONFIG, CONFIG_PATH, ROOT, digest, public_config
from .models import ad_record, identifier, now, safe_url, skill_record, text, valid_hours
from .repository import Store
from .research import build_prompt, research_worker
from .scheduler import generate_schedule
from .exporters.calendar_exporter import calendar_bytes
from .exporters.csv_exporter import csv_bytes
from .exporters.obsidian_exporter import obsidian_bytes
from .exporters.trello_exporter import trello_bytes


STORE = Store(ROOT / CONFIG['data']['file'])
LOCK = threading.RLock()
TOKEN = secrets.token_urlsafe(32)
API_KEY = os.environ.get('OPENAI_API_KEY', '')
MODEL = os.environ.get('OPENAI_MODEL', CONFIG['research']['model'])
JOBS = {}
PLATFORMS = {platform['label']: platform['domain'] for platform in CONFIG['research']['platforms']}


def validate_related_ads(option, advertisements):
    existing_ids = {ad['id'] for ad in advertisements}
    if any(ad_id not in existing_ids for ad_id in option.get('related_advertisement_ids', [])):
        raise ValueError('Related advertisement ID does not exist in your collection.')

class Handler(BaseHTTPRequestHandler):
    """Serve pages and apply changes requested by the local browser."""

    def log_message(self, *args):
        pass

    def send(self, status, body, ctype='application/json', filename=None):
        """Send JSON, a page or a downloadable file back to the browser."""
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode()
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def trusted_host(self):
        # This app is for one computer, not an open network service.
        host = self.headers.get('Host', '')
        port = self.server.server_port
        return host in (f'127.0.0.1:{port}', f'localhost:{port}')

    def do_GET(self):
        if not self.trusted_host():
            return self.send(403, {'error': 'Local access only.'})
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == '/api/state':
                with LOCK:
                    data = json.loads(json.dumps(STORE.data))
                    # Keep large raw API responses in the evidence file, not the page state.
                    for record in data['research']:
                        record.pop('raw_response', None)
                    page_state = {
                        'data': data,
                        'token': TOKEN,
                        'key_configured': bool(API_KEY),
                        'model': MODEL,
                        'jobs': JOBS,
                        'config': public_config(CONFIG),
                        'configuration_hash': digest(CONFIG),
                    }
                    return self.send(200, page_state)
            if path == '/theme.css':
                css = ':root{' + ''.join(('--' + k + ':' + v + ';' for k, v in CONFIG['interface']['theme'].items())) + '}'
                return self.send(200, css, 'text/css')
            if path == '/api/config':
                return self.send(200, {'configuration': CONFIG, 'hash': digest(CONFIG), 'filename': CONFIG_PATH.name})
            if path.startswith('/export/'):
                with LOCK:
                    d = json.loads(json.dumps(STORE.data))
                kind = path.rsplit('/', 1)[1]
                setting = CONFIG['exports'].get(kind)
                if not isinstance(setting, dict) or not setting.get('enabled'):
                    raise ValueError('This export is disabled in config.yml.')
                if kind == 'advertisements':
                    return self.send(200, csv_bytes(d['advertisements'], CONFIG['exports']['advertisements']['columns']), 'text/csv; charset=utf-8', setting['filename'])
                if kind == 'skills':
                    return self.send(200, csv_bytes(d['skills'], CONFIG['exports']['skills']['columns']), 'text/csv; charset=utf-8', setting['filename'])
                if kind == 'evidence':
                    return self.send(200, json.dumps(d, ensure_ascii=False, indent=2), 'application/json', setting['filename'])
                if not d['schedule']:
                    raise ValueError('Generate a schedule before exporting it.')
                if kind == 'calendar':
                    return self.send(200, calendar_bytes(d['schedule']), 'text/calendar; charset=utf-8', setting['filename'])
                if kind == 'obsidian':
                    return self.send(200, obsidian_bytes(d), 'application/zip', setting['filename'])
                if kind == 'trello':
                    return self.send(200, trello_bytes(d['schedule']), 'text/csv; charset=utf-8', setting['filename'])
                raise ValueError('Unknown export.')
            files = {'/': 'index.html', '/style.css': 'style.css', '/app.js': 'app.js'}
            if path in files:
                ctype = {'/': 'text/html; charset=utf-8', '/style.css': 'text/css', '/app.js': 'text/javascript'}[path]
                return self.send(200, (ROOT / 'src/internship_planner/web' / files[path]).read_bytes(), ctype)
            self.send(404, {'error': 'Not found'})
        except (ValueError, KeyError) as e:
            self.send(400, {'error': str(e)})
        except Exception:
            self.send(500, {'error': 'Unable to read data or export. Check local file permissions.'})

    def do_POST(self):
        global API_KEY, MODEL
        if not self.trusted_host() or not secrets.compare_digest(self.headers.get('X-App-Token', ''), TOKEN):
            return self.send(403, {'error': 'Reload this local app before saving.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length < 0 or length > CONFIG['limits']['request_bytes']:
                raise ValueError('Request too large; use a smaller import.')
            args = json.loads(self.rfile.read(length))
            if not isinstance(args, dict):
                raise ValueError('A JSON object is required.')
            with LOCK:
                result = self.action(urllib.parse.urlsplit(self.path).path, args)
            self.send(200, result or {'ok': True})
        except (ValueError, KeyError, TypeError) as e:
            self.send(400, {'error': str(e)})
        except Exception:
            self.send(500, {'error': 'The action could not be saved. Check local file permissions.'})

    def action(self, path, args):
        global API_KEY, MODEL
        if path == '/api/settings':
            API_KEY = text(args.get('key'), 500).strip() or API_KEY
            if args.get('forget'):
                API_KEY = ''
            MODEL = text(args.get('model'), 100).strip() or MODEL
            return {'ok': True, 'key_configured': bool(API_KEY)}
        if path == '/api/advertisements/add':
            entry = ad_record(args)
            if entry['url'] and any((a.get('url') == entry['url'] for a in STORE.data['advertisements'])):
                raise ValueError('This source URL is already in your collection.')
            STORE.data['advertisements'].append(entry)
            # Editing the plan makes the previous schedule out of date.
            STORE.data['schedule'] = []
            STORE.save('Added advertisement')
        elif path == '/api/advertisements/import':
            reader = csv.DictReader(io.StringIO(args['csv'].lstrip('\ufeff')))
            if not reader.fieldnames or 'title' not in reader.fieldnames:
                raise ValueError('CSV must include a title column.')
            records = [ad_record(r, 'CSV import') for r in reader]
            if len(records) > CONFIG['limits']['csv_rows']:
                raise ValueError('Import at most %s records at a time.' % CONFIG['limits']['csv_rows'])
            known_urls = {
                ad.get('url') for ad in STORE.data['advertisements'] if ad.get('url')
            }
            added = []
            for record in records:
                if record['url'] and record['url'] in known_urls:
                    continue
                added.append(record)
                if record['url']:
                    known_urls.add(record['url'])
            STORE.data['advertisements'].extend(added)
            STORE.data['schedule'] = []
            STORE.save('Imported %s advertisements' % len(added))
            return {'ok': True, 'message': 'Imported %s records; skipped %s repeated source URLs.' % (len(added), len(records) - len(added))}
        elif path in ('/api/advertisements/update', '/api/skills/update'):
            group = 'advertisements' if 'advertisements' in path else 'skills'
            row = next((r for r in STORE.data[group] if r['id'] == args['id']), None)
            if row is None:
                raise ValueError('Record no longer exists. Reload the page.')
            before = copy.deepcopy(row)
            candidate = copy.deepcopy(row)
            if group == 'skills' and args.get('approved'):
                valid_hours(args.get('hours', candidate.get('hours')))
                needs_source = (
                    CONFIG['learning']['require_source_for_approval']
                    and not safe_url(args.get('url', candidate.get('url')))
                )
                needs_review = (
                    CONFIG['learning']['require_review_for_approval']
                    and not text(args.get('review', candidate.get('review'))).strip()
                )
                if needs_source or needs_review:
                    raise ValueError(
                        'Add an official URL and your source verification notes before approving.'
                    )
            if group == 'advertisements':
                already_selected = sum(
                    bool(ad.get('selected')) for ad in STORE.data[group]
                )
                limit = CONFIG['research']['selection_limit']
                if args.get('selected') and not candidate.get('selected') and already_selected >= limit:
                    raise ValueError(f'The selection limit is {limit} advertisements. Unselect one first.')
                fields = ('title', 'employer', 'location', 'duration', 'requirements', 'original_text', 'review', 'selection_reason')
                if 'selected' in args:
                    candidate['selected'] = bool(args['selected'])
                if 'verified' in args:
                    candidate['verified'] = bool(args['verified'])
            else:
                fields = ('skill', 'jobs', 'certification', 'issuer', 'kind', 'difficulty', 'duration', 'prerequisites', 'rationale', 'recognition', 'alternatives', 'review')
                if 'hours' in args:
                    candidate['hours'] = valid_hours(args['hours'], True)
                if 'approved' in args:
                    candidate['approved'] = bool(args['approved'])
            for field_name in fields:
                if field_name in args:
                    candidate[field_name] = text(args[field_name])
            if group == 'skills' and 'related_advertisement_ids' in args:
                ids = args['related_advertisement_ids']
                if not isinstance(ids, list) or any((not isinstance(v, str) for v in ids)):
                    raise ValueError('Related advertisements must be a list of IDs.')
                candidate['related_advertisement_ids'] = list(dict.fromkeys(ids))
                validate_related_ads(candidate, STORE.data['advertisements'])
            if 'url' in args:
                candidate['url'] = safe_url(args['url'])
            if group == 'advertisements' and (not candidate.get('title', '').strip()):
                raise ValueError('An advertisement title is required.')
            if group == 'skills' and (not candidate.get('skill', '').strip()):
                raise ValueError('A learning option must name a skill.')
            if group == 'skills' and candidate.get('approved'):
                valid_hours(candidate.get('hours'))
                if CONFIG['learning']['require_source_for_approval'] and (not candidate.get('url')):
                    raise ValueError('Approved learning options must have an official URL.')
                if CONFIG['learning']['require_review_for_approval'] and (not candidate.get('review', '').strip()):
                    raise ValueError('Approved learning options must have source verification notes.')
            if group == 'advertisements' and candidate.get('url'):
                duplicate_url = any(
                    ad['id'] != candidate['id'] and ad.get('url') == candidate['url']
                    for ad in STORE.data['advertisements']
                )
                if duplicate_url:
                    raise ValueError('Another advertisement already has that source URL.')
            row.clear()
            row.update(candidate)
            STORE.data['events'].append({
                'date': now(),
                'action': 'Record revision',
                'group': group,
                'before': before,
                'after': copy.deepcopy(row),
            })
            STORE.data['schedule'] = []
            STORE.save('Updated ' + group + ' record; regenerate schedule')
        elif path == '/api/skills/add':
            new_option = skill_record(args)
            validate_related_ads(new_option, STORE.data['advertisements'])
            STORE.data['skills'].append(new_option)
            STORE.data['schedule'] = []
            STORE.save('Added manual learning option')
        elif path == '/api/skills/reorder':
            rows = STORE.data['skills']
            index = next((i for i, r in enumerate(rows) if r['id'] == args['id']), None)
            if index is None:
                raise ValueError('Learning option no longer exists.')
            target = index + (-1 if args.get('direction') == 'up' else 1)
            if 0 <= target < len(rows):
                rows[index], rows[target] = (rows[target], rows[index])
            STORE.data['schedule'] = []
            STORE.save('Changed learning priority order')
        elif path == '/api/delete':
            group = args['group']
            if group not in ('advertisements', 'skills'):
                raise ValueError('Unknown record type.')
            if not any((r['id'] == args['id'] for r in STORE.data[group])):
                raise ValueError('Record does not exist.')
            STORE.data[group] = [r for r in STORE.data[group] if r['id'] != args['id']]
            if group == 'advertisements':
                for skill in STORE.data['skills']:
                    skill['related_advertisement_ids'] = [v for v in skill.get('related_advertisement_ids', []) if v != args['id']]
            STORE.data['schedule'] = []
            STORE.save('Deleted ' + group + ' record')
        elif path == '/api/research':
            if not API_KEY:
                raise ValueError('Enter your OpenAI API key in Settings first.')
            if any((j['status'] == 'running' for j in JOBS.values())):
                raise ValueError('A research request is already running.')
            kind = args['kind']
            if kind not in ('advertisements', 'skills'):
                raise ValueError('Unknown research type.')
            snapshot = json.loads(json.dumps(STORE.data))
            prompt = build_prompt(kind, args, snapshot)
            domains = []
            if kind == 'advertisements' and CONFIG['research']['restrict_to_selected_platforms']:
                labels = args.get('platforms') or [p['label'] for p in CONFIG['research']['platforms'] if p['selected']]
                domains = [PLATFORMS[p] for p in labels] + CONFIG['research']['extra_allowed_domains']
                if not domains:
                    raise ValueError('Domain restriction needs at least one selected platform or extra domain.')
            job_id = identifier()
            JOBS[job_id] = {'status': 'running', 'message': 'Searching sources and preparing candidates…'}
            # Research runs separately so the browser can show progress while it works.
            worker = threading.Thread(
                target=research_worker,
                args=(job_id, kind, prompt, API_KEY, MODEL, domains, STORE, LOCK, JOBS),
                daemon=True,
            )
            worker.start()
            return {'job_id': job_id}
        elif path == '/api/evidence':
            if args.get('id'):
                row = next((r for r in STORE.data['research'] if r['id'] == args['id']), None)
                if row is None:
                    raise ValueError('Research record does not exist.')
                row['review'] = text(args.get('review'))
            else:
                STORE.data['research'].append({'id': identifier(), 'kind': 'Manual evidence', 'date': now(), 'prompt': text(args.get('prompt')), 'output': text(args.get('output')), 'review': text(args.get('review')), 'citations': []})
            STORE.save('Saved research review')
        elif path == '/api/schedule':
            sessions, summary = generate_schedule(STORE.data['skills'], args)
            STORE.data['schedule'] = sessions
            STORE.data['schedule_settings'] = {**CONFIG['schedule'], **args}
            STORE.data['schedule_summary'] = summary
            STORE.data['schedule_configuration'] = {'hash': digest(CONFIG), 'snapshot': copy.deepcopy(CONFIG)}
            STORE.save('Generated %s-week schedule from approved options' % CONFIG['schedule']['weeks'])
            return {'ok': True, 'summary': summary}
        else:
            raise ValueError('Unknown action.')



def main():
    """Start the local server, then optionally open it in the browser."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=CONFIG['server']['port'])
    parser.add_argument('--no-browser', action='store_true')
    options = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', options.port), Handler)
    config_hash = digest(CONFIG)
    if STORE.data.get('configuration_hash') != config_hash:
        if STORE.data.get('schedule') and STORE.data.get('schedule_configuration', {}).get('hash') != config_hash:
            STORE.data['schedule'] = []
            STORE.data['schedule_settings'] = {}
            STORE.data.pop('schedule_summary', None)
        STORE.data['configuration_hash'] = config_hash
        STORE.data['configuration_snapshot'] = copy.deepcopy(CONFIG)
        STORE.save('Loaded configuration ' + config_hash)
    url = 'http://127.0.0.1:' + str(server.server_port)
    print(CONFIG['project']['name'] + ': ' + url + '\nPress Ctrl+C to stop. API key is held in memory only.', flush=True)
    if not options.no_browser and CONFIG['server']['open_browser']:
        threading.Timer(CONFIG['server']['browser_delay_seconds'], lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
if __name__ == '__main__':
    main()
