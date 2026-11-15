#!/usr/bin/env python3
"""
EQM Ribbon: dagelijkse controle en ntfy-pushmelding bij een wissel.

Rekent exact zoals de app (index.html):
  * EQM: power law-fit (kleinste kwadraten in log10-log10) op alle data t/m
    gisteren, elke 7 dagen opnieuw (vanaf rij 730); risk = aandeel eerdere
    afwijkingen <= afwijking van vandaag (op de slotkoers, gelijke weging)
  * Ribbon: EMA 7 (snel) en EMA 120 (traag) van het risk;
    long bij snel - traag >= +2,5 punten, cash bij <= -2,0, daartussen transitie

De laatst gemelde toestand staat in data/ribbon-state.json. Wijkt de toestand
van vandaag daarvan af, dan gaat er een melding naar https://ntfy.sh/<NTFY_TOPIC>.
Alleen standaardbibliotheek, geen extra pakketten nodig.
"""
import bisect, csv, json, math, os, sys, urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "btc-usd-daily.csv")
STATE = os.path.join(ROOT, "data", "ribbon-state.json")
APP = "https://rcaljouw.github.io/btc-price-history/#eqm"

EQ_MIN, EQ_STEP = 730, 7
NF, NS, MU, MD = 7, 120, 0.025, 0.020
GEN = date(2009, 1, 3)
NAMES = {0: "Cash", 1: "Transitie", 2: "Long", 3: "Transitie"}
GROUP = {0: "cash", 1: "transitie", 2: "long", 3: "transitie"}


def load():
    rows = []
    with open(DATA, newline="") as f:
        for r in csv.DictReader(f):
            try:
                c = float(r["close"])
                d = date.fromisoformat(r["date"])
            except (KeyError, ValueError):
                continue
            if c > 0:
                rows.append((d, c))
    rows.sort()
    out = []
    for d, c in rows:  # dubbele datums: laatste telt (zoals een Map in de app)
        if out and out[-1][0] == d:
            out[-1] = (d, c)
        else:
            out.append((d, c))
    return out


def compute(rows):
    n = len(rows)
    x = [math.log10((d - GEN).days) for d, _ in rows]
    y = [math.log10(c) for _, c in rows]
    risk = [None] * n
    a = b = 0.0
    rs = []
    sx = sy = sxx = sxy = 0.0
    cum = []
    for i in range(n):
        sx += x[i]; sy += y[i]; sxx += x[i] * x[i]; sxy += x[i] * y[i]
        cum.append((sx, sy, sxx, sxy))
    for t in range(EQ_MIN, n):
        if (t - EQ_MIN) % EQ_STEP == 0:
            m = t
            X, Y, XX, XY = cum[m - 1]
            b = (m * XY - X * Y) / (m * XX - X * X)
            a = (Y - b * X) / m
            rs = sorted(y[j] - (a + b * x[j]) for j in range(m))
        r = y[t] - (a + b * x[t])
        risk[t] = bisect.bisect_right(rs, r) / len(rs)
    af, as_ = 2 / (NF + 1), 2 / (NS + 1)
    F = S = risk[EQ_MIN]
    cur = 0
    st, fs, ss = [None] * n, [None] * n, [None] * n
    for t in range(EQ_MIN, n):
        F += af * (risk[t] - F)
        S += as_ * (risk[t] - S)
        d = F - S
        if cur in (2, 3):
            cur = 2 if d > 0 else (0 if -d >= MD else 3)
        else:
            cur = 0 if d < 0 else (2 if d >= MU else 1)
        st[t], fs[t], ss[t] = cur, F, S
    return risk, st, fs, ss


def nl(v, dec=0):
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def notify(topic, title, body, tags, prio):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), method="POST",
        headers={"Title": title.encode("utf-8").decode("latin-1", "ignore"),
                 "Tags": tags, "Priority": prio, "Click": APP})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status


def message(uitleg, today, close, rk, f, s, gap):
    sign = "+" if gap >= 0 else "-"
    return (f"{uitleg}\n"
            f"Slotkoers {today:%d-%m-%Y}: ${nl(close)}\n"
            f"EQM-risk {nl(rk*100,1)}% | snel {nl(f*100,1)} | traag {nl(s*100,1)} | verschil {sign}{nl(abs(gap),1)} pt\n"
            f"(standaardinstellingen 7 / 120 / 2,5 / 2)")


def main():
    rows = load()
    risk, st, fs, ss = compute(rows)
    t = len(rows) - 1
    today, close = rows[t]
    cur = st[t]
    i = t
    while i > EQ_MIN and GROUP[st[i - 1]] == GROUP[cur]:
        i -= 1
    since = rows[i][0]
    gap = (fs[t] - ss[t]) * 100
    info = {"date": today.isoformat(), "state": GROUP[cur], "since": since.isoformat(),
            "close": round(close, 2), "risk": round(risk[t], 4),
            "fast": round(fs[t], 4), "slow": round(ss[t], 4)}
    print(json.dumps(info, ensure_ascii=False))

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if os.environ.get("RIBBON_TEST") == "1":  # handmatige test vanuit GitHub Actions
        if not topic:
            print("NTFY_TOPIC niet ingesteld.", file=sys.stderr); return 1
        body = message(f"Testmelding. De ribbon staat op {NAMES[cur]} sinds {since:%d-%m-%Y}.", today, close, risk[t], fs[t], ss[t], gap)
        print("ntfy test:", notify(topic, "Ribbon-test: meldingen werken", body, "white_check_mark", "default"))
        return 0

    prev = None
    if os.path.exists(STATE):
        with open(STATE) as f:
            prev = json.load(f)
    if prev is None:
        print("Eerste run: toestand vastgelegd, geen melding.")
    elif prev.get("state") == info["state"]:
        print("Geen wissel.")
    else:
        old, new = prev.get("state"), info["state"]
        nm = {"cash": "Cash", "transitie": "Transitie", "long": "Long"}
        title = f"Ribbon: {nm.get(old, old)} -> {nm[new]}"
        if new == "transitie":
            uitleg = ("Snelle en trage lijn zijn gekruist, nog niet bevestigd. "
                      + ("Lopende long wordt vastgehouden; let op." if old == "long" else "Nog geen nieuwe positie."))
        elif new == "cash":
            uitleg = "Bevestigde uitstap: de snelle lijn ligt duidelijk onder de trage."
        else:
            uitleg = "Bevestigd long: de snelle lijn ligt duidelijk boven de trage."
        body = message(uitleg, today, close, risk[t], fs[t], ss[t], gap)
        tags = {"long": "chart_with_upwards_trend", "cash": "warning", "transitie": "hourglass"}[new]
        prio = "high" if new in ("long", "cash") else "default"
        if not topic:
            print("NTFY_TOPIC niet ingesteld; melding niet verstuurd:\n" + title + "\n" + body)
        else:
            try:
                print("ntfy:", notify(topic, title, body, tags, prio))
            except Exception as e:  # melding mislukt: toestand niet bijwerken, morgen opnieuw
                print("Melding mislukt:", e, file=sys.stderr)
                return 1
    with open(STATE, "w") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
