"""Settle virtual NBA moneyline bets only after ESPN reports a final score."""
import csv
import datetime as dt
import json
import urllib.request
from zoneinfo import ZoneInfo
from paper_betting.select_bets import LEDGER, HEADERS, norm, timestamp

def scoreboard(day):
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=" + day.strftime("%Y%m%d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)["events"]

def winner(event, bet):
    if str(event.get("id")) != str(bet["game_id"]):
        return None
    status = event.get("status", {}).get("type", {})
    if status.get("completed") is not True or status.get("state") != "post":
        return None
    competition = event["competitions"][0]
    sides = {c.get("homeAway"): c for c in competition.get("competitors", [])}
    if "home" not in sides or "away" not in sides:
        return None
    home, away = sides["home"], sides["away"]
    if norm(home["team"]["displayName"]) != norm(bet["home_team"]):
        return None
    if norm(away["team"]["displayName"]) != norm(bet["away_team"]):
        return None
    home_score, away_score = int(home["score"]), int(away["score"])
    if home_score == away_score:
        return None
    return home["team"]["displayName"] if home_score > away_score else away["team"]["displayName"]

def run():
    with LEDGER.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pending = [r for r in rows if r["status"] == "open" and timestamp(r["game_time_utc"]) < dt.datetime.now(dt.timezone.utc)]
    dates = {timestamp(r["game_time_utc"]).astimezone(ZoneInfo("America/New_York")).date() for r in pending}
    events = {}
    for day in dates:
        for event in scoreboard(day):
            events[str(event["id"])] = event
    changed = 0
    balance = round(100 + sum(float(r["profit_aud"]) for r in rows if r["status"] == "settled" and r["profit_aud"]), 2)
    for row in rows:
        if row not in pending:
            continue
        event = events.get(str(row["game_id"]))
        winning_team = winner(event, row) if event else None
        if winning_team is None:
            continue
        won = norm(row["selection"]) == norm(winning_team)
        profit = round(float(row["stake_aud"]) * (float(row["decimal_odds"]) - 1), 2) if won else -float(row["stake_aud"])
        balance = round(balance + profit, 2)
        row.update(status="settled", result="won" if won else "lost", profit_aud=f"{profit:.2f}", bankroll_aud=f"{balance:.2f}")
        changed += 1
    if changed:
        tmp = LEDGER.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(LEDGER)
    print(json.dumps({"settled_now": changed, "remaining_open": sum(r["status"] == "open" for r in rows), "bankroll_aud": balance}, indent=2))

if __name__ == "__main__":
    run()
