#!/usr/bin/env python3
# <bitbar.title>Claude Usage</bitbar.title>
# <bitbar.version>1.0</bitbar.version>
# <bitbar.author>edward</bitbar.author>
# <bitbar.desc>Shows Claude 5-hour / weekly usage limits, API credit balance, and Meta Muse usage.</bitbar.desc>
# <swiftbar.environment>[]</swiftbar.environment>
# Hide SwiftBar's default footer. The "SwiftBar" item is a submenu, and macOS
# reserves a disclosure-arrow gutter on the right of every row whenever any item
# has a submenu — that gutter is dead space the panel image can't fill. Dropping
# it (and the noisy "Updated … ago" line) lets the panel define the menu width.
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
#
# SwiftBar/xbar plugin. Shows the official 5-hour and weekly usage limits from
# claude.ai's usage endpoint, plus (optionally) the platform.claude.com prepaid
# credit balance and Meta Muse (muse.ai) weekly usage / extra tokens.

import os
import sys
import io
import json
import re
import base64
import subprocess
from datetime import datetime, timezone, timedelta

try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

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

# API prepaid credit balance — the "Credit balance" shown on
# platform.claude.com → Settings › Billing. That's the developer/API console, a
# *separate* login from claude.ai, so it has its own cookie file. The row only
# appears when this cookie is set and the call succeeds (otherwise it's hidden,
# like the Sonnet window when the API omits it).
CONSOLE_COOKIE_FILE = os.path.expanduser("~/.claude/.usage_monitor_console_cookie")
CREDIT_CACHE_FILE = os.path.expanduser("~/.claude/.usage_monitor_credit_cache.json")
CREDITS_URL = "https://platform.claude.com/api/organizations/{org}/prepaid/credits"
CONSOLE_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://platform.claude.com",
    "Referer": "https://platform.claude.com/settings/billing",
    "anthropic-client-platform": "web_console",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "authority": "platform.claude.com",
}

