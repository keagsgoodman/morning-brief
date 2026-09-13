# Morning Training Brief

Every morning at 06:00 it reads Garmin (and Strava, if you want it), scores your readiness,
checks for early signs of illness, tells you what today's session is, and pushes the verdict
to your phone. It runs on GitHub's free servers — nothing of yours needs to be switched on.

---

## Setup

Once, in PowerShell:

```powershell
winget install GitHub.cli
gh auth login
.\setup.ps1
```

`setup.ps1` asks for your Garmin email and password (not echoed), creates the repo, sets
everything up, builds the first brief and prints your dashboard URL and a push topic.

Then install **ntfy** on your phone (App Store or Play Store, free) and subscribe to the
topic it printed. That's the whole setup.

Strava is optional — press Enter past it and Garmin covers everything. If you want it later,
see [Adding Strava](#adding-strava).

---

## What it tells you

**Readiness, 0–100** — a weighted blend, renormalised over whatever inputs had data:

| Input | Weight |
|---|---|
| HRV against your own balanced range | 30 |
| Sleep | 25 |
| Resting HR against a 28-day baseline | 20 |
| Overnight Body Battery recharge | 15 |
| Acute:chronic training load | 10 |

**Illness risk** — a points model. Resting HR elevation and overnight breathing rate carry
the most weight, because they move earliest: usually a day or two before you feel anything.
HRV below your floor, a drop in blood oxygen, poor recharge, elevated stress and broken
sleep add the rest. Three or more points also pulls readiness down.

Every point is shown with the reason behind it. It is not a diagnosis and not medical advice
— it is your own numbers compared against your own recent normal.

**Plus** today's planned session (read off your Garmin calendar, which is where
TrainingPeaks syncs it), distance for today / week / month / year, a twelve-week trend,
HRV and resting HR charts, your last seven sessions, VO2 max and race predictions.

---

## Things worth knowing

**Who can see it.** The repo is public, so the dashboard page is reachable by anyone who
knows its address — which is a random string nobody can guess, and the page carries no name
or identifying detail. Nothing is stored between runs: each morning's page replaces the last,
so there's no growing archive of your health data anywhere. If you'd rather it were properly
private, a paid GitHub plan lets the repo be private while the page stays published, and the
setup is otherwise identical.

**Your ntfy topic** is readable by anyone who knows the string, so don't post it anywhere.

**Your Garmin password** is stored as a GitHub secret — encrypted, and masked out of logs.

**If you have two-factor on Garmin**, password login can't work from a server. Run
`pip install garminconnect` then `python tools/mint_token.py` on this machine, and put the
result in a `GARMIN_TOKEN` secret:

```powershell
gh secret set GARMIN_TOKEN < garmin_token.txt
```

That's worth doing even without two-factor — it stops the daily SSO login that Garmin
sometimes rate-limits. The token lasts about a year.

---

## Adding Strava

1. https://www.strava.com/settings/api → create an app, callback domain `localhost`.
2. Open this with your client ID in it:
   `https://www.strava.com/oauth/authorize?client_id=YOUR_ID&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all,profile:read_all`
3. Authorize. The page fails to load — that's expected. Copy the `code=...` value from the
   address bar.
4. Trade it for a permanent refresh token:

```powershell
curl -X POST https://www.strava.com/oauth/token -d client_id=YOUR_ID -d client_secret=YOUR_SECRET -d code=THE_CODE -d grant_type=authorization_code
```

5. Add the three secrets:

```powershell
gh secret set STRAVA_CLIENT_ID
gh secret set STRAVA_CLIENT_SECRET
gh secret set STRAVA_REFRESH_TOKEN
```

---

## When something breaks

| Symptom | Fix |
|---|---|
| Auth failure | Password changed, or two-factor is on — mint a token, above |
| Fails some mornings only | Garmin rate-limiting the daily login — mint a token |
| Garmin 401s persistently | Garmin sometimes challenges datacenter IPs; re-run, or move the job to a self-hosted runner |
| Score is there but some numbers are missing | Watch wasn't worn. The page says which inputs it scored on |
| Nothing fired | GitHub pauses schedules after 60 days of no repo activity, and delays them under load. The daily commit keeps it awake |
| No push | Check the ntfy topic matches your subscription exactly |

Run it by hand any time: Actions tab → Morning brief → Run workflow.

---

## Changing it

`python morning_brief.py --selftest` runs the model against synthetic healthy and sick
profiles with no network at all. `--demo` builds the page from the same fake data. Run either
after any edit.

The numbers worth tuning live in `morning_brief.py`: `readiness_score()` holds the weights
table above, `illness_risk()` holds the thresholds. If it cries wolf, raise the resting HR
triggers (+2.5 / +4 / +7 bpm) or the breathing rate ones (+0.8 / +1.5 br/min).

Give it a few weeks first. Baselines need data, and your own sense of a rough morning is the
only calibration that counts.
