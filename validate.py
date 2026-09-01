#!/usr/bin/env python3
"""
RUN BEFORE EVERY PUSH:  python3 validate.py

This is the guard rail. It fails the build on the mistakes that have actually
bitten this project, not on hypothetical ones:
  - a field name that drifted from docs/ARCHITECTURE.md
  - a symbol offered in the UI that has no filings behind it
  - a data file that no longer matches the contract
  - an agent whose signature the orchestrator cannot call
  - a pipeline that raises instead of degrading

CI runs exactly this file. If it passes locally it passes in CI.
"""
import asyncio
import importlib
import inspect
import json
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent
FAILURES: list[str] = []
NOTES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(f"{label}: {detail}")
    return ok


# Names that were used at some point and MUST NOT come back. Left side is the
# banned spelling, right side is what to use instead.
BANNED = {
    r"\bticker\b": "symbol",
    r"\bstock_symbol\b": "symbol",
    r"\bstock_name\b": "company_name",
    r"\bprice_now\b": "current_price",
    r"\bagent\b\s*=\s*[\"']": "agent_name=",
    r"from models import": "from contracts import",
    r"\bSynthesisOutput\b": "InvestigationResult",
    r"status\s*==\s*[\"']OK[\"']": 'status in ("COMPLETE", "DEGRADED")',
    r"[\"']PENDING[\"']": "a valid Verdict (INSUFFICIENT_DATA)",
}
SCAN_EXCLUDE = {".git", ".venv", "venv", "node_modules", "__pycache__", "logs", "docs"}


def scan_for_banned_names() -> None:
    print("\n[1] naming contract (docs/ARCHITECTURE.md)")
    hits = []
    for path in BASE.rglob("*"):
        if path.is_dir() or path.suffix not in {".py", ".json", ".js", ".html", ".ts"}:
            continue
        if set(path.relative_to(BASE).parts) & SCAN_EXCLUDE or path.name == "validate.py":
            continue
        text = path.read_text(errors="ignore")
        for pattern, replacement in BANNED.items():
            for m in re.finditer(pattern, text):
                line = text[:m.start()].count("\n") + 1
                hits.append(f"{path.relative_to(BASE)}:{line} '{m.group(0)}' -> use {replacement}")
    check("no banned field names", not hits, f"{len(hits)} occurrence(s)")
    for h in hits[:12]:
        print(f"        {h}")


def check_contracts() -> bool:
    print("\n[2] contracts")
    try:
        import contracts
    except Exception as e:
        return check("contracts.py imports", False, str(e))
    ok = check("contracts.py imports", True)
    strict = all(getattr(m, "model_config", {}).get("extra") == "forbid"
                 for m in vars(contracts).values()
                 if inspect.isclass(m) and issubclass(m, contracts.Strict))
    ok &= check("every model forbids unknown fields", strict,
                "a model allows extras; naming drift would pass silently")
    return ok


def check_data() -> None:
    print("\n[3] data files")
    from contracts import MarketData, Portfolio, UserProfile
    import store
    from rag.ingest import available_symbols

    try:
        mkt = store.market()
        check("data/market/market.json validates", bool(mkt), "empty or missing")
    except Exception as e:
        check("data/market/market.json validates", False, str(e)[:110]); mkt = {}

    try:
        profs = store.profiles()
        check("data/profiles.json validates", len(profs) >= 2, f"{len(profs)} profile(s), need >= 2")
    except Exception as e:
        check("data/profiles.json validates", False, str(e)[:110]); profs = {}

    filings = set(available_symbols())
    check("filings corpus is non-empty", bool(filings), "no documents loaded")

    missing = sorted(set(mkt) - filings)
    check("every market symbol has filings", not missing,
          f"no filings for {missing} — the UI would show empty evidence")

    for uid, (_, p) in profs.items():
        if not p.holdings or p.portfolio_value <= 0:
            continue
        actual = round(max(h.current_value for h in p.holdings) / p.portfolio_value * 100, 2)
        # store derives this from the holdings; a zero here means the derivation
        # was skipped, which silently disables the conservative downgrade rule.
        check(f"{uid} concentration_score is derived", abs(actual - p.concentration_score) < 0.01,
              f"reports {p.concentration_score}, holdings say {actual}")

    risks = {p[0].risk_profile for p in profs.values()}
    check("profiles differ in risk_profile", len(risks) >= 2,
          f"all profiles are {risks} — personalization cannot be demonstrated")


def check_agents() -> None:
    print("\n[4] agent modules")
    from orchestrator import AGENTS
    found = 0
    for agent_name, module_path in AGENTS.items():
        try:
            mod = importlib.import_module(module_path)
        except ModuleNotFoundError:
            NOTES.append(f"{agent_name} not implemented yet ({module_path})")
            continue
        found += 1
        fn = getattr(mod, "run", None)
        if not check(f"{agent_name}.run exists", callable(fn), f"{module_path}.run missing"):
            continue
        params = list(inspect.signature(fn).parameters)
        check(f"{agent_name}.run(symbol, market_data)", len(params) >= 2 and params[0] == "symbol",
              f"signature is ({', '.join(params)})")
        check(f"{agent_name}.run is async", inspect.iscoroutinefunction(fn), "must be async def")
    if found == 0:
        print("  ....  no agents implemented yet (orchestrator degrades cleanly)")


def check_pipeline() -> None:
    print("\n[5] pipeline behaviour")
    import store
    from orchestrator import investigate
    from contracts import InvestigationResult

    syms = store.symbols()
    if not syms:
        check("pipeline runs", False, "no symbols available"); return
    try:
        r = asyncio.run(investigate(syms[0], "u1"))
        check("pipeline returns a valid result", isinstance(r, InvestigationResult))
        check("result is JSON-serialisable", bool(json.dumps(r.model_dump(), default=str)))
    except Exception as e:
        check("pipeline runs without raising", False, f"{type(e).__name__}: {e}")
        return
    try:
        asyncio.run(investigate("DEFINITELY_NOT_A_SYMBOL", "u1"))
        check("unknown symbol degrades instead of raising", True)
    except Exception as e:
        check("unknown symbol degrades instead of raising", False, f"{type(e).__name__}: {e}")


def main() -> int:
    print("INVESTIGATOR — pre-push validation")
    sys.path.insert(0, str(BASE))
    scan_for_banned_names()
    if check_contracts():
        check_data()
        check_agents()
        check_pipeline()

    print()
    for n in NOTES:
        print(f"  note: {n}")
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S) — DO NOT PUSH\n")
        return 1
    print("\nALL CHECKS PASSED\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
