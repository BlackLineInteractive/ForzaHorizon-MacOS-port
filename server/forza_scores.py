"""Forza Live: scoreboards (leaderboards), Rivals and their ghosts.

The game submits a score at the end of an event (Scoreboard.SubmitScore / SubmitScoreEx:
the scoreboard id of the event, the time or score, the car, its class and performance
index, assists and tuning) and reads scoreboards for its leaderboard screens and for
Rivals (GetRows, GetRival, GetRivalAndPersonalBest, GetBestScores). The answer to a
submission asks for the ghost (uploadFiles) when the score is the player's new best; the
game then uploads it (UploadFile, an opaque blob of up to 250 KB that we keep as it is)
and another player racing that score as a rival downloads it (DownloadFile, by the row's
ghostFileId). docs/title_services.md has the details.

Everything is kept in DATA_DIR/scoreboards.json (the best score of each player on each
scoreboard) and DATA_DIR/ghosts/<id>.bin.
"""

import json
import logging
import os
import time
import uuid

import forza_xtsw as x

log = logging.getLogger("forza-live")

DATA_DIR = "forza_live_data"
GHOST_MAX = 256000           # the game's download buffer (DownloadFile maxSize)
RIVAL_BOUNTY = 1000          # credits for beating a rival, shown as BOUNTY BONUS

# Score types (the submission's `type`, GetBestScores' scoreType) whose scores are better
# when bigger: drift and skill scores, speeds. Race times (3, SubmitScoreEx at the end of
# an event) are better when smaller. Unknown types are treated as times and logged.
BIGGER_IS_BETTER = {4}


class Store:
    """Best score per player per scoreboard, and the ghosts."""

    def __init__(self):
        self.boards = {}       # "sbid:stt" -> {xuid hex: entry}
        self.ghosts = {}       # scoreId hex -> (board key, xuid hex): waiting for UploadFile
        self.next_file = 1
        self.loaded = False

    def path(self):
        return os.path.join(DATA_DIR, "scoreboards.json")

    def load(self):
        if self.loaded:
            return
        self.loaded = True
        try:
            with open(self.path()) as f:
                data = json.load(f)
            self.boards = data.get("boards", {})
            self.next_file = data.get("nextFileId", 1)
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = self.path() + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"boards": self.boards, "nextFileId": self.next_file}, f, indent=1)
        os.replace(tmp, self.path())

    def board(self, sbid, stt):
        self.load()
        return self.boards.setdefault("%d:%d" % (sbid, 1 if stt else 0), {})

    def ranked(self, sbid, stt):
        """The board's entries, best first."""
        entries = list(self.board(sbid, stt).values())
        bigger = any(e.get("type") in BIGGER_IS_BETTER for e in entries)
        entries.sort(key=lambda e: (-e["score"] if bigger else e["score"], e["submitted"]))
        return entries, bigger


STORE = Store()


