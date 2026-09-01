/* AUREON frontend.
 *
 * Renders exactly one object: `investigation_result` (docs/ARCHITECTURE.md §12).
 * There is no second data shape and no client-side business logic — the verdict,
 * the confidence and the personalization all arrive already decided. This file
 * only draws what the backend says.
 *
 * Falls back to the committed fixture when the API is unreachable, so the UI is
 * demoable without a running server.
 */
const API = '';                                   // same origin; '' -> /api/...
const FIXTURE = 'fixtures/investigation_result.json';

const state = { symbols: [], profiles: [], symbol: null, userId: null, result: null };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const TONE = { BULLISH: 'bull', BEARISH: 'bear', NEUTRAL: 'neutral', CONFLICT: 'warn', UNAVAILABLE: 'neutral' };
const VERDICT_TONE = {
  STRONG_POSITIVE: 'bull', POSITIVE: 'bull', CAUTION: 'warn',
  NEGATIVE: 'bear', INSUFFICIENT_DATA: 'neutral',
};
const AGENT_LABEL = {
  market_detective: 'Market', news_detective: 'Sentiment',
  filing_detective: 'Fundamental', judge_agent: 'Judge',
};
const pct = (n) => `${Math.round((n || 0) * 100)}%`;
const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function boot() {
  try {
    [state.symbols, state.profiles] = await Promise.all([
      getJSON(`${API}/api/symbols`), getJSON(`${API}/api/profiles`),
    ]);
    state.symbol = state.symbols[0];
    state.userId = state.profiles[0].user.user_id;
    renderProfiles();
    await analyze();
  } catch (e) {
    // Offline: render the committed fixture so the UI still demonstrates.
    try {
      state.result = await getJSON(FIXTURE);
      state.symbols = [state.result.symbol];
      state.symbol = state.result.symbol;
      state.profiles = [{ user: { user_id: 'u1', user_name: 'Priya Sharma', risk_profile: 'CONSERVATIVE' } }];
      state.userId = 'u1';
      renderProfiles();
      render(true);
    } catch (_) {
      $('#app').innerHTML = `<div class="card"><b>Cannot reach the API.</b>
        <p class="muted">Start the backend with <code>uvicorn main:app --reload</code>
        and reload this page.</p><p class="muted">${esc(e.message)}</p></div>`;
    }
  }
}

function renderProfiles() {
  $('#profiles').innerHTML = state.profiles.map((p) => {
    const u = p.user;
    return `<button class="profile-btn ${u.user_id === state.userId ? 'active' : ''}"
      data-user="${esc(u.user_id)}">${esc(u.user_name.split(' ')[0])}
      <small>${esc(u.risk_profile)}</small></button>`;
  }).join('');
}

async function analyze() {
  $('#app').innerHTML = `<div class="loading"><div class="spinner"></div>
    Running agents in parallel on ${esc(state.symbol)}…</div>`;
  state.result = await getJSON(
    `${API}/api/analyze?symbol=${encodeURIComponent(state.symbol)}&user_id=${encodeURIComponent(state.userId)}`);
  render();
}

function render(offline = false) {
  const r = state.result;
  const j = r.judge_output || {};
  const dq = r.data_quality || {};
  const m = r.metrics || {};
  const md = r.market_data || {};
  const failed = (dq.warnings || []).length;

  $('#app').innerHTML = `
    ${offline ? banner('degraded', 'Offline mode — showing the committed fixture. Start the backend for live agents.') : ''}
    ${dq.overall_quality && dq.overall_quality !== 'GOOD' ? banner('degraded',
      `<b>Degraded, not failed.</b> ${esc((dq.warnings || [])[0] || '')}
       <span class="muted">Result still produced, and still cited.</span>`) : ''}
    ${j.agent_conflict ? banner('conflict',
      `<b>Agents disagree.</b> We surface the tension rather than averaging it away.`) : ''}

    <div class="grid">
      <div class="stack">
        ${watchlistCard()}
        ${qualityCard(dq, m)}
      </div>

      <div class="stack">
        ${headerCard(md, r)}
        ${verdictCard(j, r)}
        <div id="reasoning">${dimensionsCard(r.signals || {})}</div>
        ${agentsCard(r.agent_outputs || [])}
      </div>

      <div class="stack">
        <div id="portfolio">${portfolioCard(r.portfolio, r.personalization)}</div>
        <div id="integrity">${metricsCard(m, r.evidence || [])}</div>
      </div>
    </div>`;
  wire();
}

