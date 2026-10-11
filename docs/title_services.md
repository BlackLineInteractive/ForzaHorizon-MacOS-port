# Turn 10's title services (Forza Horizon's "LSP")

Forza Horizon talks to Turn 10's servers for its Horizon sign-in, the Find Game playlists
("hoppers"), online XP, scoreboards, the storefront and more. The Forza Live server
answers the calls online play needs (`server/forza_live_lsp.py`, the protocol in
`server/forza_xtsw.py`). Everything below was read from the base `default.xex` (addresses
are guest addresses) and checked against the game's requests and its reaction to our
answers.

## Finding the title server

- The game enumerates title servers every 30 s (XAM enumerator app 0xFC, open message
  0x58039, `XTitleServerCreateEnumerator`; items `X_TITLE_SERVER {inaServer, flags,
  szServerInfo[200]}`; `live_lsp.cpp` answers it).
- It keeps a server whose description matches its service mask: `sub_83155238` calls
  `Matches(mask, description)` (`sub_83153D48`; `*` and `?`, case-insensitive) with the
  LspProvider config's `defaultMask` `Turn10.*` as the pattern. Our description is
  `Turn10.Horizon` (`FORZA_LSP_SERVICES` overrides it; `*` does not match the mask, which
  gives the "Horizon server is currently unavailable" path).
- It connects to the server's address on TCP port 80 (`net.cpp` sends it to the Forza
  Live server's HTTP port) and posts to `/Services.Horizon/o.xtsw` (the LspProvider
  config; `/Services.HorizonDemo/o.xtsw` for the demo, `/Services/o.xtsw` the default).

## Transport

Request (`sub_83152710`, templates at `0x822DC8D0` and `0x822DC990`):

```
POST /Services.Horizon/o.xtsw HTTP/1.1
Host: <server>
Content-Type: bin/xtsw
Content-Length: <n>
User-Agent: Xls Client
Connection: Keep-Alive
X-TitleId: 1297287625                                   (0x4D5309C9)
X-ClassName: Forza.WebServices.Hopper, Forza.WebServices
X-Method: GetList
X-UserId: 0x9a7b6b0a63bf2                               (the caller's XUID)
X-TransactionId: <GUID as hex>                          (transactional calls only)

<parameters>
```

The call itself is `sub_82AABAC0(client, class, method, params, results member list,
&results, ...)`; each service method has a small stub that passes its class and method
names (`Logon2` calls it at `0x82ABC0A8` with class string `0x820E242C`, method
`0x820E24A4` and results member list `0x83316F18`).

Reply: the HTTP parser (`sub_831515A8`, a byte-at-a-time state machine) reads the status
line, the headers (only `Content-Length` matters) and the body. The body
(`sub_82AA9868`, header read by `sub_82AA96F0`):

| Offset | Field | |
| --- | --- | --- |
| 0 | u32 status | 0 = success; 2 = failure, the call returns `0x80510000 \| code`; anything else `0x8050000E` |
| 4 | u32 code | |
| 8 | u32 message length | a UTF-8 message follows when status != 0 (the client logs it) |
| 12 | results | decoded by `sub_82A95910(results, member list, reader)` |

Bytes after the results are ignored, so a reply of the header and enough zero bytes reads
as empty results (zero, false, empty strings and lists) for any method; the server answers
methods it doesn't handle that way. Calls made with a "compressed" flag (none of those
seen) would carry an XMemCompress block instead (`sub_82AAD798`). A failed `GetGameOptions`
ends Find Game with "You have been disconnected from the session"; most other failures are
retried (`DLCMetadata.GetStringTableInfo` every 100 ms).

## Encoding

Parameters and results are records described by type descriptors in `.rdata`, 9 words
each: `{kind, name, offset, -, count offset, size, member list, element type, flags}`
(`0x7FFFFFFF` = none). A member list is `{first descriptor, count}` in `.data`, filled by
static initializers at startup (`lis/addi` of the first field, `li` count, `b 0x82A93090`;
the Logon2 ones at `0x831AE340`). Kinds and their wire form (big-endian, packed, fields in
declaration order):

