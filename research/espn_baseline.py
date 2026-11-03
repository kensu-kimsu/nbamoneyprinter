"""Train a lightweight NBA game-winner classifier using ESPN completed games.

Uses only information available before each game. Predictions are research-only;
this model is a new baseline, NOT the legacy 106-feature XGBoost model.
"""
import datetime as dt
import json
import math
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "live_predictions"
API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"


def fetch_day(day):
    url = API + "?" + urllib.parse.urlencode({"dates": day.strftime("%Y%m%d")})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=18) as response:
        return json.load(response).get("events", [])


def parse_game(event):
    competition = event["competitions"][0]
    teams = {x["homeAway"]: x for x in competition["competitors"]}
    start = dt.datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    state = event["status"]["type"]["state"]
    game = {
        "game_id": str(event["id"]), "tipoff_utc": start,
        "home": teams["home"]["team"]["displayName"],
        "away": teams["away"]["team"]["displayName"],
        "home_id": str(teams["home"]["team"]["id"]),
        "away_id": str(teams["away"]["team"]["id"]),
        "state": state,
    }
    if state == "post":
        game["home_score"] = int(float(teams["home"]["score"]))
        game["away_score"] = int(float(teams["away"]["score"]))
    return game


def features(game, history):
    def team_values(team):
        recent = history.get(team, [])[-10:]
        if not recent:
            return 0.5, 0.0, 0.0, 0
        return (sum(x[0] for x in recent) / len(recent),
                sum(x[1] for x in recent) / len(recent) / 20.0,
                sum(x[2] for x in recent) / len(recent) / 20.0,
                len(recent))
    h, a = team_values(game["home_id"]), team_values(game["away_id"])
    return [h[0] - a[0], h[1] - a[1], h[2] - a[2],
            min(h[3], 10) / 10, min(a[3], 10) / 10]


def update(game, history):
    home = game["home_score"]
    away = game["away_score"]
    if home == away:
        return
    history.setdefault(game["home_id"], []).append((int(home > away), home-away, home))
    history.setdefault(game["away_id"], []).append((int(away > home), away-home, away))


def run(now=None):
    from sklearn.linear_model import LogisticRegression
    import numpy as np
    now = now or dt.datetime.now(dt.timezone.utc)
    # 75 days: sufficient early-season observations without relying on blocked NBA stats API.
    dates = [now.date() - dt.timedelta(days=d) for d in range(75, -2, -1)]
    events = {}
    errors = []
    for day in dates:
        try:
            for item in fetch_day(day):
                game = parse_game(item)
                events[game["game_id"]] = game
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"date": str(day), "error": type(exc).__name__})
        time.sleep(0.12)
    games = sorted(events.values(), key=lambda g: (g["tipoff_utc"], g["game_id"]))
    history, x, y, upcoming = {}, [], [], []
    for game in games:
        if game["tipoff_utc"] >= now and game["state"] == "pre":
            upcoming.append((game, features(game, history)))
        elif game["state"] == "post" and game["tipoff_utc"] < now:
            # Do not leak results of simultaneous games: group equal tipoff times below.
            pass
    history = {}
    for tipoff in sorted({g["tipoff_utc"] for g in games}):
        batch = [g for g in games if g["tipoff_utc"] == tipoff]
        if tipoff >= now:
            for game in batch:
                if game["state"] == "pre":
                    upcoming.append((game, features(game, history)))
            continue
        for game in batch:
            if game["state"] == "post" and game.get("home_score") != game.get("away_score"):
                if len(history.get(game["home_id"], [])) >= 3 and len(history.get(game["away_id"], [])) >= 3:
                    x.append(features(game, history))
                    y.append(int(game["home_score"] > game["away_score"]))
        for game in batch:
            if game["state"] == "post":
                update(game, history)
    # Rebuild upcoming only with the full available pregame history.
    upcoming = [(g, features(g, history)) for g in games if g["tipoff_utc"] > now and g["state"] == "pre"]
    if len(x) < 50 or len(set(y)) != 2:
        raise RuntimeError(f"Insufficient training games ({len(x)}); no prediction emitted")
    if not upcoming:
        raise RuntimeError("No upcoming NBA games in fetched schedule; no prediction emitted")
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(np.asarray(x), np.asarray(y))
    probabilities = model.predict_proba(np.asarray([v for _, v in upcoming]))[:, 1]
    rows = []
    for (game, vector), home_p in zip(upcoming, probabilities):
        rows.append({
            "prediction_id": f"espn-baseline-{game['game_id']}-{now.strftime('%Y%m%dT%H%M%SZ')}",
            "game_id": game["game_id"],
            "home_team": game["home"], "away_team": game["away"],
            "game_time_utc": game["tipoff_utc"].isoformat(),
            "predicted_at_utc": now.isoformat(),
            "model_version": "espn-rolling-logistic-v1",
            "home_win_probability": round(float(home_p), 6),
            "away_win_probability": round(1-float(home_p), 6),
            "predicted_winner": game["home"] if home_p >= 0.5 else game["away"],
            "feature_values": vector, "training_games": len(x),
            "paper_bet": False, "data_source": "ESPN unofficial scoreboard",
        })
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / ("predictions-" + now.strftime("%Y%m%dT%H%M%SZ") + ".json")
    dest.write_text(json.dumps({"generated_at_utc": now.isoformat(), "model": "espn-rolling-logistic-v1",
                                "training_games": len(x), "fetch_errors": errors,
                                "predictions": rows}, indent=2), encoding="utf-8")
    print(json.dumps({"saved": str(dest.relative_to(ROOT)), "training_games": len(x),
                      "predictions": len(rows), "sample": rows[0]}, indent=2))
    return rows


if __name__ == "__main__":
    run()
