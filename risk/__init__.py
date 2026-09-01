"""
risk/ — Person 5's module.

Owns: portfolio math, risk-profile rules, and what-if simulation.

Per docs/ARCHITECTURE.md (the team's shared naming contract):
  Input:  portfolio, risk_profile
  Output: personalization, scenario

This module never emits a BUY/SELL/HOLD-style verdict — that is the
Judge Agent's job (agents/judge_agent.py, owned by Person 2). This
module only explains how a user's risk profile and portfolio should
color the interpretation of whatever verdict the Judge produces.
"""