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

# The session / weekly numbers come from Anthropic's own usage endpoint — the
# exact data behind Settings › Usage — authenticated with your claude.ai browser
# cookie. We keep the cookie and a small cache of the last good response under
# ~/.claude (outside the repo). The cookie is a live session credential, so the
# file is written 0600 (user-only) and never printed in the menu.
COOKIE_FILE = os.path.expanduser("~/.claude/.usage_monitor_cookie")
CACHE_FILE = os.path.expanduser("~/.claude/.usage_monitor_cache.json")
USAGE_URL = "https://claude.ai/api/organizations/{org}/usage"
BOOTSTRAP_URL = "https://claude.ai/api/bootstrap"
# Look like the website so the endpoint answers the same way it does in-browser.
USAGE_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://claude.ai",
    "Referer": "https://claude.ai",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "authority": "claude.ai",
}

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


def read_cookie():
    """Return the saved claude.ai cookie string, or '' if unset."""
    try:
        with open(COOKIE_FILE) as fh:
            return fh.read().strip()
    except Exception:
        return ""


def save_cookie(cookie):
    """Persist the cookie privately (0600) so only the user account can read it."""
    try:
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, "w") as fh:
            fh.write(cookie.strip())
        os.chmod(COOKIE_FILE, 0o600)
    except Exception:
        pass


def clear_cookie():
    try:
        os.remove(COOKIE_FILE)
    except Exception:
        pass


def org_id_from_cookie(cookie):
    """The cookie usually carries lastActiveOrg=<uuid>; pull it straight out."""
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("lastActiveOrg="):
            return part[len("lastActiveOrg="):]
    return None


class _HttpError(Exception):
    """A non-200 status from the usage endpoint (carries the HTTP code)."""
    def __init__(self, code):
        super().__init__("HTTP {}".format(code))
        self.code = code


def _get_json(url, cookie, timeout=8):
    """GET a claude.ai JSON endpoint through the system curl. curl uses macOS's own
    trust store, so this works regardless of how the Python install's CA bundle is
    configured (the stock python.org build often has none) — the same networking
    the website itself uses. Returns the parsed dict; raises _HttpError(code) on a
    non-200 response, or OSError if curl itself fails (network down, etc.).

    `--http1.1` is essential: over HTTP/2 Cloudflare fingerprints the (non-browser)
    client and serves its 403 "Just a moment…" JS challenge; forcing HTTP/1.1 makes
    the same request answer 200, the way the browser's own XHR does."""
    args = ["/usr/bin/curl", "--silent", "--show-error", "--http1.1",
            "--max-time", str(timeout),
            "-H", "Cookie: " + cookie, "-w", "\n%{http_code}"]
    for k, v in USAGE_HEADERS.items():
        args += ["-H", "{}: {}".format(k, v)]
    args.append(url)
    out = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 5)
    if out.returncode != 0:
        raise OSError(out.stderr.strip() or "curl exit {}".format(out.returncode))
    body, _, code = out.stdout.rpartition("\n")
    try:
        status = int(code.strip())
    except ValueError:
        status = 0
    if status != 200:
        raise _HttpError(status)
    return json.loads(body)


def get_org_id(cookie):
    """Org id from the cookie if present, else from the bootstrap endpoint."""
    oid = org_id_from_cookie(cookie)
    if oid:
        return oid
    try:
        data = _get_json(BOOTSTRAP_URL, cookie)
        return (data.get("account") or {}).get("lastActiveOrgId")
    except Exception:
        return None


def fetch_usage(cookie):
    """Hit Anthropic's official usage endpoint. Returns (data, error): data is the
    raw JSON dict (five_hour / seven_day / seven_day_sonnet) or None; error is a
    short tag — 'nocookie', 'noorg', 'auth' (expired), 'net', or 'httpNNN'."""
    if not cookie:
        return None, "nocookie"
    org = get_org_id(cookie)
    if not org:
        return None, "noorg"
    try:
        return _get_json(USAGE_URL.format(org=org), cookie), None
    except _HttpError as e:
        return None, "auth" if e.code in (401, 403) else "http{}".format(e.code)
    except Exception:
        return None, "net"


def usage_window(data, key):
    """(utilization_fraction, resets_at_datetime) for one window key, or None when
    the key is absent. The API reports utilization 0..100; we return 0..1."""
    w = (data or {}).get(key)
    if not isinstance(w, dict):
        return None
    util = w.get("utilization")
    fr = (float(util) / 100.0) if isinstance(util, (int, float)) else 0.0
    return fr, parse_ts(w.get("resets_at"))


