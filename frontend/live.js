/* ===================================================================
   AUREON — LIVE DATA LAYER

   Everything on this page used to be written into the markup by hand,
   including a profile toggle that swapped two hardcoded strings. This file
   replaces all of it with one response from GET /api/analyze.

   Design rules it follows:
     - render ONLY what the API returned. Nothing here invents a number, a
       direction arrow, or a confidence
     - a missing value renders as an em dash, never as zero and never as
       neutral
     - the freshness of a price is part of the price: as_of and the provider
       are always on screen, and a stale figure says so
     - data_quality drives the degraded overlay, so a partial answer looks
       partial instead of looking complete

   SECURITY NOTE: a large part of what is rendered here originates with third
   parties — BSE filing text, Google News headlines, provider names. None of it
   is trusted. Every node below is built with document.createElement and filled
   with textContent, so markup in a filing cannot become markup on this page.
   There is no innerHTML in this file, deliberately.
   =================================================================== */

const API = '/api/analyze';
const POLL_MS = 30000;
const DASH = '—';

const state = {
  symbol: 'RELIANCE',
  userId: 'u1',
  data: null,
  timer: null,
  inFlight: false,
};

/* ── helpers ─────────────────────────────────────────────────────── */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Build an element. `text` always goes in as text, never as markup. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clear(node) {
  while (node && node.firstChild) node.removeChild(node.firstChild);
}

function dot() { return el('span', 'dot'); }

