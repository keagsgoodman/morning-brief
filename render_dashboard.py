"""Renders brief.json into an Artifact-ready HTML page (title + style + body content)."""

from datetime import datetime

# ---------------------------------------------------------------- formatting

def fmt_secs(s):
    if not s:
        return "—"
    s = int(s)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_pace(p):
    if not p:
        return "—"
    m = int(p)
    return f"{m}:{round((p - m) * 60):02d}/km"


def num(v, unit="", dp=0):
    if v is None:
        return "—"
    return f"{v:.{dp}f}{unit}" if isinstance(v, (int, float)) else f"{v}{unit}"


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def band(score):
    if score is None:
        return "unknown"
    return "good" if score >= 70 else "fair" if score >= 55 else "caution" if score >= 35 else "critical"


RISK_CLASS = {"Low": "good", "Slight": "fair", "Elevated": "caution", "High": "critical"}


# ---------------------------------------------------------------- charts

def gauge(score, label):
    """Semicircular readiness dial. 180deg arc, r=86, drawn in a 220x132 viewBox."""
    import math
    if score is None:
        score = 0
    cx, cy, r = 110, 112, 86
    def pt(frac):
        a = math.pi * (1 - frac)
        return cx + r * math.cos(a), cy - r * math.sin(a)
    x1, y1 = pt(0)
    x2, y2 = pt(1)
    ex, ey = pt(score / 100)
    large = 0
    track = f'M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f}'
    value = f'M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {ex:.1f} {ey:.1f}'
    return f'''<svg class="gauge" viewBox="0 0 220 132" role="img" aria-label="Readiness {score} out of 100">
  <path d="{track}" fill="none" stroke="var(--track)" stroke-width="16" stroke-linecap="round"/>
  <path d="{value}" fill="none" stroke="var(--sig)" stroke-width="16" stroke-linecap="round"/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="7" fill="var(--panel)" stroke="var(--sig)" stroke-width="4"/>
  <text x="110" y="98" class="gauge-num">{score}</text>
  <text x="110" y="122" class="gauge-lab">{esc(label)}</text>
</svg>'''


