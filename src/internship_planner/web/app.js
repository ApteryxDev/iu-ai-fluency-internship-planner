'use strict';
// Shortcuts for the repeated form and table elements on this page.
const $ = id => document.getElementById(id);
let state, token = '', activeJob = null, modalSave, cfg = null;
// Which row is open in the review boxes under the two tables.
let currentAdId = null, currentSkillId = null;
// Role keywords shown as chips; starts from the selected roles in config.yml.
let chips = [];

// Show listing text safely; source websites can contain HTML characters.
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const tr = key => expand(cfg?.interface.messages[key] ?? key);
const expand = value => String(value).replace(/\{(weeks|selection_limit|minimum_hours|maximum_hours)\}/g, (_, key) => ({ weeks: cfg.schedule.weeks, selection_limit: cfg.research.selection_limit, minimum_hours: cfg.schedule.minimum_weekly_hours, maximum_hours: cfg.schedule.maximum_weekly_hours }[key]));
const url = s => /^https?:\/\/[^\s]+$/i.test(s || '') ? s : '';
const link = (s, label = tr('open_source')) => url(s) ? `<a href="${esc(s)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : '<span class="muted">No source URL yet</span>';
const chosen = id => [...$(id).querySelectorAll('input:checked')].map(x => x.value);
const short = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = error ? 'error' : '';
  $('notice').hidden = false;
  setTimeout(() => $('notice').hidden = true, cfg?.interface.notice_ms ?? 12000);
}

async function api(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-App-Token': token }, body: JSON.stringify(body) });
  const data = await r.json();
  if (!r.ok) throw Error(data.error || tr('request_failed'));
  return data;
}

async function refresh() {
  const r = await fetch('/api/state');
  if (!r.ok) throw Error(tr('could_not_load_your_workspace'));
  const s = await r.json();
  state = s.data;
  token = s.token;
  if (!cfg) {
    cfg = s.config;
    applyConfig();
  }
  $('apiStatus').textContent = s.key_configured ? tr('openai_api_connected_locally') : tr('api_not_configured');
  $('apiStatus').dataset.model = s.model;
  renderAds();
  renderSkills();
  renderSchedule();
  renderEvidence();
  return s;
}

function check(value, label, selected) {
  return `<label><input type="checkbox" value="${esc(value)}" ${selected ? 'checked' : ''}>${esc(label)}</label>`;
}

function applyConfig() {
  document.querySelectorAll('[data-placeholder]').forEach(e => e.placeholder = cfg.interface.placeholders[e.dataset.placeholder] || '');
  document.querySelectorAll('[data-project-name]').forEach(e => e.textContent = cfg.project.name);
  document.querySelectorAll('[data-project-phase]').forEach(e => e.textContent = cfg.project.phase);
  document.querySelectorAll('[data-page-label]').forEach(e => e.textContent = cfg.interface.pages[e.dataset.pageLabel].label);

  // Panel 01: chips, location suggestions and platforms.
  chips = cfg.research.roles.filter(r => r.selected).map(r => ({ label: r.label, keyword: r.keyword }));
  if (cfg.research.additional_keywords.trim()) chips.push({ label: cfg.research.additional_keywords.trim(), keyword: cfg.research.additional_keywords.trim() });
  renderChips();
  $('location').value = cfg.research.location;
  const places = [cfg.research.location, 'Île-de-France', 'Paris', 'Boulogne-Billancourt', 'Paris 16e', 'Hauts-de-Seine'];
  $('locationChoices').innerHTML = [...new Set(places)].map(p => `<option value="${esc(p)}">`).join('');
  $('platforms').innerHTML = cfg.research.platforms.map(p => check(p.label, p.label, p.selected)).join('');

  // Panel 02: defaults from config.yml.
  $('skillInput').value = cfg.learning.default_skills;
  $('baseline').value = cfg.learning.default_baseline;

  // Panel 03: weekly hours as a fixed list between the minimum and maximum.
  const sc = cfg.schedule, options = [];
  for (let h = sc.minimum_weekly_hours; h <= sc.maximum_weekly_hours + 1e-9; h += sc.weekly_hours_step) options.push(Math.round(h * 10) / 10);
  $('weeklyHours').innerHTML = options.map(h => `<option value="${h}">${h} hours/week</option>`).join('');
  $('weeklyHours').value = String(sc.default_weekly_hours);
  $('days').innerHTML = cfg.interface.day_labels.map((label, i) => check(i, label, sc.days.includes(i))).join('');
  $('buildSchedule').textContent = `Generate ${sc.weeks}-week plan`;
  $('configNote').textContent = `Sessions start ${sc.start_time}, ${sc.timezone} (settings from config.yml)`;
  const d = new Date();
  d.setDate(d.getDate() + sc.start_date_offset_days);
  $('startDate').value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

  document.querySelectorAll('a[href^="/export/"]').forEach(e => e.hidden = !cfg.exports[e.getAttribute('href').split('/').pop()].enabled);
}

/* ---------- 01 Advertisements ---------- */

function renderChips() {
  const others = cfg.research.roles.filter(r => !chips.some(c => c.keyword === r.keyword));
  $('roleChips').innerHTML = chips.map((c, i) => `<span class="chip">${esc(c.label)}<button type="button" class="chip-x" data-action="remove-chip" data-index="${i}" aria-label="Remove ${esc(c.label)}">×</button></span>`).join('')
    + `<span class="chip add-chip"><input id="newKeyword" list="roleSuggestions" placeholder="+ Add keyword"><datalist id="roleSuggestions">${others.map(r => `<option value="${esc(r.label)}">`).join('')}</datalist></span>`;
  $('newKeyword').addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const value = e.target.value.trim();
    if (!value) return;
    const known = cfg.research.roles.find(r => r.label.toLowerCase() === value.toLowerCase());
    const chip = known ? { label: known.label, keyword: known.keyword } : { label: value, keyword: value };
    if (!chips.some(c => c.keyword === chip.keyword)) chips.push(chip);
    renderChips();
    $('newKeyword').focus();
  });
}

// Two selected ads from the same employer probably test the same skills.
function similarityWarning(selected) {
  const counts = {};
  selected.forEach(a => {
    const key = (a.employer || '').trim().toLowerCase();
    if (key) counts[key] = (counts[key] || 0) + 1;
  });
  const repeated = selected.filter(a => counts[(a.employer || '').trim().toLowerCase()] > 1).map(a => a.employer);
  return [...new Set(repeated)];
}

function renderAds() {
  const ads = state.advertisements;
  const selected = ads.filter(a => a.selected);
  $('selectedCount').textContent = `Selected: ${selected.length} / ${cfg.research.selection_limit}`;
  const repeated = similarityWarning(selected);
  $('similarityWarning').hidden = !repeated.length;
  $('similarityWarning').textContent = repeated.length ? `More than one selected listing from: ${repeated.join(', ')}. Check that your five positions are not too similar.` : '';

  $('adTable').querySelector('tbody').innerHTML = ads.map(a => `
    <tr data-row="ad" data-id="${a.id}" class="${a.id === currentAdId ? 'current' : ''} ${a.selected ? 'chosen' : ''}">
      <td class="narrow"><input type="checkbox" data-action="select-ad" data-id="${a.id}" ${a.selected ? 'checked' : ''} aria-label="Select ${esc(a.title)}"></td>
      <td><b>${esc(a.title)}</b>${a.verified ? ' <span class="tag">checked</span>' : ''}</td>
      <td>${esc(a.employer || '–')}</td>
      <td>${esc(a.location || '–')}</td>
      <td class="muted">${esc(short(a.requirements || a.original_text, 90) || 'not recorded yet')}</td>
    </tr>`).join('')
    || '<tr><td colspan="5" class="empty-cell">No listings yet. Add one, import a CSV or run Research. Nothing here is a real job until you check the source.</td></tr>';

  const a = ads.find(x => x.id === currentAdId);
  if (!a) {
    currentAdId = null;
    $('adReviewBody').innerHTML = '<p class="muted placeholder">Click a row above to review the original wording next to your checked requirements.</p>';
    return;
  }
  $('adReviewBody').innerHTML = `
    <div class="review-title"><b>${esc(a.title)}</b> · ${esc(a.employer || 'employer not recorded')} · ${link(a.url)}</div>
    <div class="three-col">
      <label>Original excerpt<textarea id="rvOriginal" rows="5">${esc(a.original_text)}</textarea></label>
      <label>Checked requirements<textarea id="rvRequirements" rows="5">${esc(a.requirements)}</textarea></label>
      <label>My notes<textarea id="rvNotes" rows="5">${esc(a.review)}</textarea></label>
    </div>
    <label>Why I chose or excluded it<input id="rvReason" value="${esc(a.selection_reason)}"></label>
    <div class="row spread">
      <label class="inline-check"><input type="checkbox" id="rvVerified" ${a.verified ? 'checked' : ''}> I checked the original source</label>
      <div class="row">
        <button class="secondary" data-action="edit-ad" data-id="${a.id}">All fields</button>
        <button data-action="save-ad-review" data-id="${a.id}">Save review</button>
      </div>
    </div>`;
}

/* ---------- 02 Skills and certifications ---------- */

function renderSkills() {
  const rows = state.skills;
  $('skillTable').querySelector('tbody').innerHTML = rows.map(s => `
    <tr data-row="skill" data-id="${s.id}" class="${s.id === currentSkillId ? 'current' : ''} ${s.approved ? 'chosen' : ''}">
      <td><b>${esc(s.skill)}</b>${s.approved ? ' <span class="tag">approved</span>' : ''}</td>
      <td>${esc(s.certification || '–')}<div class="muted small">${esc(s.issuer)}</div></td>
      <td>${esc(s.difficulty || '–')}</td>
      <td>${s.hours ? `${esc(s.hours)} h` : '–'}<div class="muted small">${esc(short(s.duration, 50))}</div></td>
    </tr>`).join('')
    || '<tr><td colspan="4" class="empty-cell">No courses yet. Select your advertisements first, then research or add an option you have checked yourself.</td></tr>';

  const s = rows.find(x => x.id === currentSkillId);
  if (!s) {
    currentSkillId = null;
    $('skillReviewBody').innerHTML = '<p class="muted placeholder">Click a row to check the official source, prerequisites and reason before approving.</p>';
    return;
  }
  const linked = (s.related_advertisement_ids || []).map(id => state.advertisements.find(a => a.id === id)).filter(Boolean);
  $('skillReviewBody').innerHTML = `
    <div class="review-title"><b>${esc(s.skill)}</b> · ${esc(s.certification || 'course not named')} · linked ads: ${linked.length ? linked.map(a => esc(a.title)).join(', ') : '<span class="warning-text">none yet</span>'}</div>
    <div class="four-col">
      <div>
        <span class="label">Official source</span>
        <input id="rvUrl" type="url" placeholder="https://issuer page" value="${esc(s.url)}">
        <textarea id="rvCheck" rows="3" placeholder="What I checked on the issuer page">${esc(s.review)}</textarea>
      </div>
      <div>
        <span class="label">Prerequisites</span>
        <textarea id="rvPrereq" rows="3">${esc(s.prerequisites)}</textarea>
        <label class="small-label">Hours to schedule<input id="rvHours" type="number" min="0" step="0.5" value="${esc(s.hours || 0)}"></label>
      </div>
      <div>
        <span class="label">Why this option?</span>
        <textarea id="rvWhy" rows="5">${esc(s.rationale)}</textarea>
      </div>
      <div class="approve-col">
        <button data-action="approve-skill" data-id="${s.id}">${s.approved ? 'Unapprove' : 'Approve'}</button>
        <span class="hint">verify before approval</span>
        <button class="secondary" data-action="save-skill-review" data-id="${s.id}">Save</button>
        <div class="row">
          <button class="secondary" data-action="move-up" data-id="${s.id}" aria-label="Move earlier">↑</button>
          <button class="secondary" data-action="move-down" data-id="${s.id}" aria-label="Move later">↓</button>
        </div>
        <button class="secondary" data-action="edit-skill" data-id="${s.id}">All fields</button>
      </div>
    </div>`;
}

function skillReviewValues() {
  return {
    url: $('rvUrl').value.trim(),
    review: $('rvCheck').value,
    prerequisites: $('rvPrereq').value,
    rationale: $('rvWhy').value,
    hours: Number($('rvHours').value || 0),
  };
}

/* ---------- 03 Schedule ---------- */

function renderSchedule() {
  const sessions = state.schedule || [];
  const summary = state.schedule_summary;
  const weeks = summary?.weeks || cfg.schedule.weeks;
  const head = `<thead><tr><th class="row-label">Week</th>${Array.from({ length: weeks }, (_, i) => `<th>W${i + 1}</th>`).join('')}</tr></thead>`;

  if (!sessions.length || !summary) {
    $('scheduleSummary').textContent = tr('generate_a_schedule_after_approving_options_and_checking_their_prepara');
    $('gantt').innerHTML = head + `<tbody><tr><td class="row-label muted">No plan yet</td>${'<td><span class="bar empty-bar"></span></td>'.repeat(weeks)}</tr></tbody>`;
    $('sessionCards').innerHTML = '';
    return;
  }

  const overflow = summary.overflow.length
    ? 'Does not fit in ' + weeks + ' weeks: ' + summary.overflow.map(x => `${x.skill} (${x.remaining_hours} h left)`).join(', ') + '.'
    : tr('all_approved_preparation_estimates_fit');
  $('scheduleSummary').textContent = `${summary.allocated_hours} of ${summary.capacity_hours} available hours scheduled. ${overflow} Scheduled work is not completed work.`;

  // One row per approved learning option, in the order they were scheduled.
  const order = [];
  sessions.forEach(s => { if (!order.some(o => o.id === s.skill_id)) order.push({ id: s.skill_id, skill: s.skill, certification: s.certification }); });
  const hoursIn = (skillId, week) => sessions.filter(s => s.skill_id === skillId && s.week === week).reduce((n, s) => n + s.hours, 0);
  const body = order.map(o => `<tr><td class="row-label">${esc(o.skill)}<div class="muted small">${esc(short(o.certification, 40))}</div></td>${Array.from({ length: weeks }, (_, i) => {
    const h = hoursIn(o.id, i + 1);
    return `<td>${h > 0 ? `<span class="bar">${h.toFixed(1)} h</span>` : '<span class="bar empty-bar"></span>'}</td>`;
  }).join('')}</tr>`).join('');
  const totals = Array.from({ length: weeks }, (_, i) => sessions.filter(s => s.week === i + 1).reduce((n, s) => n + s.hours, 0));
  const totalRow = `<tr class="total-row"><td class="row-label">Total per week</td>${totals.map(t => `<td class="${t > 0 && t < cfg.schedule.minimum_weekly_hours ? 'under' : ''}">${t.toFixed(1)} h</td>`).join('')}</tr>`;
  $('gantt').innerHTML = head + `<tbody>${body}${totalRow}</tbody>`;

  const zone = state.schedule_settings.timezone || cfg.schedule.timezone;
  const fmt = new Intl.DateTimeFormat(cfg.interface.locale, { timeZone: zone, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  $('sessionCards').innerHTML = Array.from({ length: weeks }, (_, i) => {
    const rows = sessions.filter(s => s.week === i + 1);
    return `<div class="week"><h3>Week ${i + 1}</h3>${rows.map(s => `<div class="session"><b>${esc(s.skill)}</b><small>${esc(fmt.format(new Date(s.start)))} · ${s.hours.toFixed(1)} h</small><button class="secondary small-btn" data-action="copy-card" data-id="${s.id}">Copy Trello card</button></div>`).join('') || '<p class="muted">Free for revision or practice.</p>'}</div>`;
  }).join('');
}

/* ---------- Evidence log ---------- */

function renderEvidence() {
  $('evidenceCards').innerHTML = [...state.research].reverse().map(r => `<details><summary>${esc(r.kind)} · ${esc(r.date.slice(0, 16).replace('T', ' '))} <span class="pill">${esc(r.status || 'NOTE')}</span></summary><div class="evidence-content"><p>${esc(r.summary || r.error || '')}</p><p>${esc(r.limitations || '')}</p><h3>Exact prompt</h3><pre>${esc(r.prompt)}</pre><h3>Actual output</h3><pre>${esc(r.output)}</pre><div class="row">${(r.citations || []).map(c => link(c.url, c.title || c.url)).join(' ')}</div><h3>My checks and changes</h3><p>${esc(r.review || tr('add_your_review_verified_sources_corrections_and_reasons_for_changes'))}</p><button class="secondary" data-action="edit-evidence" data-id="${r.id}">Record review</button></div></details>`).join('')
    || '<p class="muted">Research prompts and actual responses are saved here automatically. You can also add a manual note, for example a ChatGPT exchange.</p>';
}

/* ---------- Full edit dialogs ---------- */

function field(name, label, value = '', type = 'text') {
  return `<label>${esc(label)}${type === 'textarea' ? `<textarea name="${name}" rows="4">${esc(value)}</textarea>` : `<input name="${name}" type="${type}" value="${esc(value)}">`}</label>`;
}

function modal(title, html, save) {
  $('modalError').hidden = true;
  $('modalTitle').textContent = title;
  $('modalBody').innerHTML = html;
  modalSave = save;
  $('modalForm').querySelector('.modal-actions').hidden = !save;
  $('modal').showModal();
}

function editAd(a) {
  a = a || {};
  modal(a.id ? tr('review_advertisement') : tr('add_advertisement'), field('title', tr('job_title'), a.title) + field('employer', 'Employer', a.employer) + field('location', 'Location', a.location) + field('duration', tr('duration_contract'), a.duration) + field('url', tr('direct_source_url'), a.url, 'url') + field('original_text', tr('original_text_or_exact_excerpt_research_results_contain_excerpts_only'), a.original_text, 'textarea') + field('requirements', tr('requirements_mandatory_desirable_supporting_source_wording'), a.requirements, 'textarea') + field('review', tr('eligibility_source_checks_corrections_and_inclusion_exclusion_reasons'), a.review, 'textarea') + field('selection_reason', 'Why I included or excluded this advertisement', a.selection_reason, 'textarea') + `<label class="inline-check"><input type="checkbox" name="verified" ${a.verified ? 'checked' : ''}> I checked the original source</label>` + (a.id ? `<button type="button" class="secondary" data-action="delete-ad" data-id="${a.id}">Delete advertisement</button>` : ''), async (values) => {
    values.verified = $('modalBody').querySelector('[name=verified]').checked;
    await api(a.id ? '/api/advertisements/update' : '/api/advertisements/add', { ...values, ...(a.id ? { id: a.id } : {}) });
  });
}

function editSkill(s) {
  s = s || {};
  modal(s.id ? tr('review_learning_option') : tr('add_learning_option'), field('skill', 'Skill', s.skill) + field('jobs', tr('related_job_titles_and_advertisement_ids'), s.jobs) + `<fieldset><legend>Related advertisements (your selected listings)</legend>${state.advertisements.filter(a => a.selected).map(a => `<label class="inline-check"><input type="checkbox" name="linkedAdvertisement" value="${esc(a.id)}" ${(s.related_advertisement_ids || []).includes(a.id) ? 'checked' : ''}> ${esc(a.title)} (${esc(a.employer)})</label>`).join('') || '<p class="muted">Select your five advertisements first to link them here.</p>'}</fieldset>` + field('certification', tr('certification_course_title'), s.certification) + field('issuer', tr('issuer_provider'), s.issuer) + field('kind', tr('type_exam_credential_course_completion_certificate'), s.kind) + field('url', tr('official_resource_url'), s.url, 'url') + field('difficulty', tr('difficulty_relative_to_your_baseline'), s.difficulty) + field('duration', tr('preparation_length_range_and_assumptions'), s.duration) + field('hours', tr('preparation_hours_for_scheduling_your_checked_estimate'), s.hours || 0, 'number') + field('prerequisites', 'Prerequisites', s.prerequisites) + field('rationale', tr('why_this_option_fits_the_skill_gap'), s.rationale, 'textarea') + field('recognition', tr('evidence_of_recognition_or_not_established'), s.recognition, 'textarea') + field('alternatives', tr('alternatives_and_tradeoffs'), s.alternatives, 'textarea') + field('review', tr('your_verification_and_changes'), s.review, 'textarea') + (s.id ? `<button type="button" class="secondary" data-action="delete-skill" data-id="${s.id}">Delete option</button>` : ''), async (values) => api(s.id ? '/api/skills/update' : '/api/skills/add', { ...values, related_advertisement_ids: [...$('modalBody').querySelectorAll('[name=linkedAdvertisement]:checked')].map(e => e.value), ...(s.id ? { id: s.id } : {}) }));
}

/* ---------- Research jobs ---------- */

async function research(kind) {
  let args = { kind };
  if (kind === 'advertisements') {
    if (!chips.length) throw Error('Add at least one role keyword first.');
    args = { ...args, roles: chips.map(c => c.keyword), platforms: chosen('platforms'), location: $('location').value, contract: cfg.research.contract, limit: cfg.research.default_results };
  } else {
    args = { ...args, skills: $('skillInput').value, baseline: $('baseline').value };
  }
  const r = await api('/api/research', args);
  activeJob = r.job_id;
  poll();
}

async function poll() {
  try {
    const s = await refresh();
    const job = s.jobs[activeJob];
    if (!job) return;
    $('researchStatus').hidden = false;
    $('researchStatus').textContent = job.message;
    for (const id of ['researchAds', 'researchSkills']) $(id).disabled = job.status === 'running';
    if (job.status === 'running') setTimeout(poll, cfg.interface.poll_ms);
    else {
      notice(job.message, job.status === 'failed');
      activeJob = null;
    }
  } catch (e) {
    notice(e.message, true);
    setTimeout(poll, cfg.interface.poll_retry_ms);
  }
}

/* ---------- Event wiring ---------- */

$('modalForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const button = e.submitter;
  button.disabled = true;
  try {
    const values = Object.fromEntries(new FormData(e.target));
    await modalSave(values);
    $('modal').close();
    $('modalBody').innerHTML = '';
    await refresh();
    notice('Saved.');
  } catch (err) {
    $('modalError').textContent = err.message;
    $('modalError').hidden = false;
  } finally {
    button.disabled = false;
  }
});
$('closeModal').onclick = () => $('modal').close();
$('settingsBtn').onclick = () => modal(tr('openai_api_settings'), '<p>Paste the key here, not in chat. It is held in server memory until you stop the app. API usage is billed separately from ChatGPT.</p>' + field('key', tr('api_key_leave_blank_to_retain_current_key'), '', 'password') + field('model', tr('web_search_capable_model'), $('apiStatus').dataset.model) + '<label class="inline-check"><input type="checkbox" name="forget"> Forget current key</label>', async (values) => {
  values.forget = $('modalBody').querySelector('[name=forget]').checked;
  await api('/api/settings', values);
});
$('addAd').onclick = () => editAd();
$('addSkill').onclick = () => editSkill();
$('importBtn').onclick = () => $('importFile').click();
$('importFile').onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const r = await api('/api/advertisements/import', { csv: await file.text() });
    await refresh();
    notice(r.message);
  } catch (err) {
    notice(err.message, true);
  }
  e.target.value = '';
};
$('researchAds').onclick = () => research('advertisements').catch(e => notice(e.message, true));
$('researchSkills').onclick = () => research('skills').catch(e => notice(e.message, true));
$('buildSchedule').onclick = async () => {
  try {
    await api('/api/schedule', { start_date: $('startDate').value, start_time: cfg.schedule.start_time, weekly_hours: Number($('weeklyHours').value), days: chosen('days').map(Number), timezone: cfg.schedule.timezone });
    await refresh();
    notice(tr('schedule_generated_review_the_programme_before_exporting'));
  } catch (e) {
    notice(e.message, true);
  }
};
$('addEvidence').onclick = () => modal(tr('add_evidence_note'), field('prompt', tr('task_prompt'), '', 'textarea') + field('output', tr('actual_result_output'), '', 'textarea') + field('review', tr('your_checks_and_changes'), '', 'textarea'), v => api('/api/evidence', v));

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-action]');
  // Clicking a table row (but not its checkbox) opens it in the review box.
  if (!btn) {
    const row = e.target.closest('tr[data-row]');
    if (row) {
      if (row.dataset.row === 'ad') { currentAdId = row.dataset.id; renderAds(); }
      else { currentSkillId = row.dataset.id; renderSkills(); }
    }
    return;
  }
  const { action, id } = btn.dataset;
  try {
    const a = state.advertisements.find(x => x.id === id), s = state.skills.find(x => x.id === id);
    if (action === 'remove-chip') {
      chips.splice(Number(btn.dataset.index), 1);
      return renderChips();
    }
    if (action === 'edit-ad') return editAd(a);
    if (action === 'edit-skill') return editSkill(s);
    if (action === 'select-ad') {
      try {
        await api('/api/advertisements/update', { id, selected: !a.selected });
      } finally {
        await refresh(); // puts the checkbox back if the limit was reached
      }
      return;
    }
    if (action === 'save-ad-review') {
      await api('/api/advertisements/update', { id, original_text: $('rvOriginal').value, requirements: $('rvRequirements').value, review: $('rvNotes').value, selection_reason: $('rvReason').value, verified: $('rvVerified').checked });
      notice('Source review saved.');
    }
    if (action === 'save-skill-review') {
      await api('/api/skills/update', { id, ...skillReviewValues() });
      notice('Saved.');
    }
    if (action === 'approve-skill') {
      if (s.approved) await api('/api/skills/update', { id, approved: false });
      else {
        const v = skillReviewValues();
        if (!v.hours || (cfg.learning.require_source_for_approval && !v.url) || (cfg.learning.require_review_for_approval && !v.review.trim()))
          throw Error(tr('review_this_option_first_add_an_official_url_positive_preparation_esti'));
        await api('/api/skills/update', { id, ...v, approved: true });
      }
    }
    if (action === 'move-up' || action === 'move-down')
      await api('/api/skills/reorder', { id, direction: action === 'move-up' ? 'up' : 'down' });
    if (action.startsWith('delete-')) {
      if (!confirm(tr('delete_this_record_the_action_will_be_logged'))) return;
      await api('/api/delete', { id, group: action === 'delete-ad' ? 'advertisements' : 'skills' });
      $('modal').close();
    }
    if (action === 'edit-evidence') {
      const r = state.research.find(x => x.id === id);
      return modal(tr('record_research_review'), field('review', tr('sources_verified_errors_found_corrections_and_your_decisions'), r.review, 'textarea'), v => api('/api/evidence', { id, ...v }));
    }
    if (action === 'copy-card') {
      const t = state.schedule.find(x => x.id === id);
      await navigator.clipboard.writeText(`${t.title}\n\nJob roles: ${t.jobs}\nSkill: ${t.skill}\nCourse/certification: ${t.certification}\nDifficulty: ${t.difficulty}\nStart: ${t.start}\nDue: ${t.end}\nResource: ${t.resource}\nEvidence: ${t.evidence}\nReason: ${t.rationale}`);
      notice(tr('trello_card_text_copied_paste_it_into_a_new_card'));
      return;
    }
    await refresh();
  } catch (err) {
    notice(err.message, true);
  }
});

(async () => {
  try {
    const s = await refresh();
    const options = state.schedule_settings;
    if (options.start_date) {
      $('startDate').value = options.start_date;
      $('weeklyHours').value = String(options.weekly_hours);
      $('days').querySelectorAll('input').forEach(x => x.checked = (options.days || cfg.schedule.days).includes(Number(x.value)));
    }
    const running = Object.entries(s.jobs).find(([, j]) => j.status === 'running');
    if (running) {
      activeJob = running[0];
      poll();
    }
  } catch (e) {
    notice(e.message, true);
  }
})();

$('configBtn').onclick = async () => {
  try {
    const r = await fetch('/api/config');
    const c = await r.json();
    modal('Configuration in use', '<p>Edit config.yml and restart the app to apply changes. The snapshot below is the configuration loaded at startup.</p><p>SHA-256: ' + esc(c.hash) + '</p><pre>' + esc(JSON.stringify(c.configuration, null, 2)) + '</pre>', null);
  } catch (e) {
    notice(e.message, true);
  }
};