const banner = (kind, html) => `<div class="banner ${kind}">
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex:none;margin-top:1px">
    <path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>
  <div>${html}</div></div>`;

function watchlistCard() {
  return `<div class="card"><div class="card-title">Watchlist</div>
    ${state.symbols.map((s) => `<button class="watch-item ${s === state.symbol ? 'active' : ''}" data-symbol="${esc(s)}">
      <span class="watch-sym">${esc(s)}</span></button>`).join('')}</div>`;
}

function headerCard(md, r) {
  const up = (md.price_change_percent || 0) >= 0;
  return `<div class="card">
    <div class="muted" style="font-size:12px;letter-spacing:.06em">NSE · ${esc(r.symbol)}</div>
    <h2 style="font-size:24px;margin:2px 0 8px">${esc(md.company_name || r.symbol)}</h2>
    <div style="display:flex;align-items:baseline;gap:12px">
      <span style="font-size:32px;font-weight:800;font-variant-numeric:tabular-nums">${inr(md.current_price)}</span>
      <span class="${up ? 'up' : 'down'}" style="font-weight:700">
        ${up ? '▲' : '▼'} ${(md.price_change_percent || 0).toFixed(2)}%</span>
      <span class="muted" style="font-size:12px">RSI ${(md.rsi || 0).toFixed(1)} ·
        Vol ${(md.volume / (md.average_volume || 1)).toFixed(1)}× avg</span>
    </div></div>`;
}

function verdictCard(j, r) {
  const tone = VERDICT_TONE[j.verdict] || 'neutral';
  const p = r.personalization || {};
  return `<div class="card verdict-card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
      <div>
        <div class="muted" style="font-size:12px;letter-spacing:.06em;text-transform:uppercase">AI recommendation</div>
        <div class="verdict-word ${tone}">${esc((j.verdict || '').replace(/_/g, ' '))}</div>
      </div>
      <div style="min-width:150px">
        <div style="display:flex;justify-content:space-between;font-size:12px" class="muted">
          <span>Confidence</span><b style="color:var(--on-surface)">${pct(j.confidence)}</b></div>
        <div class="bar ${tone}" style="margin-top:6px"><i style="width:${pct(j.confidence)}"></i></div>
      </div>
    </div>
    <p style="margin:14px 0 0">${esc(j.summary)}</p>
    ${p.personalized_reason ? `<div class="personal">
      <b>Why this differs for you · ${esc(p.risk_profile)}</b>${esc(p.personalized_reason)}</div>` : ''}
  </div>`;
}

function dimensionsCard(s) {
  const dim = (title, sig) => {
    const t = TONE[sig?.signal] || 'neutral';
    return `<div class="dim ${t}">
      <h4>${title}</h4>
      <div style="display:flex;align-items:baseline;gap:8px">
        <span class="dim-val">${pct(sig?.confidence)}</span>
        <span class="chip ${t}">${esc(sig?.signal || 'N/A')}</span>
      </div>
      <div class="bar ${t}" style="margin-top:10px"><i style="width:${pct(sig?.confidence)}"></i></div>
      <ul class="reasons">${(sig?.reasons || []).slice(0, 3).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    </div>`;
  };
  return `<div>
    <div class="card-title" style="margin-bottom:10px">Three independent signal dimensions</div>
    <div class="dims">
      ${dim('Price momentum', s.price_signal)}
      ${dim('Volume anomaly', s.volume_signal)}
      ${dim('Sentiment', s.sentiment_signal)}
    </div></div>`;
}

