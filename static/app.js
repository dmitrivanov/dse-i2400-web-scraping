const byId = id => document.getElementById(id);
let current = null;
let busy = false;
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
      throw new Error(detail || 'The request could not be completed.');
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
  const rows = current.results.filter(row => !byId('organic-only').checked || organic(row));
  byId('result-count').textContent = `${rows.length} shown / ${current.results.length} stored`;
  byId('empty-state').hidden = rows.length > 0;
  byId('empty-state').textContent = current.results.length ? 'No observations match this filter.' : 'No observations were saved for this run. See its diagnostics above.';
  for (const row of rows) {
    const article = node('article', null, 'result');
    const top = node('div', null, 'result-top');
    top.append(node('span', `${current.run.engine.toUpperCase()} · PAGE ${row.page_number ?? 'not recorded'} · RANK ${row.result_rank ?? '—'}`));
    const isAd = row.is_ad === true || row.is_ad === 1;
    const isOrganic = row.is_ad === false || row.is_ad === 0;
    top.append(node('span', isAd ? 'Advertisement' : isOrganic ? 'Organic placement' : 'Unknown placement', `badge ${isAd ? 'ad' : isOrganic ? '' : 'unknown'}`));
    if (row.is_duplicate) top.append(node('span', 'Duplicate', 'badge duplicate'));
    if (!row.normalized_url) top.append(node('span', 'Invalid URL', 'badge unknown'));
    article.append(top);
    const heading = node('h3');
    const url = safeUrl(row.normalized_url);
    if (url) {
      const link = node('a', row.title || 'Untitled result'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; heading.append(link);
    } else heading.textContent = row.title || 'Untitled result';
    article.append(heading, node('span', row.normalized_url || row.original_url, 'destination'));
    article.append(node('p', row.snippet || 'No snippet was provided in the source HTML.'));
    const details = node('details'); details.append(node('summary', 'Original observed URL'), node('div', row.original_url, 'original')); article.append(details);
    list.append(article);
  }
}
function showRun(data) {
  current = data;
  const run = data.run;
  byId('run-status').textContent = `#${run.id} · ${run.status}`;
  byId('run-status').className = `badge ${run.status === 'failed' ? 'failed' : ''}`;
  const values = byId('diagnostic-values'); values.replaceChildren();
  for (const [label, value] of [ ['Query', run.query_text], ['Engine', run.engine], ['Fetcher', run.fetcher || 'Not recorded for this run'], ['Run ID', run.id], ['Status', run.status], ['Raw', run.raw_count], ['Ads', run.ad_count], ['Duplicates', run.duplicate_count], ['Unique organic', `${run.final_count} / 50`], ['Provider', run.provider || 'Historical / not recorded'], ['Error', run.error_message || 'None'] ]) {
    const item = node('div'); item.append(node('dt', label), node('dd', value)); values.append(item);
  }
  const links = byId('artifact-links'); links.replaceChildren();
  for (const item of data.artifacts) {
    for (const [label, path] of [['View screenshot', item.screenshot_url], ['Read OCR text', item.ocr_url]]) {
      if (path) { const link = node('a', `${label} · ${item.id}`); link.href = path; link.target = '_blank'; link.rel = 'noopener'; links.append(link); }
    }
  }
  let warning = data.warning || '';
  if (data.reused) warning = `Reused saved run #${run.id}. No paid request was made.`;
  if (data.target_count === 50 && run.final_count < 50) warning = [warning, `Saved ${run.final_count} / 50 unique organic URLs. The 50-URL requirement is not yet satisfied.`].filter(Boolean).join(' ');
  if (run.final_count >= 50) warning = [warning, 'This saved collection satisfies the 50-URL requirement.'].filter(Boolean).join(' ');
  if (run.error_message || run.status === 'failed' || !run.final_count) warning = [warning, run.error_message || 'This run produced zero usable organic URLs. The engine may be blocked or its HTML unsupported.'].filter(Boolean).join(' ');
  message(warning);
  renderResults();
  updateActions();
  document.querySelectorAll('.history-item').forEach(item => item.setAttribute('aria-current', String(Number(item.dataset.id) === run.id)));
}
async function openRun(id) {
  try { showRun(await api(`/api/runs/${id}`)); }
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
      button.append(node('strong', run.query_text), node('small', `#${run.id} · ${run.engine} · ${run.status} · ${run.final_count} / 50 unique organic`));
      button.addEventListener('click', () => openRun(run.id)); list.append(button);
    }
    if (initial && rows.length) await openRun(rows[0].id);
  } catch (error) { byId('history-status').textContent = error.message; }
}
function updateActions() {
  const collect = byId('mode').value === 'collect';
  byId('max-pages').disabled = busy || !collect;
  const sameQuery = current?.run.query_text === byId('query').value;
  const compatible = current?.run.provider === 'google:scraperapi:structured';
  byId('collect-more').disabled = busy || !sameQuery || !compatible || current.run.final_count >= 50;
  byId('search-button').firstChild.textContent = collect ? 'Collect 50 ' : 'Search ';
}
function setBusy(value) {
  busy = value; byId('loading').hidden = !value;
  for (const id of ['query', 'engine', 'mode', 'search-button', 'refresh-history', 'refresh-search']) byId(id).disabled = value;
  document.querySelectorAll('.history-item').forEach(item => item.disabled = value);
  updateActions();
}
async function submitSearch(refresh = false, resumeRunId = null) {
  if (busy) return;
  const mode = resumeRunId ? 'collect' : byId('mode').value;
  if (resumeRunId) byId('mode').value = 'collect';
  const pages = mode === 'collect' ? Number(byId('max-pages').value) : 1;
  if (!Number.isInteger(pages) || pages < 1 || pages > 20) { message('Choose a page budget from 1 to 20.'); return; }
  setBusy(true); message('');
  try {
    const data = await api('/api/search', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query:byId('query').value, engine:'google', mode, max_pages:pages, refresh, resume_run_id:resumeRunId})}, pages * 75000 + 15000);
    showRun(data);
  } catch (error) { message(error.message); }
  finally { await loadHistory(); setBusy(false); }
}
byId('search-form').addEventListener('submit', event => { event.preventDefault(); submitSearch(); });
byId('refresh-search').addEventListener('click', () => submitSearch(true));
byId('collect-more').addEventListener('click', () => submitSearch(false, current.run.id));
byId('mode').addEventListener('change', updateActions);
byId('query').addEventListener('input', updateActions);
byId('organic-only').addEventListener('change', renderResults);
byId('refresh-history').addEventListener('click', () => loadHistory());
loadHistory(true);
api('/api/search-options').then(options => { byId('max-pages').value = options.collection_max_pages; updateActions(); }).catch(error => message(error.message));
