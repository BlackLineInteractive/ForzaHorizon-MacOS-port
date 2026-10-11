"""Forza Live title servers ("LSP"): Turn 10's title services for Forza Horizon.

forza_live_server.py calls handle() for every HTTP request on --http-port that isn't the
status page. The game calls Turn 10's services with POST /Services.Horizon/o.xtsw
(X-ClassName, X-Method; forza_xtsw.py has the format, docs/title_services.md the
services). This answers the ones online play needs:

    Forza.WebServices.User     Logon2 (the "Horizon server" sign-in), GetPermissionsTable,
                               RetrieveOnlineCredits, WriteRaceStats(Ex) (kept per player)
    Forza.WebServices.OnlineProfile  UpdateAll (online XP and credits, kept per player:
                               the game takes its online XP from Logon2), UpdateAllTables
    Forza.WebServices.Hopper   GetList (the Find Game playlists), GetSearchSettings,
                               GetGameOptions (each round's track and game type),
                               GetSessionListFilterSettings, UserRegister, ReportQosData,
                               ReportVoting, GetRaceMultipliers

Other methods get an empty answer: success and zero bytes, which read as zero, false,
empty strings and empty lists whatever the method's results are (the game ignores bytes
after the results). Every
request is logged (with --dump-requests saved under DATA_DIR/requests); player records go
to DATA_DIR/players/<XUID>.json. Files an operator puts under DATA_DIR/storage/<path> are
served as they are for GET /storage/<path>.
"""

import json
import logging
import os
import time
import urllib.parse

import forza_xtsw as x

log = logging.getLogger("forza-live")

DATA_DIR = "forza_live_data"
DUMP = False
# The world's rounds are endless: the client (world_drop_in, on by default) runs them as
# an online free roam that later players JUMP IN to, and a free roam has no timed end.
# Clients with world_drop_in off run them as Find Game's race-like free roam, whose lobby
# does not let a player into a game in progress ("WAITING FOR PLAYERS TO FINISH GAME");
# for them a round length (minutes) ends each round on a timer, and the players waiting in
# the lobby load in with everyone at the next round (docs/online_vision.md).
WORLD_ROUND_MINUTES = 0.0

# The playlists "Find Game" offers. Hopper ids are Turn 10's: the game keeps per-hopper
# options in its database (HopperRaces) and media/gametunablesettings
# (Default{Races,Playground}HopperOptions.xml).
# Find Game lists the first category's hoppers; "Horizon World" is its first row.
WORLD_HOPPER = 3
HOPPER_CATEGORIES = [
    {"name": "Online", "description": "The shared world and races.", "hopperStartIndex": 0},
    {"name": "Playground", "description": "Playground games.", "hopperStartIndex": 2},
]
HOPPERS = [
    # The shared world: online free roam (the game's own Quick Match playlist,
    # DefaultPlaygroundHopperOptions.xml, is free roam through matchmaking too). Everyone
    # who picks it is placed into the fullest world session with room (the Forza Live
    # server answers the session search), or hosts a new one.
    {"id": WORLD_HOPPER, "name": "Horizon World",
     "description": "Free roam with everyone online. JUMP IN to a world with room, "
                    "or open a new one and drive at once.",
     "playerCount": 8, "allowVoteToSkip": False, "allowVoteToKick": False,
     "shouldVoteCarClassBeforeLaunch": False, "intermissionTimeMs": 5000},
    {"id": 1, "name": "Races", "description": "We pick the routes, you pick the game type, "
                                              "and everyone votes for the Car class.",
     "playerCount": 8},
    {"id": 2, "name": "Playground Games", "description": "Infected, Cat & Mouse and King.",
     "playerCount": 8},
]
HOPPER_DEFAULTS = {"allowVoteToSkip": True, "allowVoteToKick": True,
                   "allowVoteToRebalance": False, "payoutModifier": 1.0, "hideTrueSkill": True,
                   # -1: no limit (beginner hoppers set them: a player may join while
                   # minAllowedRaces <= races < maxAllowedRaces and wins < maxAllowedWins)
                   "maxPartySize": 8, "icon": 0, "minAllowedRaces": -1, "maxAllowedRaces": -1,
                   "maxAllowedWins": -1, "shouldVoteCarClassBeforeLaunch": True,
                   "randomizedOrder": False, "intermissionTimeMs": 30000}
