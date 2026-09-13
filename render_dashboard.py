"""Renders brief.json into an Artifact-ready HTML page (title + style + body content)."""

import os
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
    parts.append('<circle class="hdot" r="5.5" fill="var(--sig)" stroke="var(--panel)" '
                 'stroke-width="2" opacity="0" pointer-events="none"/>')
    slice_w = (W - PL - PR) / max(len(pts) - 1, 1)
    for i, (lab, v) in enumerate(pts):
        parts.append(
            f'<rect class="hit" x="{X(i) - slice_w / 2:.1f}" y="{PT}" width="{slice_w:.1f}" '
            f'height="{H - PT - PB}" fill="transparent" data-l="{esc(lab)}" data-v="{v:g}" '
            f'data-u="{esc(unit)}" data-cx="{X(i):.1f}" data-cy="{Y(v):.1f}"/>')
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
    hits = []
    for i, (lab, v) in enumerate(pts):
        h = (v / vmax) * (H - PT - PB)
        x = PL + i * bw + bw * 0.18
        last = i == len(pts) - 1
        parts.append(f'<rect class="bar" x="{x:.1f}" y="{H-PB-h:.1f}" width="{bw*0.64:.1f}" '
                     f'height="{max(h,1):.1f}" rx="2" fill="var(--sig)" '
                     f'opacity="{"1" if last else "0.45"}"/>')
        # a full-height target makes small bars tappable on a phone
        hits.append(f'<rect class="hit" x="{PL + i * bw:.1f}" y="{PT}" width="{bw:.1f}" '
                    f'height="{H - PT - PB}" fill="transparent" data-l="{esc(lab)}" '
                    f'data-v="{v:g}" data-u="{esc(unit)}" data-bar="{i}"/>')
    parts.extend(hits)
    parts.append(f'<text x="{PL-8}" y="{PT+10}" class="ctick" text-anchor="end">{vmax:.0f}</text>')
    parts.append(f'<text x="{PL}" y="{H-6}" class="ctick">{esc(pts[0][0][5:])}</text>')
    parts.append(f'<text x="{W-PR}" y="{H-6}" class="ctick" text-anchor="end">{esc(pts[-1][0][5:])}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{esc(title)}: latest {pts[-1][1]}{unit}">' + "".join(parts) + "</svg>")


def stacked(parts, colors, unit="min"):
    """Horizontal stacked bar with a legend. parts: list of (label, value)."""
    parts = [(k, v) for k, v in parts if v]
    total = sum(v for _, v in parts)
    if not total:
        return '<p class="empty">No data for last night.</p>'
    segs, legend = "", ""
    for i, (k, v) in enumerate(parts):
        pct = v / total * 100
        c = colors[i % len(colors)]
        segs += (f'<div class="seg" style="width:{pct:.2f}%;background:var({c})" '
                 f'data-l="{esc(k)}" data-v="{v:g}" data-u=" {esc(unit)}" '
                 f'data-p="{pct:.0f}"></div>')
        hrs = f"{int(v)//60}h {int(v)%60:02d}m" if unit == "min" and v >= 60 else f"{v:g} {unit}"
        legend += (f'<div class="lg"><span class="sw" style="background:var({c})"></span>'
                   f'<span class="lk">{esc(k)}</span><span class="lv">{hrs}</span>'
                   f'<span class="lp">{pct:.0f}%</span></div>')
    return f'<div class="stack">{segs}</div><div class="legend">{legend}</div>'


def goalbar(value, goal, unit=""):
    if not value:
        return '<p class="empty">No data yet.</p>'
    pct = min(value / goal * 100, 100) if goal else None
    done = goal and value >= goal
    bar = (f'<div class="gb"><div class="gbf{" hit" if done else ""}" style="width:{pct:.1f}%"></div></div>'
           if pct is not None else "")
    sub = (f'<div class="gbl">{value:,.0f} of {goal:,.0f}{unit}'
           f'{" — goal met" if done else f" ({goal - value:,.0f} to go)"}</div>'
           if goal else f'<div class="gbl">{value:,.0f}{unit}</div>')
    return bar + sub


