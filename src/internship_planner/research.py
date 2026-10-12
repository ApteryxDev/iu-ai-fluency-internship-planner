"""Build research requests, check responses and keep a record of what came back."""

import copy
import json
from string import Template

from .config import CONFIG, digest
from .integrations.openai_client import OpenAIClient
from .models import ad_record, identifier, now, skill_record, text


def response_text(payload):
    """Collect the answer and source links from a Responses API result."""
    paragraphs = []
    citations = []

    for output in payload.get('output', []):
        if output.get('type') != 'message':
            continue
        for part in output.get('content', []):
            if part.get('type') != 'output_text':
                continue
            paragraphs.append(part.get('text', ''))
            citations.extend(
                note for note in part.get('annotations', [])
                if note.get('type') == 'url_citation'
            )

    return '\n'.join(paragraphs), citations


def parse_output(output):
    """Read a JSON answer, including one wrapped in a Markdown code block."""
    output = output.strip()
    if output.startswith('```'):
        output = output.split('\n', 1)[1].rsplit('```', 1)[0].strip()

    result = json.loads(output)
    if not isinstance(result, dict):
        raise ValueError('Expected a JSON object.')
    return result


def build_prompt(kind, args, snapshot):
    """Fill in the prompt template with the user's search choices."""
    research_settings = CONFIG['research']

    if kind == 'advertisements':
        roles = args.get('roles') or [
            role['keyword'] for role in research_settings['roles'] if role['selected']
        ]
        platforms = args.get('platforms') or [
            platform['label']
            for platform in research_settings['platforms']
            if platform['selected']
        ]
        if not roles:
            raise ValueError('Choose a role or add keywords.')

        platform_domains = {
            platform['label']: platform['domain']
            for platform in research_settings['platforms']
        }
        if any(platform not in platform_domains for platform in platforms):
            raise ValueError('Unknown recruitment platform.')

        limit = int(args.get('limit', research_settings['default_results']))
        if not 1 <= limit <= research_settings['maximum_results']:
            raise ValueError('Result count exceeds the configured limit.')

        selected_platforms = [
            {'label': name, 'domain': platform_domains[name]}
            for name in platforms
        ]
        return Template(CONFIG['prompts']['advertisements']).substitute(
            today=now(),
            roles=text(roles),
            location=text(args.get('location', research_settings['location'])),
            contract=text(args.get('contract', research_settings['contract'])),
            platforms=text(selected_platforms),
            limit=limit,
        )

    selected_advertisements = [
        ad for ad in snapshot['advertisements'] if ad.get('selected')
    ]
    if not selected_advertisements:
        raise ValueError('Select advertisements before researching learning options.')

    return Template(CONFIG['prompts']['skills']).substitute(
        today=now(),
        skills=text(
            args.get('skills') or CONFIG['learning']['default_skills']
            or 'Infer candidate skills for review'
        ),
        baseline=text(
            args.get('baseline') or CONFIG['learning']['default_baseline']
            or 'Unknown; flag assumptions'
        ),
        weeks=CONFIG['schedule']['weeks'],
        alternatives=CONFIG['learning']['maximum_alternatives'],
        advertisements=json.dumps(selected_advertisements, ensure_ascii=False),
    )


def research_worker(job_id, kind, prompt, key, model, domains, store, lock, jobs,
                    client_factory=None):
    """Run research and save the full response, even when something goes wrong."""
    record = {
        'id': identifier(),
        'kind': kind,
        'date': now(),
        'prompt': prompt,
        'model': model,
        'output': '',
        'review': '',
        'citations': [],
        'configuration_hash': digest(CONFIG),
        'configuration_snapshot': copy.deepcopy(CONFIG),
    }

    try:
        # Passing a fake client in tests avoids making a paid API request.
        client_type = client_factory or OpenAIClient
        client = client_type(
            key, model,
            CONFIG['research']['timeout_seconds'],
            CONFIG['research']['max_output_tokens'],
        )
        raw_response = client.research(prompt, domains)
        answer, citations = response_text(raw_response)
        record.update(output=answer, citations=citations, raw_response=raw_response)

        if raw_response.get('status') != 'completed':
            raise ValueError(
                'Research response was incomplete. Raw output was saved; '
                'reduce the count and retry.'
            )

        result = parse_output(answer)
        list_name = 'advertisements' if kind == 'advertisements' else 'skills'
        rows = result.get(list_name)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError('The response did not contain a valid list of candidate objects.')

        # Suggestions are not automatically verified, selected or approved.
        if kind == 'advertisements':
            candidates = [
                ad_record(row, 'OpenAI web research — excerpt only') for row in rows
            ]
        else:
            candidates = [skill_record(row) for row in rows]

        for candidate in candidates:
            candidate['research_id'] = record['id']

        with lock:
            if kind == 'advertisements':
                known_urls = {
                    ad.get('url') for ad in store.data['advertisements']
                    if ad.get('url')
                }
                unique_candidates = []
                for candidate in candidates:
                    source_url = candidate.get('url')
                    if source_url and source_url not in known_urls:
                        known_urls.add(source_url)
                        unique_candidates.append(candidate)
                candidates = unique_candidates
                store.data['advertisements'].extend(candidates)
            else:
                store.data['skills'].extend(candidates)

            record.update(
                summary=text(result.get('summary')),
                limitations=text(result.get('limitations')),
                status='completed',
            )
            store.data['research'].append(record)
            store.save('Completed ' + kind + ' research')
            jobs[job_id] = {
                'status': 'completed',
                'message': f'Added {len(candidates)} candidates. Review original sources before approval.',
            }

    except Exception as error:
        message = str(error)
        if key:
            message = message.replace(key, '[redacted]')
        record.update(status='failed', error=message)
        with lock:
            store.data['research'].append(record)
            store.save('Research failed; evidence retained')
            jobs[job_id] = {'status': 'failed', 'message': message}
