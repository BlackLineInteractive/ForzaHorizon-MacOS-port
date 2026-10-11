# Online vision: a shared Horizon world

The long-term goal for online play, built in phases. Phase 1 (automatic shared free roam)
is in; the later phases are designs, based on what phase 1 showed. Notes from reverse
engineering that matter for them are collected at the end.

## The goal

Forza Horizon online where every online player is in the same world, MMO-like shared
free roam:

- Players join the game's events from the world with their own unlocked cars, under each
  event's conditions (class and car restrictions and so on), and race the other players.
- Free grid slots are filled with CPU opponents.
- The AI difficulty follows the share of humans on the grid: at most 1/3 humans gives an
  easier AI, around 1/2 intermediate, 2/3 or more harder. On an 8-car grid: 1-2 humans
  easy, 3-5 intermediate, 6 or more hard.
- Every online event gets a pre-race wait lobby. When a player starts or joins an event,
  the race waits 30 seconds for other players in the world to join before it starts, so
  by default it never starts with one human and an all-AI grid. When the 30 s run out,
  the free slots are filled with AI, whose difficulty is set from the final human share.
  *Assumption (not stated by the user):* if the grid fills with humans before the 30 s
  are up, the race starts right away.
- The game's own online pre-race lobby and countdown are the likely base for this; notes
  on them go under Findings.

## Phase 1 (built): the shared world, automatic placement

**How to play:** Multiplayer, Find Game, **Horizon World** (the first playlist). Nothing
else: the server either places you into an open world (its lobby offers **JUMP IN**, which
drives you into the running free roam) or you open a new one and drive at once, alone, and
the next players drop into yours. The world is an endless online free roam.

### The trigger: a "Horizon World" playlist in Find Game

The Forza Live server serves a third playlist (hopper 3, `server/forza_live_lsp.py`),
listed first, whose rounds are online free roam: `GameTypePreset="7"`
(`IDS_PresetFreeRoam` in `media/gametunablesettings/GameOptionPresets.xml`), the festival
as the starting location (track 1101), `StartType="OpenWorld"`, `MaxPlayers="8"`.

Why this trigger:

- It is how Playground built public free roam: the game's own fallback playlist (Quick
  Match, `DefaultPlaygroundHopperOptions.xml`) is the same preset 7 free roam through
  matchmaking. Find Game searches with `XSessionSearchEx`, which `live_xmsg.cpp` answers
  from the server, so the server decides who goes where, and the game itself joins the
  session it is given or hosts one when there is none.
- No setup: a custom game's Free Roam needs its host to go through Create Custom Game,
  Setup Game and Game Type first, and invites (Reach's `live_accept_invites`, the party
  lobby's Invite Friends) only reach a party whose leader has already set that up.
- It is two presses from the party lobby, and the playlist's options are server data:
  the round's GameOptions XML, its search settings and its intermission.

### Placement

- A host's client publishes its matchmaking session on the server (`MATCH_PUBLISH`:
  XSESSION_INFO, slots, properties, QoS data) under its playlist; the session's filled
  slots follow `XSessionJoin`/`Leave`. The playlist is the search property `0x10000030`
  (Forza's hopper id; Find Custom Game puts the game type tab's value there, free roam 8);
  before, the client looked only for Reach's `0x10000015`, so every Forza search saw every
  hosted session.
