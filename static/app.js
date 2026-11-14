const byId = id => document.getElementById(id);
let current = null;
let busy = false;
let searchType = 'internet';
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function message(text) {
  byId('message').textContent = text || '';
  byId('message').hidden = !text;
}
async function api(url, options = {}, timeoutMs = 90000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    const data = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.detail;
      const error = new Error(typeof detail === 'object' ? detail.message : detail || 'The request could not be completed.');
      error.status = response.status; error.detail = data.detail; throw error;
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Request timed out. The server may still finish saving the run; refresh history before retrying.');
    throw error;
  } finally { clearTimeout(timer); }
}
function organic(row) { return (row.is_ad === false || row.is_ad === 0) && !row.is_duplicate && Boolean(row.normalized_url); }
function safeUrl(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? value : null; }
  catch { return null; }
}
function renderResults() {
  const list = byId('results'); list.replaceChildren();
  if (!current) return;
  const rows = current.results.filter(row => byId('all-observations').checked || organic(row));
  byId('result-count').textContent = `${rows.length} shown / ${current.results.length} stored`;
  byId('empty-state').hidden = rows.length > 0;
  byId('empty-state').textContent = current.results.length ? 'No observations match this filter.' : 'No observations were saved for this run. See its diagnostics above.';
  for (const row of rows) {
    const article = node('article', null, 'result');
    const urlValue = safeUrl(row.original_url) || safeUrl(row.normalized_url);
    const domain = urlValue ? new URL(urlValue).hostname.replace(/^www\./, '') : '';
    const source = node('div', null, 'source');
    const icon = node('span', '◉', 'website-icon'); icon.setAttribute('aria-hidden', 'true'); source.append(icon);
    // A displayed_link is provider display text, never a replacement destination.
    const display = typeof row.displayed_link === 'string' ? row.displayed_link.split(/[\s›>]/)[0] : '';
    const displayUrl = safeUrl(display.startsWith('http') ? display : `https://${display}`);
    const displayDomain = displayUrl ? new URL(displayUrl).hostname.replace(/^www\./, '') : '';
    source.append(node('span', row.destination_unverified ? 'Website' : (displayDomain === domain ? displayDomain : domain) || 'Website'));
    article.append(source);
    const heading = node('h3');
    if (urlValue) {
      const link = node('a', row.title || 'Untitled result'); link.href = urlValue; link.target = '_blank'; link.rel = 'noopener noreferrer'; heading.append(link);
    } else heading.textContent = row.title || 'Untitled result';
    article.append(heading);
    article.append(node('p', row.snippet || 'No snippet provided.'));
    list.append(article);
  }
}
function showRun(data) {
  current = data;
  byId('library').hidden = true;
  byId('search-form').closest('section').hidden = false;
  const run = data.run;
  byId('query').value = run.query_text;
  setSearchType('internet');
  document.body.classList.add('has-results');
  byId('internet-results').hidden = false;
  byId('run-status').textContent = `#${run.id} · ${run.status}`;
  byId('run-status').className = `badge ${run.status === 'failed' ? 'failed' : ''}`;
  const values = byId('diagnostic-values'); values.replaceChildren();
  for (const [label, value] of [['Provider', run.engine === 'google' ? 'Google · ScraperAPI' : run.engine], ['Saved', run.started_at || run.created_at || 'Not recorded'], ['Stored results', run.final_count], ['Pages', data.collection?.pages], ['Maximum pages', data.collection?.max_pages], ['Direct URLs', run.direct_url_count], ['Unverified Google redirects', run.google_redirect_count], ['Error', run.error_message]].filter(([,value]) => value !== undefined && value !== null && value !== '')) {
    const item = node('div'); item.append(node('dt', label), node('dd', value)); values.append(item);
  }
  const links = byId('artifact-links'); links.replaceChildren();
  for (const item of data.artifacts) {
    for (const [label, path] of [['View screenshot', item.screenshot_url], ['Read OCR text', item.ocr_url]]) {
      if (path) { const link = node('a', label); link.href = path; link.target = '_blank'; link.rel = 'noopener'; links.append(link); }
    }
  }
  let warning = data.warning || '';
  if (data.reused) warning = 'Opened saved results.';
  if (data.target_count === 50 && !run.satisfies_50) warning = [warning, `Saved ${run.final_count} distinct supplied URLs, including ${run.direct_url_count ?? 0} direct URLs. The conservative 50-direct-URL target is not yet satisfied.`].filter(Boolean).join(' ');
  if (run.satisfies_50) warning = [warning, 'This saved collection contains at least 50 distinct direct URL addresses; publisher content has not been independently verified.'].filter(Boolean).join(' ');
  if (run.error_message || run.status === 'failed' || !run.final_count) warning = [warning, run.error_message || 'This run produced zero usable organic URLs. The engine may be blocked or its HTML unsupported.'].filter(Boolean).join(' ');

  message(warning);
  renderResults();
  updateActions();
  document.querySelectorAll('.history-item').forEach(item => item.setAttribute('aria-current', String(Number(item.dataset.id) === run.id)));
}
async function openRun(id) {
  try { showRun(await api(`/api/runs/${id}`)); toggleSidebar(false); scrollResults(); }
  catch (error) { message(error.message); }
}
async function loadHistory(initial = false) {
  try {
    const rows = await api('/api/runs');
    const list = byId('history-list'); list.replaceChildren();
    byId('history-status').textContent = rows.length ? '' : 'No saved runs yet.';
    for (const run of rows) {
      const button = node('button', null, 'history-item'); button.type = 'button'; button.dataset.id = run.id; button.disabled = busy;
      button.setAttribute('aria-current', String(current?.run.id === run.id));
      const date = new Date(run.started_at || run.created_at);
      const dateLabel = Number.isNaN(date.getTime()) ? 'Saved search' : date.toLocaleDateString();
      let metadata = run.collection_metadata;
      if (typeof metadata === 'string') { try { metadata = JSON.parse(metadata); } catch { metadata = null; } }
      const modeLabel = run.search_type === 'ai' ? 'AI · Gemini' : metadata?.mode === 'collect' ? 'Collect 50' : 'Search';
      button.append(node('strong', run.query_text), node('small', `${modeLabel} · ${dateLabel} · ${run.final_count} results`));
      button.addEventListener('click', () => run.search_type === 'ai' ? openAIRun(run.id) : openRun(run.id)); list.append(button);
    }
    if (initial && rows.length) await openRun(rows[0].id);
  } catch (error) { byId('history-status').textContent = error.message; }
}
function updateActions() {
  const collect = byId('mode').value === 'collect';
  byId('max-pages').disabled = busy;
  const sameQuery = current?.run.query_text === byId('query').value;
  const compatible = current?.run.provider === 'google:scraperapi:structured';
  byId('collect-more').disabled = busy || !sameQuery || !compatible || current.run.satisfies_50;
  byId('capture-run').disabled = busy || !current || !['google', 'bing'].includes(current.run.engine) || !current.results.length || current.run.status === 'running';
  byId('search-button').textContent = collect ? 'Collect 50 ↗' : 'Search ↗';
}
function setBusy(value) {
  busy = value; byId('loading').hidden = !value;
  for (const id of ['query', 'engine', 'mode', 'search-button', 'refresh-search', 'internet-mode', 'ai-mode', 'collect50', 'open-library', 'sidebar-library', 'ai-search-button', 'ai-engine', 'summarize-ai']) byId(id).disabled = value;
  document.querySelectorAll('.history-item').forEach(item => item.disabled = value);
  updateActions();
}
async function submitSearch(refresh = false, resumeRunId = null) {
  if (busy) return;
  if (searchType === 'ai') { await submitAI(); return; }
  if (!byId('query').value.trim()) { message('Enter a research query.'); return; }
  const mode = resumeRunId ? 'collect' : byId('mode').value;
  if (resumeRunId) byId('mode').value = 'collect';
  const pages = Number(byId('max-pages').value);
  if (!Number.isInteger(pages) || pages < 1 || pages > 50) { message('Choose a page limit from 1 to 50.'); return; }
  setBusy(true); message('');
  byId('loading-text').textContent = ' Checking saved collections; only authorized pages will be requested…';
  const baseline = Math.max(0, ...Array.from(document.querySelectorAll('.history-item')).map(item => Number(item.dataset.id)));
  let progressBusy = false;
  const progress = setInterval(async () => {
    if (progressBusy) return;
    progressBusy = true;
    try {
      const runs = await api('/api/runs');
      const active = runs.find(run => run.query_text === byId('query').value && run.engine === 'google' && (resumeRunId ? run.id === resumeRunId : run.id > baseline));
      if (active) {
        const data = await api(`/api/runs/${active.id}`);
        byId('loading-text').textContent = ` Run #${active.id}: ${data.collection?.pages ?? 0} pages saved, ${data.run.final_count} distinct observed URLs, ${data.run.direct_url_count ?? 0} direct URLs / 50.`;
      }
    } catch { /* Final request/error display remains authoritative. */ }
    finally { progressBusy = false; }
  }, 2000);
  const body = {query:byId('query').value, engine:byId('engine').value, mode, max_pages:pages, refresh, resume_run_id:resumeRunId, allow_paid:false};
  try {
    let data;
    try { data = await api('/api/search', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}, pages * 75000 + 15000); }
    catch (error) {
      if (error.status !== 409 || !error.detail?.requires_confirmation) throw error;
      if (!window.confirm(error.message)) { message('No paid requests were authorized.'); return; }
      body.allow_paid = true;
      data = await api('/api/search', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}, pages * 75000 + 15000);
    }
    showRun(data);
    scrollResults();
  } catch (error) { message(error.message); }
  finally { clearInterval(progress); await loadHistory(); setBusy(false); }
}
byId('search-form').addEventListener('submit', event => { event.preventDefault(); submitSearch(); });
byId('refresh-search').addEventListener('click', () => submitSearch(true));
byId('collect-more').addEventListener('click', () => submitSearch(false, current.run.id));
byId('mode').addEventListener('change', updateActions);
byId('query').addEventListener('input', updateActions);
byId('all-observations').addEventListener('change', renderResults);
byId('history-nav').addEventListener('click', () => { activeNavigation('history-nav'); loadHistory(); byId('history-list').scrollIntoView({block:'nearest'}); });
loadHistory();
updateActions();

