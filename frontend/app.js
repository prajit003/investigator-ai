/* INVESTIGATOR frontend.
 *
 * Layout follows the Stitch/Aureon structure: fixed sidebar with view
 * navigation, top bar, card grid, right-hand evidence drawer.
 *
 * Renders exactly one object: `investigation_result` (docs/ARCHITECTURE.md §12).
 * No client-side business logic — verdict, confidence and personalization all
 * arrive already decided. This file only lays them out.
 *
 * Falls back to the committed fixture when the API is unreachable.
 */
const API = '';
const FIXTURE = 'fixtures/investigation_result.json';

const state = { symbols: [], profiles: [], symbol: null, userId: null, result: null, view: 'analysis' };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const TONE = { BULLISH: 'bull', BEARISH: 'bear', NEUTRAL: 'neutral', CONFLICT: 'warn', UNAVAILABLE: 'neutral' };
const VERDICT_TONE = {
  STRONG_POSITIVE: 'bull', POSITIVE: 'bull', CAUTION: 'warn',
  NEGATIVE: 'bear', INSUFFICIENT_DATA: 'neutral',
};
const WITNESS = {
  market_detective: ['Market', 'price action & participation'],
  news_detective: ['Sentiment', 'headline coverage'],
  filing_detective: ['Fundamental', 'filings & transcripts'],
  judge_agent: ['Judge', 'synthesis'],
};
const pct = (n) => `${Math.round((n || 0) * 100)}%`;
const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const d = (i) => `style="animation-delay:${i * 55}ms"`;

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
    try {
      state.result = await getJSON(FIXTURE);
      state.symbols = [state.result.symbol];
      state.symbol = state.result.symbol;
      state.profiles = [{ user: { user_id: 'u1', user_name: 'Priya Sharma', risk_profile: 'CONSERVATIVE' } }];
      state.userId = 'u1';
      renderProfiles();
      render(true);
    } catch (_) {
      $('#app').innerHTML = `<div class="view"><div class="fatal">
        <span class="tag" style="color:var(--stamp)">Backend unreachable</span>
        <p>Start it with <code>uvicorn main:app --port 8077</code>, then reload.</p>
        <p class="mono" style="font-size:12px;color:var(--paper-faint)">${esc(e.message)}</p></div></div>`;
    }
  }
}

function renderProfiles() {
  $('#profiles').innerHTML = state.profiles.map((p) => {
    const u = p.user;
    return `<button class="${u.user_id === state.userId ? 'on' : ''}" data-user="${esc(u.user_id)}">
      <span class="who">${esc(u.user_name.split(' ')[0])}</span>
      <span class="risk">${esc(u.risk_profile)}</span></button>`;
  }).join('');
}

async function analyze() {
  $('#app').innerHTML = `<div class="view"><div class="loading">
    <span class="tag">Dispatching agents in parallel · ${esc(state.symbol)}</span>
    <div class="scan"></div></div></div>`;
  state.result = await getJSON(
    `${API}/api/analyze?symbol=${encodeURIComponent(state.symbol)}&user_id=${encodeURIComponent(state.userId)}`);
  render();
}

/* ================= views ================= */

function render(offline = false) {
  const r = state.result;
  $('#case-no').textContent = r.investigation_id || 'CASE — — — —';
  const m = r.metrics || {};
  $('#foot-note').textContent =
    `${m.agents_complete ?? 0}/${(m.agents_complete ?? 0) + (m.agents_failed ?? 0)} agents · ${m.total_latency_ms ?? 0} ms`;

  const views = { analysis: viewAnalysis, reasoning: viewReasoning, portfolio: viewPortfolio, integrity: viewIntegrity };
  $('#app').innerHTML = `<div class="view">${notices(r, offline)}${(views[state.view] || viewAnalysis)(r)}</div>`;
  wire();
}

function notices(r, offline) {
  const dq = r.data_quality || {};
  return `
    ${offline ? notice('degraded', 'Offline', 'Showing the committed fixture. Start the backend for live agents.') : ''}
    ${dq.overall_quality && dq.overall_quality !== 'GOOD'
      ? notice('degraded', 'Degraded, not failed',
        `${esc((dq.warnings || [])[0] || '')} The finding was still produced, and is still cited.`) : ''}
    ${r.judge_output?.agent_conflict
      ? notice('conflict', 'Agents disagree', 'The tension is reported rather than averaged away.') : ''}`;
}
const notice = (kind, label, text) =>
  `<div class="notice ${kind}"><b>${esc(label)}</b><span>${text}</span></div>`;