- A search (`MATCH_SEARCH`) gets the sessions with a free public slot, **the fullest
  first**, then the oldest: players gather in as few worlds as possible, and a full world
  (8/8) is never offered. The game joins the first one it reaches
  (`maxConnectAttemptsBeforeCreating` 2, `maxConnectSecondsBeforeCreating` 10 in the
  world's search settings) and hosts a new world otherwise.
- The first player in an empty world drives at once: its lobby starts the 5 s
  intermission with one player and loads the world (see "Solo start" below; before, it
  waited with "WAITING FOR PLAYERS TO JOIN..." until a second player came).
- The server logs every decision (`match #id 'name' playlist 3: 1 open session(s), first
  <session> from #host (1/8)` or `no open session, it hosts`), and its status page lists
  each player's published session (`match`: playlist, players, slots).

### Joining a world in progress: drop-in (`src/hooks/world_drop_in.cpp`)

Find Game runs its games differently from a custom game, and the difference is a mode
of the online game (the object at `*(0x83305CC4)`, mode at `+40`, set by `sub_828733A8`
when a game starts): Find Game is 7, Find Custom Game 10 (`sub_8287F2B8` picks 7 or 10 from
the matchmaking kind), a custom game's host 8 (race) or 9 (free roam). Three things follow
from it, and in the Horizon World (playlist 3, a free-roam round, mode 7) the client
(`world_drop_in`, on by default) now gives each the custom free roam's behaviour:

1. **Join in progress.** `sub_82865340(mode)` is "custom game" (8, 9, 10). Only then does
   the lobby of a game in progress say FREE ROAM IN PROGRESS (lobby state 10, the label
   picked at `0x8281B358`) and offer **JUMP IN** (button 6 of the lobby's table, handler
   `0x826EE1D0`; its filter needs "custom", and `0x82701018` makes it available), does
   the host accept the joiner's ready flag while the game runs (`0x82893B1C`), and does
   every peer add the car of a player whose status becomes "in game" (`0x8288DCD4`). In
   Find Game the joiner sat in "GAME IN PROGRESS / WAITING FOR PLAYERS TO FINISH GAME".
   The hook answers "custom" at those call sites only (by return address, plus
   `0x82624B00` in the free roam); the lobby's other buttons and the game's options
   (`0x828837A4`: the hopper's GetGameOptions, not a custom setup) stay Find Game's.
   From the code (not measured): JUMP IN is offered once the free roam has run
   `Online/Multiplayer/MinimumTimeToJumpInToFreeRoam` (20 s, `GlobalRegistry.xml`); the
   lobby counts that down (`sub_82819670`).
2. **The flow.** The launch (`sub_8286A2E0`) starts a custom game as race type 18, the
   online free roam flow (`game_start_multiplayer_playground` in `gamemodes.zip`: co-op
   challenges, joiners placed into the running world through `set_car_to_joining_session`),
   with HUD mode 17; everything else as race type 6, an online race (the TIME/RACE/LAP
   timers and PLACE 1/2 phase 1 saw, a timed end) with HUD mode 21. The type is the race
   settings' `+44` (`sub_82C0F2C0`, read by `CGameTypeDecision`, `0x82909A38`: 18 =
   multi_player_free_roam, 6 = multi_player_race). With only the join fixed, a player who
   pressed JUMP IN in a race-type world stayed on the loading screen. The hook on
   `sub_825548A0` (called from the launch) makes the world type 18 and HUD mode 17.
3. **Solo start.** The host's lobby (`sub_8287F670`) starts the intermission once
   `sub_82876D90` says ready: enough players (`+2016`, the search settings'
   `minPlayersToLaunch`, 1 in the world), nobody still joining, and in Find Game the
   team/bucket check done (`+2148`, `sub_82895018`, run by `sub_82875FB8` when `+2152` is
   set, which happens when a remote player's status changes). A host alone never had it
   run, so it waited for a second player. For a world host alone in its lobby the hook on
   `sub_82875FB8` sets the flag; the check runs, the 5 s intermission starts and the
   world loads with one player.

Measured (two instances): A alone picked Horizon World; the world launched after the 5 s
intermission and A was driving about 40 s after picking it, with the free roam HUD ("SELECT A CO-OP CHALLENGE FROM THE PAUSE MENU", no timers or place).
B picked it, was placed into A's world, saw FREE ROAM IN PROGRESS and JUMP IN, and drove in
the world about 30 s after pressing it (B's HUD "WAITING FOR HOST TO SELECT A CO-OP
CHALLENGE", both names in both lists, A's car with its tag in B's view after A drove up).

The world has no timed end now: the free roam flow ignores the round's
`<EndConditionOptions Type="Time">` (a 60 s round served from `hoppers/3.xml` ran on
past 2 minutes, no TIME in the HUD). So the server's rounds are endless by default
(`--world-round-minutes 0`); the option is kept for clients with `world_drop_in = false`,
which get phase 1's race-type world where late players wait for the round's end. A round
still ends when the host picks **END FREE ROAM** in the pause menu ("All players will
return to the lobby"): everyone goes back to the lobby, the intermission runs and the
next round loads with everyone (tested; the host asks `GetGameOptions` for it, so the
next round is the server's choice). Players (host or not) can QUIT at any time.

### Session cap: 8

- The world's size is the round's `MaxPlayers` (a byte in the game options, offset 24 of
  the block `sub_8260A4D8` serializes): the game creates its session with that many public
  slots. Served 16, the host created `16 public + 0 private slots` and its lobby opened
  normally.
- Everything the game makes itself is 8: the custom game's MAX PLAYERS option stops at 8,
  the party session has 8 slots, Turn 10's playlist XML says 8, the bucket's `MaxPlayers` 8,
  and the co-op challenges are written for 8 ("8 PLAYERS MUST COMPLETE THE CHALLENGE...").
- Raising it: the session side takes any count (the XML), so the question is whether the
  engine's per-player state holds more than 8: lobby player lists, the replicated cars and
  `CarsPerUniverse` (Tracks, 0 for the festival tracks) are the places to read. Not tried,
  and not testable on this machine with 2 instances; keep 8.

### When the host leaves

- The game migrates by itself: the remaining player keeps driving, now as the host (its
  HUD switches to the host's "SELECT A CO-OP CHALLENGE FROM THE PAUSE MENU"), the list
  drops to 1/1, and the world goes on. It calls no `XSessionMigrateHost`; the guest's
  session object is not touched at all (traced with `FORZA_NETTRACE`). The leaving host's
  client withdraws its session, so nobody advertised the world any more: the next player
  opened a second world and the two players ended up apart.
- Fix (re-placement): every player in a world someone else hosts publishes a **standby**
  record of it (`MATCH_PUBLISH` op 2: the session's info with its own address as the host,
  the playlist and QoS data it joined with; op 3 withdraws it when the game deletes the
  session). The server advertises a session's standby only while nobody hosts that
  session id: once the host left, searchers are placed into the remaining players' world,
  advertised by its oldest remaining member with the number of members as its filled
  slots. Tested: A (host) quit, B kept driving alone; A picked Horizon World again and the
  server placed it into B's world (`first 86f19a2a1352a5db from #1206 'DriverB'`), B's
  game accepted the join as the new host, and both drove together after the round. With
  drop-in A now jumps straight into B's world (test 9).
- Which member the game makes its new host (with more than two players it need not be
  the oldest) is visible in the game: the online game's host flag (`+344`,
  `sub_82865378`) turns on for it. The client watches that flag every second while it
  publishes a standby (`forza::LiveMatchTick`, `OnlineGameIsHost` in
  `world_drop_in.cpp`) and then sends its standby as op 4 ("standby of the game's host";
  op 2 again if the flag goes off); the server advertises an op 4 member before the
  oldest one. Tested with two players: A (host) quit, B's flag turned on within a second
  (`the game made us the host of the session we joined`, server: `DriverB is now the
  game's host of ...`), and A was placed into B's world. Not tested with three players
  (two instances on this machine).
- `XSessionMigrateHost` (0xB001E) is handled anyway (the SDK left the info untouched): the
  new host gets its own address in the info and publishes the session as its own.

### Tests (two instances, private server on UDP 21600 / HTTP 21601)

1. B joins A's world automatically: A picked Horizon World and hosted; B picked it and was
   placed into A's world; both loaded free roam at the festival with DriverA and DriverB
   in the list (`screenshots/2026-10-11_mmo_01_world_A_top_B_bottom.jpg`).
2. A leaves: B stays in the world as its host; A picks Horizon World again and is placed
   into B's world (`..._02_host_A_left_B_hosts_A_placed_back.jpg`, A in B's lobby).
3. Rejoin: after the round, A drives in B's world
   (`..._03_A_rejoined_B_world.jpg`). Earlier, B quit and picked Horizon World again and
   joined A's world (placed into it, then waited for the round).
4. Rounds: a 90 s world round ended into the lobby and the next round
   (`..._04_timed_round_then_lobby.jpg`).
5. Join in progress in a custom free roam: B jumped into A's running custom free roam
   (`..._05_custom_free_roam_jump_in.jpg`).

Drop-in (`world_drop_in.cpp`, server rounds endless):

6. Solo start: A alone picked Horizon World and drove in the world after the 5 s
   intermission, free roam HUD (`..._07_solo_start_free_roam_hud.jpg`).
7. Drop-in: B picked it, was placed into A's world, its lobby showed FREE ROAM IN
   PROGRESS and JUMP IN (`..._08_find_game_world_jump_in.jpg`); B pressed it and drove in
   A's world about 30 s later (`..._06_drop_in_A_top_B_bottom.jpg`).
8. Seen: after A drove up to Race Central, B saw A's car with its tag
   (`..._10_B_host_sees_A_car_after_jump_in.jpg`).
9. Host leaves: A quit; B's game made B the host (op 4 to the server); A picked Horizon
   World, was placed into B's world and jumped in
   (`..._09_host_left_A_jumped_into_B_world.jpg`).
10. END FREE ROAM (host B): both went to the lobby and loaded into the next round together
   after the intermission. A 60 s timed round did not end the free roam (2+ minutes).

## Next phases (designs)

### Phase 2: events from the world, a 30 s wait lobby, AI fill

What phase 1 showed: the world is a playlist whose rounds the server serves. The
**session host** asks for each round's options when it launches (`Hopper.GetGameOptions
(hopperId, roundNum)`, seen from the host only, and from the new host after a migration),
and the round's GameOptions XML carries everything an event needs: `GameTypePreset`
(1 circuit, 2 point to point), `TrackId`, the bucket's `CarRestrictions`, `MaxAIPlayers`,
`AIDifficulty`, laps. Since drop-in, a world round is an endless online free roam (race
type 18): it ends only through the host's END FREE ROAM, which brings everyone back to the
lobby, and the lobby launches the next round after the intermission. The drop-in hooks
apply to free-roam rounds (preset 7) only, so a race round served on the world's playlist
runs as Find Game's race (type 6): late players wait in the lobby for it to end instead of
dropping into a running race, which is what a race wants.

- **Event flow:** an event is a round. The world's rotation becomes world round, event,
  world round, ...; the event is picked from the game database (`Events` with its
  `EventRestrictions` -> the bucket's `CarRestrictions`, the event's track and laps). Every
  player picks a car from their own garage in the lobby (the lobby already has SELECT CAR
  and LOAD CAR SETUP, filtered by the bucket's restrictions), so "join with your own cars
  under the event's conditions" is the lobby as it is. Everyone in the world session goes
  to the event (one session of up to 8); a player who wants none quits and picks Horizon
  World again, which places it into another world or opens one.
- **Starting an event from the world:** a non-host cannot start anything in online free
  roam (the host starts co-op challenges from the pause menu), and timed rounds no longer
  end the world. The way out is the host's END FREE ROAM: a client hook on the world's
  host that takes that path when the server asks (an event requested by a player: a
  festival event marker reached in the world, or a pause-menu entry, sent to the server),
  then the server answers the next `GetGameOptions` with the event. The END FREE ROAM
  action is still to trace (pause menu item, then its confirm; the free roam's
  `CUnloadToPreGame destination="race_lobby"`).
- **30 s wait lobby:** the event round's intermission. The intermission comes from the
  playlist's search settings, which the game copies when the playlist is picked (`+2020`,
  `+2024` of the online game: 5000 ms for the world, which its solo start should keep), so
  a 30 s event wait needs those two set to 30000 before the event round launches (a client
  hook, or a separate event playlist). The lobby shows INTERMISSION with a countdown;
  players who join the session during it are on the grid. A grid full of humans starting
  early would need `minPlayersToLaunch` = max players plus a check on the intermission's
  end; not seen yet. After the event, END of the race brings everyone back to the lobby
  and the server serves the world (free roam) again.
- **AI fill:** the host asks for the round's options at launch, after the intermission, so
  the human count is final then: the server reads the host's published session (filled
  public slots), sets `MaxAIPlayers` = 8 - humans and `AIDifficulty` from the human share:
  at most 1/3 humans Easy, about 1/2 Medium, 2/3 or more Hard (8-car grid: 1-2 humans
  easy, 3-5 medium, 6-8 hard). The game maps `AIDifficulty` through `MPAIDifficultyMap`
  (`AISkill`, `AITemperament`). To verify first: that a playlist round with `MaxAIPlayers`
  > 0 spawns AI cars online (the field is read by `sub_8260A4D8`; Turn 10's own XML sets
  `MaxAIPlayers="0"`), and that the host simulates them for everyone.

### Phase 3: head-to-head challenges

- Trigger: the client watches the X button in free roam (`input_autopress.cpp` already
  sees the pad) and the distance to the other players' cars (their positions are in the
  replicated car state; to find in memory). Pressed within a few car lengths behind
  another player: a `CHALLENGE` message to the server (like `INVITE`: target XUID, our
  position), delivered to that player's client.
- Accept or reject: a prompt in the challenged player's game. The game has the pieces:
  the Rivals challenge alert (`IDS_RivalsAlerts_Challenge_MsgTitle/MsgBody/HudPopup`) and
  the XAM message box (`XamShowMessageBoxUI`; what the SDK shows for it is to check). A timeout (10 s)
  or a reject goes back to the challenger as a HUD message.
- The race: the game's free-roam challenges include point-to-point ones
  (`DriveFromAToBFreeRoamChallenge` in `FreeRoamChallenges.xml`: start and end
  coordinates with radii), run inside online free roam without leaving the world, but
  started by the host and for everyone. A head-to-head would generate such an A-to-B
  route from the two cars' position (end point a few km along the road network) and run
  it for the two players only; or, simpler and closer to the existing code, move the two
  into a 2-player point-to-point round (a playlist of their own on the server, track
  from the closest `Tracks` route) and back into the world afterwards.
- Single-player head-to-heads to trace for this: `StreetRace`, `CStreetRaceHubState`, the
  road-driver challenges (proximity check, button prompt), `IDS_NoChallengeHost` /
  `IDS_NoChallengeClient` (online free roam's host-only challenges).

## Backlog: player-to-player head-to-head challenges

After the game runs smoothly without crashes and the shared-world server puts everyone
in the same world (not before):

- In single player, Forza Horizon lets you drive up behind certain road drivers and
  press a button to challenge them to a quick race along a route. Online, the same
  should work between players.
- In the shared world, a player drives up behind another player's car and presses X:
  that sends a challenge request. It is not instant: the challenged player gets a prompt
  and can accept or reject, with a timeout when there is no answer.
- If accepted, a route is set up from where they are, like the single-player
  head-to-head, and the race starts for both. A reject or a timeout is reported back to
  the challenger.

To note while reversing: how the single-player head-to-head is triggered (the
proximity/behind check, the button prompt), how its route is generated or picked,
whether the original online free roam had any player-vs-player challenge, and which UI
prompts (accept/reject dialogs) the game already has that could be reused.

Found so far (strings in `default.xex`, not yet traced to code): street races
(`StreetRace`, `CStreetRaceHubState`, `streetracehub1..3_unlock`), the Rivals system
(`CShowBeatRival`, `CWaitForBeatRival`, `CIsCorrectRivalData`, `RivalsBeaten`,
`IDS_RivalsAlerts_Challenge_MsgTitle/MsgBody/ListEntry/HudPopup`: a challenge arriving as
an alert with a message, a list entry and a HUD popup, a reusable pattern), free-roam
challenges (`CFreeRoamChallengeState`, `IDS_ChallengeAvailable`, `IDS_EndChallenge`,
`IDS_SetHighlightedChallenge`) and, for online free roam, `IDS_NoChallengeHost` /
`IDS_NoChallengeClient`: the original online free roam had host-started challenges.

## Likely building blocks

1. A self-hosted server that emulates Xbox LIVE sessions and presence plus Turn 10's
   services. RecompiledHaloReach's Reach Live (`server/`, `src/kernel/live_xmsg.cpp`,
   `src/kernel/net.cpp`) is the template: a virtual network with UDP hole punching and a
   relay, XSession*/presence/QoS answered from the server.
2. The server places players into persistent free-roam sessions automatically. Needs the
   engine's per-session player cap and what sizes it.
3. Campaign event definitions loaded by the online race mode.
4. Host-simulated AI drivers replicated to clients as remote cars.
5. AI difficulty set per race from the human share.

## What to look for (and what was found)

Open questions, to fill in as the reverse engineering finds them:

- Netcode entry points: XSession*/XNet*/QoS usage, the packet layer.
- The max-players constants and arrays (Forza Horizon's online free roam holds 8
  players; the session size is the round's `MaxPlayers`, see "Session cap" above).
- How online races are set up (playlists, event selection, grid building).
- Where the single-player AI difficulty ("Drivatar" difficulty setting) is stored and
  applied.
- How race grids are built and how many AI cars a grid can take.
- The game's online pre-race lobby: its countdown, who may still join, and when the
  grid is frozen.

### Findings so far

- XAM/Live imports the game uses (Xenia's import listing of `default.xex`): the XMsg
  family (`XMsgInProcessCall`, `XMsgStartIORequest[Ex]`, `XMsgSystemProcessCall`,
  `XMsgCompleteIORequest`, `XMsgCancelIORequest`), which carries the XSession*/XUser*/
  presence/friends calls as XAM app messages (XGI 0xFB, XLiveBase 0xFC), as in Reach.
  `XNetLogonGetTitleID`, `NetDll_XNetGetTitleXnAddr` are imported too.
- The game polls `XamXStudioRequest(0x1003, &out)` every 30 ms from code around
  `0x82AD3810` (callers `0x82AD3830` ... `0x82AEDA3C`); with Kinect (NUI) imports
  around it, it looks Kinect-related rather than online.
- Single-player festival races have an 8-car grid (a 4-lap circuit race: the player
  and 7 named AI drivers). Event tickets carry the restrictions (e.g. "R2, made 2000
  or later") and the rewards (points, credits). Before the start the pre-race menu
  offers START RACE / DIFFICULTY / OPTIONS / QUIT RACE: the AI difficulty is chosen
  per race there, a natural place to set it from the human share.
- The multiplayer game types are data-driven presets, and they already know about AI
  opponents. Field names next to each other in `.rdata` (`0x8202C2A0`..`0x8202C900`):
  `CarRestrictions`, `MaxPlayers`, `MinPlayers`, `CanStartEndOfRaceCountdown`,
  `ScoringMethod`, `NumPlayers`, `NumPlayerBuckets`, `CollisionMode`,
  `DamageDifficulty`, `UseTraffic`, `GameTypePreset`, `StartingGridOptions`,
  `FieldWindowOptions`, `EndConditionOptions`, `MaxRecommendedCarClass`,
  `MinRecommendedCarClass`, `DraftingEnabled`, `AIDifficulty`, `AIFieldId`,
  `MaxAIPlayers`. Code reading them: `sub_82605F80` and `sub_82606318` (`MaxPlayers`,
  `NumPlayers`), `sub_8260A4D8` (`MaxPlayers`, `AIDifficulty`). `MaxAIPlayers` and
  `AIFieldId` suggest the engine can already fill an online grid with AI; the vision's
  "fill free slots with AI" may only need the preset values changed.
- AI difficulty data lives in the game database (SQL queries in `.rdata`):
  `SELECT * FROM MPAIDifficultyMap` (with `AISkill`, `AITemperament`; loaded in
  `sub_825704D8`), `SELECT SkillModifier,AggroModifier, RubberBandModifier FROM
  AIPlayers WHERE Id=%u`, per-event columns `AISkill%s`/`AITemperament%s`/
  `AIRubberband%s` (`SELECT %s,%s,%s FROM Events WHERE Id = %u`), and
  `SELECT * FROM EventRestrictions WHERE EventId=%d` for the event conditions. The
  single-player levels are Easy/Medium/Hard/Pro (`IDS_AIDifficulty_*`) with
  `EasyDifficultyUpperBound`..`ProDifficultyUpperBound` and `DynamicDifficulty`
  (`sub_82521200`). An MPAIDifficultyMap row picked from the human share is the
  obvious hook for the 1/3, 1/2, 2/3 rule.
- Free roam online: strings `onlinefreeroam`, `SET_MODE_FREEROAM` (`sub_825E0C60`),
  `CIsFreeRoamSessionOver` (`sub_825B3968`), and the message "... player's console as
  the session is full." `SELECT CarsPerUniverse FROM Tracks WHERE Id='%d'` may bound
  the number of cars per world.
- XAM app 0xFE message `0x2B003` is sent once when the single-player game starts
  (Xenia answers success, "Games used in: 4D5309C9").