function agentsCard(agents) {
  return `<div class="card">
    <div class="card-title">Agent reasoning
      <span class="muted" style="font-weight:500;font-size:12px">· ran in parallel</span></div>
    <div class="stack" style="gap:12px">
      ${agents.map((a) => {
        const t = TONE[a.signal] || 'neutral';
        const cls = a.status === 'FAILED' ? 'failed' : a.status === 'DEGRADED' ? 'degraded' : '';
        const statusChip = a.status === 'COMPLETE' ? '<span class="chip bull">OK</span>'
          : a.status === 'DEGRADED' ? '<span class="chip warn">Degraded</span>'
          : '<span class="chip neutral">Unavailable</span>';
        return `<div class="agent ${cls}">
          <div class="agent-head">
            <div style="display:flex;align-items:center;gap:10px">
              <span class="agent-name">${esc(AGENT_LABEL[a.agent_name] || a.agent_name)}</span>
              ${statusChip}
            </div>
            ${a.status !== 'FAILED' ? `<div style="display:flex;align-items:center;gap:10px">
              <span class="chip ${t}">${esc(a.signal)}</span>
              <b style="font-variant-numeric:tabular-nums">${pct(a.confidence)}</b></div>` : ''}
          </div>
          ${a.status !== 'FAILED' ? `<div class="bar ${t}"><i style="width:${pct(a.confidence)}"></i></div>` : ''}
          <ul class="reasons">${(a.reasons || []).slice(0, 4).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
          ${(a.evidence || []).length ? `<div class="cites">
            ${a.evidence.map((e, i) => `<button class="cite" data-agent-name="${esc(a.agent_name)}" data-idx="${i}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
              ${esc(e.source_name)} · p.${esc(e.page)}</button>`).join('')}
          </div>` : ''}
        </div>`;
      }).join('')}
    </div></div>`;
}

function portfolioCard(pf, personal) {
  if (!pf) return '';
  const conc = pf.concentration_score || 0;
  return `<div class="card"><div class="card-title">Your portfolio</div>
    <div class="kv"><span class="muted">Value</span><b>${inr(pf.portfolio_value)}</b></div>
    <div class="kv"><span class="muted">Largest position</span>
      <b class="${conc > 25 ? 'down' : ''}">${conc.toFixed(1)}%</b></div>
    <div class="kv"><span class="muted">Risk profile</span><b>${esc(personal?.risk_profile || '')}</b></div>
    <div style="margin-top:12px">
      ${(pf.holdings || []).slice(0, 6).map((h) => {
        const w = pf.portfolio_value ? (h.current_value / pf.portfolio_value) * 100 : 0;
        return `<div style="margin-bottom:8px">
          <div class="hold"><span>${esc(h.symbol)}</span>
            <span class="muted" style="font-variant-numeric:tabular-nums">${w.toFixed(1)}%</span></div>
          <div class="hold-bar"><i style="width:${w}%"></i></div></div>`;
      }).join('')}
    </div></div>`;
}

function qualityCard(dq, m) {
  const online = m.agents_complete ?? 0;
  const total = (m.agents_complete ?? 0) + (m.agents_failed ?? 0);
  const src = (s) => `<div class="kv"><span class="muted">${s[0]}</span>
    <span class="chip ${s[1] === 'AVAILABLE' ? 'bull' : 'warn'}">${esc(s[1] || 'n/a')}</span></div>`;
  return `<div class="card"><div class="card-title">Research integrity</div>
    <div class="kv"><span class="muted">Status</span>
      <span class="chip ${dq.overall_quality === 'GOOD' ? 'bull' : 'warn'}">${esc(dq.overall_quality || '')}</span></div>
    <div class="kv"><span class="muted">Agents online</span><b>${online} / ${total}</b></div>
    ${src(['Market data', dq.market_data])}
    ${src(['News data', dq.news_data])}
    ${src(['Filing data', dq.filing_data])}
    ${(dq.warnings || []).length ? `<ul class="reasons" style="margin-top:10px">
      ${dq.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
  </div>`;
}

function metricsCard(m, evidence) {
  const row = (k, v) => `<div class="kv"><span class="muted">${k}</span><b>${v}</b></div>`;
  return `<div class="card"><div class="card-title">Session metrics</div>
    ${row('Total latency', `${m.total_latency_ms ?? 0} ms`)}
    ${row('Agent latency', `${m.agent_latency_ms ?? 0} ms`)}
    ${row('Signal confidence', pct(m.signal_confidence))}
    ${row('Evidence coverage', pct(m.evidence_coverage))}
    ${row('Concentration', `${(m.concentration_score ?? 0).toFixed(1)}%`)}
    ${row('Verified sources', evidence.length)}
    <div class="muted" style="font-size:11px;margin-top:10px">Logged to logs/sessions.jsonl each run.</div>
  </div>`;
}

/* ---------- citation drawer ---------- */
function openCitation(agentName, idx) {
  const agent = (state.result.agent_outputs || []).find((a) => a.agent_name === agentName);
  const e = agent?.evidence?.[idx];
  if (!e) return;
  $('#drawer-body').innerHTML = `
    <div class="label">Source document</div>
    <h3 style="font-size:19px;margin-bottom:10px">${esc(e.source_name)}</h3>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:18px">
      <span class="chip neutral">${esc((e.source_type || '').replace(/_/g, ' '))}</span>
      ${e.source_date ? `<span class="muted" style="font-size:12px">· ${esc(e.source_date)}</span>` : ''}
      ${e.section ? `<span class="muted" style="font-size:12px">· ${esc(e.section)}, p.${esc(e.page)}</span>` : ''}
    </div>
    <div class="quote">“${esc(e.text)}”</div>
    <div class="attrib">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2">
        <rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 4v4M9 14h.01M15 14h.01"/></svg>
      <div><div class="label" style="margin:0">Attribution</div>
        <b>Used by ${esc(AGENT_LABEL[agentName] || agentName)} agent</b></div>
    </div>
    <div class="verified">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex:none;margin-top:1px">
        <path d="M20 6 9 17l-5-5"/></svg>
      <div><b>Verified quote.</b> This text was copied verbatim from chunk
        <code>${esc(e.chunk_id)}</code> in the filings corpus. The model chose which chunk
        supports its finding; it never wrote this sentence, so the quote cannot be fabricated.</div>
    </div>
    <div style="margin-top:16px" class="muted">
      <div class="label">Relevance</div>${(e.relevance_score ?? 0).toFixed(3)}
    </div>`;
  $('#drawer').classList.add('open');
  $('#drawer').setAttribute('aria-hidden', 'false');
  $('#scrim').classList.add('open');
}

function closeDrawer() {
  $('#drawer').classList.remove('open');
  $('#drawer').setAttribute('aria-hidden', 'true');
  $('#scrim').classList.remove('open');
}

function wire() {
  document.querySelectorAll('.watch-item').forEach((b) => b.onclick = () => {
    state.symbol = b.dataset.symbol; analyze();
  });
  document.querySelectorAll('.cite').forEach((b) => b.onclick = () =>
    openCitation(b.dataset.agentName, Number(b.dataset.idx)));
}

document.addEventListener('click', (ev) => {
  const p = ev.target.closest('.profile-btn');
  if (p) { state.userId = p.dataset.user; renderProfiles(); analyze(); return; }
  const nav = ev.target.closest('[data-scroll]');
  if (nav) {
    document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
    nav.classList.add('active');
    $('#' + nav.dataset.scroll)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
});
$('#drawer-close').onclick = closeDrawer;
$('#scrim').onclick = closeDrawer;
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });

boot();