/* ---- 1. STOCK ANALYSIS ---- */
function viewAnalysis(r) {
  const md = r.market_data || {};
  const j = r.judge_output || {};
  const tone = VERDICT_TONE[j.verdict] || 'neutral';
  const s = r.signals || {};
  const news = (r.agent_outputs || []).find((a) => a.agent_name === 'news_detective');

  return `<div class="grid-3">
    <div class="stack">
      <div class="card rise" ${d(0)}>
        <div class="card-title">Watchlist</div>
        <div class="watch">${state.symbols.map((sym) => `
          <button class="${sym === state.symbol ? 'on' : ''}" data-symbol="${esc(sym)}">
            <span class="mark"></span><span class="sym">${esc(sym)}</span></button>`).join('')}</div>
      </div>
      ${custodyCard(r.data_quality || {}, 1)}
    </div>

    <div class="stack">
      <div class="card subject rise" ${d(1)}>
        <span class="tag">NSE · ${esc(r.symbol)}</span>
        <h2>${esc(md.company_name || r.symbol)}</h2>
        <div class="price-row">
          <span class="price">${inr(md.current_price)}</span>
          <span class="delta ${(md.price_change_percent || 0) >= 0 ? 'up' : 'down'}">
            ${(md.price_change_percent || 0) >= 0 ? '▲' : '▼'} ${(md.price_change_percent || 0).toFixed(2)}%</span>
        </div>
        <div class="readout">
          <div><span class="tag">RSI</span><span class="v">${(md.rsi || 0).toFixed(1)}</span></div>
          <div><span class="tag">Volume</span><span class="v">${(md.volume / (md.average_volume || 1)).toFixed(1)}×</span></div>
          <div><span class="tag">Momentum</span><span class="v">${(md.momentum || 0) >= 0 ? '+' : ''}${(md.momentum || 0).toFixed(2)}</span></div>
          <div><span class="tag">Volatility</span><span class="v">${(md.volatility || 0).toFixed(2)}</span></div>
        </div>
      </div>

      <div class="rise" ${d(2)}>
        <div class="card-title">Three independent dimensions
          <span class="tag">price · volume · sentiment</span></div>
        <div class="row-3">
          ${dimCard('Price momentum', s.price_signal)}
          ${dimCard('Volume anomaly', s.volume_signal)}
          ${dimCard('Sentiment', s.sentiment_signal)}
        </div>
      </div>

      ${news && news.status !== 'FAILED' ? `<div class="card rise" ${d(3)}>
        <div class="card-title">Headline sentiment</div>
        <div class="feed">${(news.reasons || []).map((x) => {
          const t = /\+\d|positive|BULLISH/.test(x) ? 'pos' : /-\d|negative|BEARISH/.test(x) ? 'neg' : 'neu';
          return `<div class="feed-item ${t}"><p>${esc(x)}</p></div>`;
        }).join('')}</div></div>` : ''}
    </div>

    <div class="stack">
      <div class="card reco ${tone} rise" ${d(2)}>
        <span class="tag">AI recommendation</span>
        <div class="verdict-word ${tone}">${esc((j.verdict || '').replace(/_/g, ' ').toLowerCase())}</div>
        <div class="c-${tone}">
          <div style="display:flex;justify-content:space-between;margin-bottom:7px">
            <span class="tag">Confidence</span><span class="mono" style="font-size:12px">${pct(j.confidence)}</span>
          </div>
          <div class="track"><i style="width:${pct(j.confidence)}"></i></div>
        </div>
        <p style="font-size:14.5px;margin:16px 0 0">${esc(j.summary)}</p>
        <button class="btn" data-view-jump="reasoning">Open AI reasoning →</button>
      </div>

      ${r.personalization?.personalized_reason ? `<div class="inset rise" ${d(3)}>
        <span class="tag">Why this differs for you · ${esc(r.personalization.risk_profile)}</span>
        <p>${esc(r.personalization.personalized_reason)}</p></div>` : ''}
    </div>
  </div>`;
}

