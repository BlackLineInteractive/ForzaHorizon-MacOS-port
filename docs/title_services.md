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
| 11 | SYSTEMTIME | 16 bytes |
| 12 | bool | 1 byte |
| 13 | GUID | 16 bytes |
| 15 | byte array | u32 length + bytes |
| 18 | XNKID | 8 bytes |

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
| Sign-in (about 50 s after boot) | `User.Logon2(loginData)` | `responseData`: profile valid, no permission limits, `userData` (XUID, gamertag, **currentXPTotal = the player's online XP**), timeouts |
| | `OnlineProfile.UpdateAllTables`, `UpdateAll` | success; `UpdateAll`'s `playerRaceHistory` (level, XP, **onlineXP**, online races and wins) and `playerHistory` (credits) are kept per player |
| | `DLCMetadata.GetStringTableInfo("EN")`, `Xls Content.DownloadContent(0, 0, 0x40000)` x2 | empty |
| Party lobby | `Hopper.GetList(maxCategoryResults 2, maxHopperResults 32)` | the playlists (below) |
| Find Game, picking a playlist | `Hopper.GetSearchSettings(hopperId)`, `GetGameOptions(hopperId, roundNum, 0x8000)`, then (after the session search) `UserRegister(hopperId, sessionId)` every `nextRegisterSeconds` | search settings, the round's GameOptions XML, 60 s |
| Race start | `GameplayLog.Write`, `Hopper.GetRaceMultipliers` | empty, multiplier 1.0 |
| Race end | `Scoreboard.SubmitScoreEx` / `SubmitScore`, `User.SetPlayercardInfo`, `OnlineProfile.UpdateAllTables` / `UpdateAll` | empty / success (profile kept) |
| Sometimes | `Xls User.SetFriends` | empty |

`User.WriteRaceStats(Ex)` (race stats with `userXP`, credits) is implemented on the
server and keeps the stats, but was not called in these tests.

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
3 "Horizon World" and 1 "Races" (category Online), 2 "Playground Games". Horizon World is
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
`GameTypePreset` (1 circuit race, 2 point-to-point, 7 the playground game), `TrackId`
(the game database's `Tracks`), `MaxPlayers`, `MaxAIPlayers`, `UseTraffic`,
`CollisionMode`, time of day and car class attributes, and children `Buckets/Bucket` (with
`CarRestrictions`), `StartingGridOptions StartType="OpenWorld"`, `EndConditionOptions
Type="NumLaps" NumLaps=".."` and `ScoringOptions`. The server's rounds for hopper 1 are the
game database's `HopperRaces` table (preset, track, laps: (1, 322, 3), (2, 155, 1), (1, 107,
3), (2, 145, 1)), picked by `roundNum`; `DATA_DIR/hoppers/<id>.xml` replaces them.

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
`GetGameOptions` when a round launches.

### XP and credits

The game computes the rewards itself at the end of an online race ("XP REWARDS": finished
1st 1,000 XP, mileage bonus 200 XP, x1 for a 2-player game, x1.1 skills = 1,320 XP; 2nd
800 XP), with the server's race multiplier (`GetRaceMultipliers`). Credits go to the local
save. Online XP does not: the game takes it from `Logon2`'s `userData.currentXPTotal` at
every sign-in (a restart with 0 there showed online XP 0 and the wristband level reset,
credits kept), so the server keeps it: from each `UpdateAll` (`onlineXP`, only growing)
into `DATA_DIR/players/<XUID>.json`, back in the next `Logon2`. Without the title server
the game offers only the default "Quick Match" playlist, which awards no multiplayer XP.

## Not done

- The other services (storefront, auctions, gifting, scoreboards, car clubs, shared cars,
  notifications) get empty answers: their screens show nothing.
- The Playground category's playlist is answered but its game (preset 7) was not tested;
  car class voting between rounds was seen, not exercised.
- `DLCMetadata.GetStringTableInfo` / `Content.DownloadContent` (DLC string tables and
  thumbnails served by Turn 10) are empty.
