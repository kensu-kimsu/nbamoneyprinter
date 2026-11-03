"""Read-only HaterPicks NBA odds feed. No wagering or account actions."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://www.haterpicks.app/api/v1/odds?sport=NBA"


class HaterPicksError(RuntimeError):
    pass


def get_nba_odds():
    key = os.getenv("HATERPICKS_API_KEY", "").strip()
    if not key:
        raise HaterPicksError("HATERPICKS_API_KEY is missing")
    request = Request(URL, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "nbamoneyprinter/0.1",
    })
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.load(response)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise HaterPicksError("Unexpected odds response format")
            return payload
    except HTTPError as exc:
        raise HaterPicksError(f"Provider returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, ValueError) as exc:
        raise HaterPicksError(f"Request failed: {type(exc).__name__}") from None


def summarize(payload):
    rows = payload["data"]
    markets = sorted({str(row.get("market", "unknown")) for row in rows if isinstance(row, dict)})
    books = sorted({book for row in rows if isinstance(row, dict) and isinstance(row.get("prices"), dict) for book in row["prices"]})
    return {
        "generated_at": payload.get("generated_at"),
        "rows": len(rows),
        "markets": markets,
        "bookmakers": books,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(summarize(get_nba_odds()), indent=2))
    except HaterPicksError as exc:
        raise SystemExit(f"ERROR: {exc}")