SCRIPT = """<script>
(function () {
  var el = document.getElementById("ago");
  if (el && el.dataset.at) {
    var built = new Date(el.dataset.at);
    var mins = Math.round((Date.now() - built) / 60000);
    var txt = mins < 2 ? "just now"
            : mins < 60 ? mins + " min ago"
            : mins < 120 ? "an hour ago"
            : mins < 1440 ? Math.round(mins / 60) + " hours ago"
            : Math.round(mins / 1440) + " days ago";
    el.textContent = txt;
    if (mins > 720) el.className = "stale";
    el.title = "Built " + el.dataset.at.replace("T", " ");
  }
})();

(function () {
  var tip = document.createElement("div");
  tip.className = "tip";
  tip.innerHTML = '<div class="tl"></div><div class="tvv"></div>';
  document.body.appendChild(tip);
  var lit = null, pinned = false, pinTimer = null;

  function fmt(n) {
    n = Number(n);
    return Math.abs(n) >= 1000 ? n.toLocaleString() : String(n);
  }

  function show(hit, x, y) {
    var pct = hit.dataset.p ? " · " + hit.dataset.p + "%" : "";
    tip.querySelector(".tl").textContent = hit.dataset.l || "";
    tip.querySelector(".tvv").textContent = fmt(hit.dataset.v) + (hit.dataset.u || "") + pct;
    tip.classList.add("on");
    // keep it on screen near the edges
    var w = tip.offsetWidth;
    tip.style.left = Math.min(Math.max(x, w / 2 + 8), window.innerWidth - w / 2 - 8) + "px";
    tip.style.top = Math.max(y - 12, 44) + "px";

    var svg = hit.closest ? hit.closest("svg") : null;
    document.querySelectorAll(".hdot").forEach(function (d) {
      if (!svg || d !== svg.querySelector(".hdot")) d.setAttribute("opacity", "0");
    });
    if (svg) {
      var dot = svg.querySelector(".hdot");
      if (dot && hit.dataset.cx) {
        dot.setAttribute("cx", hit.dataset.cx);
        dot.setAttribute("cy", hit.dataset.cy);
        dot.setAttribute("opacity", "1");
      }
      if (hit.dataset.bar !== undefined) {
        var bars = svg.querySelectorAll(".bar");
        if (lit) lit.classList.remove("lit");
        lit = bars[+hit.dataset.bar];
        if (lit) lit.classList.add("lit");
      }
    }
  }

  function hide(force) {
    if (pinned && !force) return;       // a tapped value stays put on touch
    tip.classList.remove("on");
    document.querySelectorAll(".hdot").forEach(function (d) { d.setAttribute("opacity", "0"); });
    if (lit) { lit.classList.remove("lit"); lit = null; }
  }

  function target(e) {
    var el = e.target;
    return el && el.closest ? el.closest("[data-v]") : null;
  }

  function unpin() { pinned = false; clearTimeout(pinTimer); }

  document.addEventListener("pointermove", function (e) {
    if (e.pointerType && e.pointerType !== "mouse") return;   // touch uses taps
    var hit = target(e);
    if (hit) show(hit, e.clientX, e.clientY); else hide();
  });
  document.addEventListener("pointerdown", function (e) {
    var hit = target(e);
    if (!hit) { unpin(); hide(true); return; }
    show(hit, e.clientX, e.clientY);
    if (e.pointerType && e.pointerType !== "mouse") {
      pinned = true;                       // keep it readable after the finger lifts
      clearTimeout(pinTimer);
      pinTimer = setTimeout(function () { unpin(); hide(true); }, 4000);
    }
    e.stopPropagation();                   // tapping data is not tapping the panel
  }, true);
  document.addEventListener("click", function (e) {
    if (target(e)) e.stopPropagation();
  }, true);
  window.addEventListener("scroll", function () { unpin(); hide(true); }, { passive: true });
})();

(function () {
  var zoom = document.getElementById("zoom");
  var body = document.getElementById("zoom-body");
  var opener = null;

  function open(panel) {
    body.innerHTML = panel.innerHTML;
    zoom.hidden = false;
    document.body.style.overflow = "hidden";
    opener = panel;
    zoom.querySelector(".zoom-close").focus();
  }
  function close() {
    zoom.hidden = true;
    body.innerHTML = "";
    document.body.style.overflow = "";
    if (opener) { opener.focus(); opener = null; }
  }

  document.querySelectorAll(".panel.zoomable").forEach(function (panel) {
    panel.tabIndex = 0;
    panel.setAttribute("role", "button");
    panel.setAttribute("aria-label", "Enlarge this panel");
    panel.addEventListener("click", function (e) {
      // don't hijack a link, a button, or someone selecting text
      if (e.target.closest("a, button")) return;
      var sel = window.getSelection();
      if (sel && sel.toString().length) return;
      open(panel);
    });
    panel.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(panel); }
    });
  });

  zoom.addEventListener("click", function (e) { if (e.target === zoom) close(); });
  zoom.querySelector(".zoom-close").addEventListener("click", close);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !zoom.hidden) close();
  });
})();
</script>"""


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
  --s1:#2F5D8C; --s2:#7FA8CF; --s3:#8E7AB5; --s4:#C3CAD4;
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
    --s1:#6FA8DC; --s2:#3E6B98; --s3:#A492CE; --s4:#46505F;
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
  --s1:#6FA8DC; --s2:#3E6B98; --s3:#A492CE; --s4:#46505F;
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
header.top .ctrl{display:flex; align-items:center; gap:14px; flex-wrap:wrap}
.refresh{display:inline-flex; align-items:center; gap:7px; text-decoration:none;
  background:var(--panel); border:1px solid var(--line); color:var(--ink);
  border-radius:7px; padding:7px 13px; font-size:13px; font-weight:600;
  transition:border-color .15s, background .15s}