def line_chart(series, baseline=None, band_lo=None, band_hi=None, unit="", title=""):
    """series: list of (label, value). Returns an SVG line chart with optional baseline band."""
    pts = [(lab, v) for lab, v in series if v is not None]
    if len(pts) < 2:
        return '<p class="empty">Not enough data yet.</p>'
    W, H = 560, 190
    PL, PR, PT, PB = 40, 14, 18, 26
    vals = [v for _, v in pts]
    lo_candidates = vals + [x for x in (band_lo, baseline) if x]
    hi_candidates = vals + [x for x in (band_hi, baseline) if x]
    vmin, vmax = min(lo_candidates), max(hi_candidates)
    pad = max((vmax - vmin) * 0.15, 1)
    vmin, vmax = vmin - pad, vmax + pad
    def X(i):
        return PL + i * (W - PL - PR) / (len(pts) - 1)
    def Y(v):
        return PT + (vmax - v) / (vmax - vmin) * (H - PT - PB)

    parts = []
    if band_lo and band_hi:
        parts.append(f'<rect x="{PL}" y="{Y(band_hi):.1f}" width="{W-PL-PR}" '
                     f'height="{abs(Y(band_lo)-Y(band_hi)):.1f}" fill="var(--sig)" opacity="0.10"/>')
    if baseline:
        parts.append(f'<line x1="{PL}" y1="{Y(baseline):.1f}" x2="{W-PR}" y2="{Y(baseline):.1f}" '
                     f'stroke="var(--line)" stroke-width="1" stroke-dasharray="4 4"/>')
        parts.append(f'<text x="{PL+4}" y="{Y(baseline)-6:.1f}" class="ctick">'
                     f'baseline {baseline:g}</text>')
    d = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f} {Y(v):.1f}" for i, (_, v) in enumerate(pts))
    area = d + f" L{X(len(pts)-1):.1f} {H-PB} L{PL} {H-PB} Z"
    parts.append(f'<path d="{area}" fill="var(--sig)" opacity="0.08"/>')
    parts.append(f'<path d="{d}" fill="none" stroke="var(--sig)" stroke-width="2.2" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
    lx, lv = pts[-1]
    parts.append(f'<circle cx="{X(len(pts)-1):.1f}" cy="{Y(lv):.1f}" r="4.5" fill="var(--sig)"/>')
    for v in (vmin + pad, vmax - pad):
        parts.append(f'<text x="{PL-8}" y="{Y(v)+4:.1f}" class="ctick" text-anchor="end">{v:.0f}</text>')
    parts.append(f'<text x="{PL}" y="{H-6}" class="ctick">{esc(pts[0][0][5:])}</text>')
    parts.append(f'<text x="{W-PR}" y="{H-6}" class="ctick" text-anchor="end">{esc(lx[5:])}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{esc(title)}: latest {lv}{unit}">' + "".join(parts) + "</svg>")


def bar_chart(series, ref=None, unit="", title=""):
    """series: list of (label, value)."""
    pts = [(lab, v) for lab, v in series if v is not None]
    if not pts:
        return '<p class="empty">Not enough data yet.</p>'
    W, H = 560, 190
    PL, PR, PT, PB = 40, 14, 18, 26
    vmax = max([v for _, v in pts] + ([ref] if ref else [])) * 1.15 or 1
    bw = (W - PL - PR) / len(pts)
    parts = []
    if ref:
        y = PT + (1 - ref / vmax) * (H - PT - PB)
        parts.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="var(--line)" '
                     f'stroke-width="1" stroke-dasharray="4 4"/>')
        parts.append(f'<text x="{W-PR}" y="{y-5:.1f}" class="ctick" text-anchor="end">{ref:g}{unit}</text>')
    for i, (lab, v) in enumerate(pts):
        h = (v / vmax) * (H - PT - PB)
        x = PL + i * bw + bw * 0.18
        last = i == len(pts) - 1
        parts.append(f'<rect x="{x:.1f}" y="{H-PB-h:.1f}" width="{bw*0.64:.1f}" height="{max(h,1):.1f}" '
                     f'rx="2" fill="var(--sig)" opacity="{"1" if last else "0.45"}"/>')
    parts.append(f'<text x="{PL-8}" y="{PT+10}" class="ctick" text-anchor="end">{vmax:.0f}</text>')
    parts.append(f'<text x="{PL}" y="{H-6}" class="ctick">{esc(pts[0][0][5:])}</text>')
    parts.append(f'<text x="{W-PR}" y="{H-6}" class="ctick" text-anchor="end">{esc(pts[-1][0][5:])}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{esc(title)}: latest {pts[-1][1]}{unit}">' + "".join(parts) + "</svg>")


# ---------------------------------------------------------------- page

