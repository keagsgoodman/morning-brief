<#
  Sets the whole thing up in one go.

  First, once:
    winget install GitHub.cli
    gh auth login

  Then, from this folder:
    .\setup.ps1

  Nothing you type is echoed or written to disk.
#>

$ErrorActionPreference = "Stop"

function Rand([int]$bytes = 8) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    ($b | ForEach-Object { $_.ToString("x2") }) -join ""
}

function AskSecret($prompt) {
    $s = Read-Host -Prompt $prompt -AsSecureString
    [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}

Write-Host "`n== Morning brief setup ==`n" -ForegroundColor Cyan

if (-not (Get-Command gh  -ErrorAction SilentlyContinue)) { throw "GitHub CLI not found. Run:  winget install GitHub.cli" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git not found." }
gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Not signed in. Run:  gh auth login" }

$repo = Read-Host "Repo name [morning-brief]"
if ([string]::IsNullOrWhiteSpace($repo)) { $repo = "morning-brief" }
$owner = (gh api user --jq .login)
$slug  = "$owner/$repo"

Write-Host "`nGarmin Connect" -ForegroundColor Yellow
$gEmail = Read-Host "  Email"
$gPass  = AskSecret "  Password (not shown)"

Write-Host "`nStrava - just press Enter three times to skip it" -ForegroundColor Yellow
$sId = Read-Host "  Client ID"
$sSecret = ""; $sRefresh = ""
if ($sId) {
    $sSecret  = AskSecret "  Client secret (not shown)"
    $sRefresh = AskSecret "  Refresh token (not shown)"
}

$sitePath  = Rand 8
$ntfyTopic = "brief-" + (Rand 6)
$siteUrl   = "https://$owner.github.io/$repo/$sitePath/"

# --- repo ------------------------------------------------------------------
Write-Host "`nCreating $slug ..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    git init -q -b main
    git add -A
    git -c user.email=setup@local -c user.name=setup commit -qm "morning brief"
}
gh repo create $repo --public --source=. --remote=origin --push

# --- secrets ---------------------------------------------------------------
Write-Host "Setting secrets ..." -ForegroundColor Cyan
function SetSecret($name, $value) {
    if ([string]::IsNullOrWhiteSpace($value)) { return }
    $value | gh secret set $name --repo $slug | Out-Null
    Write-Host "  $name"
}
SetSecret "GARMIN_EMAIL"    $gEmail
SetSecret "GARMIN_PASSWORD" $gPass
SetSecret "STRAVA_CLIENT_ID"     $sId
SetSecret "STRAVA_CLIENT_SECRET" $sSecret
SetSecret "STRAVA_REFRESH_TOKEN" $sRefresh
SetSecret "SITE_PATH"     $sitePath
SetSecret "NTFY_TOPIC"    $ntfyTopic
SetSecret "DASHBOARD_URL" $siteUrl

# --- first run -------------------------------------------------------------
Write-Host "`nBuilding the first brief ..." -ForegroundColor Cyan
gh workflow run "Morning brief" --repo $slug
Start-Sleep -Seconds 8
gh run watch --repo $slug --exit-status
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nThat run failed. To see why:" -ForegroundColor Red
    Write-Host "  gh run view --repo $slug --log-failed`n"
    Write-Host "Most likely the Garmin login. If your account has two-factor on," -ForegroundColor Yellow
    Write-Host "see 'Garmin credentials' in the README - you'll need a token instead."
    exit 1
}

# --- turn on the website ---------------------------------------------------
Write-Host "Turning on the website ..." -ForegroundColor Cyan
try {
    gh api "repos/$slug/pages" -X POST -f "source[branch]=main" -f "source[path]=/docs" 2>&1 | Out-Null
} catch {
    Write-Host "  (already on)" -ForegroundColor DarkGray
}

Write-Host @"

Done. It runs itself at 06:00 every morning.

  Dashboard   $siteUrl
  ntfy topic  $ntfyTopic
  Repo        https://github.com/$slug

One thing left for you: install the ntfy app on your phone
(App Store / Play Store, free) and subscribe to the topic above.

The page takes a minute or two to go live the first time.

"@ -ForegroundColor Green
