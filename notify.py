"""Push the day's verdict to a phone via ntfy.sh."""

import os
import sys
import json


PRIORITY = {"Rest": "urgent", "Easy only": "high"}
TAG = {"Low": "green_circle", "Slight": "large_blue_circle",
       "Elevated": "warning", "High": "rotating_light"}


def push(brief, url=None):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("[notify] NTFY_TOPIC not set, skipping", file=sys.stderr)
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

    import requests

    r = brief["readiness"]
    ill = brief["illness"]
    m = brief["metrics"]

    lines = []
    if brief["planned"]:
        p = brief["planned"][0]
        bits = [x for x in (p.get("sport"),
                            f'{p["duration_min"]} min' if p.get("duration_min") else None,
                            f'{p["distance_km"]} km' if p.get("distance_km") else None) if x]
        lines.append(f'Planned: {p["title"]}' + (f' ({", ".join(bits)})' if bits else ""))
    else:
        lines.append("Planned: nothing on the calendar")

    lines.append(f'Illness risk: {ill["level"]}')
    if ill["reasons"]:
        lines.append("• " + "\n• ".join(ill["reasons"][:3]))

    facts = []
    if m.get("rhr") is not None:
        d = m.get("rhr_delta")
        facts.append(f'RHR {m["rhr"]:.0f}' + (f' ({d:+.1f})' if d is not None else ""))
    if m.get("hrv_last_night"):
        facts.append(f'HRV {m["hrv_last_night"]:.0f} ms')
    if m.get("sleep_hours"):
        facts.append(f'Sleep {m["sleep_hours"]:.1f} h')
    if facts:
        lines.append(" · ".join(facts))

    st = brief["stats"]
    lines.append(f'Year {st["year"]["km"]:g} km · {st["month"]["km"]:g} km this month')

    headers = {
        "Title": f'{r["score"] if r["score"] is not None else "?"}/100 · {r["verdict"].split(" —")[0]}',
        "Priority": PRIORITY.get(r["verdict"].split(" —")[0], "default"),
        "Tags": TAG.get(ill["level"], "runner"),
        "Markdown": "yes",
    }
    if url:
        # A date stamp makes each morning's link unique, so phones never open a
        # cached copy of yesterday's brief.
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}d={brief['date']}"
        headers["Click"] = url
        headers["Actions"] = f"view, Open dashboard, {url}"

    resp = requests.post(f"{server}/{topic}", data="\n".join(lines).encode("utf-8"),
                         headers=headers, timeout=30)
    ok = resp.status_code < 300
    print(f"[notify] ntfy {resp.status_code}", file=sys.stderr)
    return ok


def push_failure(message):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    import requests
    requests.post(f"{server}/{topic}", data=message.encode("utf-8"),
                  headers={"Title": "Morning brief failed", "Priority": "high",
                           "Tags": "warning"}, timeout=30)
    return True


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "brief.json"
    push(json.load(open(path)), os.environ.get("DASHBOARD_URL"))