CSS = """
:root{
  --ground:#EDF0F4; --panel:#FFFFFF; --panel-2:#F5F7FA;
  --ink:#141A22; --muted:#5B6875; --faint:#8A96A3;
  --line:#C9D2DC; --track:#DCE3EB;
  --accent:#2F5D8C;
  --good:#1F7A5C; --fair:#4A7FA8; --caution:#A8721C; --critical:#A83E33;
  --good-bg:#E2F1EB; --fair-bg:#E4EDF5; --caution-bg:#F7EDDA; --critical-bg:#F7E4E1;
  --sig:var(--accent);
  --shadow:0 1px 2px rgba(20,26,34,.06), 0 8px 24px -12px rgba(20,26,34,.18);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#0E131C; --panel:#171E2A; --panel-2:#1E2634;
    --ink:#E6EBF2; --muted:#98A5B5; --faint:#6B7889;
    --line:#2C3646; --track:#242E3D;
    --accent:#6FA8DC;
    --good:#5CC79E; --fair:#79B2DC; --caution:#E0A94B; --critical:#E27A6C;
    --good-bg:#122A24; --fair-bg:#14212E; --caution-bg:#2C2415; --critical-bg:#2E1B18;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }
}
:root[data-theme="dark"]{
  --ground:#0E131C; --panel:#171E2A; --panel-2:#1E2634;
  --ink:#E6EBF2; --muted:#98A5B5; --faint:#6B7889;
  --line:#2C3646; --track:#242E3D;
  --accent:#6FA8DC;
  --good:#5CC79E; --fair:#79B2DC; --caution:#E0A94B; --critical:#E27A6C;
  --good-bg:#122A24; --fair-bg:#14212E; --caution-bg:#2C2415; --critical-bg:#2E1B18;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"Source Sans 3",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px; margin:0 auto; padding:20px 18px 64px}
h1,h2,h3{font-family:Archivo,"Source Sans 3",sans-serif; text-wrap:balance; margin:0}
.mono{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace; font-variant-numeric:tabular-nums}

header.top{display:flex; justify-content:space-between; align-items:baseline; gap:16px;
  flex-wrap:wrap; padding-bottom:14px; border-bottom:1px solid var(--line); margin-bottom:20px}
header.top h1{font-size:24px; font-weight:700; letter-spacing:-.015em}
header.top .when{font-size:12px; color:var(--faint); letter-spacing:.06em; text-transform:uppercase}

/* verdict */
.verdict{display:grid; grid-template-columns:220px 1fr; gap:24px; align-items:center;
  background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:20px 22px; box-shadow:var(--shadow); border-left:4px solid var(--sig)}
.verdict.good{--sig:var(--good)} .verdict.fair{--sig:var(--fair)}
.verdict.caution{--sig:var(--caution)} .verdict.critical{--sig:var(--critical)}
.verdict h2{font-size:26px; font-weight:700; letter-spacing:-.02em; line-height:1.2}
.verdict .sub{color:var(--muted); margin-top:6px; max-width:62ch}
.gauge{width:100%; max-width:220px; height:auto; display:block}
.gauge-num{font-family:"IBM Plex Mono",monospace; font-size:42px; font-weight:600;
  fill:var(--ink); text-anchor:middle; font-variant-numeric:tabular-nums}
.gauge-lab{font-family:Archivo,sans-serif; font-size:11px; fill:var(--faint);
  text-anchor:middle; letter-spacing:.14em; text-transform:uppercase}

/* generic panel */
.panel{background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:18px 20px}
.panel h3{font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--faint);
  font-weight:600; margin-bottom:12px}
.grid{display:grid; gap:16px; margin-top:16px}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}

/* risk */
.risk{border-left:4px solid var(--sig)}
.risk.good{--sig:var(--good); background:var(--good-bg)}
.risk.fair{--sig:var(--fair); background:var(--fair-bg)}
.risk.caution{--sig:var(--caution); background:var(--caution-bg)}
.risk.critical{--sig:var(--critical); background:var(--critical-bg)}
.risk .lvl{font-family:Archivo,sans-serif; font-size:19px; font-weight:700; color:var(--sig)}
.risk ul{margin:10px 0 0; padding-left:18px; color:var(--ink)}
.risk li{margin:4px 0}
.risk .advice{margin-top:10px; font-weight:600}

/* stat strip */
.stats{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:10px; overflow:hidden}
.stat{background:var(--panel); padding:14px 16px}
.stat .k{font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--faint)}
.stat .v{font-family:"IBM Plex Mono",monospace; font-size:24px; font-weight:600;
  font-variant-numeric:tabular-nums; margin-top:2px}
.stat .m{font-size:12px; color:var(--muted)}

/* metric rows */
.rows{display:flex; flex-direction:column; gap:0}
.row{display:flex; justify-content:space-between; align-items:baseline; gap:12px;
  padding:9px 0; border-bottom:1px dashed var(--line)}
.row:last-child{border-bottom:none}
.row .lab{color:var(--muted); font-size:14px}
.row .val{font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; font-weight:500}
.delta{font-size:12px; padding:1px 6px; border-radius:999px; margin-left:6px}
.delta.up{background:var(--critical-bg); color:var(--critical)}
.delta.down{background:var(--good-bg); color:var(--good)}
.delta.flat{background:var(--panel-2); color:var(--muted)}

/* session */
.session{border-left:4px solid var(--accent)}
.session .name{font-family:Archivo,sans-serif; font-size:19px; font-weight:700}
.session .meta{color:var(--muted); font-size:13px; margin-top:2px}
.session .desc{margin-top:10px; white-space:pre-wrap; font-size:14px;
  padding-top:10px; border-top:1px solid var(--line)}

/* bars in breakdown */
.bd{display:flex; flex-direction:column; gap:10px}
.bd .item{display:grid; grid-template-columns:98px 1fr 42px; gap:10px; align-items:center}
.bd .n{font-size:13px; color:var(--muted)}
.bd .t{height:7px; background:var(--track); border-radius:999px; overflow:hidden}
.bd .f{height:100%; background:var(--accent); border-radius:999px}
.bd .s{font-family:"IBM Plex Mono",monospace; font-size:13px; text-align:right;
  font-variant-numeric:tabular-nums}
.bd .d{grid-column:1/-1; font-size:12px; color:var(--faint); margin-top:-6px}

/* chart + table */
.chart{width:100%; height:auto; display:block}
.ctick{font-family:"IBM Plex Mono",monospace; font-size:11px; fill:var(--faint)}
.tablewrap{overflow-x:auto}
table{width:100%; min-width:430px; border-collapse:collapse; font-size:14px}
th{text-align:left; font-size:11px; letter-spacing:.08em; text-transform:uppercase;
  color:var(--faint); font-weight:600; padding:6px 10px 6px 0; border-bottom:1px solid var(--line)}
td{padding:8px 10px 8px 0; border-bottom:1px solid var(--line)}
td.n{font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; text-align:right}
th.n{text-align:right}
tr:last-child td{border-bottom:none}
.empty{color:var(--faint); font-size:14px; margin:0}
footer{margin-top:28px; padding-top:14px; border-top:1px solid var(--line);
  font-size:12px; color:var(--faint)}
@media (max-width:720px){
  .verdict{grid-template-columns:1fr; text-align:center}
  .verdict .sub{margin-inline:auto}
  .gauge{margin-inline:auto}
  .g2,.g3{grid-template-columns:1fr}
  .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
"""