.refresh:hover{border-color:var(--accent); background:var(--panel-2)}
.refresh:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.refresh .ico{font-size:14px; line-height:1}
.stale{color:var(--caution)}

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
  fill:var(--ink); text-anchor:middle; font-variant-numeric:tabular-nums; pointer-events:none}
.gauge-lab{font-family:Archivo,sans-serif; font-size:11px; fill:var(--faint);
  text-anchor:middle; letter-spacing:.14em; text-transform:uppercase; pointer-events:none}

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

/* stacked bars */
.stack{display:flex; height:14px; border-radius:7px; overflow:hidden; background:var(--track)}
.seg{height:100%}
.legend{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:4px 18px; margin-top:12px}
.lg{display:flex; align-items:center; gap:8px; font-size:13px}
.sw{width:9px; height:9px; border-radius:2px; flex:none}
.lk{color:var(--muted)}
.lv{margin-left:auto; font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums}
.lp{width:34px; text-align:right; color:var(--faint); font-family:"IBM Plex Mono",monospace}

/* goal bar */
.gb{height:10px; background:var(--track); border-radius:5px; overflow:hidden}
.gbf{height:100%; background:var(--accent); border-radius:5px}
.gbf.hit{background:var(--good)}
.gbl{margin-top:8px; font-size:13px; color:var(--muted); font-variant-numeric:tabular-nums}
.big{font-family:"IBM Plex Mono",monospace; font-size:36px; font-weight:600;
  font-variant-numeric:tabular-nums; line-height:1.1; margin-bottom:10px}
.big span{font-size:15px; color:var(--muted); font-weight:400}
.tiles{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px 10px; margin-top:16px;
  padding-top:14px; border-top:1px solid var(--line)}
.tile .tv{font-family:"IBM Plex Mono",monospace; font-size:18px; font-weight:600;
  font-variant-numeric:tabular-nums}
.tile .tk{font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--faint)}

/* chart tooltips */
.hit{cursor:crosshair}
.seg{cursor:pointer; transition:filter .12s}
.seg:hover{filter:brightness(1.15)}
.tip{position:fixed; z-index:60; pointer-events:none; opacity:0; transition:opacity .1s;
  background:var(--panel); border:1px solid var(--line); border-radius:7px;
  padding:7px 11px; box-shadow:var(--shadow); font-size:13px; white-space:nowrap;
  transform:translate(-50%,-100%)}
.tip.on{opacity:1}
.tip .tl{color:var(--muted); font-size:11px; letter-spacing:.06em; text-transform:uppercase}
.tip .tvv{font-family:"IBM Plex Mono",monospace; font-weight:600; font-variant-numeric:tabular-nums}
.bar.lit{opacity:1 !important}

/* click to enlarge */
.panel{position:relative}
.panel.zoomable{cursor:zoom-in}
.panel.zoomable::after{content:"⤢"; position:absolute; top:12px; right:14px;
  color:var(--faint); font-size:13px; opacity:.5; transition:opacity .15s}
.panel.zoomable:hover::after{opacity:1}
.panel.zoomable:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.zoom[hidden]{display:none}
.zoom{position:fixed; inset:0; z-index:50; background:rgba(10,14,20,.62);
  display:flex; align-items:center; justify-content:center; padding:24px;
  backdrop-filter:blur(3px)}
.zoom-inner{background:var(--panel); border:1px solid var(--line); border-radius:12px;
  width:min(900px,100%); max-height:88vh; overflow:auto; padding:26px 28px;
  box-shadow:0 24px 64px -16px rgba(0,0,0,.5); position:relative}
.zoom-close{position:absolute; top:14px; right:14px; background:var(--panel-2);
  border:1px solid var(--line); color:var(--muted); border-radius:6px;
  padding:5px 11px; font:inherit; font-size:13px; cursor:pointer}
