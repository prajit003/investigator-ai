/* ===================================================================
   AUREON — Application JavaScript
   AI-Powered Financial Intelligence for Indian Retail Investors
   =================================================================== */

document.addEventListener('DOMContentLoaded', () => {

  // ── State ────────────────────────────────────────────────────────
  let currentScreen = 'overview';
  let currentProfile = 'priya';
  let currentFilter = 'all';
  let panelOpen = false;


  // ── Dark Mode Toggle ─────────────────────────────────────────────
  const themeToggle = document.getElementById('themeToggle');
  const htmlEl = document.documentElement;

  // Restore saved preference
  const savedTheme = localStorage.getItem('aureon-theme');
  if (savedTheme === 'dark') {
    htmlEl.setAttribute('data-theme', 'dark');
  }

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      // Add transition class for smooth color change
      htmlEl.classList.add('theme-transitioning');

      const isDark = htmlEl.getAttribute('data-theme') === 'dark';
      if (isDark) {
        htmlEl.removeAttribute('data-theme');
        localStorage.setItem('aureon-theme', 'light');
      } else {
        htmlEl.setAttribute('data-theme', 'dark');
        localStorage.setItem('aureon-theme', 'dark');
      }

      // Remove transition class after animation completes
      setTimeout(() => {
        htmlEl.classList.remove('theme-transitioning');
      }, 400);
    });
  }

  // ── Navigation ───────────────────────────────────────────────────
  const navItems = document.querySelectorAll('.sidebar__nav-item');
  const screens = document.querySelectorAll('.screen');
  const topbarTitle = document.querySelector('.topbar__title');

  const screenTitles = {
    overview: 'Overview',
    analysis: 'Stock Analysis',
    reasoning: 'AI Reasoning',
    portfolio: 'Portfolio & Profile',
    watchlist: 'Watchlist & Alerts'
  };

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const target = item.dataset.screen;
      if (target === currentScreen) return;
      switchScreen(target);
    });
  });

  function switchScreen(target) {
    currentScreen = target;
    navItems.forEach(n => n.classList.toggle('active', n.dataset.screen === target));
    screens.forEach(s => {
      s.classList.remove('active');
      if (s.id === target) {
        s.classList.add('active');
        s.scrollTop = 0;
      }
    });
    topbarTitle.textContent = screenTitles[target] || 'Overview';

    // Animate confidence bars when entering a screen
    requestAnimationFrame(() => animateBars(document.getElementById(target)));
  }

  // ── Profile Switcher ─────────────────────────────────────────────
  const profileBtns = document.querySelectorAll('.profile-switch__btn');

  profileBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const profile = btn.dataset.profile;
      if (profile === currentProfile) return;
      currentProfile = profile;
      profileBtns.forEach(b => b.classList.toggle('active', b.dataset.profile === profile));
      updateProfile(profile);
    });
  });

  function updateProfile(profile) {
    // Update greeting
    const greeting = document.querySelector('.overview__greeting h1');
    const greetingSuffix = getGreetingTime();

    if (profile === 'priya') {
      greeting.textContent = `Good ${greetingSuffix}, Priya`;
      document.querySelectorAll('.profile-dependent').forEach(el => {
        el.classList.remove('profile-arjun');
        el.classList.add('profile-priya');
      });
    } else {
      greeting.textContent = `Good ${greetingSuffix}, Arjun`;
      document.querySelectorAll('.profile-dependent').forEach(el => {
        el.classList.remove('profile-priya');
        el.classList.add('profile-arjun');
      });
    }

    // Swap profile-specific text
    document.querySelectorAll('[data-priya]').forEach(el => {
      el.textContent = profile === 'priya' ? el.dataset.priya : el.dataset.arjun;
    });

    // Swap visibility of profile-specific blocks
    document.querySelectorAll('[data-show-profile]').forEach(el => {
      el.style.display = el.dataset.showProfile === profile ? '' : 'none';
    });

    // Animate the stat changes
    document.querySelectorAll('.stat-card').forEach(card => {
      card.style.transform = 'scale(0.97)';
      card.style.opacity = '0.7';
      setTimeout(() => {
        card.style.transform = '';
        card.style.opacity = '';
      }, 200);
    });

    // Update profile comparison active state
    document.querySelectorAll('.profile-card').forEach(card => {
      card.classList.toggle('profile-card--active', card.dataset.profile === profile);
    });
  }

  function getGreetingTime() {
    const h = new Date().getHours();
    if (h < 12) return 'morning';
    if (h < 17) return 'afternoon';
    return 'evening';
  }

  // Set initial greeting time
  const greetingH1 = document.querySelector('.overview__greeting h1');
  if (greetingH1) {
    const time = getGreetingTime();
    greetingH1.textContent = `Good ${time}, Priya`;
  }


  // ── Confidence Bar Animation ─────────────────────────────────────
  function animateBars(container) {
    if (!container) return;
    container.querySelectorAll('.confidence-bar__fill').forEach(bar => {
      const target = bar.dataset.width;
      if (target) {
        bar.style.width = '0%';
        requestAnimationFrame(() => {
          setTimeout(() => { bar.style.width = target + '%'; }, 50);
        });
      }
    });
  }

  // Initial animation
  animateBars(document.getElementById('overview'));


  // ── Timeframe Pills ──────────────────────────────────────────────
  document.querySelectorAll('.timeframe-pills').forEach(group => {
    group.querySelectorAll('.timeframe-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        group.querySelectorAll('.timeframe-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
      });
    });
  });


  // ── Filter Pills ────────────────────────────────────────────────
  document.querySelectorAll('.filter-pills').forEach(group => {
    group.querySelectorAll('.filter-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        group.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        filterWatchlist(pill.dataset.filter);
      });
    });
  });

  function filterWatchlist(filter) {
    currentFilter = filter;
    document.querySelectorAll('.watchlist-table tbody tr').forEach(row => {
      if (filter === 'all') {
        row.style.display = '';
      } else {
        const signal = row.dataset.signal;
        row.style.display = signal === filter ? '' : 'none';
      }
    });
  }


  // ── Citation Side Panel ──────────────────────────────────────────
  const sidePanel = document.querySelector('.side-panel');
  const panelOverlay = document.querySelector('.panel-overlay');
  const panelClose = document.querySelector('.side-panel__close');

  // Citation data
  const citations = {
    'q1-fy26': {
      title: 'Q1 FY26 Earnings Call Transcript',
      type: 'Earnings Call',
      date: '18 July 2025',
      ref: 'REL/BSE/2025-26/Q1/001',
      quote: '"Our consumer-facing businesses continue to show strong momentum. Jio subscriber additions exceeded expectations at 12.4 million net adds, while retail revenue grew 18% year-over-year. We remain committed to our capital expenditure guidance of ₹75,000 crore for FY26, with a focus on 5G rollout and green energy investments."',
      usedBy: 'Fundamental Agent'
    },
    'sebi-filing': {
      title: 'SEBI Quarterly Filing',
      type: 'Regulatory Filing',
      date: '14 August 2025',
      ref: 'SEBI/HO/CFD/CMD1/CIR/P/2025/089',
      quote: '"Promoter holding remains stable at 50.33%. Institutional investors have increased their aggregate holding by 1.2% during the quarter, primarily driven by increased FII allocation. No significant related-party transactions reported beyond the ordinary course of business."',
      usedBy: 'Fundamental Agent'
    },
    'market-news': {
      title: 'Market News Summary — Reliance Industries',
      type: 'News Aggregation',
      date: '1 September 2025',
      ref: 'AUTO-NEWS/REL/2025-09-01',
      quote: '"Reliance Industries shares gained 1.24% in early trading following reports of a potential strategic partnership in the renewable energy sector. Analysts remain cautiously optimistic about the conglomerate\'s diversification strategy, though elevated valuations remain a concern."',
      usedBy: 'Sentiment Agent'
    }
  };

  document.querySelectorAll('.citation-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      const citationId = chip.dataset.citation;
      openPanel(citationId);
    });
  });

  function openPanel(citationId) {
    const data = citations[citationId];
    if (!data) return;

    sidePanel.querySelector('.side-panel__title').textContent = 'Evidence Source';
    sidePanel.querySelector('[data-field="source-name"]').textContent = data.title;
    sidePanel.querySelector('[data-field="source-type"]').textContent = data.type;
    sidePanel.querySelector('[data-field="source-date"]').textContent = data.date;
    sidePanel.querySelector('[data-field="source-ref"]').textContent = data.ref;
    sidePanel.querySelector('[data-field="source-quote"]').textContent = data.quote;
    sidePanel.querySelector('[data-field="used-by"]').textContent = data.usedBy;

    sidePanel.classList.add('open');
    panelOverlay.classList.add('open');
    panelOpen = true;
  }

  function closePanel() {
    sidePanel.classList.remove('open');
    panelOverlay.classList.remove('open');
    panelOpen = false;
  }

  if (panelClose) panelClose.addEventListener('click', closePanel);
  if (panelOverlay) panelOverlay.addEventListener('click', closePanel);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && panelOpen) closePanel();
  });


  // ── "View Full Analysis" link ────────────────────────────────────
  document.querySelectorAll('[data-navigate]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      switchScreen(el.dataset.navigate);
    });
  });


  // ── System State Modals ──────────────────────────────────────────
  const stateOverlays = document.querySelectorAll('.state-overlay');
  const demoButtons = document.querySelectorAll('[data-show-state]');
  const closeStateButtons = document.querySelectorAll('[data-close-state]');

  demoButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const stateId = btn.dataset.showState;
      const overlay = document.getElementById(stateId);
      if (overlay) {
        overlay.classList.add('visible');
        if (stateId === 'loading-state') runLoadingAnimation();
      }
    });
  });

  closeStateButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.state-overlay').classList.remove('visible');
    });
  });


  // ── Loading Animation ────────────────────────────────────────────
  function runLoadingAnimation() {
    const steps = document.querySelectorAll('#loading-state .loading-step');
    steps.forEach(s => { s.classList.remove('active', 'done'); });

    let i = 0;
    function activateNext() {
      if (i > 0) steps[i - 1].classList.replace('active', 'done');
      if (i < steps.length) {
        steps[i].classList.add('active');
        i++;
        setTimeout(activateNext, 1200);
      } else {
        // Auto close after last step
        setTimeout(() => {
          document.getElementById('loading-state').classList.remove('visible');
        }, 800);
      }
    }
    activateNext();
  }


  // ── Hover Lift for Cards ─────────────────────────────────────────
  document.querySelectorAll('.card--interactive, .agent-card, .stat-card').forEach(card => {
    card.addEventListener('mouseenter', () => {
      card.style.transform = 'translateY(-2px)';
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
    });
  });


  // ── Notification Bell ────────────────────────────────────────────
  const bellBtn = document.querySelector('.topbar__notification');
  if (bellBtn) {
    bellBtn.addEventListener('click', () => {
      switchScreen('watchlist');
      // Scroll to alerts
      setTimeout(() => {
        const alertsSection = document.querySelector('.alerts-section');
        if (alertsSection) alertsSection.scrollIntoView({ behavior: 'smooth' });
      }, 300);
    });
  }


  // ── Search Interaction ───────────────────────────────────────────
  const searchInput = document.querySelector('.topbar__search input');
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = searchInput.value.trim().toUpperCase();
        if (val === 'RELIANCE' || val === 'REL' || val === 'RELIANCE INDUSTRIES') {
          switchScreen('analysis');
          searchInput.value = '';
          searchInput.blur();
        }
      }
    });
  }


  // ── Add to Watchlist Button ──────────────────────────────────────
  const addWatchlistBtn = document.querySelector('.add-watchlist-btn');
  if (addWatchlistBtn) {
    addWatchlistBtn.addEventListener('click', () => {
      addWatchlistBtn.textContent = '✓ Added';
      addWatchlistBtn.classList.add('btn--secondary');
      addWatchlistBtn.classList.remove('btn--primary');
      setTimeout(() => {
        addWatchlistBtn.textContent = '+ Add Company';
        addWatchlistBtn.classList.remove('btn--secondary');
        addWatchlistBtn.classList.add('btn--primary');
      }, 2000);
    });
  }


  // ── Sparkline SVGs ───────────────────────────────────────────────
  // Generate smooth sparkline paths
  function generateSparklinePath(data, width, height) {
    const step = width / (data.length - 1);
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;

    let d = '';
    data.forEach((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / range) * height;
      d += i === 0 ? `M${x},${y}` : ` L${x},${y}`;
    });
    return d;
  }

  // Apply sparklines
  document.querySelectorAll('.sparkline-auto').forEach(svg => {
    const raw = svg.dataset.values;
    if (!raw) return;
    const data = raw.split(',').map(Number);
    const w = parseInt(svg.getAttribute('width')) || 60;
    const h = parseInt(svg.getAttribute('height')) || 24;
    const color = svg.dataset.color || 'var(--green)';
    const path = generateSparklinePath(data, w, h);
    svg.innerHTML = `<path d="${path}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`;
  });

});
