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
else: the server either places you into an open world or you open a new one, and the
next players are placed with you.

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
- The first player in an empty world waits in its lobby ("WAITING FOR PLAYERS TO JOIN...")
  until a second one arrives: the lobby launches with two players, and the search
  settings' `minPlayersToLaunch` 1 does not change that. To find in the lobby code if a
  lone player should drive at once.
- The server logs every decision (`match #id 'name' playlist 3: 1 open session(s), first
  <session> from #host (1/8)` or `no open session, it hosts`), and its status page lists
  each player's published session (`match`: playlist, players, slots).

### Players joining a world in progress: rounds

Find Game's lobby never lets a player into a free roam already running: the joiner sits in
the world's lobby with "GAME IN PROGRESS / WAITING FOR PLAYERS TO FINISH GAME" and is taken
along when the round ends (the host's Retire ended it in the first tests; both then loaded
into the next round). So the world's rounds end on a timer: the server serves the world
round with `<EndConditionOptions Type="Time" Time="600">` (seconds;
`--world-round-minutes`, default 10, 0 = endless). Then everyone, the waiting players
included, goes back to the lobby and loads into the next round after the intermission (5 s
in the world). Measured with a 90 s round: a TIME countdown in the HUD, then the lobby
("FREE ROAM 01:30 MINS", "INTERMISSION"), then the next round by itself.

The game can do real join in progress, but only in a custom game's free roam: Find Custom
Game, the FREE ROAM tab, the host's world: its lobby says "FREE ROAM IN PROGRESS" and
offers **JUMP IN**, and the joiner drives into the running world without anyone reloading
(tested). The lobby's text and its join path look at a mode value of the online game
(`*(*(0x83305CC4) + 40)`, getter `sub_82D6AE20`; `sub_82865340` is "mode is 8, 9 or 10";
the code at `0x8281B358` picks the label): a custom free roam runs as mode 9, Find Game's free roam
as mode 7, which is the race-like flow (the HUD's TIME, RACE and LAP timers and PLACE
1/2, a round that ends). Making Find Game's world run as mode 9 (where the mode is chosen at
launch) would give the world join in progress and remove the rounds; that is the next
step for phase 1. Until then Find Custom Game's Free Roam tab is the way into a running
world without waiting, and the server lists the fullest open world first there too.

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
  game accepted the join as the new host, and both drove together after the round.
- With more than two players the game picks the new host itself; if it is not the oldest
  remaining member, a searcher connects to a guest. The server cannot see the game's
  choice; a fix would read it from the game (who answers the joins) or let the guest
  refuse and fall back to the next session.
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

## Next phases (designs)

### Phase 2: events from the world, a 30 s wait lobby, AI fill

What phase 1 showed: the world is a playlist whose rounds the server serves. The
**session host** asks for each round's options when it launches (`Hopper.GetGameOptions
(hopperId, roundNum)`, seen from the host only, and from the new host after a migration),
and the round's GameOptions XML carries everything an event needs: `GameTypePreset`
(1 circuit, 2 point to point), `TrackId`, the bucket's `CarRestrictions`, `MaxAIPlayers`,
`AIDifficulty`, laps.

- **Event flow:** an event is a round. The world's rotation becomes world round, event,
  world round, ...; the event is picked from the game database (`Events` with its
  `EventRestrictions` -> the bucket's `CarRestrictions`, the event's track and laps). Every
  player picks a car from their own garage in the lobby (the lobby already has SELECT CAR
  and LOAD CAR SETUP, filtered by the bucket's restrictions), so "join with your own cars
  under the event's conditions" is the lobby as it is. Players who want no event stay
  out by leaving to a world-only playlist.
- **Starting an event from the world:** the game has no way for a non-host to start
  anything in online free roam (the host starts co-op challenges from the pause menu).
  Simplest: the next timed round is an event, announced in the world. Better: a request
  from the player (a festival event marker reached in the world, or a pause-menu entry)
  sent to the server, which ends the world round early (needs a client hook on the host
  that ends the round, the same path as Retire) and serves the event as the next round.
- **30 s wait lobby:** the playlist's intermission is it: `intermissionTimeMs` 30000 in the
  hopper and the search settings. The lobby shows INTERMISSION with a countdown; players
  who join the session during it are on the grid (they come in through the same
  matchmaking). A grid full of humans starting early would need `minPlayersToLaunch` =
  max players plus a check on the intermission's end; not seen yet.
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