function dimCard(title, sig) {
  const t = TONE[sig?.signal] || 'neutral';
  return `<div class="metric-card ${t}">
    <span class="tag">${title}</span>
    <div class="metric-row" style="margin-top:8px">
      <span class="metric-val c-${t}">${pct(sig?.confidence)}</span>
      <span class="chip solid c-${t}">${esc(sig?.signal || 'N/A')}</span>
    </div>
    <div class="c-${t}"><div class="track"><i style="width:${pct(sig?.confidence)}"></i></div></div>
    <ul class="traces">${(sig?.reasons || []).slice(0, 3).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
  </div>`;
}

/* ---- 2. AI REASONING ---- */
function viewReasoning(r) {
  const j = r.judge_output || {};
  const dq = r.data_quality || {};
  const tone = VERDICT_TONE[j.verdict] || 'neutral';
  const agents = r.agent_outputs || [];
  const live = agents.filter((a) => a.status !== 'FAILED').length;

  const src = (label, ok) => `<div class="pipe-src ${ok ? '' : 'off'}">${label}${ok ? '' : ' — unavailable'}</div>`;
  const arrow = `<div class="pipe-arrow"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 12h15m0 0-5-5m5 5-5 5"/></svg></div>`;

  return `
    <div class="card rise" ${d(0)}>
      <div class="card-title">Orchestration <span class="tag">agents dispatched concurrently</span></div>
      <div class="pipeline">
        <div class="pipe-sources">
          ${src('Market data', dq.market_data === 'AVAILABLE')}
          ${src('Filings', dq.filing_data === 'AVAILABLE')}
          ${src('News', dq.news_data === 'AVAILABLE')}
          ${src('Investor profile', true)}
        </div>
        ${arrow}
        <div class="pipe-core">
          <span class="tag">Multi-agent processing</span>
          <div class="n">${live} / ${agents.length}</div>
          <span class="tag" style="letter-spacing:.1em">reporting · ${r.metrics?.agent_latency_ms ?? 0} ms</span>
          <div class="dots"><i></i><i></i><i></i></div>
        </div>
        ${arrow}
        <div class="pipe-final">
          <span class="tag">Final synthesis</span>
          <div class="v c-${tone}">${esc((j.verdict || '').replace(/_/g, ' ').toLowerCase())}</div>
        </div>
      </div>
    </div>

    <div class="card-title rise" style="margin:26px 0 14px" ${d(1)}>Agent testimony</div>
    <div class="row-4">${agents.map((a, i) => agentCard(a, i)).join('')}</div>

    <div class="grid-2" style="margin-top:22px">
      <div class="card rise" ${d(2)}>
        <div class="card-title">Conflict detection</div>
        ${j.agent_conflict
          ? `<div class="notice conflict" style="margin:0 0 14px"><b>Tension</b>
             <span>${esc((j.key_reasons || [])[0] || 'Agents disagree on direction.')}</span></div>`
          : `<p class="muted" style="color:var(--paper-dim);margin:0 0 14px">
             No disagreement: all reporting agents point the same way.</p>`}
        <p style="margin:0">${esc(j.summary)}</p>
        ${(j.key_risks || []).length ? `<div style="margin-top:16px">
          <span class="tag">Key risks</span>
          <ul class="traces">${j.key_risks.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
      </div>
      ${integrityCard(dq, r.metrics || {}, (r.evidence || []).length, 3)}
    </div>`;
}

function agentCard(a, i) {
  const t = TONE[a.signal] || 'neutral';
  const [name, remit] = WITNESS[a.agent_name] || [a.agent_name, ''];
  const cls = a.status === 'FAILED' ? 'failed' : a.status === 'DEGRADED' ? 'degraded' : t;
  const badge = a.status === 'COMPLETE'
    ? '<span class="chip solid c-bull">OK</span>'
    : `<span class="chip solid c-warn">${esc(a.status)}</span>`;
  return `<div class="metric-card ${cls} rise" ${d(i + 1)}>
    <div class="metric-head">
      <div class="metric-name">${esc(name)}<em>${esc(remit)}</em></div>${badge}
    </div>
    ${a.status !== 'FAILED' ? `
      <div class="metric-row">
        <span class="metric-val c-${t}">${pct(a.confidence)}</span>
        <span class="chip c-${t}">${esc(a.signal)}</span>
      </div>
      <div class="c-${t}"><div class="track"><i style="width:${pct(a.confidence)}"></i></div></div>` : ''}
    <ul class="traces">${(a.reasons || []).slice(0, 3).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    ${(a.evidence || []).length ? `<div class="exhibits">
      ${a.evidence.map((e, k) => `<button class="exhibit" data-agent-name="${esc(a.agent_name)}" data-idx="${k}">
        <b>EX-${String(k + 1).padStart(2, '0')}</b> p.${esc(e.page)}</button>`).join('')}</div>` : ''}
  </div>`;
}

/* ---- 3. PORTFOLIO ---- */
function viewPortfolio(r) {
  const pf = r.portfolio;
  const p = r.personalization || {};
  if (!pf) return `<div class="card">No portfolio on file for this profile.</div>`;
  const conc = pf.concentration_score || 0;
  return `<div class="grid-2">
    <div class="card rise" ${d(0)}>
      <div class="card-title">Holdings <span class="tag">${(pf.holdings || []).length} positions</span></div>
      ${(pf.holdings || []).map((h) => {
        const w = pf.portfolio_value ? (h.current_value / pf.portfolio_value) * 100 : 0;
        return `<div class="hold ${w > 25 ? 'hot' : ''}">
          <div class="hold-top"><span>${esc(h.symbol)}</span>
            <span>${inr(h.current_value)} · ${w.toFixed(1)}%</span></div>
          <div class="hold-track"><i style="width:${w}%"></i></div></div>`;
      }).join('')}
    </div>
    <div class="stack">
      <div class="card rise" ${d(1)}>
        <div class="card-title">Mandate</div>
        <div class="kv"><span>Portfolio value</span><b>${inr(pf.portfolio_value)}</b></div>
        <div class="kv"><span>Risk profile</span><b>${esc(p.risk_profile || '')}</b></div>
        <div class="kv"><span>Risk score</span><b>${p.risk_score ?? '—'}</b></div>
        <div class="kv"><span>Horizon</span><b>${esc((p.investment_horizon || '').replace('_', ' '))}</b></div>
        <div class="kv"><span>Largest holding</span><b class="${conc > 25 ? 'down' : 'up'}">${conc.toFixed(1)}%</b></div>
      </div>
      ${p.personalized_reason ? `<div class="inset rise" ${d(2)}>
        <span class="tag">How this changed the finding</span>
        <p>${esc(p.personalized_reason)}</p></div>` : ''}
    </div>
  </div>`;
}

/* ---- 4. RESEARCH INTEGRITY ---- */
function viewIntegrity(r) {
  return `<div class="grid-2">
    ${integrityCard(r.data_quality || {}, r.metrics || {}, (r.evidence || []).length, 0)}
    <div class="card rise" ${d(1)}>
      <div class="card-title">Verified sources <span class="tag">${(r.evidence || []).length} exhibits</span></div>
      ${(r.evidence || []).length ? (r.evidence || []).map((e, i) => `
        <div style="padding:12px 0;border-bottom:1px solid var(--rule)">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:baseline">
            <b style="font-size:14px">${esc(e.source_name)}</b>
            <span class="tag">p.${esc(e.page)}</span></div>
          <p style="margin:6px 0 0;font-size:13px;font-style:italic;color:var(--paper-dim)">
            “${esc((e.text || '').slice(0, 140))}…”</p>
          <div class="exhibits"><button class="exhibit" data-agent-name="filing_detective" data-idx="${i}">
            <b>EX-${String(i + 1).padStart(2, '0')}</b> open exhibit</button></div>
        </div>`).join('')
      : `<p style="color:var(--paper-dim);margin:0">No source material was retrievable for this symbol.
         The fundamental dimension is reported as missing, not neutral.</p>`}
    </div>
  </div>`;
}

function custodyCard(dq, i) {
  const dot = (v) => `<span class="dot" style="background:${v === 'AVAILABLE' ? 'var(--bull)' : 'var(--bear)'}"></span>`;
  return `<div class="card rise" ${d(i)}>
    <div class="card-title">Chain of custody</div>
    <div class="kv"><span>Integrity</span>
      <b class="${dq.overall_quality === 'GOOD' ? 'up' : 'down'}">${esc(dq.overall_quality || '—')}</b></div>
    <div class="kv"><span>${dot(dq.market_data)}Market</span><b>${esc(dq.market_data || '—')}</b></div>
    <div class="kv"><span>${dot(dq.news_data)}News</span><b>${esc(dq.news_data || '—')}</b></div>
    <div class="kv"><span>${dot(dq.filing_data)}Filings</span><b>${esc(dq.filing_data || '—')}</b></div>
  </div>`;
}

function integrityCard(dq, m, sources, i) {
  const row = (k, v) => `<div class="kv"><span>${k}</span><b>${v}</b></div>`;
  return `<div class="card rise" ${d(i)}>
    <div class="card-title">Research integrity</div>
    <div class="kv"><span>Status</span>
      <b class="${dq.overall_quality === 'GOOD' ? 'up' : 'down'}">${esc(dq.overall_quality || '—')}</b></div>
    ${row('Agents reporting', `${m.agents_complete ?? 0} / ${(m.agents_complete ?? 0) + (m.agents_failed ?? 0)}`)}
    ${row('Verified sources', sources)}
    ${row('Evidence coverage', pct(m.evidence_coverage))}
    ${row('Signal confidence', pct(m.signal_confidence))}
    ${row('Total latency', `${m.total_latency_ms ?? 0} ms`)}
    ${row('Concentration', `${(m.concentration_score ?? 0).toFixed(1)}%`)}
    ${(dq.warnings || []).length ? `<ul class="traces" style="margin-top:12px">
      ${dq.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
    <p class="tag" style="margin-top:12px;line-height:1.7">Appended to logs/sessions.jsonl on every run.</p>
  </div>`;
}

/* ================= exhibit drawer ================= */
function openExhibit(agentName, idx) {
  const agent = (state.result.agent_outputs || []).find((a) => a.agent_name === agentName);
  const e = agent?.evidence?.[idx];
  if (!e) return;
  const [name] = WITNESS[agentName] || [agentName];
  $('#drawer-body').innerHTML = `
    <span class="tag">${esc((e.source_type || '').replace(/_/g, ' '))}</span>
    <h3>${esc(e.source_name)}</h3>
    <div class="meta-row">
      ${e.source_date ? `<span class="tag">${esc(e.source_date)}</span><span class="tag">/</span>` : ''}
      ${e.section ? `<span class="tag">${esc(e.section)}</span><span class="tag">/</span>` : ''}
      <span class="tag">Page ${esc(e.page)}</span>
    </div>
    <div class="exhibit-quote">${esc(e.text)}</div>
    <div class="attest"><span class="tag">Relied upon by</span>
      <p style="color:var(--paper);font-size:15px">${esc(name)} agent</p></div>
    <div class="attest verified"><span class="tag" style="color:var(--bull)">Verified quotation</span>
      <p>Copied verbatim from chunk <code>${esc(e.chunk_id)}</code> in the filings corpus.
      The agent chose which chunk supports its finding; it never wrote this sentence,
      so the quotation cannot be fabricated.</p></div>
    <div class="attest"><span class="tag">Retrieval relevance</span>
      <p class="mono" style="color:var(--paper)">${(e.relevance_score ?? 0).toFixed(3)}</p></div>`;
  $('#drawer').classList.add('open');
  $('#drawer').setAttribute('aria-hidden', 'false');
  $('#scrim').classList.add('open');
}
function closeDrawer() {
  $('#drawer').classList.remove('open');
  $('#drawer').setAttribute('aria-hidden', 'true');
  $('#scrim').classList.remove('open');
}

function setView(v) {
  state.view = v;
  document.querySelectorAll('#nav .nav-item').forEach((n) =>
    n.classList.toggle('active', n.dataset.view === v));
  render();
}

function wire() {
  document.querySelectorAll('[data-symbol]').forEach((b) => b.onclick = () => {
    state.symbol = b.dataset.symbol; analyze();
  });
  document.querySelectorAll('.exhibit').forEach((b) => b.onclick = () =>
    openExhibit(b.dataset.agentName, Number(b.dataset.idx)));
  document.querySelectorAll('[data-view-jump]').forEach((b) => b.onclick = () =>
    setView(b.dataset.viewJump));
}

document.addEventListener('click', (ev) => {
  const p = ev.target.closest('[data-user]');
  if (p) { state.userId = p.dataset.user; renderProfiles(); analyze(); return; }
  const nav = ev.target.closest('#nav .nav-item');
  if (nav) setView(nav.dataset.view);
});
$('#drawer-close').onclick = closeDrawer;
$('#scrim').onclick = closeDrawer;
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });

boot();