.zoom-close:hover{color:var(--ink); border-color:var(--muted)}
.zoom-inner h3{font-size:13px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--faint); font-weight:600; margin-bottom:16px}
.zoom-inner .legend{grid-template-columns:repeat(2,minmax(0,1fr))}
.zoom-inner table{min-width:0}
@media (max-width:720px){
  .tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .legend{grid-template-columns:1fr}
  .zoom{padding:10px}
  .zoom-inner{padding:20px 16px}
}

/* week ahead */
.week{display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:8px; overflow:hidden}
.wday{background:var(--panel); padding:11px 10px; min-height:92px;
  display:flex; flex-direction:column; gap:3px}
.wday.is-today{background:var(--panel-2); box-shadow:inset 0 3px 0 var(--accent)}
.wday .d{font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--faint)}
.wday .t{font-size:13px; font-weight:600; line-height:1.3}
.wday .m{font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--muted);
  font-variant-numeric:tabular-nums}
.wday .rest{font-size:12px; color:var(--faint)}
.wksum{margin-top:10px; font-size:13px; color:var(--muted)}
.wksum b{font-family:"IBM Plex Mono",monospace; color:var(--ink); font-weight:600}
@media (max-width:720px){
  .week{grid-template-columns:1fr}
  .wday{min-height:0; flex-direction:row; align-items:baseline; gap:10px; padding:9px 12px}
  .wday .d{width:58px; flex:none}
  .wday .t{flex:1}
}

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

    # --- week ahead
    wt = b.get("week_totals") or {}
    cells = ""
    for day in b.get("week", []):
        inner = ""
        for x in day["sessions"]:
            meta = " · ".join(str(y) for y in [
                f'{x["duration_min"]} min' if x.get("duration_min") else None,
                f'{x["distance_km"]:g} km' if x.get("distance_km") else None] if y)
            inner += f'<div class="t">{esc(x["title"])}</div>'
            if meta:
                inner += f'<div class="m">{meta}</div>'
        if not inner:
            inner = '<div class="rest">Rest</div>'
        cells += (f'<div class="wday{" is-today" if day["is_today"] else ""}">'
                  f'<div class="d">{esc(day["weekday"])} {day["dom"]}</div>{inner}</div>')
    week_panel = ""
    if cells:
        summary = (f'<div class="wksum"><b>{wt.get("count", 0)}</b> session'
                   f'{"" if wt.get("count") == 1 else "s"} planned'
                   + (f' · <b>{wt["km"]:g}</b> km' if wt.get("km") else "")
                   + (f' · <b>{wt["hours"]:g}</b> h' if wt.get("hours") else "")
                   + '</div>')
        week_panel = (f'<div class="grid"><div class="panel zoomable"><h3>The week ahead</h3>'
                      f'<div class="week">{cells}</div>{summary}</div></div>')

    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    refresh_btn = (
        f'<a class="refresh" href="https://github.com/{esc(repo)}/actions/workflows/brief.yml" '
        f'target="_blank" rel="noopener" title="Opens GitHub — tap Run workflow to rebuild">'
        f'<span class="ico">\u21bb</span>Refresh</a>') if repo else ""

    # --- movement ------------------------------------------------------------
    steps_goal = goalbar(m.get("steps"), m.get("step_goal"), " steps")
    tiles = "".join(
        f'<div class="tile"><div class="tv">{v}</div><div class="tk">{esc(k)}</div></div>'
        for k, v in [
            ("Floors", num(m.get("floors"))),
            ("Active kcal", f'{m["active_kcal"]:,}' if m.get("active_kcal") else "—"),
            ("Walked", num(m.get("walk_km"), " km", 1)),
            ("HR range", f'{m["min_hr"]}–{m["max_hr"]}' if m.get("min_hr") and m.get("max_hr") else "—"),
            ("7-day avg steps", f'{m["steps_7d"]:,}' if m.get("steps_7d") else "—"),
            ("Steps this week", f'{m["steps_week"]:,}' if m.get("steps_week") else "—"),
            ("Intensity min/wk", num(m.get("intensity_week"))),
            ("Body Battery", f'{m["bb_low"]}–{m["bb_high"]}' if m.get("bb_high") else "—"),
        ])
    movement = (f'<div class="panel zoomable"><h3>Movement today</h3>'
                f'<div class="big">{m["steps"]:,}<span> steps</span></div>' if m.get("steps")
                else '<div class="panel zoomable"><h3>Movement today</h3>')
    movement += steps_goal + f'<div class="tiles">{tiles}</div></div>'

    sleep_stages = ""
    if m.get("sleep_stages"):
        sleep_stages = (f'<div class="panel zoomable"><h3>Last night&rsquo;s sleep</h3>'
                        + stacked(list(m["sleep_stages"].items()),
                                  ["--s1", "--s2", "--s3", "--s4"])
                        + (f'<div class="gbl">{m["sleep_hours"]} h in bed'
                           + (f' · score {m["sleep_score"]}' if m.get("sleep_score") else "")
                           + '</div>')
                        + '</div>')

    stress_panel = ""
    if m.get("stress_split"):
        stress_panel = (f'<div class="panel zoomable"><h3>Stress through the day</h3>'
                        + stacked([("Rest", m["stress_split"]["rest"]),
                                   ("Low", m["stress_split"]["low"]),
                                   ("Medium", m["stress_split"]["medium"]),
                                   ("High", m["stress_split"]["high"])],
                                  ["--good", "--fair", "--caution", "--critical"])
                        + (f'<div class="gbl">Average {m["stress_avg"]}'
                           + (f' · usual {m["stress_baseline"]}' if m.get("stress_baseline") else "")
                           + '</div>' if m.get("stress_avg") else "")
                        + '</div>')

    steps_chart = bar_chart(m.get("steps_series", []), ref=m.get("step_goal"),
                            unit="", title="Steps")
    kcal_chart = bar_chart(m.get("kcal_series", []), unit=" kcal", title="Active calories")

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
        strava_note = (f'<div class="panel zoomable"><h3>Strava cross-check</h3><div class="rows">'
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
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Source+Sans+3:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <header class="top">
    <h1>{d.strftime("%A")}, {d.strftime("%-d %B %Y")}</h1>
    <div class="ctrl">
      <div class="when">Updated <span id="ago" data-at="{esc(b["generated_at"])}">{esc(b["generated_at"][11:16])}</span> · {esc(r["coverage"])}</div>
      {refresh_btn}
    </div>
  </header>

  <section class="verdict {cls}">
    {gauge(r["score"], "Readiness")}
    <div>
      <h2>{esc(r["verdict"])}</h2>
      <p class="sub">{esc(ill["advice"])}{garmin_line}</p>
    </div>
  </section>

  <div class="grid g2">
    <div class="panel risk zoomable {rcls}">
      <h3>Illness risk</h3>
      <div class="lvl">{esc(ill["level"])}</div>
      {reasons}
    </div>
    <div class="panel session zoomable">
      <h3>Today&rsquo;s session</h3>
      {sess}
    </div>
  </div>

  <div class="grid"><div class="stats">{stat_cells}</div></div>

  {week_panel}

  <div class="grid g2">
    {movement}
    <div class="panel zoomable"><h3>Steps, {len(m.get("steps_series", []))} days</h3>{steps_chart}</div>
  </div>

  <div class="grid g2">
    {sleep_stages}
    {stress_panel}
  </div>

  <div class="grid g2">
    <div class="panel zoomable"><h3>Readiness breakdown</h3><div class="bd">{bd}</div></div>
    <div class="panel zoomable"><h3>This morning&rsquo;s numbers</h3><div class="rows">{metric_rows}</div></div>
  </div>

  <div class="grid g2">
    <div class="panel zoomable"><h3>HRV vs your balanced range</h3>{hrv_chart}</div>
    <div class="panel zoomable"><h3>Resting heart rate, {len(m.get("rhr_series", []))} days</h3>{rhr_chart}</div>
    <div class="panel zoomable"><h3>Weekly distance</h3>{week_chart}</div>
  </div>

  <div class="grid g2">
    <div class="panel zoomable"><h3>Recent sessions</h3>{recent_tbl}</div>
    <div class="panel zoomable"><h3>Fitness</h3><div class="rows">{fit_rows}</div></div>
  </div>

  <div class="grid g2">
    <div class="panel zoomable"><h3>Active calories</h3>{kcal_chart}</div>
    <div class="panel zoomable"><h3>Sleep hours</h3>{sleep_chart}</div>
  </div>

  {f'<div class="grid">{strava_note}</div>' if strava_note else ""}

  <div class="zoom" id="zoom" hidden>
    <div class="zoom-inner" role="dialog" aria-modal="true" aria-label="Enlarged panel">
      <button class="zoom-close" type="button">Close</button>
      <div id="zoom-body"></div>
    </div>
  </div>

  <footer>
    Readiness is a weighted blend of HRV against your personal baseline, sleep, resting heart rate,
    overnight recharge and acute:chronic load — scored only on the inputs that had data.
    Illness risk is a points model over resting HR, HRV, breathing rate, blood oxygen, recharge and stress.
    Neither is a medical assessment.
  </footer>
</div>
{SCRIPT}'''