byId('capture-run').addEventListener('click', async () => {
  if (busy || !current) return;
  const runId = current.run.id;
  setBusy(true); message('Opening the original provider page for an authentic capture…');
  try {
    const result = await api(`/api/runs/${runId}/capture`, {method:'POST'}, 150000);
    await openRun(runId);
    message(result.status === 'completed' ? 'Authentic provider screenshot and local OCR saved.' : result.error || 'Capture did not complete.');
  } catch (error) { message(error.message); }
  finally { setBusy(false); }
});

function toggleSidebar(open) {
  byId('sidebar').hidden = !open;
  byId('sidebar-backdrop').hidden = !open;
  byId('toggle-history').setAttribute('aria-expanded', String(open));
  document.body.classList.toggle('sidebar-open', open);
  if (open) { loadHistory(); byId('close-history').focus(); }
  else byId('toggle-history').focus();
}
function setSearchType(type) {
  searchType = type;
  activeNavigation(current || (typeof activeAI !== 'undefined' && activeAI) ? 'history-nav' : 'new-search');
  byId('library').hidden = true;
  byId('search-form').closest('section').hidden = false;
  const ai = type === 'ai';
  byId('internet-mode').setAttribute('aria-pressed', String(!ai));
  byId('ai-mode').setAttribute('aria-pressed', String(ai));
  byId('internet-controls').hidden = ai;
  byId('ai-provider').hidden = !ai;
  byId('ai-results').hidden = !ai;
  byId('internet-results').hidden = ai || !current;
  document.body.classList.toggle('has-results', !!current || ai);
  message('');
}
function scrollResults() {
  requestAnimationFrame(() => (byId('results').firstElementChild || byId('internet-results')).scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block:'start'}));
}
byId('internet-mode').addEventListener('click', () => setSearchType('internet'));
byId('ai-mode').addEventListener('click', () => setSearchType('ai'));
byId('toggle-history').addEventListener('click', () => toggleSidebar(byId('sidebar').hidden));
byId('close-history').addEventListener('click', () => toggleSidebar(false));
byId('sidebar-backdrop').addEventListener('click', () => toggleSidebar(false));
document.addEventListener('keydown', event => { if (event.key === 'Escape' && !byId('sidebar').hidden) toggleSidebar(false); });
byId('new-search').addEventListener('click', () => {
  current = null; resetAI(); setSearchType('internet'); document.body.classList.remove('has-results');
  byId('query').value = ''; byId('mode').value = 'search'; updateActions(); toggleSidebar(false); byId('query').focus();
});

