#!/usr/bin/env python3
# <bitbar.title>Claude Usage</bitbar.title>
# <bitbar.version>1.0</bitbar.version>
# <bitbar.author>edward</bitbar.author>
# <bitbar.desc>Shows local Claude Code token usage and computed cost.</bitbar.desc>
# <swiftbar.environment>[]</swiftbar.environment>
#
# SwiftBar/xbar plugin. Reads Claude Code transcripts from ~/.claude/projects,
# sums token usage per time window, and estimates USD cost from public pricing.
# Note: this is *spend computed from local logs*, not an official balance.

import os
import sys
import json
import glob
from datetime import datetime, timezone, timedelta

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# White pixel-art Claude-invader icon (regenerate with icon_gen.py).
# Used with `templateImage=` so macOS tints it to the menu-bar label color.
MONSTER_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAIgAAABgCAYAAADGrTq9AAAACXBIWXMAAFHFAABRxQH1ERwsAAAB"
    "KElEQVR4nO3dSwqDQBBAwUzI/a9s9gaegZjxQ9XeQfExq4Z+PAAA5ht7H7gsy7L3mXxvjLHrP33u"
    "eRj3IxCSQEgCIQmEJBCSQEgCIQmEJBCSQEgCIQmEJBCSQEivo19gbWue4erzJlf7PjcISSAkgZAE"
    "QhIISSAkgZAEQhIISSAkgZAEQhIISSAkgZA+ZhPONo/AXOt5FTcISSAkgZAEQhIISSAkgZAEQhII"
    "SSAkgZAEQhIISSAkgZAEQhIISSAkgZAEQhIISSAkgZDszb0Ze3OZSiAkgZAEQhIISSAkgZAEQhII"
    "SSAkgZAEQhIISSAkgZCm7839dW/sv5/fcvT7zZ63cYOQBEISCEkgJIGQBEISCEkgJIGQBEISCEkg"
    "JIGQBEISCAAAp/MGmvQosug1gGcAAAAASUVORK5CYII="
)

# USD per 1M tokens. Cache write = input * 1.25 (5m) or * 2.0 (1h); cache read uses its own rate.
PRICING = {
    "opus":   {"in": 15.0, "out": 75.0, "cache_read": 1.50},
    "sonnet": {"in": 3.0,  "out": 15.0, "cache_read": 0.30},
    "haiku":  {"in": 1.0,  "out": 5.0,  "cache_read": 0.10},
}
DEFAULT = PRICING["sonnet"]

# ---- Plan usage limits (mirrors Settings > Plan usage limits) ----
# These windows are computed accurately from local logs. The *percentage* needs a
# limit that Anthropic does not expose locally, so calibrate it once against the
# official panel:  budget = window_cost / (percent_shown / 100)
# Leave a budget None to instead gauge against your own historical peak.
SESSION_HOURS = 5                 # rolling "Current session" window length
WEEKLY_RESET_WEEKDAY = 3          # Mon=0 .. Sun=6 ; Thu=3 (match your Settings panel)
WEEKLY_RESET_HOUR = 17            # local hour of the weekly reset (17 = 5 PM)
SESSION_BUDGET = 87.0             # calibrated so 5h matches Settings (was 12% at $10.46)
WEEKLY_BUDGET = 215.0             # calibrated so weekly matches Settings (was 10% at $21.48)


def rates_for(model):
    m = (model or "").lower()
    if "opus" in m:
        return PRICING["opus"]
    if "haiku" in m:
        return PRICING["haiku"]
    if "sonnet" in m:
        return PRICING["sonnet"]
    return DEFAULT


def parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def cost_for(usage, model):
    r = rates_for(model)
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    cread = usage.get("cache_read_input_tokens", 0) or 0
    cc = usage.get("cache_creation") or {}
    c5 = cc.get("ephemeral_5m_input_tokens", 0) or 0
    c1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
    if not (c5 or c1h):
        # fall back to flat cache_creation_input_tokens treated as 5m write
        c5 = usage.get("cache_creation_input_tokens", 0) or 0
    cost = (
        inp * r["in"]
        + out * r["out"]
        + cread * r["cache_read"]
        + c5 * r["in"] * 1.25
        + c1h * r["in"] * 2.0
    ) / 1_000_000.0
    tokens = inp + out + cread + c5 + c1h
    ctx = inp + cread + c5 + c1h          # prompt size (≈ context window fill)
    return cost, tokens, ctx


