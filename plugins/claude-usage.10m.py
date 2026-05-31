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

# Orange Claude-monster icon, COLOR png (regenerate with icon_gen.py).
# Used with `image=` (not templateImage) so the orange is preserved.
MONSTER_B64 = (
    "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"
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

    # menu bar: icon only
    print("| image={}".format(MONSTER_B64))
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