SESSION_FILTER = {
    "numStartingMatchmakingQueryResults": 25, "shouldQosProbe": False,
    "shouldReportQosToServer": False, "maxWaitingForQosDataSeconds": 5,
    "maxBpsConsumedDuringQos": 64000, "maxProbesToSend": 4, "maxMedQosRttAllowedMs": 500,
    "maxMinQosRttAllowedMs": 500, "minUpstreamBandwidth": 0, "minDownstreamBandwidth": 0,
    "scoreBonusForJoinInProgress": 0.0, "scoreBonusForJoinInShortIntermission": 0.0,
    "scoreBonusForEmptySlots": 0.0, "rankFactorMinPing": 0.0, "rankFactorAvgPing": 0.0,
    "rankFactorUpstreamBandwidth": 0.0, "rankFactorDownstreamBandwidth": 0.0,
    "minScoreToConnect": -1000000.0}
SEARCH_SETTINGS = {
    "sessionFilterSettings": SESSION_FILTER, "maxConnectAttemptsBeforeCreating": 3,
    "maxConnectSecondsBeforeCreating": 20, "maxWaitingForClientsToConnectSeconds": 20,
    "minPlayersToLaunch": 2, "intermissionTimeMs": 30000, "shortIntermissionTimeMs": 10000}
# The world starts with its first player: nobody waits in a lobby for a second one (this
# and the client's world_drop_in, which runs the launch check a host alone never ran).
WORLD_SEARCH_SETTINGS = dict(SEARCH_SETTINGS, minPlayersToLaunch=1, intermissionTimeMs=5000,
                             shortIntermissionTimeMs=5000, maxConnectAttemptsBeforeCreating=2,
                             maxConnectSecondsBeforeCreating=10)


def hopper_get_search_settings(xuid, body):
    params, _ = x.decode(x.HopperGetSearchSettings_Params, body)
    settings = WORLD_SEARCH_SETTINGS if params["hopperId"] == WORLD_HOPPER else SEARCH_SETTINGS
    return x.reply(x.HopperGetSearchSettings_Results, {"settings": settings})


def add_arguments(parser):
    parser.add_argument("--data-dir", default=os.environ.get("FORZA_LIVE_DATA", "forza_live_data"),
                        help="player records and operator-provided title storage files "
                             "(default ./forza_live_data)")
    parser.add_argument("--dump-requests", action="store_true",
                        help="save every title server request to DATA_DIR/requests")
    parser.add_argument("--world-round-minutes", type=float, default=WORLD_ROUND_MINUTES,
                        help="length of a Horizon World round in minutes (default "
                             "%(default)s: endless). Only for clients with world_drop_in off, "
                             "whose players wait in the lobby until the round ends; with "
                             "drop-in the world is a free roam without a timed end")


def configure(args):
    global DATA_DIR, DUMP, WORLD_ROUND_MINUTES
    DATA_DIR = args.data_dir
    DUMP = args.dump_requests
    WORLD_ROUND_MINUTES = max(0.0, args.world_round_minutes)
    os.makedirs(DATA_DIR, exist_ok=True)


def dump(method, path, headers, body):
    folder = os.path.join(DATA_DIR, "requests")
    os.makedirs(folder, exist_ok=True)
    name = "%d-%s-%s" % (int(time.time() * 1000), method,
                         urllib.parse.quote(headers.get("x-method", path), safe="")[:100])
    with open(os.path.join(folder, name), "wb") as f:
        f.write(("\r\n".join(f"{k}: {v}" for k, v in headers.items()) + "\r\n\r\n").encode())
        f.write(body)


