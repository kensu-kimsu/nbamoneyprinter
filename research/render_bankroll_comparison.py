"""Build README SVG of both realized virtual bankrolls from experiment day one.

Daily values are end-of-day (Australia/Melbourne) realized balances. Open bets
and unpriced hypothetical predictions do not change balances.
"""
import csv
import datetime as dt
import html
import json
from collections import defaultdict
from zoneinfo import ZoneInfo
from paper_betting.select_bets import ROOT, timestamp

TZ = ZoneInfo("Australia/Melbourne")
START = dt.date(2026, 11, 4)
OUT = ROOT / "research" / "prediction_results"
SVG = ROOT / "paper_betting" / "bankroll_comparison.svg"

def day(value):
    return timestamp(value).astimezone(TZ).date()

def series():
    all_daily = defaultdict(float)
    filtered_daily = defaultdict(float)
    with (OUT / "all_picks_hypothetical.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["simulation_status"] in ("won", "lost") and row["profit_aud"]:
                all_daily[day(row["game_time_utc"])] += float(row["profit_aud"])
    with (ROOT / "paper_betting" / "ledger.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] != "settled" or not row["profit_aud"]:
                continue
            # Prefer the settlement timestamp where recorded; otherwise use
            # scheduled game day and disclose this approximation in the README.
            settled_at = row.get("settled_at_utc") or row.get("settled_at")
            date = day(settled_at or row["game_time_utc"])
            filtered_daily[date] += float(row["profit_aud"])
    today = dt.datetime.now(dt.timezone.utc).astimezone(TZ).date()
    last = max([START, today, *all_daily.keys(), *filtered_daily.keys()])
    dates = [START + dt.timedelta(days=i) for i in range((last-START).days+1)]
    all_balance, filtered_balance = 100.0, 100.0
    rows = []
    for date in dates:
        all_balance = round(all_balance + all_daily[date], 2)
        filtered_balance = round(filtered_balance + filtered_daily[date], 2)
        rows.append((date,all_balance,filtered_balance))
    return rows

def render(rows):
    width,height=1000,420
    left,right,top,bottom=84,28,76,72
    plot_w,plot_h=width-left-right,height-top-bottom
    values=[v for _,a,b in rows for v in (a,b)]
    lo=min(100,*values)-1
    hi=max(100,*values)+1
    if hi-lo<4:
        mid=(hi+lo)/2
        lo,hi=mid-2,mid+2
    def x(i):
        return left + plot_w*i/max(1,len(rows)-1)
    def y(v):
        return top+(hi-v)*plot_h/(hi-lo)
    def poly(index):
        return " ".join(f"{x(i):.1f},{y(row[index]):.1f}" for i,row in enumerate(rows))
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="NBA paper bankroll history for all AI picks and filtered positive EV bets">',
           '<rect width="100%" height="100%" fill="#0d1117"/>',
           '<text x="84" y="38" fill="#f0f6fc" font-family="Arial,sans-serif" font-size="23" font-weight="bold">NBA Paper Bankroll Progress</text>',
           '<text x="84" y="59" fill="#8b949e" font-family="Arial,sans-serif" font-size="13">Realized AUD • daily close • Australia/Melbourne • A$100 start</text>']
    for i in range(5):
        val=lo+(hi-lo)*i/4
        yy=y(val)
        parts.extend([f'<line x1="{left}" x2="{width-right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#30363d"/>',
                      f'<text x="{left-12}" y="{yy+5:.1f}" fill="#8b949e" text-anchor="end" font-family="Arial,sans-serif" font-size="12">{val:.2f}</text>'])
    if len(rows)>1:
        parts.append(f'<polyline fill="none" stroke="#58a6ff" stroke-width="3" stroke-linejoin="round" points="{poly(1)}"/>')
        parts.append(f'<polyline fill="none" stroke="#3fb950" stroke-width="3" stroke-linejoin="round" points="{poly(2)}"/>')
    else:
        for idx,color in ((1,"#58a6ff"),(2,"#3fb950")):
            parts.append(f'<circle cx="{x(0)}" cy="{y(rows[0][idx])}" r="4" fill="{color}"/>')
    for idx,color in ((1,"#58a6ff"),(2,"#3fb950")):
        parts.append(f'<circle cx="{x(len(rows)-1):.1f}" cy="{y(rows[-1][idx]):.1f}" r="4" fill="{color}"/>')
    tick_ids=sorted(set(round(i*(len(rows)-1)/min(5,max(1,len(rows)-1))) for i in range(min(5,max(1,len(rows)-1))+1)))
    for i in tick_ids:
        parts.append(f'<text x="{x(i):.1f}" y="{height-43}" text-anchor="middle" fill="#8b949e" font-family="Arial,sans-serif" font-size="12">{html.escape(rows[i][0].strftime("%d %b"))}</text>')
    parts.extend([f'<line x1="84" y1="{height-18}" x2="111" y2="{height-18}" stroke="#58a6ff" stroke-width="4"/>',
                  f'<text x="119" y="{height-13}" fill="#c9d1d9" font-family="Arial,sans-serif" font-size="13">All AI picks: A${rows[-1][1]:.2f}</text>',
                  f'<line x1="380" y1="{height-18}" x2="407" y2="{height-18}" stroke="#3fb950" stroke-width="4"/>',
                  f'<text x="415" y="{height-13}" fill="#c9d1d9" font-family="Arial,sans-serif" font-size="13">Filtered EV: A${rows[-1][2]:.2f}</text>',
                  '</svg>'])
    return "\n".join(parts)+"\n"

def run():
    rows=series()
    SVG.parent.mkdir(parents=True,exist_ok=True)
    SVG.write_text(render(rows),encoding="utf-8")
    (OUT/"bankroll_daily_history.csv").write_text(
        "date_melbourne,all_ai_picks_aud,filtered_ev_aud\n"+
        "".join(f"{d.isoformat()},{a:.2f},{b:.2f}\n" for d,a,b in rows),encoding="utf-8")
    print(json.dumps({"chart":str(SVG.relative_to(ROOT)),"days":len(rows),
        "all_ai_picks_aud":rows[-1][1],"filtered_ev_aud":rows[-1][2]}))
if __name__=="__main__":
    run()
