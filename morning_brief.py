#!/usr/bin/env python3
"""
Morning training brief: Garmin Connect + Strava -> readiness score, illness risk,
today's planned session, and distance stats.

Usage:
  python morning_brief.py --mint-garmin-token      # one-time: email/password -> long-lived token
  python morning_brief.py --run                    # daily: writes brief.json + dashboard.html
  python morning_brief.py --selftest               # no network; runs the model on synthetic data

Environment:
  GARMIN_TOKEN            token string from --mint-garmin-token   (required for --run)
  GARMIN_EMAIL/PASSWORD   only needed for --mint-garmin-token
  STRAVA_CLIENT_ID        optional
  STRAVA_CLIENT_SECRET    optional
  STRAVA_REFRESH_TOKEN    optional
  BRIEF_TZ                IANA timezone, default Africa/Johannesburg
"""

import argparse
import json
import os
import statistics
import sys
import traceback
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("BRIEF_TZ", "Africa/Johannesburg"))
OUT_JSON = os.environ.get("BRIEF_JSON", "brief.json")
OUT_HTML = os.environ.get("BRIEF_HTML", "dashboard.html")

STATS_DAYS = 28          # daily summaries pulled for RHR / steps / stress baselines
SLEEP_DAYS = 14          # nights pulled for sleep, respiration, SpO2 baselines
M_PER_KM = 1000.0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def log(msg):
    print(f"[brief] {msg}", file=sys.stderr)


def safe(fn, *a, **kw):
    """Call a Garmin endpoint; never let one bad endpoint kill the run."""
    try:
        return fn(*a, **kw)
    except Exception as e:
        log(f"  ! {getattr(fn, '__name__', fn)}{a}: {type(e).__name__}: {str(e)[:120]}")
        return None


def g(d, *path, default=None):
    """Nested get that tolerates None and missing keys."""
    cur = d
    for k in path:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(k)
        elif isinstance(cur, list) and isinstance(k, int) and -len(cur) <= k < len(cur):
            cur = cur[k]
        else:
            return default
    return default if cur is None else cur


def find_key(obj, key, depth=0):
    """Depth-first search for the first non-null value of `key` anywhere in a
    nested payload. Garmin moves these fields between releases; searching for
    them by name survives that."""
    if depth > 8 or obj is None:
        return None
    if isinstance(obj, dict):
        if obj.get(key) is not None:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key, depth + 1)
            if r is not None:
                return r
    return None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ds(d):
    return d.isoformat()


# --------------------------------------------------------------------------
# Garmin
# --------------------------------------------------------------------------

def mint_garmin_token():
    from garminconnect import Garmin
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ").strip()
    pw = os.environ.get("GARMIN_PASSWORD") or input("Garmin password: ").strip()

    def prompt_mfa():
        return input("Garmin MFA code: ").strip()

    api = Garmin(email, pw, prompt_mfa=prompt_mfa)
    api.login()
    token = api.client.dumps()
    with open("garmin_token.txt", "w") as f:
        f.write(token)
    log(f"logged in as {api.full_name}; token written to garmin_token.txt ({len(token)} chars)")
    return token


def garmin_client():
    """Prefer the long-lived token; fall back to email/password so setup needs no
    local minting step. Password login hits Garmin's SSO every run, which is more
    exposed to rate limiting and cannot answer an MFA challenge."""
    from garminconnect import Garmin
    token = os.environ.get("GARMIN_TOKEN", "").strip()
    if token:
        api = Garmin()
        api.login(tokenstore=token)
        log("garmin: authenticated with stored token")
        return api

    email = os.environ.get("GARMIN_EMAIL", "").strip()
    pw = os.environ.get("GARMIN_PASSWORD", "")
    if not (email and pw):
        raise SystemExit("Set GARMIN_TOKEN, or GARMIN_EMAIL and GARMIN_PASSWORD.")
    api = Garmin(email, pw)
    api.login()
    log("garmin: authenticated with password")
    try:
        log(f"garmin: token for GARMIN_TOKEN secret is {len(api.client.dumps())} chars "
            f"(set it to stop hitting SSO daily)")
    except Exception:
        pass
    return api


