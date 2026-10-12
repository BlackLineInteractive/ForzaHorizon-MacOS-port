# Hosting a Forza Live server

`server/` is a standard-library Python server: UDP rendezvous/relay plus the HTTP title
services (Turn 10's services, kept-alive connections) and a JSON status page.

| Port | Protocol | Use |
|------|----------|-----|
| 21200 | UDP | game, rendezvous, relay |
| 21201 | TCP | title services, status page at `/` |

Forward both on the router to the host. Players set `live_server = "your.host:21200"` (or
`FORZA_SERVER=your.host:21200`). The title services are reached at the same IP as the UDP
address, so LAN players can use the LAN IP and everyone else the public name; players
forward nothing (UDP hole punching, server relay as fallback).

## Docker

    docker build -t forza-live server/
    docker run -d --name forza-live --restart unless-stopped --network host \
        -e FORZA_ADMIN_TOKEN=choose-a-token \
        -v /path/to/data:/data forza-live --host 0.0.0.0

Use `--network host`: with a bridge network the players' public ip:port is hidden behind
Docker's UDP proxy. The optional world events need the game's `gamedb.slt`
(`--game-db`, not included; mount it into the container).

Unraid: copy `server/` to `/mnt/user/appdata/forza-live/src`, build there, run with
`-v /mnt/user/appdata/forza-live/data:/data`. `docker inspect forza-live` shows the token.

## Operator endpoints

`GET /gift?to=<gamertag|XUID>&credits=<n>[&message=..]` or `&car=<id>`,
`GET /notify?to=..&type=..`, and `GET /world/event?session=all|<id>[&event=<id>]` are
operator-only. They are answered for requests from the server's own machine (loopback, not
through a reverse proxy), or with `FORZA_ADMIN_TOKEN` (header `X-Admin-Token: <token>` or
`?token=<token>`); everything else gets 403. From the host or Unraid terminal:

    docker exec forza-live python3 -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:21201/gift?to=Name&credits=50000').read())"

or from your LAN: `curl -H "X-Admin-Token: <token>" "http://192.168.1.x:21201/gift?..."`.
Without the token variable, remote use is impossible. Do not expose the token on the
internet side (it travels in plain HTTP).

## Limits (all untrusted input)

- per address: 16 players, 1500 datagrams/s, 2 new registrations/s, 32 HTTP connections
  (they stay open while idle: the game needs that);
- per player: relay budget 64 KB/s (`--rate-limit`), 30 open auctions, 50 unretrieved
  gifts, 100 shared cars; one upload at most 2 MB, HTTP bodies at most 8 MB;
- whole server: ghosts, cars and market blobs at most `FORZA_DISK_CAP_MB` (default 4096) MB,
  at most `FORZA_MAX_PLAYERS` (20000) player records;
- the status page lists gamertags and XUIDs but no IP addresses.

Players are not authenticated (the XUID is whatever the client claims).
