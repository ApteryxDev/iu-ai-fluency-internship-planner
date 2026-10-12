# Your configuration workbook

`config.yml` is the app's single source for operator-editable settings. Changes affect the Python server, browser controls, research instructions, scheduling rules and export files. Code variables such as IDs, request tokens and calculated totals are runtime state, not configuration. API keys stay in the Settings dialog or environment; never put them in this file.

## First use

1. Open `config.yml` in VS Code or another plain-text editor.
2. Change the settings you have chosen yourself. Keep indentation (spaces, no tabs).
3. Run `PYTHONPATH=src .venv/bin/python -m internship_planner.config` to validate it.
4. Stop the running app with Ctrl+C, then open `Launch.command` again.
5. Click **View YAML configuration** to inspect the values currently in use.

`Launch.command` installs the project dependencies in a project-local virtual environment on first use. This requires an internet connection. You can also create a virtual environment manually as described in README.md. No system Python packages are changed.

## Where to make decisions

| Section | Your controls | Effect |
| --- | --- | --- |
| `project` | Name, phase, configuration author, decision notes | App identity and a record of your reasoning |
| `research` | Roles, keywords, platforms/domains, location, contract, result counts, selection limit, model, timeout, token budget | Browser search choices, request parameters, selection cap and search instructions |
| `learning` | Baseline, skill priorities, alternative count, estimate limit, approval requirements | Learning research context and approval validation |
| `schedule` | Weeks, weekly hours, days, start time, timezone, session title and evidence requirement | Calendar allocation and session content |
| `exports` | Enabled outputs, filenames, CSV field order, Obsidian folder names and descriptions | Available downloads and their contents |
| `interface` | Colours, page titles, navigation labels, messages, placeholders, date locale and polling intervals | Presentation and browser behaviour |
| `prompts` | Full advertisement and skill-research instructions | Actual prompts sent to OpenAI |
| `server`, `data`, `limits` | Port, auto-open behaviour, JSON data path, input limits | Local operation and storage |

## Small changes to try

Change existing values under the relevant section; do not paste a second section with the same name.

```yaml
research:
  location: "Boulogne-Billancourt and Paris 16"
  contract: "Six-month AI engineering internship"
  default_results: 25
  selection_limit: 5
```

This is a **partial example**, not a complete replacement file. Keep the other existing `research` settings. `default_results` must be in `result_choices` and at or below `maximum_results`.

Add a role to the existing `roles` list:

```yaml
  roles:
    - label: "Computer vision"
      keyword: "computer vision engineer internship"
      selected: true
```

For your current assignment, keep `schedule.weeks: 12`, `minimum_weekly_hours: 5`, `maximum_weekly_hours: 8` and `research.selection_limit: 5`. These are editable for reuse, but changing them changes the project scope.

Days are `0` Monday, `1` Tuesday, through `6` Sunday. Quote times such as `"18:00"` and colours such as `"#205c44"`. The YAML file retains comments and editable text when you edit it manually; the app does not rewrite it.

## Search coverage

By default, the selected platforms guide the prompt, and employer websites can also be searched. Set `research.restrict_to_selected_platforms: true` to apply actual API domain restrictions. Add employer domains under `extra_allowed_domains` if you want them included with restrictions enabled. Domains have no `https://` prefix. Skill/certification research always remains unrestricted so official issuer websites can be reached.

## Prompts

`$roles`, `$location`, `$contract`, `$platforms`, `$limit`, `$today`, `$skills`, `$baseline`, `$weeks`, `$alternatives` and `$advertisements` are substituted where supported by each template. Keep required JSON field names and placeholders. A literal dollar sign must be `$$`. Unknown placeholders and malformed YAML stop startup with a readable error.

Change the question, emphasis and comparison criteria to reflect your decisions. Research remains unverified until you check sources. No setting automatically converts an AI candidate into a verified fact or an approved course.

## Defaults and overrides

- `config.yml` supplies defaults at startup.
- Browser form edits apply to the current request. They do not rewrite YAML.
- `OPENAI_MODEL` and `OPENAI_API_KEY` environment variables override the model/key at startup; the Settings dialog can override them for that running session.
- `--port` overrides `server.port`; `--no-browser` suppresses auto-opening.
- Advanced: `PLANNER_CONFIG` selects a different YAML file. The data path still resolves relative to the program folder.
- Existing saved schedule form values are restored when the configuration is unchanged. A changed configuration invalidates an existing schedule on restart so it can be regenerated with the new settings. Advertisement and skill records remain saved.

## Evidence and authorship

Research records include the exact prompt, actual output, model, a configuration snapshot and its SHA-256 fingerprint. Generated schedules also retain their configuration. `project.configuration_author` is intentionally blank until you choose and review the settings. Fill `project.decision_notes` with what you actually changed and why.

Choosing settings and explaining why they fit your goals is your own contribution. Keep a commit or a before/after copy when you change them. For the portfolio, describe your choices separately from the AI-assisted Python implementation, and only claim edits you actually made.

## Deliberately fixed in code

Loopback-only binding, the OpenAI destination, secret handling, HTML escaping, approval state transitions, JSON record structure and authentication checks stay in code. Internal function arguments and temporary variables do not belong in YAML. Some technical validation/error messages and low-level layout rules also remain in code. Changing them is an implementation change, rather than a project setting.