def collect_garmin(api, today):
    """Pull everything we need. Every call is individually fault-tolerant."""
    t = ds(today)
    y = ds(today - timedelta(days=1))
    raw = {"date": t}

    log("garmin: today's wellness")
    raw["readiness"] = safe(api.get_training_readiness, t) or safe(api.get_training_readiness, y)
    raw["hrv"] = safe(api.get_hrv_data, t) or safe(api.get_hrv_data, y)
    raw["sleep"] = safe(api.get_sleep_data, t)
    raw["stats"] = safe(api.get_stats, t)
    raw["respiration"] = safe(api.get_respiration_data, t)
    raw["spo2"] = safe(api.get_spo2_data, t)
    raw["stress"] = safe(api.get_all_day_stress, t)
    raw["body_battery"] = safe(api.get_body_battery, ds(today - timedelta(days=2)), t)

    log("garmin: training status & fitness")
    raw["training_status"] = safe(api.get_training_status, t)
    raw["max_metrics"] = safe(api.get_max_metrics, t)
    raw["race_predictions"] = safe(api.get_race_predictions)
    raw["endurance"] = safe(api.get_endurance_score, ds(today - timedelta(days=28)), t)
    raw["hill"] = safe(api.get_hill_score, ds(today - timedelta(days=28)), t)

    log(f"garmin: {STATS_DAYS}d daily summaries")
    hist = []
    for i in range(STATS_DAYS):
        d = today - timedelta(days=i)
        s = safe(api.get_stats, ds(d))
        if s:
            hist.append({
                "date": ds(d),
                "rhr": s.get("restingHeartRate"),
                "steps": s.get("totalSteps"),
                "stress": s.get("averageStressLevel"),
                "bb_high": s.get("bodyBatteryHighestValue"),
                "bb_low": s.get("bodyBatteryLowestValue"),
                "intensity": (s.get("moderateIntensityMinutes") or 0) + 2 * (s.get("vigorousIntensityMinutes") or 0),
                "sleep_sec": s.get("sleepingSeconds"),
            })
    raw["daily_history"] = hist

    log(f"garmin: {SLEEP_DAYS}d sleep history")
    nights = []
    for i in range(SLEEP_DAYS):
        d = today - timedelta(days=i)
        s = safe(api.get_sleep_data, ds(d))
        dto = g(s, "dailySleepDTO", default={}) or {}
        if not dto:
            continue
        nights.append({
            "date": ds(d),
            "seconds": dto.get("sleepTimeSeconds"),
            "score": g(dto, "sleepScores", "overall", "value"),
            "deep": dto.get("deepSleepSeconds"),
            "rem": dto.get("remSleepSeconds"),
            "awake": dto.get("awakeSleepSeconds"),
            "resp_avg": dto.get("averageRespirationValue"),
            "resp_low": dto.get("lowestRespirationValue"),
            "resp_high": dto.get("highestRespirationValue"),
            "spo2_avg": dto.get("averageSpO2Value"),
            "spo2_low": dto.get("lowestSpO2Value"),
            "restless": g(s, "restlessMomentsCount"),
            "body_battery_change": dto.get("bodyBatteryChange"),
            "hrv_avg": g(s, "avgOvernightHrv"),
            "rhr": g(s, "restingHeartRate"),
        })
    raw["sleep_history"] = nights

    log("garmin: planned workouts")
    sched = safe(api.get_scheduled_workouts, today.year, today.month) or {}
    raw["scheduled"] = sched

    log("garmin: activities")
    jan1 = date(today.year, 1, 1)
    raw["activities_ytd"] = safe(api.get_activities_by_date, ds(jan1), ds(today)) or []
    return raw


# --------------------------------------------------------------------------
# Strava
# --------------------------------------------------------------------------

