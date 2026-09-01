/* INVESTIGATOR — "The Dossier" frontend.
 *
 * Renders exactly one object: `investigation_result` (docs/ARCHITECTURE.md §12).
 * No client-side business logic: the verdict, the confidence and the
 * personalization all arrive already decided. This file only sets type.
 *
 * Falls back to the committed fixture when the API is unreachable, so the
 * interface still demonstrates with no server running.
 */
const API = '';
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
/* Agents are witnesses. Each gets a plain-English name and a remit. */
const WITNESS = {
  market_detective: ['Market', 'price action and participation'],
  news_detective: ['Sentiment', 'headline coverage'],
  filing_detective: ['Fundamental', 'regulatory filings and transcripts'],
  judge_agent: ['Judge', 'synthesis'],
};
const pct = (n) => `${Math.round((n || 0) * 100)}%`;
const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const delay = (i) => `style="animation-delay:${i * 55}ms"`;

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
      $('#app').innerHTML = `<div class="body"><div class="fatal">
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
  $('#app').innerHTML = `<div class="body"><div class="loading">
    <span class="tag">Dispatching agents in parallel &middot; ${esc(state.symbol)}</span>
    <div class="scan"></div></div></div>`;
  state.result = await getJSON(
    `${API}/api/analyze?symbol=${encodeURIComponent(state.symbol)}&user_id=${encodeURIComponent(state.userId)}`);
  render();
}

/* ---------------------------------------------------------------- */

function render(offline = false) {
  const r = state.result;
  const j = r.judge_output || {};
  const dq = r.data_quality || {};
  const m = r.metrics || {};
  const md = r.market_data || {};
  const tone = VERDICT_TONE[j.verdict] || 'neutral';

  $('#case-no').textContent = r.investigation_id || 'CASE — — — — —';

  $('#app').innerHTML = `<div class="page">

    <aside class="rail">
      <div class="block-head"><span class="tag">Docket</span><hr class="rule-h"></div>
      <div class="docket">${state.symbols.map((s, i) => `
        <button class="${s === state.symbol ? 'on' : ''} rise" data-symbol="${esc(s)}" ${delay(i)}>
          <span class="mark"></span><span class="sym">${esc(s)}</span>
        </button>`).join('')}
      </div>
      ${custodyBlock(dq)}
    </aside>

    <main class="body">
      ${offline ? notice('degraded', 'Offline', 'Showing the committed fixture. Start the backend for live agents.') : ''}
      ${dq.overall_quality && dq.overall_quality !== 'GOOD'
        ? notice('degraded', 'Degraded, not failed',
          `${esc((dq.warnings || [])[0] || '')} The finding was still produced, and is still cited.`) : ''}
      ${j.agent_conflict
        ? notice('conflict', 'Agents disagree',
          'The tension is reported rather than averaged away.') : ''}

      <section class="block subject rise" ${delay(1)}>
        <div>
          <span class="tag">NSE &middot; ${esc(r.symbol)}</span>
          <h2>${esc(md.company_name || r.symbol)}</h2>
          <div class="price-row">
            <span class="price">${inr(md.current_price)}</span>
            <span class="delta ${(md.price_change_percent || 0) >= 0 ? 'up' : 'down'}">
              ${(md.price_change_percent || 0) >= 0 ? '▲' : '▼'} ${(md.price_change_percent || 0).toFixed(2)}%</span>
          </div>
        </div>
        <div class="readout">
          <div><span class="tag">RSI</span><span class="v">${(md.rsi || 0).toFixed(1)}</span></div>
          <div><span class="tag">Volume</span><span class="v">${(md.volume / (md.average_volume || 1)).toFixed(1)}×</span></div>
          <div><span class="tag">Momentum</span><span class="v">${(md.momentum || 0) >= 0 ? '+' : ''}${(md.momentum || 0).toFixed(2)}</span></div>
        </div>
      </section>

      <section class="block finding rise" ${delay(2)}>
        <span class="tag">The finding</span>
        <div class="verdict-word ${tone}">${esc((j.verdict || '').replace(/_/g, ' ').toLowerCase())}</div>
        <div class="conf-line c-${tone}">
          <div style="display:flex;justify-content:space-between;margin-bottom:6px">
            <span class="tag">Confidence</span>
            <span class="mono" style="font-size:12px">${pct(j.confidence)}</span>
          </div>
          <div class="conf-track"><i style="width:${pct(j.confidence)}"></i></div>
        </div>
        <p class="summary">${esc(j.summary)}</p>
        ${r.personalization?.personalized_reason ? `
          <div class="pullquote">
            <span class="tag">Why this differs for you &middot; ${esc(r.personalization.risk_profile)}</span>
            <p>${esc(r.personalization.personalized_reason)}</p>
          </div>` : ''}
      </section>

      <section class="block rise" id="dimensions" ${delay(3)}>
        <div class="block-head"><span class="tag">Three independent dimensions</span><hr class="rule-h"></div>
        <div class="dims">
          ${dimension('Price momentum', r.signals?.price_signal)}
          ${dimension('Volume anomaly', r.signals?.volume_signal)}
          ${dimension('Sentiment', r.signals?.sentiment_signal)}
        </div>
      </section>

      <section class="block rise" id="testimony" ${delay(4)}>
        <div class="block-head"><span class="tag">Testimony &middot; agents ran in parallel</span><hr class="rule-h"></div>
        ${(r.agent_outputs || []).map(testimony).join('')}
      </section>
    </main>

    <aside class="rail rail-r">
      ${portfolioBlock(r.portfolio, r.personalization)}
      ${metricsBlock(m, (r.evidence || []).length)}
    </aside>
  </div>`;
  wire();
}

const notice = (kind, label, text) =>
  `<div class="notice ${kind}"><b>${esc(label)}</b><span>${text}</span></div>`;

function dimension(title, sig) {
  const t = TONE[sig?.signal] || 'neutral';
  return `<div class="dim">
    <span class="tag">${title}</span>
    <div class="dim-top" style="margin-top:8px">
      <span class="dim-val c-${t}">${pct(sig?.confidence)}</span>
      <span class="verdict-chip c-${t}">${esc(sig?.signal || 'N/A')}</span>
    </div>
    <ul class="traces">${(sig?.reasons || []).slice(0, 4).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
  </div>`;
}

function testimony(a) {
  const t = TONE[a.signal] || 'neutral';
  const [name, remit] = WITNESS[a.agent_name] || [a.agent_name, ''];
  const cls = a.status === 'FAILED' ? 'failed' : a.status === 'DEGRADED' ? 'degraded' : '';
  const status = a.status === 'COMPLETE' ? '' : `<span class="verdict-chip c-warn">${esc(a.status)}</span>`;
  return `<article class="testimony ${cls}">
    <div class="t-head">
      <h4 class="t-name">${esc(name)}<em>${esc(remit)}</em></h4>
      <div class="t-right">
        ${status}
        ${a.status !== 'FAILED' ? `<span class="verdict-chip c-${t}">${esc(a.signal)}</span>
          <span class="t-conf c-${t}">${pct(a.confidence)}</span>` : ''}
      </div>
    </div>
    <ul class="traces">${(a.reasons || []).slice(0, 4).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    ${(a.evidence || []).length ? `<div class="exhibits">
      ${a.evidence.map((e, i) => `<button class="exhibit" data-agent-name="${esc(a.agent_name)}" data-idx="${i}">
        <b>EX-${String(i + 1).padStart(2, '0')}</b> ${esc(e.source_name)} &middot; p.${esc(e.page)}
      </button>`).join('')}</div>` : ''}
  </article>`;
}

function custodyBlock(dq) {
  const dot = (v) => `<span class="status-dot" style="background:${v === 'AVAILABLE' ? 'var(--bull)' : 'var(--bear)'}"></span>`;
  return `<div class="block" style="margin-top:32px">
    <div class="block-head"><span class="tag">Chain of custody</span><hr class="rule-h"></div>
    <div class="kv"><span>Integrity</span><b class="${dq.overall_quality === 'GOOD' ? 'up' : 'down'}">${esc(dq.overall_quality || '—')}</b></div>
    <div class="kv"><span>${dot(dq.market_data)}Market</span><b>${esc(dq.market_data || '—')}</b></div>
    <div class="kv"><span>${dot(dq.news_data)}News</span><b>${esc(dq.news_data || '—')}</b></div>
    <div class="kv"><span>${dot(dq.filing_data)}Filings</span><b>${esc(dq.filing_data || '—')}</b></div>
    ${(dq.warnings || []).length ? `<ul class="traces" style="margin-top:12px">
      ${dq.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
  </div>`;
}

function portfolioBlock(pf, personal) {
  if (!pf) return '';
  const conc = pf.concentration_score || 0;
  return `<div class="block">
    <div class="block-head"><span class="tag">Your position</span><hr class="rule-h"></div>
    <div class="kv"><span>Portfolio</span><b>${inr(pf.portfolio_value)}</b></div>
    <div class="kv"><span>Largest holding</span><b class="${conc > 25 ? 'down' : ''}">${conc.toFixed(1)}%</b></div>
    <div class="kv"><span>Mandate</span><b>${esc(personal?.risk_profile || '')}</b></div>
    <div style="margin-top:14px">
      ${(pf.holdings || []).slice(0, 6).map((h) => {
        const w = pf.portfolio_value ? (h.current_value / pf.portfolio_value) * 100 : 0;
        return `<div class="hold ${w > 25 ? 'hot' : ''}">
          <div class="hold-top"><span>${esc(h.symbol)}</span><span>${w.toFixed(1)}%</span></div>
          <div class="hold-track"><i style="width:${w}%"></i></div></div>`;
      }).join('')}
    </div></div>`;
}

function metricsBlock(m, sources) {
  const row = (k, v) => `<div class="kv"><span>${k}</span><b>${v}</b></div>`;
  return `<div class="block">
    <div class="block-head"><span class="tag">Session record</span><hr class="rule-h"></div>
    ${row('Total latency', `${m.total_latency_ms ?? 0} ms`)}
    ${row('Agent latency', `${m.agent_latency_ms ?? 0} ms`)}
    ${row('Signal confidence', pct(m.signal_confidence))}
    ${row('Evidence coverage', pct(m.evidence_coverage))}
    ${row('Concentration', `${(m.concentration_score ?? 0).toFixed(1)}%`)}
    ${row('Agents reporting', `${m.agents_complete ?? 0} / ${(m.agents_complete ?? 0) + (m.agents_failed ?? 0)}`)}
    ${row('Verified sources', sources)}
    <p class="tag" style="margin-top:12px;line-height:1.7">Appended to logs/sessions.jsonl on every run.</p>
  </div>`;
}

/* ---------------- exhibit panel ---------------- */
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
    <div class="attest">
      <span class="tag">Relied upon by</span>
      <p style="color:var(--paper);font-size:15px">${esc(name)} agent</p>
    </div>
    <div class="attest verified">
      <span class="tag" style="color:var(--bull)">Verified quotation</span>
      <p>Copied verbatim from chunk <code>${esc(e.chunk_id)}</code> in the filings corpus.
      The agent chose which chunk supports its finding; it never wrote this sentence,
      so the quotation cannot be fabricated.</p>
    </div>
    <div class="attest">
      <span class="tag">Retrieval relevance</span>
      <p class="mono" style="color:var(--paper)">${(e.relevance_score ?? 0).toFixed(3)}</p>
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
  document.querySelectorAll('[data-symbol]').forEach((b) => b.onclick = () => {
    state.symbol = b.dataset.symbol; analyze();
  });
  document.querySelectorAll('.exhibit').forEach((b) => b.onclick = () =>
    openExhibit(b.dataset.agentName, Number(b.dataset.idx)));
}

document.addEventListener('click', (ev) => {
  const p = ev.target.closest('[data-user]');
  if (p) { state.userId = p.dataset.user; renderProfiles(); analyze(); }
});
$('#drawer-close').onclick = closeDrawer;
$('#scrim').onclick = closeDrawer;
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });

boot();
