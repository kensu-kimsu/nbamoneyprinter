"""Exploratory walk-forward 2025-26 NBA backtest, not verified executable returns.

Historical CSV odds lack capture timestamps. Uses ONLY earlier-game outcomes
to construct features and train the model. Market odds are used for selection
and settlement, never as model features.
"""
import csv
import datetime as dt
import json
import math
import pathlib
import sys

START=dt.date(2025,10,1)
END=dt.date(2026,7,1)
FEATURE_LOOKBACK=10

def price(american):
    a=float(american)
    if not math.isfinite(a) or abs(a)<100 or a==0: raise ValueError("invalid American odds")
    return 1+a/100 if a>0 else 1+100/abs(a)

def vector(home,away,history):
    def vals(team):
        h=history.get(team,[])[-FEATURE_LOOKBACK:]
        if not h:return (0.5,0.0,0.0,0)
        return (sum(x[0] for x in h)/len(h),
                sum(x[1] for x in h)/len(h)/20,
                sum(x[2] for x in h)/len(h)/20,len(h))
    h,a=vals(home),vals(away)
    return [h[0]-a[0],h[1]-a[1],h[2]-a[2],min(h[3],10)/10,min(a[3],10)/10]

def main(source,output):
    from sklearn.linear_model import LogisticRegression
    import numpy as np
    with open(source,newline="",encoding="utf-8-sig") as f: raw=list(csv.DictReader(f))
    games=[]
    for row in raw:
        try:
            date=dt.date.fromisoformat(row["Date"])
            home=row["Home"].strip()
            away=row["Away"].strip()
            hp,ap=price(row["ML_Home"]),price(row["ML_Away"])
            win=int(row["home_win"])
            total=float(row["Points"])
            margin=float(row["Win_Margin"])
            home_points=(total+margin)/2
            away_points=(total-margin)/2
            if not all(math.isfinite(v) and v>=0 for v in (home_points,away_points)):continue
            if not home or not away or home==away or win not in (0,1):continue
            games.append((date,home,away,hp,ap,win,home_points,away_points))
        except (ValueError,KeyError,TypeError,OverflowError):continue
    games.sort(key=lambda g:(g[0],g[1],g[2]))
    if not games:raise RuntimeError("No valid historical games")
    history={}
    x_train,y_train=[],[]
    report_rows=[]
    unique=set()
    for date in sorted({g[0] for g in games}):
        batch=[g for g in games if g[0]==date]
        pending=[]
        # Every same-day game is predicted before updating that day's results.
        for day,home,away,hp,ap,win,home_points,away_points in batch:
            key=(day,home,away)
            if key in unique:raise RuntimeError("Duplicate game "+str(key))
            unique.add(key)
            feat=vector(home,away,history)
            if START<=day<END and len(x_train)>=300 and len(set(y_train))==2:
                # Strict chronological training; no target-season future results.
                model=LogisticRegression(max_iter=300,random_state=42)
                model.fit(np.asarray(x_train),np.asarray(y_train))
                p=float(model.predict_proba(np.asarray([feat]))[0,1])
                p=min(.999999,max(.000001,p))
                report_rows.append({"date":str(day),"home":home,"away":away,
                    "home_prob":p,"away_prob":1-p,"home_odds":hp,"away_odds":ap,
                    "home_win":win,"training_games":len(x_train)})
            pending.append((home,away,win,feat,home_points,away_points))
        # Update only after all games of that date were evaluated.
        for home,away,win,feat,home_points,away_points in pending:
            x_train.append(feat);y_train.append(win)
            history.setdefault(home,[]).append((win,home_points-away_points,home_points))
            history.setdefault(away,[]).append((1-win,away_points-home_points,away_points))
    # Note: intentionally uses only rolling win-rate feature in practical effect;
    # margin and points features are zero because CSV has no per-team final scores.
    strategies={"old":{"balance":100.0,"bets":0,"wins":0,"losses":0,"peak":100.0,"max_dd":0.0},
                "new":{"balance":100.0,"bets":0,"wins":0,"losses":0,"peak":100.0,"max_dd":0.0}}
    for r in report_rows:
        opts=[("home",r["home_prob"],r["home_odds"]),("away",r["away_prob"],r["away_odds"])]
        old=max(opts,key=lambda o:o[1]*o[2]-1)
        winner=max(opts,key=lambda o:o[1])
        for name,q,accept in [
            ("old",old,old[1]*old[2]-1>=.05),
            ("new",winner,winner[1]>=.60 and winner[2]<=2 and winner[1]*winner[2]-1>=.08)]:
            if not accept:continue
            s=strategies[name];stake=round(s["balance"]*.01,2)
            if stake<=0:continue
            won=(q[0]=="home")==bool(r["home_win"])
            s["balance"]=round(s["balance"]+(round(stake*(q[2]-1),2) if won else -stake),2)
            s["bets"]+=1;s["wins" if won else "losses"]+=1
            s["peak"]=max(s["peak"],s["balance"])
            s["max_dd"]=max(s["max_dd"],100*(s["peak"]-s["balance"])/s["peak"])
    for s in strategies.values():
        s["profit_aud"]=round(s["balance"]-100,2)
        s["roi_pct"]=s["profit_aud"]
        s["max_drawdown_pct"]=round(s.pop("max_dd"),2)
        s.pop("peak")
    result={"status":"exploratory_not_verified","season":"2025-26",
        "historical_source_rows":len(raw),"target_season_games":sum(START<=g[0]<END for g in games),
        "walk_forward_predictions":len(report_rows),"strategies":strategies,
        "model":"chronological logistic regression, rolling win-rate features, re-fit before each date",
        "warnings":["Historical moneylines lack source capture timestamps; prices may be closing or revised.",
        "Model is a simplified reconstruction, NOT the original live ESPN rolling logistic model.",
        "Sequential 1% stakes; 5% concurrent exposure limit not simulated.",
        "Selection thresholds were chosen after seeing recent results; this season is not a clean prospective test.",
        "No bookmaker availability, limits, voids, or transaction fees modeled."]}
    out=pathlib.Path(output);out.mkdir(parents=True,exist_ok=True)
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    with (out/"predictions.csv").open("w",newline="") as f:
        if report_rows:
            w=csv.DictWriter(f,fieldnames=list(report_rows[0]));w.writeheader();w.writerows(report_rows)
    print(json.dumps(result,indent=2))
    if not report_rows:raise RuntimeError("No out-of-sample predictions generated")

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: python -m research.walkforward_2025_26 SOURCE.csv OUTPUT_DIR")
    main(sys.argv[1],sys.argv[2])
