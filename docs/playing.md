# Playing: details

Moved out of the README; the short version is there.

## Running the game

```sh
tools/play.sh                 # play with your own profile (~/.local/share/forza)
tools/play.sh --xenia         # continue your Xenia Canary save (a copy; see below)
tools/play.sh --offline       # without Xbox LIVE
tools/run_forza.sh 120        # a two-minute test run; logs in ${XDG_RUNTIME_DIR:-/tmp}/forza_run
```

- **Profile and controllers:** the game runs signed in to one local profile on player 1,
  and every connected controller drives player 1, so START on any pad gets you past the
  title screen (with Steam Input or Sunshine virtual pads around, your pad is often not
  the first one, and the game used to ask that pad to sign in).
  `FORZA_PAD_PER_USER=1` gives each pad its own player again.
- **Keyboard:** the SDK's keyboard emulation of a pad is available with `--mnk_mode=true`
  (bindings: the SDK's `keybind_*` settings; not tested yet).
- **Xbox LIVE:** the game signs in to an emulated Xbox LIVE, as a Gold member, through a
  Forza Live server (`server/forza_live_server.py`, Python 3 standard library only).
  `play.sh` starts one on this machine for the session (UDP 21200, HTTP 21201, data in
  `~/.local/share/forza/live_server/`), or uses the one already running there. To play
  with others, run the server where everyone can reach it
  (`python3 server/forza_live_server.py --http-port 21201`) and start the game with
  `FORZA_SERVER=host[:port]` (or `live_server = "host:port"` in `forza.toml` next to the
  binary). Your online identity (XUID, gamertag: your login name unless
  `FORZA_GAMERTAG` is set) is kept in `~/.local/share/forza/4D5309C9/live_identity.txt`.
  Everyone in the server's room is your friend.
  **The shared world:** Multiplayer, Find Game, **Horizon World** (the first playlist).
  The server puts you into the fullest open world (8 players each) or you open a new one
  and start driving at once, alone, and everyone who picks it after you is placed with
  you: their lobby says FREE ROAM IN PROGRESS, and **JUMP IN** drives them into the
  running world. The world is an endless online free roam (co-op challenges from the
  host's pause menu); when its host leaves, the others keep driving and the next players
  are placed with them. The host's END FREE ROAM takes everyone back to the lobby, and the
  world starts again after 5 s. `world_drop_in = false` in `forza.toml` turns this off
  (the world is then Find Game's race-like free roam, which a late player only enters
  after the round; `--world-round-minutes` on the server ends those rounds on a timer).
  Details: [`docs/online_vision.md`](docs/online_vision.md).
  To play together in a party: everyone opens
  Multiplayer; one player picks Invite Friends in the party lobby (there is no Guide, so
  this invites everyone in the room) and the others join that party on their own
  (`live_accept_invites`). The party leader then picks Create Custom Game, sets the game
  type under Setup Game (Free Roam, races, ...), saves the setup (YES) and starts once
  the others are ready. Or, without a party: Find Game, then the Races playlist; the
  first player hosts the playlist's lobby and the next ones join it, and the race starts
  after the intermission once two players are in. The server also stands in for Turn 10's
  title services ("the Horizon server", `docs/title_services.md`): the playlists, the
  rounds' tracks, and online XP, which it keeps per player (`players/` in its data
  directory) and gives back at every sign-in; credits stay in your save. It also keeps
  every player's best lap on each event with its ghost (`scoreboards.json`, `ghosts/`):
  Race Central's LEADERBOARDS show them, and X RIVALS on an event's ticket races you
  against another player's ghost for a bounty.
- **Frame rate:** `frame_rate = 60` in `forza.toml` (or `tools/play.sh --frame_rate=60`)
  runs the game at 60 fps instead of the console's 30. The game times its physics and
  clocks in real time, so they keep their speed. Free roam runs 59 fps; a race with 7 AI
  cars about 42 fps for now, bound by the GPU emulation
  ([`docs/framerate.md`](docs/framerate.md)).
- **DLC:** install your DLC packages (the `4D5309C9/00000002/` folder of your content)
  once with `python3 tools/install_dlc.py /path/to/4D5309C9/00000002`.
- **Saves** live in `~/.local/share/forza/B13EBABEBABEBABE/4D5309C9/`.
- **Your Xenia save:** `tools/play.sh --xenia` copies your Xenia Canary profile's Forza
  Horizon save (`~/xenia_canary_windows/content/<XUID>/4D5309C9`, or
  `$FORZA_XENIA_CONTENT/<XUID>/4D5309C9`) into `~/.local/share/forza/xenia-<XUID>/` and
  plays it signed in with that XUID: Forza ties its save to the profile's XUID, and
  refuses (freezes on the title screen) a save made under another one. The copy is made
  once, so progress made here stays in it; `--xenia-refresh` copies the Xenia save again.
  The Xenia original is never modified. With several Xenia profiles, name one:
  `tools/play.sh --xenia E030000004B490FA`. (Equivalent by hand: copy the save under the
  runtime's profile folder and start with `--profile_xuid=<XUID>`.)
