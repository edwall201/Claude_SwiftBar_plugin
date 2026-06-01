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
import io
import json
import glob
import base64
import subprocess
from datetime import datetime, timezone, timedelta

try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

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
SESSION_BUDGET = 46.0             # calibrated vs Settings Pro panel: $34.33 -> 75% (Jun 2026)
WEEKLY_BUDGET = 344.0             # calibrated vs Settings Pro panel: $65.29 -> 19% (Jun 2026)


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


def is_dark_mode():
    """True when macOS is in Dark mode (so the menu background is dark)."""
    try:
        out = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2)
        return "dark" in (out.stdout or "").strip().lower()
    except Exception:
        return False


def _load_font(size):
    for p in ("/System/Library/Fonts/SFNS.ttf",
              "/System/Library/Fonts/SFNSDisplay.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _level_color(fr):
    """Calm blue normally; warn orange/red as a limit fills up."""
    if fr >= 0.85:
        return (255, 69, 58)        # red
    if fr >= 0.60:
        return (255, 159, 10)       # orange
    return (47, 98, 224)            # blue


def render_panel(rows):
    """Render the whole usage panel as one crisp base64 PNG. An image menu item
    keeps full color (macOS doesn't dim it like grey text) and isn't a row of
    clickable buttons. Returns a base64 string, or None on any failure."""
    try:
        S = 2                       # supersample, paired with 144 DPI => retina
        W = 370                     # logical width. Wider => smaller right margin
        #                             (the menu reserves trailing space on the right
        #                             for the SwiftBar submenu arrow).
        pad = 14
        row_h = 42
        div_gap = 12
        top = 12
        bot = 10
        n = len(rows)
        ndiv = sum(1 for r in rows if r.get("divider"))
        H = top + row_h * n + div_gap * ndiv + bot

        dark = is_dark_mode()
        text_col = (245, 245, 247) if dark else (29, 29, 31)
        sub_col = (152, 152, 160) if dark else (120, 120, 128)
        track_col = (74, 74, 78) if dark else (224, 224, 230)
        div_col = (255, 255, 255, 28) if dark else (0, 0, 0, 24)

        img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        f_label = _load_font(14 * S)
        f_value = _load_font(12 * S)

        y = top * S
        inner = (W - 2 * pad) * S
        for r in rows:
            if r.get("divider"):
                y += div_gap * S
                ly = y - (div_gap // 2) * S
                d.line([(pad * S, ly), ((W - pad) * S, ly)],
                       fill=div_col, width=max(1, S))
            d.text((pad * S, y), r["label"], font=f_label, fill=text_col)
            vw = d.textlength(r["value"], font=f_value)
            d.text((W * S - pad * S - vw, y + 3 * S), r["value"],
                   font=f_value, fill=sub_col)
            by = y + 24 * S
            bh = 8 * S
            rad = bh / 2.0
            d.rounded_rectangle([pad * S, by, pad * S + inner, by + bh],
                                radius=rad, fill=track_col)
            fr = max(0.0, min(1.0, r["frac"]))
            if fr > 0:
                fw = max(bh, inner * fr)
                d.rounded_rectangle([pad * S, by, pad * S + fw, by + bh],
                                    radius=rad, fill=_level_color(fr))
            y += row_h * S

        buf = io.BytesIO()
        dpi = 72 * S
        img.save(buf, format="PNG", dpi=(dpi, dpi))
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def main():
    entries, latest = collect()
    now = datetime.now(timezone.utc).astimezone()
    BLUE = "#2F62E0"          # solid bar color
    INK = "#000000"          # solid dropdown text
    TXT = "Menlo-Bold"       # bold so vibrancy doesn't wash it to grey
    BAR_W = 40

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
        print("No Claude Code usage found")
        print("Refresh | refresh=true")
        return

    # The dropdown is rendered as a single image so the text stays crisp and dark
    # (macOS dims grey *text* items, and making them clickable turns every line
    # into a highlightable button). An image item is neither dimmed nor a button.
    ctx_value = "{:.1f}k / {:.0f}k · {:.0f}%".format(
        ctx_tok / 1000, ctx_max / 1000, ctx_frac * 100)
    sess_value = ("{:.0f}% · resets {}".format(sess_frac * 100, fmt_hm(session_reset - now))
                  if session_active else "ready")
    wk_value = "{:.0f}% · resets {}".format(wk_frac * 100, fmt_hm(weekly_reset - now))
    rows = [
        {"label": "Context window", "value": ctx_value, "frac": ctx_frac, "divider": False},
        {"label": "5-hour limit", "value": sess_value, "frac": sess_frac, "divider": True},
        {"label": "Weekly · all models", "value": wk_value, "frac": wk_frac, "divider": False},
    ]

    panel = render_panel(rows) if HAVE_PIL else None
    if panel:
        print("| image={}".format(panel))
    else:
        # Fallback (no PIL): plain text rows, no refresh=true so they aren't buttons.
        for r in rows:
            print("{}  {} | font={} color={}".format(r["label"], r["value"], TXT, INK))
            print("{} | font=Menlo color={}".format(pct_bar(r["frac"], BAR_W), BLUE))
    print("---")
    print("Refresh | refresh=true")


if __name__ == "__main__":
    main()