| Kind | Type | Wire |
| --- | --- | --- |
| 0 | u8 | 1 byte |
| 1, 2 | u16, i16 | 2 bytes |
| 3, 4 | i32, u32 | 4 bytes |
| 5, 6 | i64, u64 | 8 bytes |
| 7 | float | 4 bytes |
| 8 | WCHAR string (fixed buffer) | u32 length + that many bytes (UTF-8; `DriverA` is 7) |
| 9 | struct | its fields |
| 10 | array (inline, or a pointer with count/capacity fields for results) | u32 count + elements |
| 11 | SYSTEMTIME | ISO 8601 text like a string: u32 length + `2026-10-11T15:25:00Z` (the reader, `sub_82A954D8`, parses `%4hd-%2hd-%2hd`, `T`, `%2hd:%2hd:%2hd`, an optional `.ms` and `Z` or `+hh:mm`; anything else, the empty string too, fails the whole reply with `0x8050005C`) |
| 12 | bool | 1 byte |
| 13 | GUID | 16 bytes |
| 15 | byte array | u32 length + bytes |
| 16, 17, 18 | XNKID (18) and two other fixed blobs | u32 length (must be 36, 16, 8), then the bytes |

Flags: 0 = a parameter passed by value, 3 = by pointer; 1 = a result, 5 = a result in a
caller buffer (an array whose capacity comes from a `max...` parameter). A method's
parameters are `Forza<Class><Method>_Params` and its results `..._Results` (some methods
have no results: the reply is the 12-byte header). The type names, field names and
layouts of all 292 service records can be dumped from a running game: read the
descriptors (they start at the record's name string's reference, `kind 9`) and member
lists from `/proc/PID/mem` (guest address X is host `0x100000000 + X`). The 111-byte
`Logon2` request decodes to exactly its length with this table, and `UpdateAll` (325 bytes)
too.

## Services

Classes: `Forza.WebServices.{User, Hopper, OnlineProfile, DLCMetadata, Scoreboard,
Storefront*, Auction, Gifting, Gift*, SharedCar, CarClub, DLC, DailyCreditBonus,
GameplayLog, Notifications, LargeFileUpload}` and `Xls.WebServices.{User, Clan, Content,
Notifications, Transaction}`. What the game calls, in order:

