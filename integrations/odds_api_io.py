"""Read-only Odds-API.io v3 client. No betting/account actions."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.odds-api.io/v3"
DEFAULT_BOOKMAKERS = ("Sportsbet", "TAB", "Ladbrokes", "Neds")


class OddsApiError(RuntimeError):
    pass


def _request(endpoint, **params):
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        raise OddsApiError("ODDS_API_KEY is missing. Set it locally or in GitHub Actions secrets.")
    query = urlencode({"apiKey": key, **params})
    request = Request(
        f"{BASE_URL}/{endpoint}?{query}",
        headers={"Accept": "application/json", "User-Agent": "nbamoneyprinter/0.1"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not include URL or server body: URLs contain the secret key.
        raise OddsApiError(f"Odds-API.io returned HTTP {exc.code}. Check plan, permissions or rate limits.") from None
    except (URLError, TimeoutError, ValueError) as exc:
        raise OddsApiError(f"Odds-API.io request failed ({type(exc).__name__}).") from None


def get_sports():
    return _request("sports")


def get_leagues(sport="basketball"):
    return _request("leagues", sport=sport)


def get_events(league, sport="basketball", limit=20):
    """League must be a slug returned by get_leagues, not an assumed NBA key."""
    return _request("events", sport=sport, league=league, status="pending", limit=limit)


def get_odds(event_id, bookmakers=DEFAULT_BOOKMAKERS):
    """Bookmaker names must match the provider catalog and subscription."""
    if not event_id:
        raise ValueError("event_id is required")
    return _request("odds", eventId=event_id, bookmakers=",".join(bookmakers))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inspect Odds-API.io coverage (read-only)")
    parser.add_argument("action", choices=["sports", "leagues", "events", "odds"])
    parser.add_argument("--league", help="Exact league slug returned by 'leagues'")
    parser.add_argument("--event-id", help="Event ID returned by 'events'")
    parser.add_argument("--bookmakers", default=",".join(DEFAULT_BOOKMAKERS))
    args = parser.parse_args()
    try:
        if args.action == "sports":
            data = get_sports()
        elif args.action == "leagues":
            data = get_leagues()
        elif args.action == "events":
            if not args.league:
                parser.error("--league is required for events")
            data = get_events(args.league)
        else:
            if not args.event_id:
                parser.error("--event-id is required for odds")
            data = get_odds(args.event_id, args.bookmakers.split(","))
        print(json.dumps(data, indent=2))
    except OddsApiError as exc:
        parser.exit(1, f"Error: {exc}\n")
