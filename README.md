# poker-cli

[English](README.md) · [简体中文](README.zh-CN.md)

A terminal app for LAN multiplayer Texas Hold'em (No-Limit Hold'em). Launch it with a single command; once the host creates a room, friends on the same LAN can see it in the room list and join with zero configuration.

```
██████╗  ██████╗ ██╗  ██╗███████╗██████╗        ██████╗██╗     ██╗
██╔══██╗██╔═══██╗██║ ██╔╝██╔════╝██╔══██╗      ██╔════╝██║     ██║
██████╔╝██║   ██║█████╔╝ █████╗  ██████╔╝█████╗██║     ██║     ██║
██╔═══╝ ██║   ██║██╔═██╗ ██╔══╝  ██╔══██╗╚════╝██║     ██║     ██║
██║     ╚██████╔╝██║  ██╗███████╗██║  ██║      ╚██████╗███████╗██║
╚═╝      ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝       ╚═════╝╚══════╝╚═╝
```

## Install

Requires [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync                # Install dependencies (sets up Python 3.11+ automatically)
uv run poker-cli       # Launch
```

Or install it as a global command:

```bash
uv tool install .
poker-cli
```

Runtime dependencies are just `rich` and `prompt_toolkit`; all networking uses the standard library.

## How to play

- **Create a room**: Main menu → Create room → set room name / table size / blinds → press Enter in the waiting area to start (empty seats are auto-filled by bots).
- **Join a room**: Main menu → Join room → pick from the auto-discovered list (shows N/M players; full tables and rooms already in a hand are hidden automatically; or type `IP:port` manually).
- **Local practice**: play against 3 bots.
- If a joiner's nickname equals the host's, it is auto-renamed to `nickname2`, `nickname3`, … (handy for testing two clients on one machine).

In-game keys:

| Key | Action |
|---|---|
| `F` / `C` / `R` / `A` | Fold / Check or Call / Raise / All-in (first-letter shortcuts) |
| `←` `→` | Adjust the raise amount (`Shift` for large steps; also 1 min / 2 half-pot / 3 pot / 4 all-in) |
| `↑` `↓` + `Enter` | Menu selection (number keys also work) |
| `M` | Chat — available any time during the game, typed inside the frame |
| `V` | Toggle rich / simple display mode (saved instantly) |
| `L` | Hand history & chat overlay |
| `?` | Help overlay |
| `Ctrl-C` | Quit with confirmation |
| `Q` | Host closes the room from the waiting area |

## Display modes

- **Rich** (default): a stable single-frame table — bordered seat boxes with the hero anchored
  at the bottom, a centred board panel with the pot as its title, real card faces
  (11x9 hero cards, 6x5 board, 5x4 mini), deal/flip and showdown sequences with a pot
  pulse and a thinking indicator for bots.
- **Simple**: the same facts in compact single-line text — ideal for narrow terminals
  (below 70x24 it is chosen automatically), slow links, or minimalists. An information-parity
  test guarantees no game fact is lost in either mode.

Both modes draw through one alternate-screen frame that refreshes only when content
actually changes, so the table never flickers or scrolls.

When the action timer expires it auto-checks/folds; when a player disconnects the system plays their hand to the end — the game never stalls.

## Rules covered

Standard No-Limit Texas Hold'em: blind and button rotation, heads-up special cases, minimum raise and short all-in (which does not reopen the action), layered side-pot settlement, odd chips awarded in button order, uncalled bets returned, A-2-3-4-5 wheel. Played tournament-style to the end (busting = elimination); between hands you may continue or end and see the final standings.

## Known limits (v1 design trade-offs)

- No joining once a hand has started (joins in the waiting area are unrestricted); a disconnected player's seat cannot be taken over.
- When broadcast cannot cross subnets or isolated switches, join via manual IP entry (the host's waiting area shows the local IP).
- On Windows the first run raises a firewall prompt — allow it for private networks; same-machine play does not need this.
- Chat: the host in the waiting area; during a hand anyone can chat with `M` from inside the frame.

On Windows, prefer Windows Terminal; if card suits render incorrectly, run `chcp 65001` first.

## Development

```bash
uv run pytest              # 101 engine/protocol/UI tests
uv run python tests/e2e_lan.py   # Two-process end-to-end game (create → discover → join → play → settle)
uv run python tests/smoke_local.py  # Scripted single-player session smoke
uv run python -m rpoker.ui.showcase  # Render every card/seat/frame state
uv run ruff check src tests
```

Architecture: one-way dependency `domain ← engine ← {actors, ui, net} ← app`; the engine is the sole authority for state; RNG/clock are fully injected; and an entire game is replayable from the same seed.