def collect_strava():
    cid = os.environ.get("STRAVA_CLIENT_ID")
    secret = os.environ.get("STRAVA_CLIENT_SECRET")
    refresh = os.environ.get("STRAVA_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        log("strava: credentials not set, skipping")
        return None
    import requests
    try:
        r = requests.post("https://www.strava.com/oauth/token", data={
            "client_id": cid, "client_secret": secret,
            "grant_type": "refresh_token", "refresh_token": refresh,
        }, timeout=30)
        r.raise_for_status()
        tok = r.json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        out = {"new_refresh_token": tok.get("refresh_token")}
        me = requests.get("https://www.strava.com/api/v3/athlete", headers=h, timeout=30).json()
        out["athlete"] = {k: me.get(k) for k in ("id", "firstname", "lastname", "weight")}
        out["stats"] = requests.get(
            f"https://www.strava.com/api/v3/athletes/{me['id']}/stats", headers=h, timeout=30).json()
        out["gear"] = [
            {"name": s.get("name"), "km": round((s.get("distance") or 0) / M_PER_KM, 1),
             "retired": s.get("retired")}
            for s in (me.get("shoes") or [])
        ]
        after = int(datetime(date.today().year, 1, 1).timestamp())
        acts, page = [], 1
        while page <= 8:
            batch = requests.get("https://www.strava.com/api/v3/athlete/activities",
                                 headers=h, params={"after": after, "per_page": 200, "page": page},
                                 timeout=45).json()
            if not isinstance(batch, list) or not batch:
                break
            acts.extend(batch)
            if len(batch) < 200:
                break
            page += 1
        out["activities"] = [{
            "name": a.get("name"), "type": a.get("sport_type") or a.get("type"),
            "start": a.get("start_date_local"), "km": round((a.get("distance") or 0) / M_PER_KM, 2),
            "moving_s": a.get("moving_time"), "elev": a.get("total_elevation_gain"),
            "avg_hr": a.get("average_heartrate"), "suffer": a.get("suffer_score"),
        } for a in acts]
        log(f"strava: {len(acts)} activities this year")
        return out
    except Exception as e:
        log(f"strava: failed - {type(e).__name__}: {str(e)[:200]}")
        return None


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def build_metrics(raw):
    """Flatten raw payloads into the numbers the model needs."""
    m = {}
    hist = raw.get("daily_history") or []
    nights = raw.get("sleep_history") or []

    # --- resting heart rate -------------------------------------------------
    rhr_today = g(raw, "stats", "restingHeartRate")
    if rhr_today is None and nights:
        rhr_today = nights[0].get("rhr")
    prior_rhr = [d["rhr"] for d in hist[1:] if d.get("rhr")]
    m["rhr"] = rhr_today
    m["rhr_baseline"] = round(mean(prior_rhr), 1) if prior_rhr else None
    m["rhr_delta"] = round(rhr_today - m["rhr_baseline"], 1) if (rhr_today and m["rhr_baseline"]) else None
    m["rhr_series"] = [(d["date"], d["rhr"]) for d in reversed(hist) if d.get("rhr")]

    # --- HRV ----------------------------------------------------------------
    hrv = raw.get("hrv") or {}
    m["hrv_last_night"] = g(hrv, "hrvSummary", "lastNightAvg")
    m["hrv_7d"] = g(hrv, "hrvSummary", "weeklyAvg")
    m["hrv_status"] = g(hrv, "hrvSummary", "status")
    m["hrv_baseline_low"] = g(hrv, "hrvSummary", "baseline", "lowUpper")
    m["hrv_baseline_high"] = g(hrv, "hrvSummary", "baseline", "upperBalanced")
    m["hrv_baseline_mid"] = g(hrv, "hrvSummary", "baseline", "balancedAverage")
    m["hrv_series"] = [(n["date"], n["hrv_avg"]) for n in reversed(nights) if n.get("hrv_avg")]

    # --- sleep --------------------------------------------------------------
    last = nights[0] if nights else {}
    m["sleep_hours"] = round((last.get("seconds") or 0) / 3600, 2) if last.get("seconds") else None
    m["sleep_score"] = last.get("score")
    m["sleep_deep_min"] = round((last.get("deep") or 0) / 60) if last.get("deep") else None
    m["sleep_rem_min"] = round((last.get("rem") or 0) / 60) if last.get("rem") else None
    m["sleep_awake_min"] = round((last.get("awake") or 0) / 60) if last.get("awake") is not None else None
    prior_sleep = [n["seconds"] for n in nights[1:8] if n.get("seconds")]
    m["sleep_7d_hours"] = round(mean(prior_sleep) / 3600, 2) if prior_sleep else None
    m["sleep_debt_hours"] = (round(m["sleep_7d_hours"] * 7 - sum(prior_sleep) / 3600, 2)
                             if prior_sleep and m["sleep_7d_hours"] else None)
    m["sleep_series"] = [(n["date"], round((n["seconds"] or 0) / 3600, 2), n.get("score"))
                         for n in reversed(nights) if n.get("seconds")]

    # --- respiration & SpO2 (illness tells) ---------------------------------
    m["resp_last_night"] = last.get("resp_avg")
    prior_resp = [n["resp_avg"] for n in nights[1:] if n.get("resp_avg")]
    m["resp_baseline"] = round(mean(prior_resp), 1) if prior_resp else None
    m["resp_delta"] = (round(m["resp_last_night"] - m["resp_baseline"], 1)
                       if (m["resp_last_night"] and m["resp_baseline"]) else None)
    m["spo2_last_night"] = last.get("spo2_avg")
    prior_spo2 = [n["spo2_avg"] for n in nights[1:] if n.get("spo2_avg")]
    m["spo2_baseline"] = round(mean(prior_spo2), 1) if prior_spo2 else None
    m["spo2_delta"] = (round(m["spo2_last_night"] - m["spo2_baseline"], 1)
                       if (m["spo2_last_night"] and m["spo2_baseline"]) else None)

    # --- body battery & stress ---------------------------------------------
    m["bb_overnight_charge"] = last.get("body_battery_change")
    m["bb_high_today"] = g(raw, "stats", "bodyBatteryHighestValue")
    m["bb_now"] = g(raw, "stats", "bodyBatteryMostRecentValue")
    m["stress_avg"] = g(raw, "stats", "averageStressLevel")
    prior_stress = [d["stress"] for d in hist[1:] if d.get("stress") and d["stress"] > 0]
    m["stress_baseline"] = round(mean(prior_stress), 1) if prior_stress else None

    # --- Garmin's own readiness --------------------------------------------
    r = raw.get("readiness")
    if isinstance(r, list):
        r = r[0] if r else {}
    r = r or {}
    m["garmin_readiness"] = r.get("score")
    m["garmin_readiness_label"] = r.get("level")
    m["garmin_readiness_feedback"] = r.get("feedbackShort")

    # --- training load ------------------------------------------------------
    ts = raw.get("training_status")
    status = (find_key(ts, "trainingStatusFeedbackPhrase") or find_key(ts, "trainingStatus"))
    if isinstance(status, str):
        m["training_status"] = status.replace("_", " ").title()
    m["acute_load"] = find_key(ts, "acuteTrainingLoad")
    m["load_ratio"] = (find_key(ts, "dailyAcuteChronicWorkloadRatio") or find_key(ts, "acwr"))
    mm = raw.get("max_metrics")
    m["vo2max"] = find_key(mm, "vo2MaxPreciseValue") or find_key(mm, "vo2MaxValue")
    m["fitness_age"] = find_key(mm, "fitnessAge")

    # overnight recharge: sleep payload first, else today's body battery charge
    if m.get("bb_overnight_charge") is None:
        bb = raw.get("body_battery")
        if isinstance(bb, list):
            for entry in bb:
                if str(g(entry, "date", default=""))[:10] == raw.get("date"):
                    m["bb_overnight_charge"] = find_key(entry, "charged")
                    break
            if m.get("bb_overnight_charge") is None and bb:
                m["bb_overnight_charge"] = find_key(bb[-1], "charged")
    return m


def compute_load_from_activities(acts, today):
    """Fallback acute:chronic ratio from activity training load or duration."""
    def load_of(a):
        return (a.get("activityTrainingLoad") or 0) or ((a.get("duration") or 0) / 60.0)

    def window(days):
        cut = today - timedelta(days=days)
        tot = 0.0
        for a in acts:
            try:
                d = datetime.fromisoformat((a.get("startTimeLocal") or "").replace(" ", "T")).date()
            except Exception:
                continue
            if cut < d <= today:
                tot += load_of(a)
        return tot

    acute = window(7)
    chronic = window(28) / 4.0
    return (round(acute, 1), round(chronic, 1),
            round(acute / chronic, 2) if chronic > 0 else None)


def readiness_score(m):
    """Transparent 0-100 readiness score. Components renormalise when data is missing."""
    parts = []

    # HRV vs personal baseline (30)
    hrv, lo, hi, mid = m.get("hrv_last_night"), m.get("hrv_baseline_low"), m.get("hrv_baseline_high"), m.get("hrv_baseline_mid")
    if hrv and lo and hi:
        if hrv >= hi:
            s = 1.0
        elif hrv >= (mid or (lo + hi) / 2):
            s = 0.75 + 0.25 * (hrv - (mid or (lo + hi) / 2)) / max(hi - (mid or (lo + hi) / 2), 1)
        elif hrv >= lo:
            s = 0.45 + 0.30 * (hrv - lo) / max((mid or (lo + hi) / 2) - lo, 1)
        else:
            s = clamp(0.45 * hrv / max(lo, 1))
        parts.append(("HRV", 30, clamp(s), f"{hrv} ms vs baseline {lo}–{hi}"))
    elif hrv and m.get("hrv_7d"):
        s = clamp(0.5 + (hrv - m["hrv_7d"]) / max(m["hrv_7d"], 1) * 2.0)
        parts.append(("HRV", 30, s, f"{hrv} ms vs 7-day {m['hrv_7d']} ms"))

    # Sleep (25)
    if m.get("sleep_score"):
        parts.append(("Sleep", 25, clamp(m["sleep_score"] / 100), f"score {m['sleep_score']}"))
    elif m.get("sleep_hours"):
        parts.append(("Sleep", 25, clamp((m["sleep_hours"] - 4.5) / 3.0),
                      f"{m['sleep_hours']} h"))

    # Resting HR vs baseline (20)
    if m.get("rhr_delta") is not None:
        d = m["rhr_delta"]
        s = 1.0 if d <= -2 else 0.9 if d <= 0 else clamp(0.9 - d * 0.18)
        parts.append(("Resting HR", 20, s, f"{m['rhr']} bpm ({d:+.1f} vs {m['rhr_baseline']})"))

    # Overnight recharge (15)
    if m.get("bb_overnight_charge") is not None:
        parts.append(("Body Battery", 15, clamp(m["bb_overnight_charge"] / 60.0),
                      f"+{m['bb_overnight_charge']} overnight"))
    elif m.get("bb_high_today") is not None:
        parts.append(("Body Battery", 15, clamp(m["bb_high_today"] / 90.0),
                      f"peak {m['bb_high_today']}"))

    # Training load balance (10)
    lr = m.get("load_ratio")
    if lr:
        if lr < 0.8:
            s = 0.85
        elif lr <= 1.3:
            s = 1.0
        elif lr <= 1.5:
            s = 0.6
        else:
            s = 0.3
        parts.append(("Load balance", 10, s, f"acute:chronic {lr}"))

    if not parts:
        return None, [], "no data"

    total_w = sum(p[1] for p in parts)
    score = round(sum(p[1] * p[2] for p in parts) / total_w * 100)
    breakdown = [{"name": n, "weight": round(w / total_w * 100), "score": round(s * 100), "detail": d}
                 for n, w, s, d in parts]
    coverage = f"{len(parts)} of 5 inputs"
    return score, breakdown, coverage


def illness_risk(m):
    """Points-based early-warning flag. Every point is explained."""
    pts, reasons = 0, []

    d = m.get("rhr_delta")
    if d is not None:
        if d >= 7:
            pts += 3; reasons.append(f"Resting HR {d:+.1f} bpm above your {STATS_DAYS}-day baseline — a large jump")
        elif d >= 4:
            pts += 2; reasons.append(f"Resting HR {d:+.1f} bpm above baseline")
        elif d >= 2.5:
            pts += 1; reasons.append(f"Resting HR mildly elevated ({d:+.1f} bpm)")

    hrv, lo = m.get("hrv_last_night"), m.get("hrv_baseline_low")
    if hrv and lo and hrv < lo:
        pts += 2; reasons.append(f"HRV {hrv} ms is below your balanced range (floor {lo} ms)")
    elif hrv and m.get("hrv_7d") and hrv < 0.85 * m["hrv_7d"]:
        pts += 1; reasons.append(f"HRV {hrv} ms is {round((1 - hrv / m['hrv_7d']) * 100)}% under your 7-day average")

    rd = m.get("resp_delta")
    if rd is not None:
        if rd >= 1.5:
            pts += 2; reasons.append(f"Overnight breathing rate {rd:+.1f} br/min above baseline — a classic early infection sign")
        elif rd >= 0.8:
            pts += 1; reasons.append(f"Overnight breathing rate slightly up ({rd:+.1f} br/min)")

    sd = m.get("spo2_delta")
    if sd is not None and sd <= -2:
        pts += 1; reasons.append(f"Overnight SpO2 {sd:.1f}% below baseline")

    if m.get("bb_overnight_charge") is not None and m["bb_overnight_charge"] < 30:
        pts += 1; reasons.append(f"Poor overnight recharge (Body Battery +{m['bb_overnight_charge']})")

    if m.get("stress_avg") and m.get("stress_baseline") and m["stress_avg"] > m["stress_baseline"] + 8:
        pts += 1; reasons.append(f"Average stress {m['stress_avg']} vs usual {m['stress_baseline']}")

    if m.get("sleep_awake_min") is not None and m["sleep_awake_min"] > 60:
        pts += 1; reasons.append(f"{m['sleep_awake_min']} min awake during the night")

    level = "High" if pts >= 5 else "Elevated" if pts >= 3 else "Slight" if pts >= 1 else "Low"
    advice = {
        "High": "Strong signs your body is fighting something. Skip hard work today — rest or very easy movement only.",
        "Elevated": "Several markers are off. Downgrade today's session to easy aerobic and reassess tomorrow.",
        "Slight": "One marker is mildly off. Proceed, but treat it as a cue to keep intensity honest.",
        "Low": "No infection markers standing out. Train as planned.",
    }[level]
    return {"level": level, "points": pts, "reasons": reasons, "advice": advice}


def todays_session(raw, today):
    """Today's planned workout, from the TrainingPeaks -> Garmin calendar sync."""
    sched = raw.get("scheduled") or {}
    items = []
    for key in ("calendarItems", "workoutScheduleList", "items"):
        v = sched.get(key)
        if isinstance(v, list):
            items = v
            break
    if not items and isinstance(sched, list):
        items = sched
    t = ds(today)
    # Garmin's calendar carries completed activities, sleep and naps alongside
    # planned workouts. Only the planned ones are "today's session".
    SKIP = ("activity", "sleep", "nap", "all_day", "wellness", "event", "race")
    out = []
    for it in items:
        d = it.get("date") or it.get("scheduledDate") or it.get("calendarDate") or ""
        if str(d)[:10] != t:
            continue
        kind = str(it.get("itemType") or it.get("type") or "").lower()
        if any(k in kind for k in SKIP):
            continue
        w = it.get("workout") or it
        is_planned = (kind and "workout" in kind) or bool(
            w.get("workoutId") or w.get("workoutName") or w.get("estimatedDurationInSecs"))
        if not is_planned:
            continue
        out.append({
            "title": w.get("workoutName") or it.get("title") or "Planned workout",
            "sport": (g(w, "sportType", "sportTypeKey") or it.get("itemType") or "").replace("_", " "),
            "duration_min": round((w.get("estimatedDurationInSecs") or 0) / 60) or None,
            "distance_km": round((w.get("estimatedDistanceInMeters") or 0) / M_PER_KM, 2) or None,
            "description": (w.get("description") or "")[:600],
        })
    return out


def distance_stats(acts, today, strava):
    """Totals for today, this month, this year - Garmin activities, Strava as cross-check."""
    def parse(a):
        try:
            return datetime.fromisoformat((a.get("startTimeLocal") or "").replace(" ", "T")).date()
        except Exception:
            return None

    buckets = {"day": [], "week": [], "month": [], "year": []}
    monday = today - timedelta(days=today.weekday())
    for a in acts:
        d = parse(a)
        if not d or d.year != today.year:
            continue
        buckets["year"].append(a)
        if d >= monday:
            buckets["week"].append(a)
        if d.month == today.month:
            buckets["month"].append(a)
        if d == today:
            buckets["day"].append(a)

    def summarise(rows):
        return {
            "count": len(rows),
            "km": round(sum((a.get("distance") or 0) for a in rows) / M_PER_KM, 1),
            "hours": round(sum((a.get("duration") or 0) for a in rows) / 3600, 1),
            "elev_m": round(sum((a.get("elevationGain") or 0) for a in rows)),
            "run_km": round(sum((a.get("distance") or 0) for a in rows
                                if "running" in (a.get("activityType", {}) or {}).get("typeKey", "")) / M_PER_KM, 1),
        }

    out = {k: summarise(v) for k, v in buckets.items()}

    # weekly running distance for the trend chart
    weeks = {}
    for a in acts:
        d = parse(a)
        if not d:
            continue
        wk = (d - timedelta(days=d.weekday())).isoformat()
        weeks[wk] = weeks.get(wk, 0) + (a.get("distance") or 0) / M_PER_KM
    out["weekly_series"] = sorted(({"week": k, "km": round(v, 1)} for k, v in weeks.items()),
                                  key=lambda r: r["week"])[-12:]

    if strava and strava.get("stats"):
        s = strava["stats"]
        out["strava"] = {
            "ytd_run_km": round(g(s, "ytd_run_totals", "distance", default=0) / M_PER_KM, 1),
            "ytd_run_count": g(s, "ytd_run_totals", "count", default=0),
            "ytd_ride_km": round(g(s, "ytd_ride_totals", "distance", default=0) / M_PER_KM, 1),
            "all_run_km": round(g(s, "all_run_totals", "distance", default=0) / M_PER_KM, 1),
            "recent_run_km": round(g(s, "recent_run_totals", "distance", default=0) / M_PER_KM, 1),
            "gear": strava.get("gear", []),
        }
    return out


def recent_activities(acts, today, n=7):
    rows = []
    for a in acts:
        try:
            d = datetime.fromisoformat((a.get("startTimeLocal") or "").replace(" ", "T"))
        except Exception:
            continue
        rows.append({
            "date": d.date().isoformat(),
            "name": a.get("activityName") or "",
            "type": (a.get("activityType", {}) or {}).get("typeKey", "").replace("_", " "),
            "km": round((a.get("distance") or 0) / M_PER_KM, 2),
            "min": round((a.get("duration") or 0) / 60),
            "avg_hr": a.get("averageHR"),
            "load": a.get("activityTrainingLoad"),
            "pace_min_km": (round((a.get("duration") or 0) / 60 / ((a.get("distance") or 1) / M_PER_KM), 2)
                            if (a.get("distance") or 0) > 500 else None),
        })
    return sorted(rows, key=lambda r: r["date"], reverse=True)[:n]


def build_brief(raw, strava, today):
    m = build_metrics(raw)
    acts = raw.get("activities_ytd") or []

    if not m.get("load_ratio"):
        acute, chronic, ratio = compute_load_from_activities(acts, today)
        m["acute_load"] = m.get("acute_load") or acute
        m["chronic_load"] = chronic
        m["load_ratio"] = ratio
        m["load_source"] = "computed from activities"
    else:
        m["load_source"] = "Garmin"

    score, breakdown, coverage = readiness_score(m)
    illness = illness_risk(m)

    # illness pulls readiness down - a body fighting something is not ready
    adjusted = score
    if score is not None and illness["points"] >= 3:
        adjusted = max(0, score - min(20, illness["points"] * 4))

    verdict = ("Rest" if (adjusted or 100) < 35 or illness["level"] == "High"
               else "Easy only" if (adjusted or 100) < 55 or illness["level"] == "Elevated"
               else "Train as planned" if (adjusted or 0) < 80
               else "Green light — go hard if the plan says so")

    return {
        "generated_at": datetime.now(TZ).isoformat(timespec="minutes"),
        "date": ds(today),
        "weekday": today.strftime("%A"),
        "readiness": {"score": adjusted, "raw_score": score, "breakdown": breakdown,
                      "coverage": coverage, "verdict": verdict,
                      "garmin_score": m.get("garmin_readiness"),
                      "garmin_label": m.get("garmin_readiness_label"),
                      "garmin_feedback": m.get("garmin_readiness_feedback")},
        "illness": illness,
        "metrics": m,
        "planned": todays_session(raw, today),
        "stats": distance_stats(acts, today, strava),
        "recent": recent_activities(acts, today),
        "fitness": {"vo2max": m.get("vo2max"), "fitness_age": m.get("fitness_age"),
                    "training_status": m.get("training_status"),
                    "race_5k": g(raw, "race_predictions", "time5K"),
                    "race_10k": g(raw, "race_predictions", "time10K"),
                    "race_half": g(raw, "race_predictions", "timeHalfMarathon"),
                    "race_full": g(raw, "race_predictions", "timeMarathon")},
    }


# --------------------------------------------------------------------------
# self-test with synthetic data
# --------------------------------------------------------------------------

def synthetic_raw(today, sick=False):
    nights, hist = [], []
    for i in range(SLEEP_DAYS):
        d = today - timedelta(days=i)
        base_resp, base_spo2 = 13.2, 95.0
        nights.append({
            "date": ds(d), "seconds": 26000 - (i % 3) * 1800,
            "score": 78 - (i % 4) * 3, "deep": 4200, "rem": 5400,
            "awake": 2900 if (sick and i == 0) else 1200,
            "resp_avg": base_resp + (2.1 if (sick and i == 0) else 0.1 * (i % 3)),
            "spo2_avg": base_spo2 - (2.5 if (sick and i == 0) else 0),
            "body_battery_change": 18 if (sick and i == 0) else 52,
            "hrv_avg": 42 if (sick and i == 0) else 61 - (i % 5),
            "rhr": 52 + (8 if (sick and i == 0) else 0), "restless": 20,
        })
    for i in range(STATS_DAYS):
        d = today - timedelta(days=i)
        hist.append({"date": ds(d), "rhr": 52 + (8 if (sick and i == 0) else (i % 3) - 1),
                     "steps": 9000, "stress": 40 if (sick and i == 0) else 27,
                     "bb_high": 88, "bb_low": 20, "intensity": 45, "sleep_sec": 26000})
    acts = []
    for i in range(0, 120, 3):
        d = today - timedelta(days=i)
        acts.append({"activityName": "Morning Run", "startTimeLocal": f"{ds(d)} 05:40:00",
                     "distance": 10500 + (i % 4) * 1500, "duration": 3300,
                     "elevationGain": 90, "averageHR": 148, "activityTrainingLoad": 120,
                     "activityType": {"typeKey": "running"}})
    return {
        "date": ds(today),
        "hrv": {"hrvSummary": {"lastNightAvg": nights[0]["hrv_avg"], "weeklyAvg": 58,
                               "status": "UNBALANCED" if sick else "BALANCED",
                               "baseline": {"lowUpper": 48, "balancedAverage": 58, "upperBalanced": 68}}},
        "stats": {"restingHeartRate": hist[0]["rhr"], "averageStressLevel": hist[0]["stress"],
                  "bodyBatteryHighestValue": 88, "bodyBatteryMostRecentValue": 70},
        "readiness": [{"score": 34 if sick else 81, "level": "LOW" if sick else "HIGH",
                       "feedbackShort": "RECOVERY_LOW" if sick else "READY"}],
        "sleep_history": nights, "daily_history": hist,
        "sleep": {"dailySleepDTO": {}},
        "training_status": {}, "max_metrics": [{"generic": {"vo2MaxPreciseValue": 54.2, "fitnessAge": 29}}],
        "race_predictions": {"time5K": 1210, "time10K": 2530, "timeHalfMarathon": 5580, "timeMarathon": 11820},
        "activities_ytd": acts,
        "scheduled": {"calendarItems": [{"date": ds(today), "workout": {
            "workoutName": "Threshold 4 x 8 min", "sportType": {"sportTypeKey": "running"},
            "estimatedDurationInSecs": 3900, "estimatedDistanceInMeters": 13000,
            "description": "4 x 8 min at threshold, 2 min float between."}}]},
    }


def selftest():
    today = datetime.now(TZ).date()
    ok = True
    for sick in (False, True):
        raw = synthetic_raw(today, sick=sick)
        b = build_brief(raw, None, today)
        label = "SICK" if sick else "HEALTHY"
        print(f"\n=== {label} ===")
        print(f"readiness: {b['readiness']['score']} (raw {b['readiness']['raw_score']}) "
              f"| verdict: {b['readiness']['verdict']}")
        print(f"illness: {b['illness']['level']} ({b['illness']['points']} pts)")
        for r in b["illness"]["reasons"]:
            print("   -", r)
        print("breakdown:", [(x["name"], x["score"]) for x in b["readiness"]["breakdown"]])
        print("planned:", [p["title"] for p in b["planned"]])
        print("stats day/month/year km:", b["stats"]["day"]["km"],
              b["stats"]["month"]["km"], b["stats"]["year"]["km"])
        if sick and b["illness"]["level"] not in ("High", "Elevated"):
            print("FAIL: sick profile did not raise illness risk"); ok = False
        if not sick and b["illness"]["level"] not in ("Low", "Slight"):
            print("FAIL: healthy profile flagged"); ok = False
        if not sick and (b["readiness"]["score"] or 0) < 60:
            print("FAIL: healthy readiness too low"); ok = False
        if sick and (b["readiness"]["score"] or 100) > 55:
            print("FAIL: sick readiness too high"); ok = False
        html = render_html(b)
        if len(html) < 2000 or "<title>" not in html:
            print("FAIL: html render"); ok = False
    print("\nSELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# render  (imported from render_dashboard.py)
# --------------------------------------------------------------------------

from render_dashboard import render_html  # noqa: E402


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mint-garmin-token", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--demo", action="store_true",
                    help="build the site from synthetic data (no network)")
    ap.add_argument("--out", default=os.environ.get("SITE_DIR", "docs"),
                    help="directory the site is written to")
    ap.add_argument("--history", default=os.environ.get("HISTORY_DIR", ""),
                    help="optional directory for a dated JSON archive; off by default")
    ap.add_argument("--quiet", action="store_true",
                    help="don't print metrics (keeps them out of public CI logs)")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()

    if a.mint_garmin_token:
        mint_garmin_token()
        return 0
    if a.selftest:
        return selftest()
    if not (a.run or a.demo):
        ap.print_help()
        return 1

    today = datetime.now(TZ).date()
    if a.demo:
        brief, strava = build_brief(synthetic_raw(today), None, today), None
        log("demo mode: synthetic data")
    else:
        api = garmin_client()
        raw = collect_garmin(api, today)
        strava = collect_strava()
        brief = build_brief(raw, strava, today)

    # site + machine-readable copy + a dated archive for long-range trends
    secret = os.environ.get("SITE_PATH", "").strip("/")
    site_dir = os.path.join(a.out, secret) if secret else a.out
    os.makedirs(site_dir, exist_ok=True)
    if a.history:
        os.makedirs(a.history, exist_ok=True)

    with open(os.path.join(site_dir, "index.html"), "w") as f:
        f.write(render_html(brief))
    if a.history:
        with open(os.path.join(a.history, f"{brief['date']}.json"), "w") as f:
            json.dump(brief, f, indent=2, default=str)
    with open(OUT_JSON, "w") as f:
        json.dump(brief, f, indent=2, default=str)
    log(f"wrote {site_dir}/index.html")

    summary = {
        "date": brief["date"],
        "readiness": brief["readiness"]["score"],
        "verdict": brief["readiness"]["verdict"],
        "illness": brief["illness"]["level"],
        "planned": [p["title"] for p in brief["planned"]],
    }
    print("brief built" if a.quiet else json.dumps(summary, indent=2))

    if not a.no_push:
        try:
            from notify import push
            push(brief, os.environ.get("DASHBOARD_URL"))
        except Exception as e:
            log(f"push failed: {type(e).__name__}: {e}")

    if strava and strava.get("new_refresh_token"):
        log("strava token refreshed ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        try:
            from notify import push_failure
            push_failure("The Garmin/Strava pull failed this morning. "
                         "Check the Actions log — the token may need re-minting.")
        except Exception:
            pass
        sys.exit(2)
