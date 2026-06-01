# Claude Usage — macOS menu bar monitor

A [SwiftBar](https://github.com/swiftbar/SwiftBar) plugin that shows your local
Claude Code usage in the macOS menu bar, mirroring the compact `/usage` popover:
context window, 5-hour limit, and weekly (all models) — each with a progress bar
and a minute-precise reset countdown.

The menu bar shows a small orange Claude-monster icon; click it for the breakdown.

![icon](monster.png)

## How it works

The plugin reads Claude Code transcripts from `~/.claude/projects/**/*.jsonl`,
deduplicates by `(message.id, requestId)`, and computes token usage and an
estimated USD cost from public per-model pricing. It then groups spend into a
rolling 5-hour session window and a weekly window (resets Thu 5 PM local).

Note: this is *spend computed from local logs*, not an official Anthropic balance.
Anthropic doesn't expose plan limits locally, so the percentages are calibrated
against the official Settings panel via `SESSION_BUDGET` / `WEEKLY_BUDGET`.

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
3. The plugin file is `plugins/claude-usage.10m.py` — the `10m` means it refreshes
   every 10 minutes.

## Files

- `plugins/claude-usage.10m.py` — the SwiftBar plugin (reads logs, renders the panel).
- `icon_gen.py` — regenerates the orange monster icon (PIL/Pillow) and re-embeds
  the base64 into the plugin.
- `monster.png` / `monster.b64` — the generated icon.

## Tuning

- Icon size in the menu bar: `ICON_POINT_H` in `icon_gen.py` (lower → smaller icon).
- Dropdown panel: the breakdown is drawn as a single image in `render_panel()`
  (`claude-usage.10m.py`) so the text stays crisp and dark and the rows aren't
  clickable buttons. Tune `W` / `row_h` for size and `_level_color()` for the
  bar colors. Colors auto-adapt to macOS light/dark mode.
- Percentage calibration: `SESSION_BUDGET` / `WEEKLY_BUDGET`.

After editing the icon, run `python3 icon_gen.py`, then force-restart SwiftBar
(`killall SwiftBar; open -a SwiftBar`) to clear its image cache.
