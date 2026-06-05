# Claude Usage — macOS menu bar monitor

A [SwiftBar](https://github.com/swiftbar/SwiftBar) plugin that puts your Claude
usage in the macOS menu bar — the same numbers as Claude's `/usage` popover:
**context window**, **5-hour limit**, **weekly** usage, and optionally your
**API credit balance**, each with a progress bar and a live reset countdown.

![icon](monster.png)

---

## Quick start

```sh
# 1. Install SwiftBar
brew install swiftbar

# 2. Install Pillow (needed for the graphical panel; skip for plain-text fallback)
python3 -m pip install --user Pillow

# 3. Point SwiftBar at the plugins folder and launch
defaults write com.ameba.SwiftBar PluginDirectory "$(pwd)/plugins"
open -a SwiftBar
```

The Claude-monster icon appears in your menu bar within a few seconds and
refreshes every 30 seconds automatically.

> **5-hour & weekly rows are hidden until you set your cookie** — see
> [Set your claude.ai cookie](#set-your-claudeai-cookie) below.

---

## What you'll see

Click the monster icon to open the panel:

| Row | What it shows |
|-----|--------------|
| **Context window** | How full the current Claude Code conversation is (out of the 200 k-token limit). Derived from local transcripts — no cookie needed. |
| **5-hour limit** | Your rolling 5-hour usage, percentage used + time until reset. |
| **Weekly · all models** | 7-day usage across all models. |
| **Weekly · Sonnet** | 7-day Sonnet-only usage (shown only when Anthropic reports it separately). |
| **Credit balance** | Your prepaid API credit balance from platform.claude.com — shown only after setting the console cookie (optional). |

Each row shows a **percentage**, a **"resets in …"** countdown, and a
**progress bar** that shifts blue → orange (≥ 60 %) → red (≥ 85 %) as you
approach a limit. The credit-balance bar runs the opposite direction: green
when full, orange → red as it drains.

---

## Requirements

- **macOS** with [SwiftBar](https://github.com/swiftbar/SwiftBar) (`brew install swiftbar`)
- **Python 3** (pre-installed on macOS, or from python.org / Homebrew)
- **[Pillow](https://pypi.org/project/Pillow/)** — for the rendered image panel.
  Without it the plugin still works, falling back to plain text rows.
- A **claude.ai account** — needed only for the 5-hour / weekly rows

---

## Set your claude.ai cookie

The 5-hour and weekly rows call Anthropic's official usage endpoint
(`Settings › Usage`), which requires your `claude.ai` session cookie.

1. Open <https://claude.ai/settings/usage> while signed in.
2. Open DevTools (**⌥⌘I**) → **Network** tab, then refresh the page.
3. Click the **`usage`** request → **Request Headers** → copy the entire
   **`Cookie`** value.
4. Click the menu-bar monster → **Set claude.ai cookie…**, paste it, and **Save**.

Numbers appear on the next refresh. When the panel says
*"Cookie expired — set it again,"* grab a fresh value and use **Update cookie…**.

---

## Set your credit-balance cookie (optional)

This unlocks the **Credit balance** row, which shows your prepaid API balance
from [platform.claude.com](https://platform.claude.com) — a separate login
from claude.ai, so it needs its own cookie.

1. Open <https://platform.claude.com/settings/billing> while signed in.
2. Open DevTools (**⌥⌘I**) → **Network** tab, then refresh the page.
3. Click the **`credits`** request → **Request Headers** → copy the entire
   **`Cookie`** value.
4. Click the menu-bar monster → **Set credit-balance cookie…**, paste it, and
   **Save**.

The balance row appears on the next refresh. Use **Update credit-balance
cookie…** when it expires, or **Clear credit-balance cookie** to remove it.

---

## Install (detailed)

1. **Install SwiftBar:**
   ```sh
   brew install swiftbar
   ```

2. **Install Pillow** into the Python that will run the plugin:
   ```sh
   python3 -m pip install --user Pillow
   python3 -c "import PIL; print('Pillow OK')"
   ```

3. **Point SwiftBar at `plugins/`** and launch it:
   ```sh
   defaults write com.ameba.SwiftBar PluginDirectory "$(pwd)/plugins"
   open -a SwiftBar
   ```
   Or pick the `plugins/` folder when SwiftBar prompts on first launch.

4. **Check the file is executable** (the repo ships it that way, but just in case):
   ```sh
   chmod +x plugins/claude-usage.30s.py
   ```

The `30s` in the filename tells SwiftBar to auto-refresh every 30 seconds.

---

## Everyday use

- **Auto-refresh:** the panel updates every 30 s. **Refresh** in the menu
  forces an immediate update.
- **Offline:** the panel keeps the last good numbers and notes
  *"showing last good data"* until it reconnects.
- **Cookie management:** use **Update cookie… / Clear cookie** (and their
  console counterparts) from the dropdown at any time.

---

## Troubleshooting

| Message in panel | What to do |
|-----------------|------------|
| *Set your claude.ai cookie to show limits* | No cookie saved — use **Set claude.ai cookie…** |
| *Cookie expired — set it again* | Session expired — grab a fresh cookie and use **Update cookie…** |
| *Couldn't find your org id — re-set the cookie* | The pasted cookie is missing the org token; copy the **whole** Cookie header again |
| *Couldn't reach claude.ai (offline?)* | Network blip — cached data shown until it reconnects |
| Rows show as plain text, not an image panel | Pillow isn't installed for the plugin's Python — see [Requirements](#requirements) |
| Nothing appears in the menu bar | Confirm the file is executable and SwiftBar points at `plugins/` |

---

## How it works

**5-hour & weekly:** calls `GET https://claude.ai/api/organizations/{org}/usage`
— the same endpoint that powers Settings › Usage — authenticated with your
`claude.ai` cookie. Uses `curl --http1.1` to avoid Cloudflare's HTTP/2
fingerprinting. `utilization` percentages and `resets_at` times come directly
from Anthropic, so they match the official panel exactly.

**Context window:** no server endpoint exists for this, so the plugin reads
your local Claude Code transcripts (`~/.claude/projects/**/*.jsonl`),
deduplicates by `(message.id, requestId)`, and measures the most recent
assistant turn's prompt size against the 200 k-token limit.

**Credit balance:** calls `GET https://platform.claude.com/api/organizations/{org}/prepaid/credits`
with your platform.claude.com cookie — the same data shown on the Billing page.

---

## Privacy & security

Your cookies are live session credentials. They are stored privately at:

- `~/.claude/.usage_monitor_cookie` (claude.ai — chmod 600)
- `~/.claude/.usage_monitor_console_cookie` (platform.claude.com — chmod 600)

Both files are outside this repo, never committed or printed, and only ever
sent to their respective Anthropic endpoints. The last good API responses are
cached at `~/.claude/.usage_monitor_cache.json` and
`~/.claude/.usage_monitor_credit_cache.json` so a brief outage doesn't blank
the panel.

---

## Files

| File | Purpose |
|------|---------|
| `plugins/claude-usage.30s.py` | SwiftBar plugin — fetches usage, reads transcripts, renders the panel |
| `icon_gen.py` | Regenerates the monster icon (Pillow) and re-embeds its base64 into the plugin |
| `monster.png` / `monster.b64` | The generated menu-bar icon |

---

## Tuning

| Setting | Where |
|---------|-------|
| Menu-bar icon size | `ICON_POINT_H` in `icon_gen.py` (lower = smaller) |
| Panel width / row height | `W` / `row_h` in `render_panel()` inside `claude-usage.30s.py` |
| Bar color thresholds | `_level_color()` (usage bars) and `_balance_color()` (credit bar) |
| Cookie / cache paths | `COOKIE_FILE`, `CONSOLE_COOKIE_FILE`, `CACHE_FILE`, `CREDIT_CACHE_FILE` |

After editing the icon, regenerate and restart SwiftBar:

```sh
python3 icon_gen.py
killall SwiftBar; open -a SwiftBar
```
