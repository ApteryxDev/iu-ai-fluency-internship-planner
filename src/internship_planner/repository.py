"""Save the planner's records in a local JSON file."""

import json
from pathlib import Path

from .models import now


class Store:
    """Keep the current project in memory and write it to disk when it changes."""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
        else:
            self.data = {}

        if not isinstance(self.data, dict):
            raise ValueError('data/project.json must contain a JSON object.')

        collections = ('advertisements', 'tasks', 'events', 'skills', 'research', 'schedule')
        for name in collections:
            self.data.setdefault(name, [])

        self.data.setdefault('schedule_settings', {})
        self.data.setdefault('revision', 0)

        for name in ('advertisements', 'skills', 'research', 'schedule', 'events'):
            if not isinstance(self.data[name], list):
                raise ValueError('Project JSON lists are malformed; restore a backup.')

    def save(self, action):
        """Record a change and replace the JSON file once writing has finished."""
        self.data['revision'] += 1
        self.data['events'].append({'date': now(), 'action': action})
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # A temporary file avoids leaving half-written JSON after an interruption.
        temporary_file = self.path.with_suffix('.tmp')
        temporary_file.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        temporary_file.replace(self.path)