# Meta Muse (muse.ai) usage — the numbers behind its Settings › General › Usage
# panel. Muse is a Next.js app with no REST usage endpoint: the panel calls a
# server action (POST / with a `Next-Action` header). That action id is a build
# hash, so it may change when Muse redeploys; if the row turns into an error,
# re-capture it from DevTools (the POST to / whose response has "percentUsed").
MUSE_COOKIE_FILE = os.path.expanduser("~/.claude/.usage_monitor_muse_cookie")
MUSE_CACHE_FILE = os.path.expanduser("~/.claude/.usage_monitor_muse_cache.json")
MUSE_URL = "https://muse.ai/"
MUSE_ACTION_ID = "409a453bab86cadab1629915e1baf2d9c1701284be"
MUSE_HEADERS = {
    "Accept": "text/x-component",
    "Content-Type": "text/plain;charset=UTF-8",
    "Next-Action": MUSE_ACTION_ID,
    "Origin": "https://muse.ai",
    "Referer": "https://muse.ai/",
    # Muse's middleware 403s requests without the fetch-metadata headers a
    # browser sends on a same-origin fetch, even with a valid session cookie.
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "User-Agent": USAGE_HEADERS["User-Agent"],
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


def pct_bar(frac, width=22):
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def _level_color(fr):
    """Calm blue normally; warn orange/red as a limit fills up."""
    if fr >= 0.85:
        return (255, 69, 58)        # red
    if fr >= 0.60:
        return (255, 159, 10)       # orange
    return (47, 98, 224)            # blue


def _balance_color(fr):
    """Credit-balance gauge runs the opposite way to a usage bar: full = healthy,
    so it's green when there's plenty left and warns as it drains toward empty."""
    if fr >= 0.50:
        return (52, 199, 89)        # green
    if fr >= 0.20:
        return (255, 159, 10)       # orange
    return (255, 69, 58)            # red


def _hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


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


def render_panel(rows):
    """Render the whole usage panel as one crisp base64 PNG. An image menu item
    keeps full color (macOS doesn't dim it like grey text) and isn't a row of
    clickable buttons. Returns a base64 string, or None on any failure."""
    try:
        S = 2                       # supersample, paired with 144 DPI => retina
        W = 300                     # logical width. With the submenu footer hidden
        #                             (see header) the panel is the widest row, so
        #                             W sets the menu width directly — no reserved
        #                             arrow gutter to leave blank space on the right.
        pad = 8                     # left+right inner margin (smaller => content
        #                             hugs both edges of the panel more tightly)
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
                bar_col = (_balance_color(fr) if r.get("kind") == "balance"
                           else _level_color(fr))
                d.rounded_rectangle([pad * S, by, pad * S + fw, by + bh],
                                    radius=rad, fill=bar_col)
            y += row_h * S

        buf = io.BytesIO()
        dpi = 72 * S
        img.save(buf, format="PNG", dpi=(dpi, dpi))
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


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


def read_console_cookie():
    """Return the saved platform.claude.com cookie string, or '' if unset."""
    try:
        with open(CONSOLE_COOKIE_FILE) as fh:
            return fh.read().strip()
    except Exception:
        return ""


def save_console_cookie(cookie):
    try:
        os.makedirs(os.path.dirname(CONSOLE_COOKIE_FILE), exist_ok=True)
        with open(CONSOLE_COOKIE_FILE, "w") as fh:
            fh.write(cookie.strip())
        os.chmod(CONSOLE_COOKIE_FILE, 0o600)
    except Exception:
        pass


def clear_console_cookie():
    try:
        os.remove(CONSOLE_COOKIE_FILE)
    except Exception:
        pass


def read_file_cookie(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except Exception:
        return ""


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


def _get_json(url, cookie, timeout=8, headers=None):
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
    for k, v in (headers or USAGE_HEADERS).items():
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


def fetch_credits():
    """API prepaid credit balance from platform.claude.com (the console billing
    page). Best-effort: returns the raw dict ({'amount': cents, 'currency': ...,
    'last_paid_purchase_cents': ...}) or None when there's no console cookie or
    the call fails. Uses its own cookie (a different login from claude.ai)."""
    cookie = read_console_cookie()
    if not cookie:
        return None
    org = org_id_from_cookie(cookie)
    if not org:
        return None
    try:
        return _get_json(CREDITS_URL.format(org=org), cookie, headers=CONSOLE_HEADERS)
    except Exception:
        return None


def fetch_muse():
    """Muse subscription/usage via its settings server action. Returns the
    `subscription` dict (usage.percentUsed, usage.resetsAt epoch secs,
    topupBalance, topupTotal, ...) or None when there's no cookie or it fails."""
    cookie = read_file_cookie(MUSE_COOKIE_FILE)
    if not cookie:
        return None
    args = ["/usr/bin/curl", "--silent", "--show-error", "--http1.1",
            "--max-time", "8", "-X", "POST",
            "-H", "Cookie: " + cookie, "--data", '[{"includeAgreement":true}]']
    for k, v in MUSE_HEADERS.items():
        args += ["-H", "{}: {}".format(k, v)]
    args.append(MUSE_URL)
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=13)
    except Exception:
        return None
    # React Server Components stream: one "<id>:<json>" record per line; the
    # action's return value is the record holding "subscription".
    for line in (out.stdout or "").splitlines():
        _, _, payload = line.partition(":")
        if '"subscription"' not in payload:
            continue
        try:
            sub = json.loads(payload).get("subscription")
        except Exception:
            return None
        return sub if isinstance(sub, dict) else None
    return None


def load_cache(path=CACHE_FILE):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def save_cache(data, path=CACHE_FILE):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
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


def prompt_console_cookie():
    """Pop a native dialog to paste the platform.claude.com cookie (the API
    console — separate login from claude.ai), then save it privately."""
    msg = ("Paste your platform.claude.com cookie.\\n\\n"
           "platform.claude.com → Settings → Billing, open DevTools (⌥⌘I) → "
           "Network, refresh, click the 'credits' request, then copy the whole "
           "'Cookie' value from its Request Headers.")
    osa = ('set t to text returned of (display dialog "{}" default answer "" '
           'with title "Claude Usage — set credit-balance cookie" '
           'buttons {{"Cancel", "Save"}} default button "Save")').format(msg)
    try:
        out = subprocess.run(["osascript", "-e", osa],
                             capture_output=True, text=True, timeout=180)
        cookie = (out.stdout or "").strip()
        if cookie:
            save_console_cookie(cookie)
    except Exception:
        pass


def prompt_muse_cookie():
    """Pop a native dialog to paste the muse.ai cookie, then save it privately."""
    msg = ("Paste your muse.ai cookie.\\n\\n"
           "muse.ai → open DevTools (⌥⌘I) → Network, open Settings, click the "
           "POST request to muse.ai/ (its response has percentUsed), then copy "
           "the whole 'Cookie' value from its Request Headers.")
    osa = ('set t to text returned of (display dialog "{}" default answer "" '
           'with title "Claude Usage — set Muse cookie" '
           'buttons {{"Cancel", "Save"}} default button "Save")').format(msg)
    try:
        out = subprocess.run(["osascript", "-e", osa],
                             capture_output=True, text=True, timeout=180)
        cookie = (out.stdout or "").strip()
        if cookie:
            os.makedirs(os.path.dirname(MUSE_COOKIE_FILE), exist_ok=True)
            with open(MUSE_COOKIE_FILE, "w") as fh:
                fh.write(cookie)
            os.chmod(MUSE_COOKIE_FILE, 0o600)
    except Exception:
        pass


def main():
    now = datetime.now(timezone.utc).astimezone()
    INK = "#000000"          # solid dropdown text
    TXT = "Menlo-Bold"       # bold so vibrancy doesn't wash it to grey
    BAR_W = 40
    script = os.path.abspath(__file__)

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
    rows = []
    for key, label, div in (("five_hour", "5-hour limit", False),
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

    # API prepaid credit balance (platform.claude.com console). Separate login, so
    # this is best-effort: the row only shows when that cookie is set and the call
    # works. Cached like the usage data so a blip doesn't drop it.
    credit = fetch_credits()
    if credit is not None:
        save_cache(credit, CREDIT_CACHE_FILE)
    else:
        credit = load_cache(CREDIT_CACHE_FILE)
    if isinstance(credit, dict) and isinstance(credit.get("amount"), (int, float)):
        cents = credit["amount"]
        cur = credit.get("currency") or "USD"
        sym = "$" if cur == "USD" else cur + " "
        ref = credit.get("last_paid_purchase_cents") or 0
        if ref < cents:                       # no/old top-up reference => full gauge
            ref = cents
        frac = (cents / ref) if ref else 0.0
        rows.append({"label": "Credit balance",
                     "value": "{}{:.2f}".format(sym, cents / 100.0),
                     "frac": frac, "divider": True, "kind": "balance"})

    # Meta Muse: weekly plan usage + prepaid top-up tokens. Best-effort like the
    # credit balance — hidden until a muse.ai cookie is set.
    muse = fetch_muse()
    if muse is not None:
        save_cache(muse, MUSE_CACHE_FILE)
    elif read_file_cookie(MUSE_COOKIE_FILE):
        muse = load_cache(MUSE_CACHE_FILE)
    if isinstance(muse, dict):
        u = muse.get("usage") or {}
        pct = u.get("percentUsed")
        if isinstance(pct, (int, float)):
            fr = pct / 100.0
            value = "{:.0f}%".format(pct)
            ra = u.get("resetsAt")
            if isinstance(ra, (int, float)):
                reset = datetime.fromtimestamp(ra, timezone.utc).astimezone()
                if reset > now:
                    value += " · resets {}".format(fmt_hm(reset - now))
            rows.append({"label": "Muse · weekly", "value": value,
                         "frac": fr, "divider": True})
        bal, tot = muse.get("topupBalance"), muse.get("topupTotal")
        if isinstance(bal, (int, float)) and isinstance(tot, (int, float)) and tot > 0:
            # topupBalance isn't in tokens (240M total shows as ~6B tokens on the
            # site), so take the "5.9B tokens left" text from Muse's own label.
            m = re.search(r"\(([^)]*left)\)", muse.get("topupRowValueLabel") or "")
            rows.append({"label": "Muse · extra tokens",
                         "value": m.group(1) if m else "{:.0f}% left".format(bal / tot * 100),
                         "frac": bal / tot, "divider": False, "kind": "balance"})

    panel = render_panel(rows) if HAVE_PIL else None
    if panel:
        print("| image={}".format(panel))
    else:
        # Fallback (no PIL, or the image failed to render): plain text rows
        # with the same color-coded bars and section dividers.
        for i, r in enumerate(rows):
            if r.get("divider") and i > 0:
                print("---")
            bar_color = _hex(_balance_color(r["frac"]) if r.get("kind") == "balance" else _level_color(r["frac"]))
            print("{}  {} | font={} color={}".format(r["label"], r["value"], TXT, INK))
            print("{} | font=Menlo color={}".format(pct_bar(r["frac"], BAR_W), bar_color))

    # Status line + cookie actions. SwiftBar incrementally diffs menu items on
    # refresh, and a big image= item next to a *varying* item count above/below
    # it desyncs that diff (https://github.com/swiftbar/SwiftBar/issues/482),
    # corrupting the rendered panel. So every branch below prints a fixed
    # number of lines each cycle — only the label/color changes with state.
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
    else:
        print("✓ Live | color=#999999 size=11")

    label = "Update cookie…" if cookie else "Set claude.ai cookie…"
    print("{} | bash=\"{}\" param1=--set-cookie terminal=false refresh=true".format(label, script))
    print("Clear cookie | bash=\"{}\" param1=--clear-cookie terminal=false refresh=true".format(script))

    label = "Update credit-balance cookie…" if read_console_cookie() else "Set credit-balance cookie…"
    print("{} | bash=\"{}\" param1=--set-console-cookie terminal=false refresh=true".format(label, script))
    print("Clear credit-balance cookie | bash=\"{}\" param1=--clear-console-cookie terminal=false refresh=true".format(script))
    label = "Update Muse cookie…" if read_file_cookie(MUSE_COOKIE_FILE) else "Set Muse cookie…"
    print("{} | bash=\"{}\" param1=--set-muse-cookie terminal=false refresh=true".format(label, script))
    print("Clear Muse cookie | bash=\"{}\" param1=--clear-muse-cookie terminal=false refresh=true".format(script))
    print("Refresh | refresh=true")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--set-cookie":
        prompt_cookie()
    elif arg == "--clear-cookie":
        clear_cookie()
    elif arg == "--set-console-cookie":
        prompt_console_cookie()
    elif arg == "--clear-console-cookie":
        clear_console_cookie()
    elif arg == "--set-muse-cookie":
        prompt_muse_cookie()
    elif arg == "--clear-muse-cookie":
        try:
            os.remove(MUSE_COOKIE_FILE)
        except Exception:
            pass
    else:
        main()