def collect():
    """Return (entries, latest) where latest=(ts, ctx_tokens, model) for the most
    recent assistant turn (used to estimate the live context-window fill)."""
    seen = set()
    entries = []
    latest = None
    for path in glob.glob(os.path.join(PROJECTS_DIR, "**", "*.jsonl"), recursive=True):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or '"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    msg = d.get("message") or {}
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    key = (msg.get("id"), d.get("requestId"))
                    if key != (None, None) and key in seen:
                        continue
                    seen.add(key)
                    ts = parse_ts(d.get("timestamp"))
                    model = msg.get("model") or ""
                    if "synthetic" in model.lower():
                        continue
                    cost, tokens, ctx = cost_for(usage, model)
                    if tokens == 0:
                        continue
                    entries.append((ts, model, cost, tokens))
                    if ts is not None and (latest is None or ts > latest[0]):
                        latest = (ts, ctx, model)
        except Exception:
            continue
    return entries, latest


def pct_bar(frac, width=22):
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def fmt_hm(delta):
    """Minute-precise countdown: '3d 1h 5m', '4h 12m', '7m'."""
    secs = max(0, int(delta.total_seconds()))
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return "{}d {}h {}m".format(days, hours, mins)
    if hours:
        return "{}h {}m".format(hours, mins)
    return "{}m".format(mins)


def weekly_anchor(dt, weekday, hour):
    """Most recent weekly-reset boundary at/just before dt."""
    cand = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    cand -= timedelta(days=(dt.weekday() - weekday) % 7)
    if cand > dt:
        cand -= timedelta(days=7)
    return cand


def build_sessions(time_costs, hours):
    """Group (dt, cost) into rolling sessions; a new session starts when a message
    lands >= `hours` after the current session's start. Returns [(start, cost), ...]."""
    span = timedelta(hours=hours)
    sessions = []
    start, acc = None, 0.0
    for dt, c in time_costs:
        if start is None or dt >= start + span:
            if start is not None:
                sessions.append((start, acc))
            start, acc = dt, 0.0
        acc += c
    if start is not None:
        sessions.append((start, acc))
    return sessions


def frac(cost, budget, peak):
    """Usage fraction: vs the calibrated budget if set, else vs your own peak."""
    if budget and budget > 0:
        return cost / budget
    return cost / peak if peak > 0 else 0.0


def main():
    entries, latest = collect()
    now = datetime.now(timezone.utc).astimezone()
    BLUE = "#3B6FE0"
    BAR_W = 30

    # rolling 5h session
    time_costs = sorted((ts.astimezone(), cost) for ts, model, cost, tokens in entries if ts)
    span = timedelta(hours=SESSION_HOURS)
    sessions = build_sessions(time_costs, SESSION_HOURS)
    session_active = bool(sessions) and now < sessions[-1][0] + span
    session_cost = sessions[-1][1] if session_active else 0.0
    session_peak = max((c for _, c in sessions), default=0.0)
    session_reset = sessions[-1][0] + span if session_active else None
    sess_frac = frac(session_cost, SESSION_BUDGET, session_peak)

    # weekly window
    weekly_buckets = {}
    for dt, c in time_costs:
        a = weekly_anchor(dt, WEEKLY_RESET_WEEKDAY, WEEKLY_RESET_HOUR)
        weekly_buckets[a] = weekly_buckets.get(a, 0.0) + c
    cur_anchor = weekly_anchor(now, WEEKLY_RESET_WEEKDAY, WEEKLY_RESET_HOUR)
    weekly_cost = weekly_buckets.get(cur_anchor, 0.0)
    weekly_peak = max(weekly_buckets.values(), default=0.0)
    weekly_reset = cur_anchor + timedelta(days=7)
    wk_frac = frac(weekly_cost, WEEKLY_BUDGET, weekly_peak)

    # context window (latest assistant turn)
    ctx_max = 200_000
    ctx_tok = latest[1] if latest else 0
    ctx_frac = ctx_tok / ctx_max

    # menu bar: white invader icon (template image auto-tints to the bar color)
    print("| templateImage={}".format(MONSTER_B64))
    print("---")
    if not entries:
        print("No Claude Code usage found | color=gray")
        print("Refresh | refresh=true")
        return

    print("Context window   {:.1f}k / {:.0f}k ({:.0f}%) | font=Menlo".format(
        ctx_tok / 1000, ctx_max / 1000, ctx_frac * 100))
    print("{} | font=Menlo color={}".format(pct_bar(ctx_frac, BAR_W), BLUE))
    print("---")
    print("Plan usage | font=Menlo")
    sess_reset_txt = "resets in " + fmt_hm(session_reset - now) if session_active else "ready"
    print("5-hour limit   {:.0f}% · {} | font=Menlo".format(sess_frac * 100, sess_reset_txt))
    print("{} | font=Menlo color={}".format(pct_bar(sess_frac, BAR_W), BLUE))
    print("Weekly · all models   {:.0f}% · resets in {} | font=Menlo".format(
        wk_frac * 100, fmt_hm(weekly_reset - now)))
    print("{} | font=Menlo color={}".format(pct_bar(wk_frac, BAR_W), BLUE))
    print("---")
    print("Refresh | refresh=true")


if __name__ == "__main__":
    main()
