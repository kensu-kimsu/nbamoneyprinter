"""Generate an SVG bankroll history from settled paper bets (standard library only)."""
import csv
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "paper_betting" / "ledger.csv"
CHART = ROOT / "paper_betting" / "bankroll.svg"
STARTING_BANKROLL = 100.0


def main():
    with LEDGER.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    points = [STARTING_BANKROLL]
    labels = ["Start"]
    for row in rows:
        if row.get("status", "").strip().lower() not in ("won", "lost", "push", "void"):
            continue
        try:
            profit = float(row["profit_aud"])
        except (ValueError, KeyError, TypeError):
            raise SystemExit(f"Missing/invalid profit for settled bet {row.get('bet_id')!r}")
        if row.get("bankroll_aud", "").strip():
            value = float(row["bankroll_aud"])
            if abs(value - (points[-1] + profit)) > 0.011:
                raise SystemExit(f"Bankroll mismatch on bet {row.get('bet_id')!r}")
        else:
            value = points[-1] + profit
        points.append(value)
        labels.append(row.get("bet_id", "")[:20] or f"Bet {len(points)-1}")
    width, height = 900, 320
    left, right, top, bottom = 78, 28, 55, 60
    low = min(points + [STARTING_BANKROLL])
    high = max(points + [STARTING_BANKROLL])
    padding = max(2, (high - low) * .15)
    low -= padding
    high += padding
    def xy(i, value):
        x = left + (width-left-right) * i / max(1, len(points)-1)
        y = height-bottom - (height-top-bottom) * (value-low)/(high-low)
        return x, y
    poly = " ".join(f"{xy(i,v)[0]:.1f},{xy(i,v)[1]:.1f}" for i,v in enumerate(points))
    baseline = xy(0, STARTING_BANKROLL)[1]
    ticks = []
    for j in range(5):
        value = low+(high-low)*j/4
        y = xy(0,value)[1]
        ticks.append(f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e4e7ec"/><text x="{left-12}" y="{y+4:.1f}" text-anchor="end" font-size="13" fill="#475467">A\u0024{value:.2f}</text>')
    status = "No settled paper bets yet" if len(points)==1 else f"{len(points)-1} settled bets · A\u0024{points[-1]:.2f} current"
    circles = "".join(f'<circle cx="{xy(i,v)[0]:.1f}" cy="{xy(i,v)[1]:.1f}" r="3.5" fill="#2563eb"><title>{html.escape(labels[i])}: A\u0024{v:.2f}</title></circle>' for i,v in enumerate(points))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="NBA paper betting bankroll history">
<rect width="{width}" height="{height}" rx="16" fill="#ffffff"/>
<text x="{left}" y="30" font-size="21" font-family="Arial,sans-serif" font-weight="bold" fill="#101828">Paper betting bankroll (AUD)</text>
<g font-family="Arial,sans-serif">{''.join(ticks)}
<line x1="{left}" x2="{width-right}" y1="{baseline:.1f}" y2="{baseline:.1f}" stroke="#98a2b3" stroke-dasharray="5 5"/>
<polyline points="{poly}" fill="none" stroke="#2563eb" stroke-width="3" stroke-linejoin="round"/>
{circles}
<text x="{left}" y="{height-25}" font-size="14" fill="#475467">Starting bankroll: A\u0024100.00</text>
<text x="{width-right}" y="{height-25}" text-anchor="end" font-size="14" fill="#475467">{html.escape(status)}</text></g></svg>'''
    CHART.write_text(svg, encoding="utf-8")
    print(status)


if __name__ == "__main__":
    main()