document.addEventListener('keydown', event => {
  if (event.key !== 'Tab' || byId('sidebar').hidden || matchMedia('(min-width:1200px)').matches) return;
  const controls = [...byId('sidebar').querySelectorAll('button:not(:disabled), a[href]')];
  const first = controls[0], last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

let libraryPage = 1;
async function loadLibrary() {
  if (busy) return;
  activeNavigation('sidebar-library');
  byId('library').hidden = false;
  byId('search-form').closest('section').hidden = true;
  byId('internet-results').hidden = true;
  byId('ai-results').hidden = true;
  document.body.classList.add('has-results');
  byId('saved-ai').replaceChildren(); message('');
  byId('library-status').textContent = 'Loading…';
  byId('library-prev').disabled = true; byId('library-next').disabled = true;
  try {
    const filter = byId('library-filter').value;
    const data = await api(`/api/library?page=${libraryPage}${filter ? `&search_type=${filter}` : ''}`);
    const list = byId('library-list'); list.replaceChildren();
    for (const item of data.items) {
      const button = node('button', null, 'library-item');
      button.append(node('strong', item.query_text), node('small', `${item.search_type === 'web' ? 'Web' : item.search_type === 'ai' ? 'AI' : 'Unknown'} · ${item.provider || 'Unknown provider'} · ${new Date(item.created_at).toLocaleString()} · ${item.result_count} results · ${item.summary_available ? 'Summary available' : 'No summary'}`));
      button.addEventListener('click', async () => {
        if (item.kind === 'run' && item.search_type !== 'ai') { await openRun(item.id); return; }
        try {
          const output = await api(`/api/library/${item.kind}/${item.id}`);
          if (output.responses?.[0]?.prompt_version) { await openAI(output.responses[0].id); return; }
          const area = byId('saved-ai'); area.replaceChildren(node('h2', item.query_text));
          for (const response of output.responses) {
            const details = node('details'); details.append(node('summary', `${response.provider} · ${response.model_name || 'Model not recorded'}`), node('pre', response.response_text)); area.append(details);
          }
          for (const summary of output.summaries) { area.append(node('h3', 'Saved summary'), node('pre', summary.summary_text)); appendDownloads(area, summary.id); }
          if (!output.responses.length && !output.summaries.length) area.append(node('p', 'No saved AI output for this run.'));
        } catch (error) { byId('library-status').textContent = error.message; }
      });
      list.append(button);
    }
    byId('library-status').textContent = data.items.length ? '' : 'No saved items.';
    byId('library-page').textContent = `Page ${data.page}`;
    byId('library-prev').disabled = libraryPage <= 1;
    byId('library-next').disabled = !data.has_more;
  } catch (error) { byId('library-status').textContent = error.message; }
}
for (const id of ['open-library', 'sidebar-library', 'ai-search-button', 'ai-engine', 'summarize-ai']) byId(id).addEventListener('click', () => { toggleSidebar(false); libraryPage = 1; loadLibrary(); });
byId('close-library').addEventListener('click', () => setSearchType(searchType));
byId('library-filter').addEventListener('change', () => { libraryPage = 1; loadLibrary(); });
byId('library-prev').addEventListener('click', () => { libraryPage--; loadLibrary(); });
byId('library-next').addEventListener('click', () => { libraryPage++; loadLibrary(); });
byId('collect50').addEventListener('click', () => { byId('mode').value = 'collect'; submitSearch(); });
byId('max-pages').addEventListener('change', () => { byId('mode').value = 'search'; updateActions(); });

function activeNavigation(id) {
  document.querySelectorAll('.sidebar-nav button').forEach(button => button.removeAttribute('aria-current'));
  byId(id).setAttribute('aria-current', 'page');
}