def configure(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    STORE.__init__()


def better(new, old, bigger):
    return new > old if bigger else new < old


def submit(xuid, gamertag, kind, data, extra=None):
    """Keeps a submission if it is the player's best; returns the reply (scoreId, and
    uploadFiles when we want its ghost)."""
    sbid, stt, score = data["gameScoreboardId"], data["isServerTimeTrial"], data["score"]
    score_id = uuid.uuid4().bytes
    log.info("title: score %016X '%s': board %d%s type %d score %.3f car %d class %d PI %.3f%s",
             xuid, gamertag, sbid, " (time trial)" if stt else "", kind, score, data["carId"],
             data["carClassId"], data["carPerformanceIndex"],
             " passed %d" % extra if extra is not None else "")
    if sbid < 0 or score <= 0:
        return x.reply(x.ScoreboardSubmitScore_Results, {"scoreId": score_id, "uploadFiles": False})
    board = STORE.board(sbid, stt)
    key = "%016X" % xuid
    old = board.get(key)
    bigger = kind in BIGGER_IS_BETTER
    if old and not better(score, old["score"], bigger):
        return x.reply(x.ScoreboardSubmitScore_Results, {"scoreId": score_id, "uploadFiles": False})
    entry = {"xuid": key, "gamertag": gamertag, "type": kind, "score": score,
             "submitted": int(time.time()), "scoreId": score_id.hex(),
             "carId": data["carId"], "carClassId": data["carClassId"],
             "carPerformanceIndex": data["carPerformanceIndex"], "ghostFileId": -1}
    for k in ("usedSTM", "usedTCS", "usedABS", "usedAutoBrake", "usedAutoShifting", "usedClutch"):
        entry[k] = data[k]
    if old and old.get("ghostFileId", -1) >= 0:
        remove_ghost(old["ghostFileId"])
    board[key] = entry
    STORE.ghosts[score_id.hex()] = ("%d:%d" % (sbid, 1 if stt else 0), key)
    STORE.save()
    log.info("title: score %016X: new best on board %d, asking for the ghost", xuid, sbid)
    return x.reply(x.ScoreboardSubmitScore_Results, {"scoreId": score_id, "uploadFiles": True})


def ghost_path(file_id):
    return os.path.join(DATA_DIR, "ghosts", "%d.bin" % file_id)


def remove_ghost(file_id):
    try:
        os.remove(ghost_path(file_id))
    except OSError:
        pass


def upload_file(xuid, body):
    params, _ = x.decode(x.ScoreboardUploadFile_Params, body)
    sid = params["scoreId"].hex()
    found = STORE.ghosts.pop(sid, None)
    data = params["data"]
    if not found:
        log.info("title: UploadFile %016X: unknown score %s (%d bytes)", xuid, sid, len(data))
        return x.reply()
    board_key, key = found
    entry = STORE.boards.get(board_key, {}).get(key)
    if not entry or entry["scoreId"] != sid:
        return x.reply()  # beaten again since
    file_id = STORE.next_file
    STORE.next_file += 1
    os.makedirs(os.path.dirname(ghost_path(file_id)), exist_ok=True)
    with open(ghost_path(file_id), "wb") as f:
        f.write(data)
    entry["ghostFileId"] = file_id
    STORE.save()
    log.info("title: ghost %d from %016X for board %s (%d bytes)", file_id, xuid, board_key,
             len(data))
    return x.reply()


def download_file(xuid, body):
    params, _ = x.decode(x.ScoreboardDownloadFile_Params, body)
    try:
        with open(ghost_path(params["id"]), "rb") as f:
            data = f.read()
    except OSError:
        log.info("title: DownloadFile %d for %016X: no such file", params["id"], xuid)
        return x.failure(1, "no such file")
    if params["maxSize"] > 0 and len(data) > params["maxSize"]:
        return x.failure(1, "file too big")
    log.info("title: DownloadFile %d for %016X (%d bytes)", params["id"], xuid, len(data))
    return x.reply(x.ScoreboardDownloadFile_Results, {"data": data})


def user_data(entry):
    return {"qwXuid": int(entry["xuid"], 16), "wzGamerTag": entry["gamertag"],
            "currentCareerLevel": entry.get("level", 0)}


def row(entry, position):
    r = {k: entry[k] for k in ("score", "carId", "carClassId", "carPerformanceIndex",
                                "usedSTM", "usedTCS", "usedABS", "usedAutoBrake",
                                "usedAutoShifting", "usedClutch", "ghostFileId")}
    r.update(position=position, rank=position, user=user_data(entry),
             submittedTime=entry["submitted"],
             bounty=RIVAL_BOUNTY)
    return r


NO_ROW = {"position": 0, "rank": 0, "ghostFileId": -1}


def rows_view(entries, xuid, view, start_at, max_results):
    """(rows, the caller's row) for a view: 0 the top, 1 around the caller, 2 friends
    (everyone here), others the top."""
    key = "%016X" % xuid
    mine = next((i for i, e in enumerate(entries) if e["xuid"] == key), None)
    max_results = max(0, min(max_results, 200))
    if view == 1 and mine is not None:
        first = max(0, min(mine - max_results // 2, len(entries) - max_results))
    else:
        first = max(0, start_at - 1)
    rows = [row(e, i + 1) for i, e in enumerate(entries)][first:first + max_results]
    user_row = row(entries[mine], mine + 1) if mine is not None else NO_ROW
    return rows, user_row


def get_rows(xuid, body):
    p, _ = x.decode(x.ScoreboardGetRows_Params, body)
    entries, _ = STORE.ranked(p["gameScoreboardId"], p["isServerTimeTrial"])
    rows, user_row = rows_view(entries, xuid, p["view"], p["startAt"], p["maxResults"])
    log.info("title: GetRows %016X board %d%s type %d view %d from %d max %d: %d of %d", xuid,
             p["gameScoreboardId"], " (time trial)" if p["isServerTimeTrial"] else "",
             p["type"], p["view"], p["startAt"], p["maxResults"], len(rows), len(entries))
    return x.reply(x.ScoreboardGetRows_Results, {"rows": rows, "userRow": user_row,
                                                 "available": len(entries),
                                                 "totalRowCount": len(entries)})


# Rollup boards (GetRollupRows: Race Central's LEADERBOARDS, "VIEW OVERALL"): eventTypeId 1
# festival events, 2 street races, 3 showcases; pivotId -1 all, else a wristband level.
# A scoreboard id is the event's Id in the game database (Events: HorizonEventID "FR61",
# Level 6 for board 199, GoPro Millennia Masters).
EVENT_TYPES = {1: "FR", 2: "ST", 3: "EX"}
EVENTS = None  # Id -> (HorizonEventID prefix, wristband level)


def events():
    global EVENTS
    if EVENTS is None:
        EVENTS = {}
        import forza_world
        if forza_world.GAME_DB and os.path.isfile(forza_world.GAME_DB):
            import sqlite3
            try:
                db = sqlite3.connect("file:%s?mode=ro" % forza_world.GAME_DB, uri=True)
                EVENTS = {i: ((h or "")[:2], lvl) for i, h, lvl in
                          db.execute("select Id, HorizonEventID, Level from Events")}
                db.close()
            except sqlite3.Error as e:
                log.warning("scoreboards: game database: %s", e)
    return EVENTS


def in_rollup(board_key, event_type, pivot):
    sbid, stt = (int(v) for v in board_key.split(":"))
    if stt:
        return False
    info = events().get(sbid)
    if info is None:
        return not events()  # without the database every board counts
    prefix, level = info
    if event_type in EVENT_TYPES and prefix != EVENT_TYPES[event_type]:
        return False
    return pivot < 0 or level == pivot


def rollup_entries(event_type, pivot):
    """Every player's total over the boards of a rollup: ranked by the number of events
    they have a time on, then by the total of their best times (the score shown)."""
    STORE.load()
    players = {}
    for board_key, board in STORE.boards.items():
        if not in_rollup(board_key, event_type, pivot):
            continue
        for e in board.values():
            if e.get("type") in BIGGER_IS_BETTER:
                continue
            p = players.setdefault(e["xuid"], dict(e, score=0.0, boards=0))
            p["boards"] += 1
            p["score"] += e["score"]
            p["submitted"] = max(p["submitted"], e["submitted"])
            p["ghostFileId"] = -1
    out = sorted(players.values(), key=lambda e: (-e["boards"], e["score"]))
    return out


def get_rollup_rows(xuid, body):
    p, _ = x.decode(x.ScoreboardGetRollupRows_Params, body)
    entries = rollup_entries(p["eventTypeId"], p["pivotId"])
    rows, user_row = rows_view(entries, xuid, p["view"], p["startAt"], p["maxResults"])
    log.info("title: GetRollupRows %016X type %d view %d pivot %d event type %d: %d rows", xuid,
             p["type"], p["view"], p["pivotId"], p["eventTypeId"], len(rows))
    return x.reply(x.ScoreboardGetRollupRows_Results,
                   {"rows": rows, "userRow": user_row, "available": len(entries)})


def pick_rival(entries, xuid, bigger):
    """The rival for a player: the score just better than theirs; without a score of
    their own, the slowest other player (an easy first rival)."""
    key = "%016X" % xuid
    others = [e for e in entries if e["xuid"] != key]
    if not others:
        return None
    mine = next((e for e in entries if e["xuid"] == key), None)
    if mine is None:
        return others[-1]
    ahead = [e for e in others if better(e["score"], mine["score"], bigger)]
    return ahead[-1] if ahead else others[0]


def rival_reply(xuid, body, with_best):
    p, _ = x.decode(x.ScoreboardGetRival_Params, body)
    entries, bigger = STORE.ranked(p["gameScoreboardId"], p["isServerTimeTrial"])
    if p["rivalXuid"]:
        rival = next((e for e in entries if int(e["xuid"], 16) == p["rivalXuid"]), None)
    else:
        rival = pick_rival(entries, xuid, bigger)
    mine = next((e for e in entries if e["xuid"] == "%016X" % xuid), None)
    log.info("title: rival for %016X on board %d (asked %016X): %s", xuid, p["gameScoreboardId"],
             p["rivalXuid"], "%s %.3f ghost %d" % (rival["gamertag"], rival["score"],
                                                  rival["ghostFileId"]) if rival else "none")
    if rival is None:
        result = {"rival": {"scoreData": NO_ROW, "bounty": 0}}
    else:
        result = {"rival": {"scoreData": row(rival, entries.index(rival) + 1),
                            "bounty": RIVAL_BOUNTY}}
    if with_best:
        result["personalBest"] = {"score": mine["score"] if mine else 0.0}
        return x.reply(x.ScoreboardGetRivalAndPersonalBest_Results, result)
    return x.reply(x.ScoreboardGetRival_Results, result)


def get_best_scores(xuid, body):
    p, _ = x.decode(x.ScoreboardGetBestScores_Params, body)
    entries, _ = STORE.ranked(p["gameScoreboardId"], p["isServerTimeTrial"])
    best = entries[0]["score"] if entries else 0.0
    log.info("title: GetBestScores %016X board %d type %d car %d class %d: %.3f", xuid,
             p["gameScoreboardId"], p["scoreType"], p["carId"], p["carClassId"], best)
    return x.reply(x.ScoreboardGetBestScores_Results, {"bestScore": {"score": best}})


def notify_rival(xuid, body, notify=None):
    p, _ = x.decode(x.ScoreboardNotifyRival_Params, body)
    log.info("title: %016X beat rival %016X on board %d (type %d)", xuid, p["rivalXuid"],
             p["gameScoreboardId"], p["type"])
    if notify:
        notify(p)
    return x.reply()


# Race Central's MONTHLY RIVALS: the server's time trials (GetTimeTrials). Each one is a
# scoreboard of its own (isServerTimeTrial, board = the trial id) and a round of
# TIME_TRIAL_HOPPER (Hopper.GetGameOptions(hopper, gameOptionsIndex): its track and laps).
# Categories (TimeTrial.str): 0 time, 1 time with traffic, 2 drift, 3 Top Gear, 4 time
# spec, 5 weekly, 6 autocross.
TIME_TRIAL_HOPPER = 10
# Off by default (--time-trials): with these two the game's MONTHLY RIVALS screen asked for
# nothing more and kept its YOUR RIVAL, BOUNTY and description spinners going.
TIME_TRIALS_ENABLED = False
TIME_TRIALS = [
    # id, category, name, description, track id, track name, laps, car class (-1 any)
    (1001, 0, "Horizon Monthly: Clear Springs", "Two laps of the Clear Springs Circuit, "
     "any car. Beat the other players' times.", 156, "Clear Springs Circuit", 2, -1),
    (1002, 0, "Horizon Monthly: Festival Sprint", "One lap on the festival's road course "
     "in a class A car.", 322, "Festival Circuit", 1, 5),
]


def time_trial_rounds():
    """{gameOptionsIndex: (track, laps, class)} of TIME_TRIAL_HOPPER."""
    return {i: (t[4], t[6], t[7]) for i, t in enumerate(TIME_TRIALS)}


def get_time_trials(xuid, body):
    p, _ = x.decode(x.ScoreboardGetTimeTrials_Params, body)
    now = time.time()
    month = time.gmtime(now)
    start = time.mktime((month.tm_year, month.tm_mon, 1, 0, 0, 0, 0, 0, 0))
    end = start + 32 * 86400
    cats, trials = [], []
    for i, (tid, cat, name, desc, track, track_name, laps, cls) in enumerate(
            TIME_TRIALS if TIME_TRIALS_ENABLED else []):
        if not cats or cats[-1]["category"] != cat:
            cats.append({"category": cat, "startIndex": len(trials)})
        trials.append({"id": tid, "scoreType": 3, "name": name, "description": desc,
                       "trackId": track, "trackName": track_name,
                       "hopperId": TIME_TRIAL_HOPPER, "gameOptionsIndex": i,
                       "startDate": start, "endDate": end, "userRegistered": True,
                       "featured": i == 0, "active": True, "displayCarClass": cls})
    log.info("title: GetTimeTrials %016X (max %d categories, %d trials): %d", xuid,
             p["maxTimeTrialCategories"], p["maxTimeTrialResults"], len(trials))
    return x.reply(x.ScoreboardGetTimeTrials_Results, {
        "timeTrialCategories": cats[:p["maxTimeTrialCategories"]],
        "timeTrials": trials[:p["maxTimeTrialResults"]]})


def submit_score(gamertag_of, ex):
    def handler(xuid, body):
        if ex:
            p, _ = x.decode(x.ScoreboardSubmitScoreEx_Params, body)
            return submit(xuid, gamertag_of(xuid), p["type"], p["data"]["base"],
                          p["data"]["numCarsPassed"])
        p, _ = x.decode(x.ScoreboardSubmitScore_Params, body)
        return submit(xuid, gamertag_of(xuid), p["type"], p["data"])
    return handler


def services(gamertag_of):
    return {
        ("Scoreboard", "SubmitScore"): submit_score(gamertag_of, False),
        ("Scoreboard", "SubmitScoreEx"): submit_score(gamertag_of, True),
        ("Scoreboard", "UploadFile"): upload_file,
        ("Scoreboard", "DownloadFile"): download_file,
        ("Scoreboard", "GetRows"): get_rows,
        ("Scoreboard", "GetRollupRows"): get_rollup_rows,
        ("Scoreboard", "GetRival"): lambda xuid, body: rival_reply(xuid, body, False),
        ("Scoreboard", "GetRivalAndPersonalBest"): lambda xuid, body: rival_reply(xuid, body, True),
        ("Scoreboard", "GetBestScores"): get_best_scores,
        ("Scoreboard", "NotifyRival"): notify_rival,
        ("Scoreboard", "GetTimeTrials"): get_time_trials,
    }
