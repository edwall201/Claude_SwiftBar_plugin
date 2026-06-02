# Claude Usage — macOS menu bar monitor

A [SwiftBar](https://github.com/swiftbar/SwiftBar) plugin that shows your Claude
usage in the macOS menu bar, mirroring the compact `/usage` popover: context
window, 5-hour limit, and weekly (all models) — each with a progress bar and a
minute-precise reset countdown.

The 5-hour and weekly numbers come straight from Anthropic's own usage endpoint
(the exact data behind Settings › Usage), so they match the official panel.

The menu bar shows a small orange Claude-monster icon; click it for the breakdown.

![icon](monster.png)

## How it works

For the **5-hour and weekly limits**, the plugin calls Anthropic's official usage
endpoint — `GET https://claude.ai/api/organizations/{org}/usage`, the same data
the Settings › Usage panel renders — authenticated with your `claude.ai` browser
cookie. The `utilization` percentages and `resets_at` times are reported by
Anthropic, so they match the panel exactly (no local estimation or calibration).

For the **context window** there is no server endpoint, so the plugin reads your
local Claude Code transcripts (`~/.claude/projects/**/*.jsonl`), deduplicates by
`(message.id, requestId)`, and measures the most recent assistant turn's prompt
size against the 200k window.

Your cookie is stored privately at `~/.claude/.usage_monitor_cookie` (chmod 600,
outside this repo) and is only ever sent to `claude.ai`. The last good API
response is cached at `~/.claude/.usage_monitor_cache.json` so a brief network
blip doesn't blank the panel.

## Install

1. Install SwiftBar:
   ```sh
   brew install swiftbar
   ```
2. Point SwiftBar at the `plugins/` directory (SwiftBar prompts for a plugin
   folder on first launch, or):
   ```sh
   defaults write com.ameba.SwiftBar PluginDirectory "$(pwd)/plugins"
   open -a SwiftBar
   ```
3. The plugin file is `plugins/claude-usage.30s.py` — the `30s` means it auto-refreshes
   every 30 seconds, so the numbers stay close to live without pressing Refresh.

## Setup: claude.ai cookie

The 5-hour / weekly numbers need your `claude.ai` session cookie (the context
window works without it). To set it:

1. Open <https://claude.ai/settings/usage> in your browser.
2. Open DevTools (⌥⌘I) → **Network**, then refresh the page.
3. Click the **`usage`** request, and under **Request Headers** copy the whole
   **`Cookie`** value.
4. In the menu bar, click the icon → **Set claude.ai cookie…**, paste, and Save.

Cookies expire periodically; when the panel shows *"Cookie expired — set it
again,"* repeat the steps (use **Update cookie…**). **Clear cookie** removes it.

## Files

- `plugins/claude-usage.30s.py` — the SwiftBar plugin (fetches official usage,
  reads logs for the context window, renders the panel).
- `icon_gen.py` — regenerates the orange monster icon (PIL/Pillow) and re-embeds
  the base64 into the plugin.
- `monster.png` / `monster.b64` — the generated icon.

## Tuning

- Icon size in the menu bar: `ICON_POINT_H` in `icon_gen.py` (lower → smaller icon).
- Dropdown panel: the breakdown is drawn as a single image in `render_panel()`
  (`claude-usage.30s.py`) so the text stays crisp and dark and the rows aren't
  clickable buttons. Tune `W` / `row_h` for size and `_level_color()` for the
  bar colors. Colors auto-adapt to macOS light/dark mode.
- Cookie / cache locations: `COOKIE_FILE` / `CACHE_FILE`. Request fidelity (if the
  endpoint ever changes): `USAGE_URL` / `USAGE_HEADERS`.

After editing the icon, run `python3 icon_gen.py`, then force-restart SwiftBar
(`killall SwiftBar; open -a SwiftBar`) to clear its image cache.
