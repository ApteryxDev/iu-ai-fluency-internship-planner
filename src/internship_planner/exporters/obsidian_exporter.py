"""Bundle programme, learning options, research and ICS into an Obsidian vault ZIP."""
import io
import zipfile
from ..config import CONFIG
from .calendar_exporter import calendar_bytes, description

def markdown_schedule(sessions):
    parts = ['# ' + CONFIG['exports']['programme_title'] + '\n\n' + CONFIG['exports']['programme_note'] + '\n']
    for s in sessions:
        parts.append('## Week %s · %s\n\n%s → %s\n\n%s\n\n- [ ] Complete activity\n- [ ] Attach evidence\n' % (s['week'], s['title'], s['start'], s['end'], description(s)))
    return '\n'.join(parts)

def obsidian_bytes(data):
    settings = CONFIG['exports']['obsidian']
    folder = settings['folder'] + '/'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(folder + settings['programme_file'], markdown_schedule(data['schedule']))
        z.writestr(folder + settings['calendar_file'], calendar_bytes(data['schedule']))
        for s in data['skills']:
            z.writestr(folder + settings['skills_folder'] + '/' + s['id'] + '.md', '# ' + s['skill'] + '\n\n' + '\n\n'.join((k + ': ' + str(v) for k, v in s.items())))
        for r in data['research']:
            z.writestr(folder + settings['evidence_folder'] + '/' + r['id'] + '.md', '# ' + r['kind'] + '\n\nDate: ' + r['date'] + '\n\n## Prompt\n' + r['prompt'] + '\n\n## Actual output\n' + r.get('output', '') + '\n\n## Your review\n' + r.get('review', ''))
    return output.getvalue()