def stored_file(path):
    rel = os.path.normpath(path.lstrip("/"))
    if rel.startswith(".."):
        return None
    full = os.path.join(DATA_DIR, rel)
    if os.path.isfile(full):
        with open(full, "rb") as f:
            return f.read()
    return None


# ---- Player records ----

def player_path(xuid):
    return os.path.join(DATA_DIR, "players", "%016X.json" % xuid)


def load_player(xuid):
    try:
        with open(player_path(xuid)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_player(xuid, record):
    path = player_path(xuid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(record, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


# ---- Services ----

def user_logon2(xuid, body):
    params, _ = x.decode(x.UserLogon2_Params, body)
    login = params["loginData"]
    xuid = login["qwXuid"] or xuid
    record = load_player(xuid)
    record.update(gamertag=login["wzGamerTag"], lastLogon=int(time.time()),
                  careerLevel=login["currentCareerLevel"], logons=record.get("logons", 0) + 1)
    save_player(xuid, record)
    log.info("title: Logon2 %016X '%s' level %d", xuid, login["wzGamerTag"],
             login["currentCareerLevel"])
    return x.reply(x.UserLogon2_Results, {"responseData": {
        "isProfileValid": True,
        "userData": {"qwXuid": xuid, "wzGamerTag": login["wzGamerTag"],
                     "currentCareerLevel": login["currentCareerLevel"],
                     "currentBadgeId": login["currentBadgeId"],
                     "currentPlayerTitleId": login["currentPlayerTitleId"],
                     "currentXPTotal": record.get("profile", {}).get("onlineXP", 0)},
        "notificationPollIntervalSeconds": 600,
        "gameplayLogConfig": {"Enabled": False, "Throttle": bytes(26)},
        "defaultTimeoutMs": 30000, "defaultContentTimeoutMs": 60000}})


def user_write_race_stats(xuid, body):
    head, _ = x.decode(x.UserWriteRaceStats_Head, body)
    stats = head["raceStats"]
    record = load_player(xuid)
    record.update(userLevel=stats["userLevel"], userXP=stats["userXP"],
                  currentCredits=stats["currentCredits"], totalWinnings=stats["totalWinnings"],
                  onlineWinnings=stats["onlineWinnings"],
                  races=record.get("races", 0) + 1, lastRace={
                      k: (v.hex() if isinstance(v, bytes) else v) for k, v in stats.items()})
    save_player(xuid, record)
    log.info("title: race stats %016X: event %d hopper %d place %d/%d finished %d, level %d "
             "XP %d credits %d", xuid, stats["eventId"], stats["hopperId"],
             stats["userFinishPosition"], stats["maxPlaces"], stats["finished"],
             stats["userLevel"], stats["userXP"], stats["currentCredits"])
    return x.reply()


PROFILE_FIELDS = ("level", "xp", "onlineXP", "onlineWristbandLevel", "numOnlineRaces",
                  "numOnlineVictories", "numRaces", "numVictories", "numCreditsEarned",
                  "onlineWinnings", "totalWinnings")


def online_profile_update_all(xuid, body):
    """The profile upload: keeps the player's levels, XP (career and online) and credits."""
    params, _ = x.decode(x.OnlineProfileUpdateAll_Params, body)
    record = load_player(xuid)
    profile = {}
    if params["playerRaceHistory"]:
        race = params["playerRaceHistory"][0]
        profile = {k: race[k] - (1 << 32) if race[k] >= 1 << 31 else race[k]
                   for k in PROFILE_FIELDS}
    if params["playerHistory"]:
        profile["credits"] = params["playerHistory"][0]["credits"]
    # Online XP lives on the server: the game takes it from Logon2 (userData.currentXPTotal)
    # and reports it back here, so the upload right after signing in carries what we gave.
    # It only grows; keep the largest.
    stored = record.get("profile", {})
    for key in ("onlineXP", "onlineWristbandLevel"):
        if key in profile:
            profile[key] = max(profile[key], stored.get(key, 0))
    if profile:
        if profile != record.get("profile"):
            log.info("title: profile %016X: level %d, online XP %d (wristband %d), %d online "
                     "races, %d credits", xuid, profile.get("level", 0),
                     profile.get("onlineXP", 0), profile.get("onlineWristbandLevel", 0),
                     profile.get("numOnlineRaces", 0), profile.get("credits", 0))
        record.update(profile=profile, profileUpdated=int(time.time()))
        save_player(xuid, record)
    return x.reply()


def hopper_get_list(xuid, body):
    params, _ = x.decode(x.HopperGetList_Params, body)
    hoppers = [dict(HOPPER_DEFAULTS, **h) for h in HOPPERS]
    return x.reply(x.HopperGetList_Results, {
        "hopperCategories": HOPPER_CATEGORIES[:params["maxCategoryResults"]],
        "hoppers": hoppers[:params["maxHopperResults"]]})


def hopper_user_register(xuid, body):
    params, _ = x.decode(x.HopperUserRegister_Params, body)
    log.info("title: hopper %d register %016X session %s", params["hopperId"], xuid,
             params["sessionId"].hex())
    return x.reply(x.HopperUserRegister_Results, {"nextRegisterSeconds": 60})


EMPTY_ANSWER = 4096  # zero bytes after the header for methods without a handler

# Each hopper's rounds: (GameTypePreset, TrackId, laps). The game's database lists the
# races of its own default playlist in HopperRaces (1 = circuit, 2 = point to point);
# 7 is the playground game of DefaultPlaygroundHopperOptions.xml.
HOPPER_ROUNDS = {
    1: [(1, 322, 3), (2, 155, 1), (1, 107, 3), (2, 145, 1)],
    2: [(7, 317, 0)],
    # Free roam (GameOptionPresets.xml's IDS_PresetFreeRoam) from the festival (track 1101,
    # the custom game's default starting location), no end condition.
    WORLD_HOPPER: [(7, 1101, 0)],
}

GAME_OPTIONS_XML = """<GameOptions GameTypePreset="{preset}"{filter} TrackId="{track}" UseTraffic="false"
    CollisionMode="Default" MaxPlayers="{players}" MaxAIPlayers="0" NumPlayerBuckets="1"
    NumTeams="0" HorizonTimeOfDayIsRandom="true" HorizonTimeOfDay="Invalid"
    PauseTimeOfDay="false" MinRecommendedCarClass="255" MaxRecommendedCarClass="255">
  <Buckets>
    <Bucket Name="GROUP 1" CanStartEndOfRaceCountdown="1" MinPlayers="1" MaxPlayers="{players}">
      <CarRestrictions CarClassId="255"/>
    </Bucket>
  </Buckets>
  <StartingGridOptions StartType="OpenWorld" GridOrderingType="Random"/>
  <EndConditionOptions Type="{end}" NumLaps="{laps}"{time} EndRaceCounter="30.0"/>
  <ScoringOptions Type="TimeBased" BiggerIsBetter="0"/>
</GameOptions>
"""


def hopper_get_game_options(xuid, body):
    """A round's options as GameOptions XML (the format of the game's
    media/gametunablesettings Default*HopperOptions.xml). DATA_DIR/hoppers/<hopperId>.xml
    overrides the built-in rotation (HOPPER_ROUNDS, picked by roundNum)."""
    params, _ = x.decode(x.HopperGetGameOptions_Params, body)
    hopper, round_num = params["hopperId"], params["roundNum"]
    path = os.path.join(DATA_DIR, "hoppers", "%d.xml" % hopper)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            xml = f.read()
    else:
        rounds = HOPPER_ROUNDS.get(hopper, HOPPER_ROUNDS[1])
        preset, track, laps = rounds[round_num % len(rounds)]
        players = next((h["playerCount"] for h in HOPPERS if h["id"] == hopper), 8)
        # A free roam (laps 0) has no end, or a timed one (Type "Time", seconds) in the world.
        end, time_attr = ("NumLaps", "") if laps else ("None", "")
        if hopper == WORLD_HOPPER and WORLD_ROUND_MINUTES > 0:
            end, time_attr = "Time", ' Time="%d"' % round(WORLD_ROUND_MINUTES * 60)
        xml = GAME_OPTIONS_XML.format(
            preset=preset, track=track, laps=max(laps, 1), players=players,
            # the custom game's Free Roam preset sets it (GameOptionPresets.xml)
            filter=' GameTypeFilterType="FreeRoam"' if preset == 7 else "",
            end=end, time=time_attr).encode()
        log.info("title: hopper %d round %d for %016X: preset %d track %d laps %d", hopper,
                 round_num, xuid, preset, track, laps)
    return x.reply(x.HopperGetGameOptions_Results, {"gameOptionsXml": xml})


SERVICES = {
    ("User", "Logon2"): user_logon2,
    ("User", "GetPermissionsTable"): lambda xuid, body: x.reply(x.UserGetPermissionsTable_Results),
    ("User", "RetrieveOnlineCredits"):
        lambda xuid, body: x.reply(x.UserRetrieveOnlineCredits_Results, {"credit": 0}),
    ("User", "WriteRaceStats"): user_write_race_stats,
    ("User", "WriteRaceStatsEx"): user_write_race_stats,
    ("OnlineProfile", "UpdateAll"): online_profile_update_all,
    ("OnlineProfile", "UpdateAllTables"): lambda xuid, body: x.reply(),
    ("Hopper", "GetList"): hopper_get_list,
    ("Hopper", "GetSearchSettings"): hopper_get_search_settings,
    ("Hopper", "GetSessionListFilterSettings"):
        lambda xuid, body: x.reply(x.HopperGetSessionListFilterSettings_Results,
                                   {"settings": SESSION_FILTER}),
    ("Hopper", "UserRegister"): hopper_user_register,
    ("Hopper", "GetGameOptions"): hopper_get_game_options,
    ("Hopper", "ReportQosData"): lambda xuid, body: x.reply(),
    ("Hopper", "ReportVoting"): lambda xuid, body: x.reply(),
    ("Hopper", "GetRaceMultipliers"):
        lambda xuid, body: x.reply(x.HopperGetRaceMultipliers_Results,
                                   {"specialMultiplier": 1.0}),
}


def service_call(headers, body):
    """bin/xtsw call -> reply body."""
    cls = headers.get("x-classname", "").split(",")[0]          # Forza.WebServices.Hopper
    short = cls.rsplit(".", 1)[-1]
    method = headers.get("x-method", "")
    try:
        xuid = int(headers.get("x-userid", "0"), 16)
    except ValueError:
        xuid = 0
    fn = SERVICES.get((short, method)) if cls.startswith("Forza.WebServices.") else None
    if fn is None:
        log.info("title: %s.%s from %016X (%d bytes): empty answer", cls, method, xuid,
                 len(body))
        return x.reply() + bytes(EMPTY_ANSWER)
    try:
        return fn(xuid, body)
    except ValueError as e:  # parameters that don't parse
        log.warning("title: %s.%s: bad parameters (%s): %s", cls, method, e, body.hex())
        return x.failure(2, "bad parameters")


def handle(server, method, path, headers, body, peer):
    """Returns (HTTP status, content type, body bytes)."""
    if DUMP:
        dump(method, path, headers, body)
    url = urllib.parse.urlsplit(path)
    if method == "POST" and url.path.endswith("/o.xtsw"):
        log.info("LSP %s.%s (%d bytes)", headers.get("x-classname", "?").split(",")[0],
                 headers.get("x-method", "?"), len(body))
        return 200, "bin/xtsw", service_call(headers, body)
    log.info("LSP request %s %s (%d bytes)", method, path, len(body))
    if url.path.startswith("/storage/") and method == "GET":
        data = stored_file(url.path)
        if data is not None:
            return 200, "application/octet-stream", data
    return 404, "text/plain", b"not found"