| When | Call | Our answer |
| --- | --- | --- |
| Sign-in (about 50 s after boot) | `User.Logon2(loginData)` | `responseData`: profile valid, a permission table allowing every feature (below), `userData` (XUID, gamertag, **currentXPTotal = the player's online XP**), timeouts |
| | `OnlineProfile.UpdateAllTables`, `UpdateAll` | success; `UpdateAll`'s `playerRaceHistory` (level, XP, **onlineXP**, online races and wins) and `playerHistory` (credits) are kept per player |
| | `DLCMetadata.GetStringTableInfo("EN")`, `Xls Content.DownloadContent(0, 0, 0x40000)` x2 | empty |
| Party lobby | `Hopper.GetList(maxCategoryResults 2, maxHopperResults 32)` | the playlists (below) |
| Find Game, picking a playlist | `Hopper.GetSearchSettings(hopperId)`, `GetGameOptions(hopperId, roundNum, 0x8000)`, then (after the session search) `UserRegister(hopperId, sessionId)` every `nextRegisterSeconds` | search settings, the round's GameOptions XML, 60 s |
| Race start | `GameplayLog.Write`, `Hopper.GetRaceMultipliers` | empty, multiplier 1.0 |
| Race end | `Scoreboard.SubmitScoreEx` / `SubmitScore`, `User.SetPlayercardInfo`, `OnlineProfile.UpdateAllTables` / `UpdateAll` | the score kept (scoreboards below) / success (profile kept) |
| End of a Rivals race (also retiring) | `User.WriteRaceStatsEx(id, raceStats, scoreData)` | kept per player (`userXP`, credits, the race) |
| Message Center (online free roam, after races) | `Xls Notifications.StartNewSession`, then `RetrieveForUser` every `nextRetrieveSeconds` | nonce 1, 60 s (with 0 the game polled 7 times a second) |
| Sometimes | `Xls User.SetFriends` | empty |

The game keeps one HTTP connection to the title server for all its calls. The server must
leave it open while idle: when it closed idle connections after 15 s, the game's next call
minutes later (Rivals from the single-player free roam) was never sent and failed as
"The Forza Horizon server is not available", until the game found its title server again
(about 12 minutes later in one test). `forza_live_server.py` now waits 6 hours.

### Permissions (features)

Before an online feature the game looks it up in the permission table that `Logon2`
(and `GetPermissionsTable`) returned: `sub_8264D570(feature)` -> `sub_82CE97B8` ->
`sub_82AAEE98` finds the entry whose `MethodId` is the feature id (Rivals is 61; others
used: 20, 21, 22, 28, 45, 66, 84, 123) and returns its `Access` as the error code (0 =
allowed). A feature missing from the table is error 4: the popup "FEATURE UNAVAILABLE.
The Forza Horizon server is not available at this time" without any request reaching the
server. The table is up to 256 entries `{MethodId, Tier, IsEnabled, Access}`; the server
sends ids 0-255, all enabled with `Access` 0.

### Playlists (hoppers)

`GetList` returns `hopperCategories[] {name, description, hopperStartIndex}` and
`hoppers[] {id, name, description, playerCount, allowVoteToSkip, allowVoteToKick,
allowVoteToRebalance, payoutModifier, hideTrueSkill, maxPartySize, icon,
minAllowedRaces, maxAllowedRaces, maxAllowedWins, shouldVoteCarClassBeforeLaunch,
randomizedOrder, intermissionTimeMs}`. A category holds the hoppers from its
`hopperStartIndex` to the next category's. The Find Game screen ("Playlists", built by
`sub_82730500`) lists the first category's hoppers that every party member may join
(`sub_82888988` -> `sub_828864D0`): with `-1` meaning no limit, races < `maxAllowedRaces`,
wins < `maxAllowedWins` and races >= `minAllowedRaces` (beginner playlists). Our hoppers:
3 "Horizon World", 1 "Races" and 2 "Playground Games", all in the one category Online
(a second category's hoppers would not be listed). Horizon World is
the shared free-roam world (`docs/online_vision.md`): preset 7 rounds from the festival
(track 1101), `GameTypeFilterType="FreeRoam"`, endless (`EndConditionOptions Type="None"`;
the client runs them as an online free roam that players JUMP IN to, which has no timed
end anyway; `--world-round-minutes` serves `Type="Time" Time=` seconds for clients with
`world_drop_in` off), its own search settings (`minPlayersToLaunch` 1, intermission 5 s, 2
connect attempts); `GetSearchSettings` is answered per hopper. The game copies a
playlist's search settings into its online game object when the playlist is picked
(`+2016` min players to launch, `+2020`/`+2024` the intermission times).

`GetGameOptions` returns `gameOptionsXml`: the round's options in the format of the game's
own `media/gametunablesettings.zip` `DefaultRacesHopperOptions.xml` and
`DefaultPlaygroundHopperOptions.xml` (used for the "Quick Match" playlist when the server
is unavailable; they are compressed with zip method 21, XMemCompress LZX with a 128 KB
window: a block is `FF, u16 uncompressed size, u16 compressed size, data`, which
libmspack's `lzxd` with window bits 17 decodes). The root is `<GameOptions>` with
`GameTypePreset` (`GameOptionPresets.xml`: 1 circuit race, 2 point-to-point, 4
Infected, 5 Cat & Mouse, 6 King, 7 free roam, 198 street race), `TrackId`
(the game database's `Tracks`), `MaxPlayers`, `MaxAIPlayers`, `UseTraffic`,
`CollisionMode`, time of day and car class attributes, and children `Buckets/Bucket` (with
`CarRestrictions`), `StartingGridOptions StartType="OpenWorld"`, `EndConditionOptions
Type="NumLaps" NumLaps=".."` and `ScoringOptions`. The server's rounds for hopper 1 are the
game database's `HopperRaces` table (preset, track, laps: (1, 322, 3), (2, 155, 1), (1, 107,
3), (2, 145, 1)), picked by `roundNum`; `DATA_DIR/hoppers/<id>.xml` replaces them. The
Playground Games playlist (2) serves the game's own Infected (4, arena track 215), Cat &
Mouse (5, track 322, 2 laps) and King (6, track 215, 180 s) presets in turn
(`server/playground_rounds.xml`, copied from `GameOptionPresets.xml` with their buckets,
tag and scoring options; the game's own playground hopper default is a free roam);
`--playground-games 6,4` picks and orders them.

Tested with two consoles (fresh online profiles; both picked PLAYGROUND GAMES in Find
Game, A hosted, B joined, the game started 40 s later): **Infected** in the arena (A
"You're INFECTED, crash into the survivors!", B "You're a SURVIVOR...", both in rental Ford
GTs), ended after its 300 s with B 1st (survived) and A 2nd: `WriteRaceStats` for both
(hopper 2, place 1/2 and 2/2), `SubmitScore(type 4, 1100)` each (the online XP earned,
board -1) and `UpdateAll` with online XP 1100; then the lobby "PLAYGROUND GAMES - KING"
(Addison West Steelworks, Playground Arena, off road, 03:00 mins, both in rental Nissan
GT-R R34s, INTERMISSION counting down) and **King** at night (B "You're the KING, run away
from all the other players!", A "Crash into the KING to steal their golden Gamertag!")
(`screenshots/2026-10-11_playground_0*.jpg`). King ended after its 3 minutes with B 1st (1500
XP) and A 2nd (880 XP), online XP 2600 and 1980 (wristband 2), and the lobby went on to the
next round (Infected again). With rental cars forced
(`ForceOnlyRentalCars`) the lobby shows no car class vote. **Cat & Mouse** (an earlier
run) loaded on both (A the mouse in a red Fiat 500 "race to the finish line! PROGRESS:
0/2 LAPS", B a cat) but it only ends when the mouse finishes 2 laps, so nobody driving
never ended it.

`GetSearchSettings` returns the session filter (`numStartingMatchmakingQueryResults`,
QoS limits, ranking factors) and `maxConnectAttemptsBeforeCreating`,
`maxConnectSecondsBeforeCreating`, `maxWaitingForClientsToConnectSeconds`,
`minPlayersToLaunch` (2), intermission times.

### Matchmaking

Find Game searches with `XSessionSearchEx` (XGI message 0xB001C, procedure 4, up to 25
results) for property `0x10000030` = the hopper id (Find Custom Game: procedure 5, the game
type tab's value, free roam 8, which public custom games set on their host), properties `0x30008105` and
`0x30008106` (doubles, 3.0 and 1.0) and contexts `X_CONTEXT_GAME_TYPE` (0x800A) = 1 and
`X_CONTEXT_GAME_MODE` (0x800B) = 0. With no result it hosts a matchmaking session itself
(`XSessionCreate`, flags 0x2D) and registers it with `Hopper.UserRegister`; a later searcher
finds it and joins. `live_xmsg.cpp` answers `XSessionSearchEx` like `XSessionSearch` from
the sessions the room's players host for that property's value (published on the Forza
Live server), those with a free slot only, the fullest first. The **session host** calls
`GetGameOptions` for the **next** round when a round starts (the answer is the round the
lobby shows after this one; a vote to skip asks again). In the Horizon World the server
answers it with a festival event when one was requested for that world
(`server/forza_world.py`, `docs/online_vision.md` phase 2).

### XP and credits

The game computes the rewards itself at the end of an online race ("XP REWARDS": finished
1st 1,000 XP, mileage bonus 200 XP, x1 for a 2-player game, x1.1 skills = 1,320 XP; 2nd
800 XP), with the server's race multiplier (`GetRaceMultipliers`). Credits go to the local
save. Online XP does not: the game takes it from `Logon2`'s `userData.currentXPTotal` at
every sign-in (a restart with 0 there showed online XP 0 and the wristband level reset,
credits kept), so the server keeps it: from each `UpdateAll` (`onlineXP`, only growing)
into `DATA_DIR/players/<XUID>.json`, back in the next `Logon2`. Without the title server
the game offers only the default "Quick Match" playlist, which awards no multiplayer XP.

### Scoreboards, leaderboards and Rivals (`server/forza_scores.py`)

The method stubs (`Forza.WebServices.Scoreboard`, all calling `sub_82A92018`) and their
callers:

| Method | Stub | Called from |
| --- | --- | --- |
| `SubmitScore(type, data)` / `SubmitScoreEx(type 3, {data, numCarsPassed})` | `82AB9570` / `82AB95E0` | the scoreboard manager `0x82897xxx` (race end), `0x828DF464` |
| `UploadFile(scoreId, data)` | `82AB9650` | `0x82897918`, after a submission answered `uploadFiles` |
| `DownloadFile(id, maxSize 256000)` | `82AB90D0` | `0x82897A1C` (a rival's ghost, by `ghostFileId`) |
| `GetBestScores(scoreType, board, isServerTimeTrial, car, class, drive type)` | `82AB9140` | `0x828976FC`; seen at the start of a Rivals race |
| `GetRivalAndPersonalBest(board, isServerTimeTrial, rivalXuid)` | `82AB9228` | `sub_8290CD58` ("RivalData: Rival Net Task"): X RIVALS on an event's ticket |
| `GetRival(board, isServerTimeTrial, rivalXuid)` | `82AB91B8` | `sub_827D09F0` |
| `GetRows(type, view, board, isServerTimeTrial, isClubBoard, startAt, maxResults)` | `82AB9330` | the leaderboard screen's fetch `sub_82826E88` (50 rows from `startAt`), `0x828C7F1C` (view 5, 200 rows) |
| `GetRollupRows(type, view, pivotId, eventTypeId, isClubBoard, startAt, max)` | `82AB9298` | `sub_82826E88` |
| `GetStorefrontRows`, `GetTimeTrials(7, 150)`, `NotifyRival` | `82AB93D0`, `82AB9460`, `82AB94E0` | `sub_82826E88`; the Rivals menu `0x827AD614`; `0x82897E38`, `0x828DE9F4` |

A row is `{position, rank, user (UserData), score, submittedTime, carId, carClassId,
carPerformanceIndex, 6 assist flags, ghostFileId (-1 none), clanData, bounty}`.

The server keeps each player's best score per scoreboard (`gameScoreboardId` and
`isServerTimeTrial`; online races submit board -1, not kept) in
`DATA_DIR/scoreboards.json`. Lower is better except for score types in
`BIGGER_IS_BETTER` (4, seen with XP-like values after an online race). A new best is
answered with a fresh `scoreId` and `uploadFiles` true; the ghost the game then uploads
is kept as it is in `DATA_DIR/ghosts/<id>.bin` (the row's `ghostFileId`) and served by
`DownloadFile`. Views: 0 the top from `startAt`, 1 around the caller, others (friends are
everyone here) like 0; `userRow` is the caller's row (position 0 when they have none).
Rollups rank players by the boards they lead. The rival is the one asked for, or (rival
0) the score just better than the caller's (without a score of their own, the slowest
other player); the bounty is 1000 (the game showed 5,000 Cr).

Seen in the game (single player, a copy of a career save, event "GoPro Millennia
Masters", board 199): X RIVALS on the event's ticket calls `GetRivalAndPersonalBest(199)`.
With no rival the game says "There was an error communicating with the Turn 10 server";
with a rival (another player's submitted score, 235 s) it shows YOUR RIVAL, the rival's
gamertag, TARGET 03:55.000 and BOUNTY 5,000 Cr; A goes to car select, the Rivals race
starts (`GetBestScores(3, 199, car, class)` first) with the target on the HUD. Retiring
calls `WriteRaceStatsEx` (finished, place 2 of 2) and shows "FINISHED - YOU LOST".

A real race (`tools/autodrive.py` drove the car along the CPU drivers' line: the 4 laps
of Millennia Masters in the Aventador, 8th of 8): at the finish the game sent
`SubmitScoreEx(type 3, board 199, score 115.13)`: the score is the **best lap** time
(1:55.13), with the car (1398, class 7, PI 0.864), assists, parts and tuning. The server
answered `uploadFiles`, and the game uploaded its ghost of that lap at once
(`UploadFile`, 17,332 bytes: a 16-byte header `000002A0 0000410C 00000298 00000ABC`, then
compressed data), kept as ghost 2; then `WriteRaceStatsEx` (place 8 of 8) and
`GetRivalAndPersonalBest(199)` for the results screen's offer "NEW RIVAL vs <rival>,
TARGET, BOUNTY 5,000Cr: Do you want to race your Rival? NO THANKS / BRING IT". The rival
of a Rivals race is the one fetched when it started (RESTART keeps it).

Race Central (at the festival; the map's X fast-travels there) has LEADERBOARDS: Festival
Events (VIEW OVERALL and the seven wristbands' event lists), Street Races, Showcase
Events and Online XP. VIEW OVERALL is `GetRollupRows(type 0, view, pivot -1, eventTypeId
1)`; an event is `GetRows(type 3, view, board = the event's Id)`; X changes the filter:
view 2 Friends Only, 3 Favorites, 1 Near Me, 0 Global. Seen with the seeded score: the
event's board showed "1 Seeded Rival, S 686 Gallardo LP570, 03:55.000" with ABS/TCS/gear
columns and "YOU'RE NOT ON THE LEADERBOARD"; the overall board showed the rollup score as
a time. A on a row offers SHOW GAMER CARD and ADD AS FAVORITE (`Storefront.
AddFavoriteUser`, `GetStorefrontFavorites`; empty answers). Race Central's RIVALS has
Monthly Rivals (`GetTimeTrials(7, 150)`: the server's time trials, none yet) and the
career events' Rivals.

### The Auction House and car gifts (`server/forza_market.py`)

The server side is complete and unit-tested (`Auction.*`: GetGlobalConfig, Create,
UploadAuctionTextures, SearchForAuction, GetAuctions, GetDetails, GetMyAuctions,
GetMyBids, PlaceBid, RetrieveCarForAuction, RetrievePaymentForAuctionSold,
RetrievePaymentsForAuctionLost, Cancel, Restart, RemoveMyBannedAuction, ReportContent;
`Gifting.SendCarGift`, `RetrieveCarGift`, `RetrieveCreditsGift`), with the records in
`DATA_DIR/auctions.json`, `gifts.json` and the car blobs in `DATA_DIR/market/`. The
model follows the game's own tables:

- Status per viewer (the labels in `sub_827DC788`, which reads the status at +0x68 of
  its auction item = the wire record + 8): 0 active, 1 expired, 2 SOLD, 3 expired
  (cancelled), 4 active and you are the top bidder, 5 WON, 6 OUTBID, 7 LOST; the buyout
  price shows for 0, 4 and 6.
- `allowedActions` bits (the action table at `0x8323E528`, 0x28-byte entries: label,
  confirm, success title and text string ids, the bit, 1 = bidder / 2 = seller action):
  0x1 Bid, 0x2 Buyout, 0x4 ResolveWon (collect the car), 0x8 ResolveFailedAuction (the car
  back), 0x10 Restart, 0x20 Cancel, 0x40 Report, 0x80 RemoveBannedItem, 0x100 ReceiveMoney
  (an outbid bid back), 0x200 ReceiveMoney (the sale); search a player's auctions, view
  their storefront and gamercard have no bit.
- Money: the game takes a bid from its own credits; PlaceBid's `amountRefunded` gives back
  the bidder's earlier bid on the same auction; an outbid player collects theirs with
  RetrievePaymentsForAuctionLost, the seller the winning bid with
  RetrievePaymentForAuctionSold, the winner the car with RetrieveCarForAuction (marked
  `wasOriginallyFromAuctionHouse`, one more owner in its history). A bid at the buyout
  price ends the auction at once.

**Not reachable in the game so far.** None of the menus checked opens the Auction House:
the festival's Autoshow (manufacturers and a "$" tile, which is TRADE-IN CARS), Dak's
Garage, the Paintshop (Design Creator, Load Design, Design Storefront), Race Central,
the Car Club, the pause menu and the party lobby. The code is there (FM4's: the screens
around `0x82864000`-`0x82888000`, `sub_82683930` the auction house screen, the config
loader `sub_82873DC0` -> `GetGlobalConfig`, a menu entry `0x104` in the table at
`0x8323E8C0` whose enable callback `sub_82674790` waits for that config) but no request
to the Auction service was seen. Gifting has stubs only for `SendCarGift`,
`RetrieveCarGift`, `RetrieveCreditsGift`, `MarkFileGiftRetrieved` (no
`GetGiftsForUser`/`SendCreditsGift` in this game): a received gift arrives as a Message
Center notification (`FileDepot_GiftCar` and others, below), whose parameter format is
not known yet.

### Notifications (Message Center)

`Xls Notifications.StartNewSession` and `RetrieveForUser(nonce, maxResults 512,
cbParameterBlockSize 0xC800)` (`sub_82AB3CF0`) fill the Message Center; each result is
`{id, xuidRecipient, notificationType, hasThumbnail, isRead, deleteAction,
expirationDate, cbParameters}` and their parameters follow in `parameterBlock`. Each type
has a handler class (title string, created through a visitor whose vtables are at
`0x82071A20`, `0x82071AE8` and `0x82071BB8`): TopFeatures_NewDlc `sub_82834668`,
GeneralNews_SimpleMessage `sub_82834998`, GeneralNews_Banned `sub_82834B68`,
FileDepot_AuctionOutbid/Won/Sold/Failed `sub_82834DF8`/`82835048`/`82835298`/`82835520`,
OutOfStock `sub_82835768`, MoneyReceived `sub_82835940`, GiftMoney `sub_82835B70`,
GiftItem `sub_82835DA8`, GiftCar and DeliveryFailed `sub_828362D8`, the Car Club ones
(`sub_82836760`-`sub_82838138`), RivalsAlerts_Challenge and SpeedCamera_Challenge
`sub_828386A0`, RivalsAlerts_Recommendation `sub_82838F48`. The server answers no
notifications yet (the type numbers and parameter layouts are still to be read from
these handlers).

## Not done

- The other services (storefront, car clubs, shared cars, notification contents, the
  Rivals menu's monthly time trials) get empty answers.
- Scoreboards: the ghost download (`DownloadFile`) and a Rivals race against a ghost,
  beating a rival (`NotifyRival`, the bounty) and the ONLINE XP leaderboard were not seen
  yet; the Monthly Rivals screen does not load with the server's time trials
  (`--time-trials`).
- Playground Games: a round of Cat & Mouse played to its end, and three or more
  consoles, were not tested.
- `DLCMetadata.GetStringTableInfo` / `Content.DownloadContent` (DLC string tables and
  thumbnails served by Turn 10) are empty.
