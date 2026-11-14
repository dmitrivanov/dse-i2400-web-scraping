// Gemini UI shares the existing composer, request helper and single busy guard.
let activeAI = null;
function markdownInto(container, text, allowedSources = []) {
  container.replaceChildren();
  const allowed = new Set(allowedSources.map(source => source.url));
  function inline(parent, value) {
    // Deliberately small safe Markdown subset: no model HTML executes.
    const tokens = value.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^\s]+\))/g);
    for (const token of tokens) {
      const link = token.match(/^\[([^\]]+)\]\(([^\s]+)\)$/);
      if (link && safeUrl(link[2]) && allowed.has(link[2])) {
        const a = node('a', link[1]); a.href = link[2]; a.target = '_blank'; a.rel = 'noopener noreferrer'; parent.append(a);
      } else if (token.startsWith('**') && token.endsWith('**')) parent.append(node('strong', token.slice(2,-2)));
      else parent.append(document.createTextNode(token));
    }
  }
  for (const block of text.split(/\n\s*\n/)) {
    for (const line of block.split('\n')) {
      if (!line.trim()) continue;
      const heading = line.match(/^(#{1,6})\s+(.*)$/);
      const element = node(heading ? `h${Math.min(heading[1].length + 1, 6)}` : 'p');
      inline(element, heading ? heading[2] : line);
      container.append(element);
    }
  }
}
function appendDownloads(area, id) {
  for (const [label, format] of [['Download Markdown','markdown'],['Download PDF','pdf']]) {
    const a = node('a', label); a.href = `/api/ai/summaries/${id}/export?format=${format}`; area.append(a);
  }
}
function showAI(data) {
  activeAI = data;
  const response = data.response;
  byId('query').value = response.query_text;
  setSearchType('ai');
  byId('ai-status').textContent = data.reused ? 'Opened saved Gemini research.' : 'Gemini research · saved';
  markdownInto(byId('ai-response'), response.response_text, data.sources);
  const sources = byId('ai-sources'); sources.replaceChildren();
  byId('ai-sources-heading').hidden = false;
  if (!data.sources.length) sources.append(node('p', 'No grounded sources were returned. Links written in the response are not verified citations.'));
  for (const source of data.sources) {
    if (!safeUrl(source.url)) continue;
    const a = node('a', source.title || 'Source'); a.href = source.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
    const item = node('div', null, 'grounded-source'); item.append(a); sources.append(item);
  }
  if (data.sources.length) sources.append(node('p', 'Sources supplied by Gemini grounding; publisher destinations have not been independently verified.', 'hint'));
  let grounding = response.grounding_metadata || {};
  if (typeof grounding === 'string') { try { grounding = JSON.parse(grounding); } catch { grounding = {}; } }
  const suggestions = byId('ai-suggestions'); suggestions.replaceChildren();
  if (grounding.search_entry_point?.rendered_content) {
    const frame = node('iframe'); frame.title = 'Google Search suggestions'; frame.setAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox'); frame.src = `/api/ai/responses/${response.id}/suggestions`; suggestions.append(frame);
  }
  byId('summarize-ai').hidden = !response.run_id || response.provider !== 'gemini';
  byId('ai-summary').hidden = !data.summary;
  if (data.summary) {
    markdownInto(byId('ai-summary-text'), data.summary.summary_text, data.sources);
    byId('ai-downloads').replaceChildren(); appendDownloads(byId('ai-downloads'), data.summary.id);
  }
  byId('ai-details').hidden = false;
  const metadata = byId('ai-metadata'); metadata.replaceChildren();
  for (const [label,value] of [['Model',response.model_name || 'Not recorded'],['Saved',response.created_at],['Prompt version',response.prompt_version],['Grounded sources',data.sources.length]]) {
    if (value === undefined || value === null) continue;
    const item = node('div'); item.append(node('dt', label), node('dd', value)); metadata.append(item);
  }
  byId('ai-results').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',block:'start'});
}
async function authorizedAI(url, body) {
  try { return await api(url, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,allow_paid:false})},150000); }
  catch (error) {
    if (error.status !== 409 || !error.detail?.requires_confirmation) throw error;
    if (!confirm(error.message)) { message('No Gemini request was authorized.'); return null; }
    return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,allow_paid:true})},150000);
  }
}
async function submitAI() {
  if (busy) return;
  setBusy(true); message(''); byId('loading-text').textContent = 'Checking saved Gemini research…';
  try { const data = await authorizedAI('/api/ai/search',{query:byId('query').value}); if (data) showAI(data); }
  catch (error) { message(error.message); }
  finally { await loadHistory(); setBusy(false); }
}
async function openAI(id) {
  try { showAI({...await api(`/api/ai/responses/${id}`),reused:true}); toggleSidebar(false); }
  catch (error) { message(error.message); }
}
async function openAIRun(id) {
  try {
    const saved = await api(`/api/library/run/${id}`);
    if (!saved.responses.length) { const detail = await api(`/api/runs/${id}`); toggleSidebar(false); message(detail.run.error_message || `AI run status: ${detail.run.status}. No response has been saved.`); return; }
    await openAI(saved.responses[0].id);
  } catch (error) { message(error.message); }
}
byId('summarize-ai').addEventListener('click', async () => {
  if (busy || !activeAI) return;
  setBusy(true); message(''); byId('loading-text').textContent = 'Checking saved summary…';
  try { const data = await authorizedAI(`/api/ai/responses/${activeAI.response.id}/summarize`,{}); if (data) showAI(data); }
  catch (error) { message(error.message); }
  finally { setBusy(false); }
});

function resetAI() {
  activeAI = null;
  for (const id of ['ai-response', 'ai-sources', 'ai-suggestions', 'ai-downloads', 'ai-summary-text']) byId(id).replaceChildren();
  byId('ai-status').textContent = '';
  for (const id of ['summarize-ai', 'ai-summary', 'ai-sources-heading', 'ai-details']) byId(id).hidden = true;
}
