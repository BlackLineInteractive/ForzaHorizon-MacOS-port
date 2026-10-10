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
- XAM app 0xFE message `0x2B003` is sent once when the single-player game starts
  (Xenia answers success, "Games used in: 4D5309C9").
