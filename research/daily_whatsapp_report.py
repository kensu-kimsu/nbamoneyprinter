"""Daily Melbourne-time NBA paper-trading summary and optional Twilio WhatsApp delivery.

Requires an approved Twilio WhatsApp Content Template with a single {{1}}
variable for the complete report. No credentials are stored in this repository.
"""
import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
import base64
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "prediction_results"
TZ = ZoneInfo("Australia/Melbourne")

def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def create_report(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(TZ).date()
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    comparison = json.loads((OUT / "bankroll_comparison.json").read_text(encoding="utf-8"))
    daily = read_csv(OUT / "bankroll_daily_history.csv")
    if not daily or daily[-1]["date_melbourne"] != today.isoformat():
        raise RuntimeError("Daily bankroll history is missing today's Melbourne date")
    audit_at = dt.datetime.fromisoformat(summary["generated_at_utc"].replace("Z","+00:00"))
    if (now-audit_at).total_seconds()>7200:
        raise RuntimeError("Prediction audit is older than two hours; refusing stale report")
    latest = daily[-1]
    previous = daily[-2] if len(daily)>1 else {"all_ai_picks_aud":"100","filtered_ev_aud":"100"}
    all_delta = float(latest["all_ai_picks_aud"])-float(previous["all_ai_picks_aud"])
    filtered_delta = float(latest["filtered_ev_aud"])-float(previous["filtered_ev_aud"])
    bets = read_csv(ROOT / "paper_betting" / "ledger.csv")
    # Report settled game outcomes by game date, not time of ledger update.
    today_bets = [b for b in bets if b["status"]=="settled" and b.get("profit_aud")
                  and dt.datetime.fromisoformat(b["game_time_utc"].replace("Z","+00:00")).astimezone(TZ).date()==today]
    wins = sum(b["result"]=="won" for b in today_bets)
    losses = sum(b["result"]=="lost" for b in today_bets)
    report = (
        f"NBA Money Printer | {today:%d %b %Y} (Melbourne)\n"
        f"AI accuracy: {summary['correct_predictions']}/{summary['final_games']} "
        f"({summary['accuracy_pct'] if summary['accuracy_pct'] is not None else 'N/A'}%)\n"
        f"All AI picks: A${float(latest['all_ai_picks_aud']):.2f} (day {all_delta:+.2f})\n"
        f"Filtered EV: A${float(latest['filtered_ev_aud']):.2f} (day {filtered_delta:+.2f})\n"
        f"Today's settled bets: {wins}W/{losses}L; "
        f"profit A${sum(float(b['profit_aud']) for b in today_bets):+.2f}\n"
        f"Total settled filtered bets: {comparison['filtered_actual']['settled_bets']}; "
        f"open: {comparison['filtered_actual']['open_bets']}\n"
        f"Upcoming AI predictions: {summary['upcoming']}\n"
        "Paper trading only. https://github.com/kensu-kimsu/nbamoneyprinter"
    )
    return report

def send_whatsapp(report):
    names=("TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","TWILIO_WHATSAPP_FROM",
           "WHATSAPP_TO","TWILIO_CONTENT_SID")
    values={name:os.environ.get(name,"").strip() for name in names}
    missing=[name for name in names if not values[name]]
    if missing:
        print("WhatsApp disabled: missing "+", ".join(missing))
        return False
    for name in ("TWILIO_WHATSAPP_FROM","WHATSAPP_TO"):
        if not values[name].startswith("whatsapp:+"):
            raise ValueError(name+" must be formatted whatsapp:+<countrycode><number>")
    url="https://api.twilio.com/2010-04-01/Accounts/"+urllib.parse.quote(values["TWILIO_ACCOUNT_SID"],safe="")+"/Messages.json"
    data=urllib.parse.urlencode({
        "From":values["TWILIO_WHATSAPP_FROM"],"To":values["WHATSAPP_TO"],
        "ContentSid":values["TWILIO_CONTENT_SID"],
        "ContentVariables":json.dumps({"1":report},ensure_ascii=False)
    }).encode("utf-8")
    auth=base64.b64encode((values["TWILIO_ACCOUNT_SID"]+":"+values["TWILIO_AUTH_TOKEN"]).encode()).decode()
    req=urllib.request.Request(url,data=data,headers={"Authorization":"Basic "+auth,
        "Content-Type":"application/x-www-form-urlencoded"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            result=json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Twilio WhatsApp request failed with HTTP {exc.code}; check approved template and sender configuration") from None
    print("Twilio accepted WhatsApp message SID:",result.get("sid","unknown"),
          "status:",result.get("status","unknown"))
    return True

def run():
    report=create_report()
    print(report)
    send_whatsapp(report)

if __name__=="__main__":
    run()