def load_cache():
    try:
        with open(CACHE_FILE) as fh:
            return json.load(fh)
    except Exception:
        return None


def save_cache(data):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def prompt_cookie():
    """Pop a native dialog to paste the cookie, then save it. Invoked by the
    dropdown 'Set cookie…' item (which re-runs this script with --set-cookie)."""
    msg = ("Paste your claude.ai cookie.\\n\\n"
           "claude.ai → Settings → Usage, open DevTools (⌥⌘I) → Network, refresh "
           "the page, click the 'usage' request, then copy the whole 'Cookie' "
           "value from its Request Headers.")
    osa = ('set t to text returned of (display dialog "{}" default answer "" '
           'with title "Claude Usage — set cookie" buttons {{"Cancel", "Save"}} '
           'default button "Save")').format(msg)
    try:
        out = subprocess.run(["osascript", "-e", osa],
                             capture_output=True, text=True, timeout=180)
        cookie = (out.stdout or "").strip()
        if cookie:
            save_cookie(cookie)
    except Exception:
        pass


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
    _, latest = collect()
    now = datetime.now(timezone.utc).astimezone()
    BLUE = "#2F62E0"          # solid bar color
    INK = "#000000"          # solid dropdown text
    TXT = "Menlo-Bold"       # bold so vibrancy doesn't wash it to grey
    BAR_W = 40
    script = os.path.abspath(__file__)

    # Context window (latest assistant turn) — the one figure the official API
    # doesn't expose, so we still derive it from the local transcripts.
    ctx_max = 200_000
    ctx_tok = latest[1] if latest else 0
    ctx_frac = ctx_tok / ctx_max
    ctx_value = "{:.1f}k / {:.0f}k · {:.0f}%".format(
        ctx_tok / 1000, ctx_max / 1000, ctx_frac * 100)

    # Session + weekly: the real numbers straight from Anthropic's usage endpoint.
    cookie = read_cookie()
    data, err = fetch_usage(cookie)
    stale = False
    if data is not None:
        save_cache(data)                 # remember the last good snapshot
    elif err == "net":
        data = load_cache()              # transient outage: show what we last saw
        stale = data is not None

    # menu bar: white invader icon (template image auto-tints to the bar color)
    print("| templateImage={}".format(MONSTER_B64))
    print("---")

    # Build rows. The dropdown is rendered as one image so the text stays crisp
    # and dark (macOS dims grey *text* items, and making them clickable turns
    # every line into a highlightable button); an image is neither.
    rows = [{"label": "Context window", "value": ctx_value,
             "frac": ctx_frac, "divider": False}]
    for key, label, div in (("five_hour", "5-hour limit", True),
                            ("seven_day", "Weekly · all models", False),
                            ("seven_day_sonnet", "Weekly · Sonnet", False)):
        w = usage_window(data, key)
        if not w:
            continue
        fr, reset = w
        if reset and reset.astimezone() > now:
            value = "{:.0f}% · resets {}".format(fr * 100, fmt_hm(reset.astimezone() - now))
        else:
            value = "{:.0f}%".format(fr * 100)
        rows.append({"label": label, "value": value, "frac": fr, "divider": div})

    panel = render_panel(rows) if HAVE_PIL else None
    if panel:
        print("| image={}".format(panel))
    else:
        # Fallback (no PIL): plain text rows, no refresh=true so they aren't buttons.
        for r in rows:
            print("{}  {} | font={} color={}".format(r["label"], r["value"], TXT, INK))
            print("{} | font=Menlo color={}".format(pct_bar(r["frac"], BAR_W), BLUE))

    # Status line + cookie actions.
    print("---")
    if data is None:
        hint = {
            "nocookie": "Set your claude.ai cookie to show limits",
            "noorg": "Couldn't find your org id — re-set the cookie",
            "auth": "Cookie expired — set it again",
            "net": "Couldn't reach claude.ai (offline?)",
        }.get(err, "Couldn't load usage ({})".format(err))
        print("⚠ {} | color=#cc6600".format(hint))
    elif stale:
        print("⚠ showing last good data (couldn't refresh) | color=#999999 size=11")

    if cookie:
        print("Update cookie… | bash=\"{}\" param1=--set-cookie terminal=false refresh=true".format(script))
        print("Clear cookie | bash=\"{}\" param1=--clear-cookie terminal=false refresh=true".format(script))
    else:
        print("Set claude.ai cookie… | bash=\"{}\" param1=--set-cookie terminal=false refresh=true".format(script))
    print("Refresh | refresh=true")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--set-cookie":
        prompt_cookie()
    elif arg == "--clear-cookie":
        clear_cookie()
    else:
        main()