def render_html(b):
    r = b["readiness"]
    ill = b["illness"]
    m = b["metrics"]
    st = b["stats"]
    cls = band(r["score"])
    rcls = RISK_CLASS.get(ill["level"], "fair")
    d = datetime.fromisoformat(b["date"])

    # --- readiness breakdown
    bd = "".join(
        f'<div class="item"><div class="n">{esc(x["name"])}</div>'
        f'<div class="t"><div class="f" style="width:{x["score"]}%"></div></div>'
        f'<div class="s">{x["score"]}</div>'
        f'<div class="d">{esc(x["detail"])}</div></div>'
        for x in r["breakdown"]) or '<p class="empty">No inputs available.</p>'

    # --- illness reasons
    reasons = ("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in ill["reasons"]) + "</ul>"
               if ill["reasons"] else
               '<p class="empty" style="margin-top:8px">No markers outside your normal range.</p>')

    # --- planned session
    if b["planned"]:
        sess = ""
        for p in b["planned"]:
            meta = " · ".join(x for x in [
                p.get("sport") or None,
                f'{p["duration_min"]} min' if p.get("duration_min") else None,
                f'{p["distance_km"]} km' if p.get("distance_km") else None] if x)
            sess += (f'<div class="name">{esc(p["title"])}</div>'
                     f'<div class="meta">{esc(meta) or "Scheduled"}</div>'
                     + (f'<div class="desc">{esc(p["description"])}</div>' if p.get("description") else ""))
    else:
        sess = ('<div class="name">Nothing scheduled</div>'
                '<div class="meta">No session on your TrainingPeaks calendar for today.</div>')

    # --- deltas
    def delta_pill(v, invert=False, unit=""):
        if v is None:
            return ""
        c = "flat" if abs(v) < 0.5 else ("down" if (v < 0) != invert else "up")
        return f'<span class="delta {c}">{v:+g}{unit}</span>'

    rows = [
        ("Resting HR", f'{num(m.get("rhr"))} bpm', delta_pill(m.get("rhr_delta"), unit=" bpm")),
        ("HRV last night", f'{num(m.get("hrv_last_night"))} ms',
         f'<span class="delta flat">{esc(m.get("hrv_status") or "")}</span>' if m.get("hrv_status") else ""),
        ("Overnight breathing", f'{num(m.get("resp_last_night"), dp=1)} br/min',
         delta_pill(m.get("resp_delta"))),
        ("Blood oxygen", f'{num(m.get("spo2_last_night"), "%")}', delta_pill(m.get("spo2_delta"), invert=True, unit="%")),
        ("Sleep", f'{num(m.get("sleep_hours"), " h", 1)}',
         f'<span class="delta flat">score {m["sleep_score"]}</span>' if m.get("sleep_score") else ""),
        ("Deep / REM", f'{num(m.get("sleep_deep_min"))} / {num(m.get("sleep_rem_min"))} min', ""),
        ("Overnight recharge", f'+{num(m.get("bb_overnight_charge"))} BB', ""),
        ("Average stress", num(m.get("stress_avg")),
         f'<span class="delta flat">usual {m["stress_baseline"]}</span>' if m.get("stress_baseline") else ""),
        ("Acute:chronic load", num(m.get("load_ratio"), dp=2),
         f'<span class="delta flat">{esc(m.get("load_source") or "")}</span>'),
    ]
    metric_rows = "".join(
        f'<div class="row"><span class="lab">{esc(a)}</span>'
        f'<span class="val">{b_}{c}</span></div>' for a, b_, c in rows)

    # --- stats strip
    sv = st.get("strava", {})
    stat_cells = "".join([
        f'<div class="stat"><div class="k">Today</div><div class="v">{st["day"]["km"]}<span style="font-size:14px"> km</span></div>'
        f'<div class="m">{st["day"]["count"]} session{"" if st["day"]["count"]==1 else "s"}</div></div>',
        f'<div class="stat"><div class="k">This week</div><div class="v">{st["week"]["km"]}<span style="font-size:14px"> km</span></div>'
        f'<div class="m">{st["week"]["hours"]} h moving</div></div>',
        f'<div class="stat"><div class="k">{d.strftime("%B")}</div><div class="v">{st["month"]["km"]}<span style="font-size:14px"> km</span></div>'
        f'<div class="m">{st["month"]["run_km"]} km running</div></div>',
        f'<div class="stat"><div class="k">{d.year} to date</div><div class="v">{st["year"]["km"]}<span style="font-size:14px"> km</span></div>'
        f'<div class="m">{st["year"]["hours"]} h · {st["year"]["elev_m"]:,} m climbed</div></div>',
    ])

    # --- recent activities
    if b["recent"]:
        recent = "".join(
            f'<tr><td class="n">{esc(x["date"][5:])}</td><td>{esc(x["name"] or x["type"])}</td>'
            f'<td class="n">{x["km"]:g}</td><td class="n">{x["min"]}</td>'
            f'<td class="n">{fmt_pace(x["pace_min_km"])}</td>'
            f'<td class="n">{num(x["avg_hr"])}</td></tr>' for x in b["recent"])
        recent_tbl = (f'<div class="tablewrap"><table><thead><tr><th class="n">Date</th><th>Session</th>'
                      f'<th class="n">km</th><th class="n">min</th><th class="n">Pace</th>'
                      f'<th class="n">Avg HR</th></tr></thead><tbody>{recent}</tbody></table></div>')
    else:
        recent_tbl = '<p class="empty">No recent activities.</p>'

    # --- fitness
    f = b["fitness"]
    fit_rows = "".join(
        f'<div class="row"><span class="lab">{esc(k)}</span><span class="val">{v}</span></div>'
        for k, v in [
            ("VO2 max", num(f.get("vo2max"), dp=1)),
            ("Training status", esc(f.get("training_status") or "—").replace("_", " ").title()),
            ("Predicted 5K", fmt_secs(f.get("race_5k"))),
            ("Predicted 10K", fmt_secs(f.get("race_10k"))),
            ("Predicted half", fmt_secs(f.get("race_half"))),
            ("Fitness age", num(f.get("fitness_age"))),
        ] if v != "—" or k in ("VO2 max", "Training status"))

    # --- charts
    hrv_chart = line_chart(m.get("hrv_series", []), band_lo=m.get("hrv_baseline_low"),
                           band_hi=m.get("hrv_baseline_high"), unit=" ms", title="HRV")
    rhr_chart = line_chart(m.get("rhr_series", []), baseline=m.get("rhr_baseline"),
                           unit=" bpm", title="Resting heart rate")
    sleep_chart = bar_chart([(x[0], x[1]) for x in m.get("sleep_series", [])], ref=7.5,
                            unit=" h", title="Sleep")
    wk = [(w["week"], w["km"]) for w in st.get("weekly_series", [])]
    week_chart = bar_chart(wk, unit=" km", title="Weekly distance")

    strava_note = ""
    if sv:
        gear = " · ".join(f'{esc(x["name"])} {x["km"]:g} km' for x in sv.get("gear", [])[:3] if not x.get("retired"))
        strava_note = (f'<div class="panel"><h3>Strava cross-check</h3><div class="rows">'
                       f'<div class="row"><span class="lab">Running this year</span>'
                       f'<span class="val">{sv["ytd_run_km"]:g} km · {sv["ytd_run_count"]} runs</span></div>'
                       f'<div class="row"><span class="lab">Last 4 weeks</span>'
                       f'<span class="val">{sv["recent_run_km"]:g} km</span></div>'
                       f'<div class="row"><span class="lab">All-time running</span>'
                       f'<span class="val">{sv["all_run_km"]:g} km</span></div>'
                       + (f'<div class="row"><span class="lab">Shoes</span>'
                          f'<span class="val" style="font-size:13px">{gear}</span></div>' if gear else "")
                       + '</div></div>')

    garmin_line = ""
    if r.get("garmin_score"):
        garmin_line = (f' Garmin’s own readiness reads {r["garmin_score"]}'
                       f'{" (" + esc(str(r["garmin_label"]).title()) + ")" if r.get("garmin_label") else ""}.')

    return f'''<title>Morning Readiness</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Source+Sans+3:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <header class="top">
    <h1>{d.strftime("%A")}, {d.strftime("%-d %B %Y")}</h1>
    <div class="when">Brief generated {esc(b["generated_at"][11:16])} · {esc(r["coverage"])}</div>
  </header>

  <section class="verdict {cls}">
    {gauge(r["score"], "Readiness")}
    <div>
      <h2>{esc(r["verdict"])}</h2>
      <p class="sub">{esc(ill["advice"])}{garmin_line}</p>
    </div>
  </section>

  <div class="grid g2">
    <div class="panel risk {rcls}">
      <h3>Illness risk</h3>
      <div class="lvl">{esc(ill["level"])}</div>
      {reasons}
    </div>
    <div class="panel session">
      <h3>Today&rsquo;s session</h3>
      {sess}
    </div>
  </div>

  <div class="grid"><div class="stats">{stat_cells}</div></div>

  <div class="grid g2">
    <div class="panel"><h3>Readiness breakdown</h3><div class="bd">{bd}</div></div>
    <div class="panel"><h3>This morning&rsquo;s numbers</h3><div class="rows">{metric_rows}</div></div>
  </div>

  <div class="grid g2">
    <div class="panel"><h3>HRV vs your balanced range</h3>{hrv_chart}</div>
    <div class="panel"><h3>Resting heart rate, {len(m.get("rhr_series", []))} days</h3>{rhr_chart}</div>
    <div class="panel"><h3>Sleep hours</h3>{sleep_chart}</div>
    <div class="panel"><h3>Weekly distance</h3>{week_chart}</div>
  </div>

  <div class="grid g2">
    <div class="panel"><h3>Recent sessions</h3>{recent_tbl}</div>
    <div class="panel"><h3>Fitness</h3><div class="rows">{fit_rows}</div></div>
  </div>

  {f'<div class="grid">{strava_note}</div>' if strava_note else ""}

  <footer>
    Readiness is a weighted blend of HRV against your personal baseline, sleep, resting heart rate,
    overnight recharge and acute:chronic load — scored only on the inputs that had data.
    Illness risk is a points model over resting HR, HRV, breathing rate, blood oxygen, recharge and stress.
    Neither is a medical assessment.
  </footer>
</div>'''
