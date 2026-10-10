# Online vision: a shared Horizon world

The long-term goal for online play (not being implemented yet; bring-up comes first).
Notes from reverse engineering that matter for it are collected below as they turn up.

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
  players).
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
