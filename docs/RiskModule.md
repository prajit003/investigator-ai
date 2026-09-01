# risk/ module — Person 5

Owner: Person 5. Follows the shared naming contract in
`docs/ARCHITECTURE.md` exactly. This doc explains the *implementation*
of that contract's `portfolio`, `personalization`, and `scenario`
objects; it doesn't redefine any shared names.

## Why this isn't a BUY/HOLD synthesis layer

An earlier task brief for this role described a `synthesis.py` that
would vote across four agents and decide `BUY/HOLD/AVOID/REDUCE`.
`docs/ARCHITECTURE.md` (the contract the whole team actually signed
off on) explicitly rules that out:

> "Do not use BUY/SELL as the primary verdict. We're building an
> intelligence system, not an automated trading bot."

That verdict — `STRONG_POSITIVE / POSITIVE / CAUTION / NEGATIVE /
INSUFFICIENT_DATA` — is produced by the **Judge Agent**
(`agents/judge_agent.py`, Person 2's file). Person 5's job, per the
team contract table, is:

```
Input:  portfolio, risk_profile
Output: personalization, scenario
```

So `risk/` explains *how a user's risk profile and portfolio should
color the interpretation* of whatever the Judge already decided — it
never overrides or replaces that verdict.

## Files

### `risk/portfolio.py`
- `compute_stock_exposure(portfolio, symbol) -> float`
  Fraction (0.0–1.0) of `portfolio_value` held in `symbol`.
- `compute_concentration_score(portfolio) -> int`
  Portfolio-wide concentration, 0–100, via Herfindahl-Hirschman Index
  (`sum(weight_i ** 2) * 100`). A single 100%-weight holding scores
  100; many small even positions score near 0. This is a *whole
  portfolio* metric, distinct from `stock_exposure`, which is scoped
  to one symbol.
- `build_portfolio_summary(portfolio) -> dict`
  Assembles the `portfolio` master object per ARCHITECTURE.md §9.

### `risk/profiles.py`
- `build_personalization(user_profile, portfolio, symbol) -> dict`
  Builds the `personalization` object per ARCHITECTURE.md §10.
  Deterministic Python rules, not an LLM — the same portfolio and
  symbol reliably produce different `personalized_reason` text for a
  `CONSERVATIVE` vs. `AGGRESSIVE` user, because each risk tier has a
  different single-stock exposure ceiling and concentration ceiling:

  | risk_profile | single-stock ceiling | concentration ceiling |
  |---|---|---|
  | CONSERVATIVE | 20% | 20/100 |
  | BALANCED | 30% | 30/100 |
  | AGGRESSIVE | 40% | 45/100 |

  `personalized_reason` always names the exact numbers involved (e.g.
  "Your RELIANCE position is 30.0% of your portfolio, above the 20%
  single-stock ceiling for a Conservative investor.") rather than
  vague text like "risk profile affected the result."

  Never crashes: malformed/missing `user_profile` or `portfolio`
  fields fall back to a `BALANCED` / zero-exposure default rather
  than raising.

### `risk/simulation.py`
- `run_scenario(portfolio, symbol, scenario, scenario_change_percent=None) -> dict`
  Builds the `scenario` (what-if) object per ARCHITECTURE.md §11.
  Applies a price-change percentage to `symbol`'s current holding
  value; other holdings are assumed unaffected (no cross-asset
  correlation modeling — deliberately simple for a hackathon).
  Presets: `BULL_CASE` (+15%), `BASE_CASE` (0%), `BEAR_CASE` (-10%),
  `CRASH` (-25%); or pass an explicit `scenario_change_percent`.

## `data/profiles.json`

Two fixtures matching ARCHITECTURE.md's USER VARIABLES + `portfolio`
shape exactly (no invented fields):

- **u1 / Priya** — `CONSERVATIVE`, ₹500,000 portfolio, ~30%
  concentrated in RELIANCE (breaches the conservative ceiling).
- **u2 / Arjun** — `AGGRESSIVE`, ~₹500,000 portfolio, diversified
  across 10 holdings, max single position ~12% (within every
  ceiling).

## Tests

`tests/test_synthesis.py` (filename kept as originally scaffolded)
proves the core personalization requirement: **same portfolio + same
symbol + different `risk_profile` → different `personalization`**,
using both a synthetic fixture and the real `data/profiles.json`
fixtures. It also covers the concentration-score formula, scenario
math, and never-crash behavior on empty/malformed input.

Run with:

```
python3 tests/test_synthesis.py
```

## What I deliberately did not touch

- `contracts.py`, `safety.py`, `validate.py` — currently empty stub
  files owned by other roles; left untouched per the "don't modify
  another teammate's files" rule.
- `docs/ARCHITECTURE.md` — the team's shared contract, already
  committed by another teammate; this file (`RISK_MODULE.md`) is a
  separate doc so the shared contract stays a single source of truth.
