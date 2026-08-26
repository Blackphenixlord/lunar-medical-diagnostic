# Put VITALS on GitHub. Run this ON WINDOWS, from the repo root:
#
#     powershell -ExecutionPolicy Bypass -File scripts\push_to_github.ps1
#
# It creates the local git history if there is none, then pushes to GitHub.
# It NEVER touches your source files.
#
# Two ways it can reach GitHub:
#   * If the GitHub CLI (`gh`) is installed, it creates the repo for you.
#   * If not, it tells you the two clicks to make, then pushes.
#
# Install gh once and this becomes a single command forever:
#     winget install -e --id GitHub.cli
#     gh auth login

$ErrorActionPreference = "Stop"

$RepoName  = "vitals"
$Visibility = "private"     # change to "public" when you want judges to browse it

# --- sanity: are we in the right folder? -----------------------------------

if (-not (Test-Path ".\src\vitals\__init__.py")) {
    Write-Host "Run this from the repo root (the folder containing src\, kb\, tests\)." -ForegroundColor Red
    exit 1
}

# --- leftovers from working over the Claude device bridge -------------------
# The bridge cannot delete files, so anything that needed deleting was moved
# into _to_delete\ instead: the old src\mdx package, the first broken .git,
# the retired init_git.ps1. None of it is needed. Same reason a stale
# .git\index.lock can be lying around - git on Linux could not remove it.

if (Test-Path "_to_delete") {
    Write-Host "Removing _to_delete\ (leftovers, safe to lose) ..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "_to_delete"
}
if (Test-Path "_broken_git_MOVE_ME") {
    Remove-Item -Recurse -Force "_broken_git_MOVE_ME"
}
if (Test-Path ".git\index.lock") {
    Remove-Item -Force ".git\index.lock"
}

# --- local history ----------------------------------------------------------

if (-not (Test-Path ".git")) {
    Write-Host "No git repo here yet - creating one." -ForegroundColor Cyan
    git init
    git branch -M main
}

git config user.name  "Joshua Collado"
git config user.email "joshuacollado636@gmail.com"
git config core.autocrlf false

# The repo was last written from a Linux mount, which marks every file
# executable. Without this, git reports all 65 files as modified for no reason.
git config core.filemode false

git add -A

# `git commit` exits non-zero when there is nothing staged, which is fine.
$staged = git diff --cached --name-only
if ($staged) {
    $message = @"
VITALS: spaceflight medical decision support

Team TETHER. NASA HUNCH 2026-27, Software & Technology.
Joshua (lead/engine), Joaquin (medical research), Cruz (UI/testing).

Ollama reasons, the knowledge base grounds it.

  complaint -> extract findings -> retrieve KB conditions -> ollama answers
            -> citations looked up from the KB, never written by the model

Constraints enforced in code, not requested in the prompt:
  - the model may only name condition ids it was given; invented ids are dropped
  - it never writes a citation; it returns an id and we look up the source
  - temperature 0, so the same complaint gives the same answer and tests exist
  - it is told what is ALREADY KNOWN so it cannot re-ask what was just said
  - if it names an urgent condition and forgets to escalate, we escalate anyway

Contents:
  kb/          14 cited conditions, 72-finding controlled vocabulary, JSON Schema
  src/vitals/  extraction, retrieval, ollama reasoning, scoring engine, CLI, web UI
  prompts/     33 crewmember complaints; hit rate AND refusal rate are scored
  tests/       111 tests
  docker/      the language model baked into its own image, so a demo never
               waits on a download

Sensors are declared and deliberately unimplemented - no hardware is attached,
and a fabricated vital sign is worse than a missing one.

Known caveat, stated plainly: the prior/weight numbers in kb/conditions were
authored by us, not taken from literature. The citations support that the
conditions exist and how microgravity changes them, not those numbers. The
model never sees them, and a test fails the build if one leaks into its context.
"@
    git commit -m $message
} else {
    Write-Host "Nothing new to commit." -ForegroundColor Yellow
}

# --- remote -----------------------------------------------------------------

$hasRemote = git remote 2>$null | Where-Object { $_ -eq "origin" }

if (-not $hasRemote) {
    $gh = Get-Command gh -ErrorAction SilentlyContinue

    if ($gh) {
        Write-Host "Creating the GitHub repo with the GitHub CLI ..." -ForegroundColor Cyan
        gh repo create $RepoName --$Visibility --source=. --remote=origin --push
        Write-Host ""
        Write-Host "Done." -ForegroundColor Green
        gh repo view --web
        exit 0
    }

    Write-Host ""
    Write-Host "The GitHub CLI is not installed, so do this bit by hand:" -ForegroundColor Cyan
    Write-Host "  1. Open https://github.com/new"
    Write-Host "  2. Name it '$RepoName', set it to $Visibility."
    Write-Host "     Do NOT tick 'Add a README' or any .gitignore - the repo must be EMPTY."
    Write-Host "  3. Copy your username, then run:"
    Write-Host ""
    Write-Host "       git remote add origin https://github.com/<your-username>/$RepoName.git" -ForegroundColor White
    Write-Host "       git push -u origin main" -ForegroundColor White
    Write-Host ""
    Write-Host "Or install the CLI once and re-run this script:" -ForegroundColor Cyan
    Write-Host "       winget install -e --id GitHub.cli"
    Write-Host "       gh auth login"
    exit 0
}

Write-Host "Pushing to origin ..." -ForegroundColor Cyan
git push -u origin main

Write-Host ""
Write-Host "Done. Add Joaquin and Cruz as collaborators in the repo Settings." -ForegroundColor Green