// A number we do not have is not zero. These return the em dash rather than
// "0" so an absent figure can never read as a real one.
function rupees(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return DASH;
  const abs = Math.abs(n);
  if (abs >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

function pct(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return DASH;
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
}

function titleCase(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

// One table decides what colour a signal is, so the overview cards, the
// reasoning cards and the hero pill can never disagree with each other.
const TONE = {
  BULLISH: 'green', BEARISH: 'red', NEUTRAL: 'slate',
  CONFLICT: 'amber', UNAVAILABLE: 'slate',
  STRONG_POSITIVE: 'green', POSITIVE: 'green', CAUTION: 'amber',
  NEGATIVE: 'red', INSUFFICIENT_DATA: 'slate',
  COMPLETE: 'green', DEGRADED: 'amber', FAILED: 'red',
  GOOD: 'green', POOR: 'red',
};
const tone = (v) => TONE[v] || 'slate';

const AGENT_LABEL = {
  market_detective: 'Market Agent',
  news_detective: 'Sentiment Agent',
  filing_detective: 'Fundamental Agent',
  behavioral_detective: 'Behavioural Agent',
  bull_agent: 'Bull Agent',
  bear_agent: 'Bear Agent',
  judge_agent: 'Judge',
};
const agentLabel = (n) => AGENT_LABEL[n] || titleCase(n);

/* ── fetching ────────────────────────────────────────────────────── */

async function fetchAnalysis() {
  if (state.inFlight) return;
  state.inFlight = true;
  try {
    const url = `${API}?symbol=${encodeURIComponent(state.symbol)}`
              + `&user_id=${encodeURIComponent(state.userId)}`;
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    state.data = await res.json();
    hideState('error-state');
    render(state.data);
  } catch (err) {
    // An unreachable backend must not leave the last numbers on screen looking
    // current. Show the error state instead of quietly going stale.
    showState('error-state', `Could not reach the analysis API: ${err.message}`);
  } finally {
    state.inFlight = false;
    hideState('loading-state');
  }
}

// The overlay is shown by the stylesheet's own `.visible` class — it sets
// opacity and visibility, and a class of any other name leaves the overlay
// transparent while the DOM claims it is showing. That failure mode is exactly
// the one these overlays exist to prevent, so the class name matters.
function showState(id, detail) {
  const node = document.getElementById(id);
  if (!node) return;
  if (detail) {
    const p = node.querySelector('.state-card__desc');
    if (p) p.textContent = detail;
  }
  node.classList.add('visible');
}

function hideState(id) {
  const node = document.getElementById(id);
  if (!node) return;
  node.classList.remove('visible');
}

/* ── rendering ───────────────────────────────────────────────────── */

function render(d) {
  const md = d.market_data || {};
  const judge = d.judge_output || {};
  const pers = d.personalization || {};
  const pf = d.portfolio || {};
  const dq = d.data_quality || {};
  const metrics = d.metrics || {};
  const holdings = pf.holdings || [];
  const here = holdings.find((h) => h.symbol === d.symbol);
  const missingSources = [dq.market_data, dq.news_data, dq.filing_data]
    .filter((v) => v === 'UNAVAILABLE').length;
  const top = topHolding(holdings);

  const values = {
    company_name: d.company_name || d.symbol,
    listing: `NSE: ${d.symbol}${md.source ? ` · ${md.source}` : ''}`,
    price: md.current_price ? rupees(md.current_price) : DASH,
    change: pct(md.price_change_percent),
    change_detail: md.price_change
      ? `${md.price_change >= 0 ? '+' : '−'}${rupees(Math.abs(md.price_change))} `
        + `(${pct(md.price_change_percent)})`
      : DASH,
    as_of: md.as_of || 'no timestamp',

    // Indicators are Optional in the contract for a reason: they are derived
    // from history this system accumulates itself. When one is null the panel
    // says why rather than showing a number nobody computed.
    rsi: md.rsi === null || md.rsi === undefined ? DASH : md.rsi.toFixed(1),
    rsi_note: md.rsi === null || md.rsi === undefined
      ? 'Not enough daily closes yet'
      : (md.rsi >= 70 ? 'Overbought territory'
        : md.rsi <= 30 ? 'Oversold territory' : 'Neither overbought nor oversold'),
    momentum: md.momentum === null || md.momentum === undefined
      ? DASH : pct(md.momentum * 100),
    momentum_note: md.momentum === null || md.momentum === undefined
      ? 'Needs 21 daily closes' : 'Change over the last 20 sessions',
    volatility: md.volatility === null || md.volatility === undefined
      ? DASH : pct(md.volatility * 100),
    volatility_note: md.volatility === null || md.volatility === undefined
      ? 'Needs 21 daily closes' : 'Annualised, from daily log returns',
    volume_ratio: md.volume && md.average_volume
      ? `${(md.volume / md.average_volume).toFixed(2)}x` : DASH,
    volume_note: md.volume
      ? `${md.volume.toLocaleString('en-IN')} vs `
        + `${(md.average_volume || 0).toLocaleString('en-IN')} average`
      : 'No credible volume reported for this session',
    history_note: md.rsi === null || md.rsi === undefined
      ? 'Price history is still being collected — one close per session. '
        + 'A chart appears here once there are enough sessions to draw one '
        + 'from real data.'
      : 'Price history available. Charting is not implemented yet; the '
        + 'indicators below are computed from the same series.',
    verdict: titleCase(judge.verdict || 'Insufficient Data'),
    verdict_confidence: judge.confidence
      ? `${Math.round(judge.confidence * 100)}% confidence`
      : 'confidence unavailable',
    summary: judge.summary || DASH,
    personalized_reason: pers.personalized_reason || DASH,
    profile_impact_label: `Impact for a ${titleCase(pers.risk_profile)} profile:`,
    portfolio_value: rupees(pf.portfolio_value),
    portfolio_note: `${holdings.length} holding(s), marked to market`,
    position_value: here ? rupees(here.current_value) : 'No position',
    position_note: here
      ? `${d.symbol} at ${rupees(here.average_price)} average`
      : `You do not hold ${d.symbol}`,
    quality_note: missingSources
      ? `${missingSources} of 3 sources unavailable`
      : 'All three sources available',
    evidence_count: (d.evidence || []).length,
    agents_note: `${metrics.agents_complete || 0} reporting, `
               + `${metrics.agents_failed || 0} failed`,
    user_name: pers.risk_profile === 'AGGRESSIVE' ? 'Arjun' : 'Priya',
    risk_profile: titleCase(pers.risk_profile),
    risk_score: `${pers.risk_score === undefined ? DASH : pers.risk_score}`,
    risk_score_100: `${pers.risk_score === undefined ? DASH : pers.risk_score} / 100`,
    risk_label: `${titleCase(pers.risk_profile)} profile`,
    horizon: titleCase(pers.investment_horizon),
    diversification: holdings.length >= 8 ? 'Good'
      : holdings.length ? 'Concentrated' : DASH,
    holdings_note: `${holdings.length} holding(s)`,
    top_holding: (top && top.symbol) || DASH,
    top_holding_note: pf.concentration_score
      ? `${pf.concentration_score.toFixed(1)}% of portfolio` : DASH,
    comparison_title: `Profile Comparison — ${d.symbol} recommendation`,
    concentration: (pf.concentration_score && top)
      ? `${top.symbol} is ${pf.concentration_score.toFixed(1)}% of the portfolio` : '',
  };

  $$('[data-bind]').forEach((node) => {
    const key = node.getAttribute('data-bind');
    if (!(key in values)) return;
    node.textContent = values[key];
  });

  // data_quality is a pill with a status dot, so it is rebuilt rather than set.
  const dqNode = $('[data-bind="data_quality"]');
  if (dqNode) {
    clear(dqNode);
    dqNode.appendChild(dot());
    dqNode.appendChild(document.createTextNode(` ${titleCase(dq.overall_quality)}`));
    paint(dqNode, tone(dq.overall_quality));
  }
  $$('[data-bind="verdict"]').forEach((n) => paint(n, tone(judge.verdict)));

  // The session pill: a price is either live or it is a last close, and the
  // page has to say which. Derived from the provider's own timestamp, not from
  // our clock — the two disagree exactly when it matters.
  $$('[data-bind="session"]').forEach((n) => {
    const live = isFreshQuote(md);
    clear(n);
    n.appendChild(dot());
    n.appendChild(document.createTextNode(live ? ' Live' : ' Last close'));
    paint(n, live ? 'green' : 'slate');
  });

  const chg = $('[data-bind="change"]');
  if (chg) {
    chg.classList.remove('text-green', 'text-red');
    if (md.price_change_percent > 0) chg.classList.add('text-green');
    else if (md.price_change_percent < 0) chg.classList.add('text-red');
  }

  renderFreshness(md, metrics);
  renderDonuts(holdings, pf.portfolio_value);
  renderSignalCards(d.signals || {});
  renderAgentCards(d.agent_outputs || []);
  renderHoldings(holdings, pf.portfolio_value);
  renderHoldingsTable(holdings, pf.portfolio_value);
  renderWarnings(dq.warnings || []);
  renderComparison(d.symbol);

  const conc = $('#live-concentration');
  if (conc) conc.style.display = pf.concentration_score ? '' : 'none';

  if ((dq.overall_quality || 'GOOD') === 'GOOD') {
    hideState('degraded-state');
  } else {
    showState('degraded-state', (dq.warnings || [])[0]
      || 'Some sources are unavailable; this result is partial, not wrong.');
  }
}

/* A quote counts as live only if the PROVIDER stamped it within the last few
   minutes and it did not come from the cache or the fixture file. */
function isFreshQuote(md) {
  const source = md.source || '';
  if (!md.as_of || /fixture|cached/i.test(source)) return false;
  const stamped = Date.parse(md.as_of.replace(' ', 'T'));
  if (Number.isNaN(stamped)) return false;
  return Math.abs(Date.now() - stamped) < 10 * 60 * 1000;
}

function topHolding(holdings) {
  return holdings.reduce(
    (a, b) => (!a || b.current_value > a.current_value ? b : a), null);
}

function paint(node, colour) {
  if (!node) return;
  node.classList.remove('pill--green', 'pill--red', 'pill--amber',
                        'pill--blue', 'pill--slate');
  node.classList.add('pill', `pill--${colour}`);
}

function renderFreshness(md, metrics) {
  const node = $('#live-freshness');
  if (!node) return;
  const source = md.source || '';
  const stale = !isFreshQuote(md);
  const parts = [md.as_of ? `${source || 'feed'} · ${md.as_of}` : 'no quote'];
  if (stale) parts.push('STALE');
  if (metrics.total_latency_ms !== undefined) {
    parts.push(`${metrics.total_latency_ms}ms`);
  }
  clear(node);
  node.appendChild(dot());
  node.appendChild(document.createTextNode(` ${parts.join(' · ')}`));
  node.style.color = stale ? 'var(--amber)' : '';
  node.title = stale
    ? 'This figure is not a live market price. See the warnings panel.'
    : 'Provider timestamp, not our fetch time.';
}

/* The three independent dimensions, straight from `signals`. */
function renderSignalCards(signals) {
  const host = $('#live-signal-cards');
  if (!host) return;
  clear(host);

  [['Price', signals.price_signal],
   ['Volume', signals.volume_signal],
   ['Sentiment', signals.sentiment_signal]].forEach(([label, sig]) => {
    const s = sig || {};
    const colour = tone(s.signal);
    const conf = Math.round((s.confidence || 0) * 100);
    const unavailable = s.signal === 'UNAVAILABLE';

    const card = el('div', `agent-card agent-card--${colour}`);
    const header = el('div', 'agent-card__header');
    const name = el('div', 'agent-card__name');
    name.appendChild(el('span', null, label));
    header.appendChild(name);
    header.appendChild(el('span',
      `agent-card__confidence agent-card__confidence--${colour}`,
      unavailable ? DASH : `${conf}%`));
    card.appendChild(header);

    const pill = el('span', `pill pill--${colour} pill--sm`);
    pill.appendChild(dot());
    pill.appendChild(document.createTextNode(` ${titleCase(s.signal || 'Unavailable')}`));
    card.appendChild(pill);

    // No confidence bar for a dimension that did not report: a 0%-wide bar
    // looks like a measured zero rather than an absence.
    if (!unavailable) {
      const bar = el('div', 'confidence-bar mt-8');
      const fill = el('div', `confidence-bar__fill confidence-bar__fill--${colour}`);
      fill.style.width = `${conf}%`;
      bar.appendChild(fill);
      card.appendChild(bar);
    }

    card.appendChild(el('p', 'agent-card__reasoning', (s.reasons || []).join(' ')));
    host.appendChild(card);
  });
}

/* One card per agent, with its citations. */
function renderAgentCards(agents) {
  const host = $('#live-agent-cards');
  if (!host) return;
  clear(host);

  agents.forEach((a) => {
    const colour = tone(a.signal);
    const statusColour = tone(a.status);
    const conf = Math.round((a.confidence || 0) * 100);
    const unavailable = a.signal === 'UNAVAILABLE';

    const card = el('div', 'reasoning-agent-card');
    const header = el('div', 'reasoning-agent-card__header');
    const nameWrap = el('div', 'reasoning-agent-card__name');
    const nameInner = el('div');
    nameInner.appendChild(el('h4', null, agentLabel(a.agent_name)));
    nameWrap.appendChild(nameInner);
    header.appendChild(nameWrap);

    const status = el('div', 'reasoning-agent-card__status');
    const statusPill = el('span', `pill pill--${statusColour}`);
    statusPill.style.fontSize = '10px';
    statusPill.appendChild(dot());
    statusPill.appendChild(document.createTextNode(` ${a.status}`));
    const signalPill = el('span', `pill pill--${colour}`);
    signalPill.appendChild(dot());
    signalPill.appendChild(document.createTextNode(` ${titleCase(a.signal)}`));
    status.appendChild(statusPill);
    status.appendChild(signalPill);
    header.appendChild(status);
    card.appendChild(header);

    if (!unavailable) {
      const row = el('div', 'reasoning-agent-card__confidence-row');
      row.appendChild(el('span', 'reasoning-agent-card__confidence-label', 'Confidence'));
      row.appendChild(el('span',
        `reasoning-agent-card__confidence-value text-${colour}`, `${conf}%`));
      card.appendChild(row);

      const bar = el('div', 'confidence-bar');
      const fill = el('div', `confidence-bar__fill confidence-bar__fill--${colour}`);
      fill.style.width = `${conf}%`;
      bar.appendChild(fill);
      card.appendChild(bar);
    }

    card.appendChild(el('p', 'reasoning-agent-card__reasoning', (a.reasons || []).join(' ')));

    const evidence = a.evidence || [];
    if (evidence.length) {
      const cites = el('div', 'reasoning-agent-card__citations');
      evidence.forEach((ev) => {
        // The chip label is filing-supplied text, so it goes in as text.
        const chip = el('span', 'citation-chip', ev.source_name || ev.chunk_id);
        // The evidence object is attached to the node, not encoded into an
        // attribute the click handler would have to parse back out.
        chip.addEventListener('click', () => openEvidence(ev, agentLabel(a.agent_name)));
        cites.appendChild(chip);
      });
      card.appendChild(cites);
    }

    host.appendChild(card);
  });
}

function openEvidence(ev, usedBy) {
  if (!ev) return;
  const set = (field, value) => {
    const node = $(`[data-field="${field}"]`);
    if (node) node.textContent = value || DASH;
  };
  set('source-name', ev.source_name);
  set('source-type', titleCase(ev.source_type));
  set('source-date', ev.source_date);
  set('source-ref', ev.chunk_id);
  set('used-by', usedBy);

  const quote = $('[data-field="source-quote"]');
  if (quote) {
    // The verbatim corpus text. The grounding guard's whole guarantee is that
    // this string was copied from the source document and not written by a
    // model, so it is shown exactly as stored — as text.
    quote.textContent = `“${ev.text}”`;
    const parent = quote.parentElement;
    const existing = parent.querySelector('.evidence-link');
    if (existing) existing.remove();
    if (ev.url && /^https?:\/\//i.test(ev.url)) {
      const link = el('a', 'evidence-link', 'Open the filed document ↗');
      link.href = ev.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      parent.appendChild(link);
    }
  }

  const panel = $('.side-panel');
  const overlay = $('.panel-overlay');
  if (panel) panel.classList.add('active');
  if (overlay) overlay.classList.add('active');
}

function renderHoldings(holdings, total) {
  const host = $('#live-holdings');
  if (!host) return;
  clear(host);

  if (!holdings.length) {
    host.appendChild(el('p', 'text-xs text-slate', 'No holdings on file.'));
    return;
  }
  const colours = ['var(--blue)', 'var(--green)', 'var(--amber)',
                   'var(--red)', 'var(--slate-light)'];
  [...holdings]
    .sort((a, b) => b.current_value - a.current_value)
    .forEach((h, i) => {
      const share = total ? (h.current_value / total) * 100 : 0;
      const row = el('div', 'holding-row');
      row.appendChild(el('span', 'holding-row__ticker', h.symbol));
      const bar = el('div', 'holding-row__bar');
      const fill = el('div', 'holding-row__bar-fill');
      fill.style.width = `${share.toFixed(1)}%`;
      fill.style.background = colours[Math.min(i, colours.length - 1)];
      bar.appendChild(fill);
      row.appendChild(bar);
      row.appendChild(el('span', 'holding-row__pct', `${share.toFixed(1)}%`));
      host.appendChild(row);
    });
}

/* The allocation rings. Arc lengths come from the marked-to-market holdings,
   so the picture and the percentages beside it cannot drift apart. */
const SLICE_COLOURS = ['#4361EE', '#0D9668', '#F59E0B', '#C2553A', '#7C3AED', '#94A3B8'];
const SVG_NS = 'http://www.w3.org/2000/svg';

function sliceModel(holdings, total) {
  if (!holdings.length || !total) return [];
  const sorted = [...holdings].sort((a, b) => b.current_value - a.current_value);
  const head = sorted.slice(0, SLICE_COLOURS.length - 1);
  const tail = sorted.slice(SLICE_COLOURS.length - 1);
  const slices = head.map((h, i) => ({
    label: h.symbol,
    share: (h.current_value / total) * 100,
    colour: SLICE_COLOURS[i],
  }));
  if (tail.length) {
    slices.push({
      label: `Other (${tail.length})`,
      share: (tail.reduce((sum, h) => sum + h.current_value, 0) / total) * 100,
      colour: SLICE_COLOURS[SLICE_COLOURS.length - 1],
    });
  }
  return slices;
}

function renderDonuts(holdings, total) {
  const slices = sliceModel(holdings, total);
  ['live-donut-small', 'live-donut-big'].forEach((id) => {
    const host = document.getElementById(id);
    if (!host) return;
    clear(host);
    const r = Number(host.dataset.radius);
    const cx = Number(host.dataset.cx);
    const cy = Number(host.dataset.cy);
    const width = Number(host.dataset.stroke);
    const circumference = 2 * Math.PI * r;

    let offset = 0;
    slices.forEach((slice) => {
      const length = (slice.share / 100) * circumference;
      const arc = document.createElementNS(SVG_NS, 'circle');
      arc.setAttribute('cx', cx);
      arc.setAttribute('cy', cy);
      arc.setAttribute('r', r);
      arc.setAttribute('fill', 'none');
      arc.setAttribute('stroke', slice.colour);
      arc.setAttribute('stroke-width', width);
      arc.setAttribute('stroke-dasharray', `${length.toFixed(1)} ${(circumference - length).toFixed(1)}`);
      arc.setAttribute('stroke-dashoffset', `${(-offset).toFixed(1)}`);
      arc.setAttribute('transform', `rotate(-90 ${cx} ${cy})`);
      host.appendChild(arc);
      offset += length;
    });
  });

  const legend = document.getElementById('live-legend');
  if (!legend) return;
  clear(legend);
  slices.forEach((slice) => {
    const item = el('div', 'portfolio__legend-item');
    const swatch = el('div', 'portfolio__legend-dot');
    swatch.style.background = slice.colour;
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(
      ` ${slice.label} ${slice.share.toFixed(1)}%`));
    legend.appendChild(item);
  });
}

/* The holdings table. P&L is computed from average_price and the live price,
   both of which are real fields — nothing here is a target weight or a
   suggested action, because the engine does not produce those. */
function renderHoldingsTable(holdings, total) {
  const host = document.getElementById('live-holdings-table');
  if (!host) return;
  clear(host);

  if (!holdings.length) {
    const row = el('tr');
    const cell = el('td', null, 'No holdings on file.');
    cell.colSpan = 5;
    row.appendChild(cell);
    host.appendChild(row);
    return;
  }

  [...holdings]
    .sort((a, b) => b.current_value - a.current_value)
    .forEach((h) => {
      const share = total ? (h.current_value / total) * 100 : 0;
      const cost = (h.average_price || 0) * (h.quantity || 0);
      const pnl = cost ? h.current_value - cost : null;
      const pnlPct = cost ? (pnl / cost) * 100 : null;

      const row = el('tr');
      row.appendChild(el('td', 'holdings-table__ticker', h.symbol));
      row.appendChild(el('td', null, `${share.toFixed(1)}%`));
      row.appendChild(el('td', null, rupees(h.current_value)));

      const pnlCell = el('td', pnl === null ? null : (pnl >= 0 ? 'text-green' : 'text-red'),
        pnl === null ? DASH
          : `${pnl >= 0 ? '+' : '−'}${rupees(Math.abs(pnl))} (${pct(pnlPct)})`);
      row.appendChild(pnlCell);

      // "Risk" here is concentration, the one risk dimension this system
      // actually measures per holding.
      const band = share >= 25 ? ['amber', 'High'] : share >= 15 ? ['blue', 'Moderate']
                                                                : ['green', 'Low'];
      const riskCell = el('td');
      const pill = el('span', `pill pill--${band[0]}`, band[1]);
      pill.style.fontSize = '10px';
      pill.style.padding = '2px 8px';
      riskCell.appendChild(pill);
      row.appendChild(riskCell);

      host.appendChild(row);
    });
}

/* SIDE-BY-SIDE PROFILES — the personalization requirement, made checkable.

   Both profiles are fetched for the SAME symbol at the same moment, so any
   difference between the two cards came from the rules and not from the market
   moving between two clicks. The panel this replaced asserted "HOLD vs BUY" in
   hardcoded markup, which proved nothing at all. When today's data happens to
   produce the same verdict for both, this says so rather than manufacturing a
   disagreement. */
async function renderComparison(symbol) {
  const host = document.getElementById('live-profile-comparison');
  if (!host) return;

  let results;
  try {
    results = await Promise.all(['u1', 'u2'].map((uid) =>
      fetch(`${API}?symbol=${encodeURIComponent(symbol)}&user_id=${uid}`,
            { headers: { Accept: 'application/json' } })
        .then((r) => (r.ok ? r.json() : null))));
  } catch (err) {
    return;   // The main panel already reports an unreachable API.
  }

  clear(host);
  const verdicts = new Set();

  results.filter(Boolean).forEach((d) => {
    const judge = d.judge_output || {};
    const pers = d.personalization || {};
    const pf = d.portfolio || {};
    const here = (pf.holdings || []).find((h) => h.symbol === d.symbol);
    const aggressive = pers.risk_profile === 'AGGRESSIVE';
    const name = aggressive ? 'Arjun Mehta' : 'Priya Sharma';
    const colour = tone(judge.verdict);
    verdicts.add(judge.verdict);

    const card = el('div', 'profile-card'
      + (pers.risk_profile === (state.userId === 'u2' ? 'AGGRESSIVE' : 'CONSERVATIVE')
        ? ' profile-card--active' : ''));

    const header = el('div', 'profile-card__header');
    header.appendChild(el('div',
      `profile-card__avatar profile-card__avatar--${aggressive ? 'arjun' : 'priya'}`,
      name[0]));
    const who = el('div');
    who.appendChild(el('div', 'profile-card__name', name));
    who.appendChild(el('div', 'profile-card__risk',
      `${titleCase(pers.risk_profile)} · ${titleCase(pers.investment_horizon)}`));
    header.appendChild(who);
    const badge = el('span', `pill pill--${colour}`, titleCase(judge.verdict));
    badge.style.marginLeft = 'auto';
    badge.style.fontSize = '10px';
    badge.style.padding = '3px 10px';
    header.appendChild(badge);
    card.appendChild(header);

    const rows = el('div', 'profile-card__rows');
    [['Recommendation', titleCase(judge.verdict)],
     ['Confidence', judge.confidence ? `${Math.round(judge.confidence * 100)}%` : DASH],
     ['Risk score', `${pers.risk_score === undefined ? DASH : pers.risk_score} / 100`],
     ['Position in this stock', here && pf.portfolio_value
       ? `${((here.current_value / pf.portfolio_value) * 100).toFixed(1)}%` : 'None'],
     ['Largest position', pf.concentration_score
       ? `${pf.concentration_score.toFixed(1)}%` : DASH],
    ].forEach(([label, value]) => {
      const row = el('div', 'profile-card__row');
      row.appendChild(el('span', 'profile-card__row-label', label));
      row.appendChild(el('span', 'profile-card__row-value', value));
      rows.appendChild(row);
    });
    card.appendChild(rows);

    // The rule that fired, in the engine's own words.
    card.appendChild(el('div', 'profile-card__explanation',
      pers.personalized_reason || DASH));
    host.appendChild(card);
  });

  const title = $('[data-bind="comparison_title"]');
  if (title && verdicts.size) {
    title.textContent = verdicts.size > 1
      ? `Profile Comparison — ${symbol}: the two profiles disagree`
      : `Profile Comparison — ${symbol}: both profiles reach the same verdict today, `
        + 'for different stated reasons';
  }
}

/* data_quality.warnings, verbatim. Every fallback the backend took is named
   here — that is the difference between degrading and pretending. */
function renderWarnings(warnings) {
  const host = $('#live-warnings');
  if (!host) return;
  clear(host);
  if (!warnings.length) {
    host.style.display = 'none';
    return;
  }
  host.style.display = '';
  warnings.forEach((w) => host.appendChild(el('div', 'live-warning', w)));
}

/* ── wiring ──────────────────────────────────────────────────────── */

function wire() {
  // The profile toggle now REFETCHES rather than swapping two hardcoded
  // strings. Whatever changes on screen changed because the rules ran again.
  $$('.profile-switch__btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      $$('.profile-switch__btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.userId = btn.getAttribute('data-profile') === 'arjun' ? 'u2' : 'u1';
      fetchAnalysis();
    });
  });

  const search = $('.topbar__search input');
  if (search) {
    search.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      const sym = search.value.trim().toUpperCase();
      if (!sym) return;
      state.symbol = sym;
      fetchAnalysis();
    });
  }

  $$('[data-symbol]').forEach((node) => node.addEventListener('click', () => {
    state.symbol = node.getAttribute('data-symbol').toUpperCase();
    fetchAnalysis();
  }));

  // Polling pauses when the tab is hidden: a background tab does not need a
  // price, and these are somebody else's servers.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearInterval(state.timer);
      state.timer = null;
    } else if (!state.timer) {
      fetchAnalysis();
      state.timer = setInterval(fetchAnalysis, POLL_MS);
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  wire();
  showState('loading-state');
  fetchAnalysis();
  state.timer = setInterval(fetchAnalysis, POLL_MS);
});
