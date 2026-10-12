"""Read config.yml and check that the app has the settings it expects."""
import copy
import hashlib
import json
import math
import os
import re
from datetime import time
from pathlib import Path
from string import Template
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
try:
    import yaml
except ImportError:
    raise SystemExit('PyYAML is required. Run Launch.command or install requirements.txt in your virtual environment.')
ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.environ.get('PLANNER_CONFIG', str(ROOT / 'config.yml'))).expanduser().resolve()

class ConfigError(ValueError):
    pass
_ALLOWED_KEYS = {'data': {'file'},
 'exports': {'advertisements',
             'calendar',
             'description_template',
             'evidence',
             'obsidian',
             'programme_note',
             'programme_title',
             'skills',
             'trello'},
 'exports.advertisements': {'filename', 'enabled', 'columns'},
 'exports.calendar': {'filename', 'product_id', 'enabled'},
 'exports.evidence': {'filename', 'enabled'},
 'exports.obsidian': {'calendar_file',
                      'enabled',
                      'evidence_folder',
                      'filename',
                      'folder',
                      'programme_file',
                      'skills_folder'},
 'exports.skills': {'filename', 'enabled', 'columns'},
 'exports.trello': {'filename', 'list_prefix', 'enabled', 'columns'},
 'interface': {'copy',
               'day_labels',
               'locale',
               'messages',
               'notice_ms',
               'pages',
               'placeholders',
               'poll_ms',
               'poll_retry_ms',
               'theme'},
 'interface.pages': {'skills', 'ads', 'exports'},
 'interface.pages.ads': {'title', 'subtitle', 'label'},
 'interface.pages.exports': {'title', 'subtitle', 'label'},
 'interface.pages.skills': {'title', 'subtitle', 'label'},
 'interface.theme': {'bg', 'white', 'ink', 'line', 'muted', 'mint', 'green'},
 'learning': {'default_baseline',
              'default_skills',
              'maximum_alternatives',
              'maximum_preparation_hours',
              'require_review_for_approval',
              'require_source_for_approval'},
 'limits': {'advertisement_preview_characters',
            'csv_rows',
            'request_bytes',
            'short_text_characters',
            'skill_text_characters',
            'text_characters',
            'url_characters'},
 'project': {'name', 'decision_notes', 'phase', 'configuration_author'},
 'prompts': {'skills', 'advertisements'},
 'research': {'additional_keywords',
              'contract',
              'default_results',
              'extra_allowed_domains',
              'location',
              'max_output_tokens',
              'maximum_results',
              'model',
              'platforms',
              'restrict_to_selected_platforms',
              'result_choices',
              'roles',
              'selection_limit',
              'timeout_seconds'},
 'schedule': {'days',
              'default_weekly_hours',
              'evidence_requirement',
              'maximum_weekly_hours',
              'minimum_weekly_hours',
              'session_status',
              'start_date_offset_days',
              'start_time',
              'timezone',
              'timezone_choices',
              'title_template',
              'weekly_hours_step',
              'weeks'},
 'server': {'port', 'browser_delay_seconds', 'open_browser'}}

class UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML parsing with duplicate-key rejection, rather than last value wins."""

    def construct_mapping(self, node, deep=False):
        pairs = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ConfigError('YAML mapping keys must be strings.')
            if key in pairs:
                raise ConfigError('Duplicate YAML key: ' + key)
            pairs[key] = self.construct_object(value_node, deep=deep)
        return pairs

def validate(c):

    def get(path):
        value = c
        for k in path.split('.'):
            if not isinstance(value, dict) or k not in value:
                raise ConfigError('Missing setting: ' + path)
            value = value[k]
        return value

    def string(path, empty=False):
        v = get(path)
        if not isinstance(v, str) or (not empty and (not v.strip())):
            raise ConfigError(path + ' must be a string' + ('' if empty else ' with a value') + '.')
        return v

    def number(path, low, high, integer=False):
        v = get(path)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or (not math.isfinite(v)) or (not low <= v <= high) or (integer and (not isinstance(v, int))):
            raise ConfigError('%s must be %s between %s and %s.' % (path, 'an integer' if integer else 'a number', low, high))
        return v

    def boolean(path):
        if type(get(path)) is not bool:
            raise ConfigError(path + ' must be true or false.')

    def sequence(path):
        v = get(path)
        if not isinstance(v, list) or not v:
            raise ConfigError(path + ' must be a non-empty list.')
        return v

    def component(value, path):
        if not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', value) or value in ('.', '..'):
            raise ConfigError(path + ' must be a simple filename/folder without slashes or spaces.')
    if not isinstance(c, dict):
        raise ConfigError('config.yml must contain a mapping.')
    sections = {'schema_version', 'project', 'server', 'data', 'research', 'learning', 'schedule', 'limits', 'exports', 'interface', 'prompts'}
    if set(c) != sections:
        raise ConfigError('Missing or unknown top-level sections: ' + ', '.join(sorted(set(c) ^ sections)))
    for section, keys in _ALLOWED_KEYS.items():
        actual = get(section)
        if not isinstance(actual, dict):
            raise ConfigError(section + ' must be a mapping.')
        extra = set(actual) - keys
        if extra:
            raise ConfigError('Unknown settings in ' + section + ': ' + ', '.join(sorted(extra)))
    if get('schema_version') != 1:
        raise ConfigError('schema_version must be 1.')
    for k in ('name', 'phase', 'configuration_author', 'decision_notes'):
        string('project.' + k, empty=k in ('configuration_author', 'decision_notes'))
    number('server.port', 1024, 65535, True)
    boolean('server.open_browser')
    number('server.browser_delay_seconds', 0, 10)
    data = Path(string('data.file'))
    if data.is_absolute() or '..' in data.parts or data.suffix != '.json':
        raise ConfigError('data.file must be a relative .json path inside this project.')
    string('research.model')
    number('research.timeout_seconds', 10, 900, True)
    number('research.max_output_tokens', 256, 64000, True)
    for k in ('location', 'contract', 'additional_keywords'):
        string('research.' + k, empty=True)
    maximum = number('research.maximum_results', 1, 100, True)
    number('research.default_results', 1, maximum, True)
    choices = sequence('research.result_choices')
    if any((type(n) is not int or not 1 <= n <= maximum for n in choices)) or get('research.default_results') not in choices:
        raise ConfigError('research.result_choices must be valid counts including default_results.')
    number('research.selection_limit', 1, 100, True)
    boolean('research.restrict_to_selected_platforms')
    domain_pattern = '(?:[a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}'
    for key, value_key in [('roles', 'keyword'), ('platforms', 'domain')]:
        entries = sequence('research.' + key)
        names = set()
        for item in entries:
            if not isinstance(item, dict) or set(item) != {'label', value_key, 'selected'} or (not isinstance(item['label'], str)) or (not item['label'].strip()) or (not isinstance(item[value_key], str)) or (not item[value_key].strip()) or (type(item['selected']) is not bool):
                raise ConfigError('Each research.' + key + ' entry needs label, ' + value_key + ' and selected.')
            if item['label'] in names:
                raise ConfigError('Duplicate ' + key + ' label: ' + item['label'])
            names.add(item['label'])
            if key == 'platforms' and (not re.fullmatch(domain_pattern, item[value_key])):
                raise ConfigError('Use a domain without https:// for ' + item['label'])
    extra = get('research.extra_allowed_domains')
    if not isinstance(extra, list) or any((not isinstance(x, str) or not re.fullmatch(domain_pattern, x) for x in extra)):
        raise ConfigError('research.extra_allowed_domains must contain domains only.')
    for k in ('default_skills', 'default_baseline'):
        string('learning.' + k, True)
    number('learning.maximum_alternatives', 0, 10, True)
    number('learning.maximum_preparation_hours', 1, 10000)
    for k in ('require_source_for_approval', 'require_review_for_approval'):
        boolean('learning.' + k)
    number('schedule.weeks', 1, 104, True)
    low = number('schedule.minimum_weekly_hours', 0.5, 80)
    high = number('schedule.maximum_weekly_hours', low, 80)
    number('schedule.default_weekly_hours', low, high)
    number('schedule.weekly_hours_step', 0.1, 10)
    number('schedule.start_date_offset_days', 0, 365, True)
    try:
        time.fromisoformat(string('schedule.start_time'))
    except ValueError:
        raise ConfigError('schedule.start_time must be quoted HH:MM.')
    days = sequence('schedule.days')
    if any((type(d) is not int or d not in range(7) for d in days)) or len(days) != len(set(days)):
        raise ConfigError('schedule.days must contain unique numbers 0–6.')
    zones = sequence('schedule.timezone_choices')
    if string('schedule.timezone') not in zones:
        raise ConfigError('schedule.timezone must be included in timezone_choices.')
    try:
        for z in zones:
            ZoneInfo(z)
    except (ZoneInfoNotFoundError, TypeError):
        raise ConfigError('Unknown timezone in schedule.timezone_choices.')
    for k in ('evidence_requirement', 'session_status', 'title_template'):
        string('schedule.' + k)
    for key in ('request_bytes', 'csv_rows', 'text_characters', 'short_text_characters', 'url_characters', 'skill_text_characters', 'advertisement_preview_characters'):
        number('limits.' + key, 1, 10000000, True)
    for key in ('advertisements', 'skills', 'evidence', 'calendar', 'trello', 'obsidian'):
        boolean('exports.' + key + '.enabled')
        component(string('exports.' + key + '.filename'), 'exports.' + key + '.filename')
    allowed = {'advertisements': {'duration',
                        'employer',
                        'id',
                        'location',
                        'origin',
                        'original_text',
                        'requirements',
                        'retrieved_at',
                        'review',
                        'selected',
                        'selection_reason',
                        'title',
                        'url',
                        'verified'},
     'skills': {'alternatives',
                'approved',
                'certification',
                'difficulty',
                'duration',
                'hours',
                'issuer',
                'jobs',
                'kind',
                'prerequisites',
                'rationale',
                'recognition',
                'review',
                'skill',
                'url'},
     'trello': {'Name', 'Description', 'List', 'Due', 'Start'}}
    for key, fields in allowed.items():
        cols = sequence('exports.' + key + '.columns')
        if any((not isinstance(x, str) or x not in fields for x in cols)) or len(cols) != len(set(cols)):
            raise ConfigError('Invalid or duplicate export columns for ' + key)
    for key in ('folder', 'programme_file', 'calendar_file', 'skills_folder', 'evidence_folder'):
        component(string('exports.obsidian.' + key), 'exports.obsidian.' + key)
    for key in ('calendar.product_id', 'trello.list_prefix', 'description_template', 'programme_title', 'programme_note'):
        string('exports.' + key)
    string('interface.locale')
    for k in ('notice_ms', 'poll_ms', 'poll_retry_ms'):
        number('interface.' + k, 250, 120000, True)
    for k in ('ink', 'muted', 'green', 'bg', 'line', 'white', 'mint'):
        if not re.fullmatch('#[0-9A-Fa-f]{6}', string('interface.theme.' + k)):
            raise ConfigError('Theme values must be six-digit hex colours.')
    for page in ('ads', 'skills', 'exports'):
        for k in ('label', 'title', 'subtitle'):
            string('interface.pages.' + page + '.' + k)
    if len(sequence('interface.day_labels')) != 7 or any((not isinstance(x, str) for x in get('interface.day_labels'))):
        raise ConfigError('interface.day_labels needs seven strings.')
    for k in ('copy', 'messages', 'placeholders'):
        value = get('interface.' + k)
        if not isinstance(value, dict) or any((not isinstance(v, str) for v in value.values())):
            raise ConfigError('interface.' + k + ' must map keys to text.')
    templates = {'prompts.advertisements': {'limit', 'roles', 'contract', 'platforms', 'today', 'location'},
     'prompts.skills': {'skills', 'advertisements', 'weeks', 'today', 'alternatives', 'baseline'},
     'schedule.title_template': {'skill', 'certification'},
     'exports.description_template': {'certification',
                                      'difficulty',
                                      'evidence',
                                      'jobs',
                                      'rationale',
                                      'resource',
                                      'skill'}}
    for path, names in templates.items():
        value = string(path)
        try:
            Template(value).substitute({n: 'example' for n in names})
        except (KeyError, ValueError) as e:
            raise ConfigError('Invalid $placeholder in ' + path + ': ' + str(e))
    # Check that every label used by the interface exists in config.yml.
    source = (ROOT / 'src/internship_planner/web/index.html').read_text()
    for key in re.findall('data-copy="([^"]+)"', source):
        string('interface.copy.' + key, True)
    for key in re.findall('data-placeholder="([^"]+)"', source):
        string('interface.placeholders.' + key, True)
    js = (ROOT / 'src/internship_planner/web/app.js').read_text()
    for key in set(re.findall("tr\\('([^']+)'\\)", js)):
        string('interface.messages.' + key, True)
    return c

def load_config(path=CONFIG_PATH):
    try:
        c = yaml.load(Path(path).read_text(encoding='utf-8'), Loader=UniqueSafeLoader)
        return validate(c)
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError('Could not load ' + str(path) + ': ' + str(e)) from e

def digest(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def public_config(c):
    """Only send ordinary settings to the browser, never environment secrets."""
    return copy.deepcopy({k: c[k] for k in ('project', 'research', 'learning', 'schedule', 'interface', 'exports', 'limits')})
try:
    CONFIG = load_config()
except ConfigError as error:
    raise SystemExit('Configuration error: ' + str(error))
if __name__ == '__main__':
    print('config.yml is valid. Configuration SHA-256: ' + digest(CONFIG))
