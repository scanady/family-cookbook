# Set up a family cookbook on Windows in one step: a folder with the cookbook
# engine, the browser it lays pages out with, Ghostscript for the print files,
# a new book, and the AI key if you have one. In PowerShell:
#
#   irm https://raw.githubusercontent.com/scanady/family-cookbook/main/install.ps1 | iex
#
# Run it again on the same folder to upgrade the engine: nothing in book\ changes.
# COOKBOOK_DIR names the folder without asking; COOKBOOK_VERSION picks another
# release tag; COOKBOOK_PACKAGE installs from somewhere else (a local clone, say);
# COOKBOOK_ASSUME_DEFAULTS=1 answers every question with its default.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is many times faster without the bar

$Version = if ($env:COOKBOOK_VERSION) { $env:COOKBOOK_VERSION } else { 'v1.3.0' }
$Package = if ($env:COOKBOOK_PACKAGE) { $env:COOKBOOK_PACKAGE } else {
    "family-cookbook @ https://github.com/scanady/family-cookbook/archive/refs/tags/$Version.zip" }

function Say([string]$Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }

# Ask "question" "default": the answer, or the default when nobody can answer.
function Ask([string]$Question, [string]$Default = '') {
    if ($env:COOKBOOK_ASSUME_DEFAULTS -or [Console]::IsInputRedirected) { return $Default }
    $prompt = if ($Default) { "$Question [$Default]" } else { $Question }
    $answer = Read-Host $prompt
    if ($answer) { $answer.Trim() } else { $Default }
}

# Run a program and stop the install when it fails.
function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') failed (exit $LASTEXITCODE)" }
}

# A Python 3.11 or newer, as the full path to python.exe. The Microsoft Store's
# python.exe placeholder fails the version check, so it is never picked.
function Find-Python {
    # Windows PowerShell turns a redirected stderr line into an error; under Stop it would end the script.
    $ErrorActionPreference = 'Continue'
    foreach ($candidate in 'py -3', 'python', 'python3') {
        $exe, $rest = $candidate -split ' '
        $rest = @($rest | Where-Object { $_ })
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $found = & $exe @rest -c 'import sys; print(sys.executable) if sys.version_info >= (3, 11) else sys.exit(1)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) { return ($found | Select-Object -Last 1).Trim() }
    }
    return $null
}

# gswin64c.exe: on PATH, or where Ghostscript's installer puts it (it leaves PATH alone).
function Find-Ghostscript {
    $onPath = Get-Command gswin64c -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    Get-ChildItem "$env:ProgramFiles\gs\gs*\bin\gswin64c.exe" -ErrorAction SilentlyContinue |
        Select-Object -Last 1 -ExpandProperty FullName
}

$python = Find-Python
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'The cookbook needs Python 3.11 or newer: install it from https://www.python.org/downloads/ and run this again.'
    }
    Say 'Installing Python 3.12 (for your Windows account only)'
    Invoke-Checked winget @('install', '-e', '--id', 'Python.Python.3.12', '--scope', 'user',
                            '--accept-package-agreements', '--accept-source-agreements')
    $python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $python)) { throw "Python installed, but not at ${python}: open a new PowerShell window and run this again." }
}

$dir = if ($env:COOKBOOK_DIR) { $env:COOKBOOK_DIR } else { Ask 'Folder for the book' (Join-Path $HOME 'our-cookbook') }
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$dir = (Resolve-Path $dir).Path
Set-Location $dir

Say "Installing the cookbook engine into $dir\.venv"
if (-not (Test-Path .venv)) { Invoke-Checked $python @('-m', 'venv', '.venv') }
$venvPython = Join-Path $dir '.venv\Scripts\python.exe'
Invoke-Checked $venvPython @('-m', 'pip', 'install', '--quiet', '--upgrade', 'pip')
Invoke-Checked $venvPython @('-m', 'pip', 'install', '--quiet', '--upgrade', $Package)

Say 'Installing Chromium, the browser that lays out the pages (about 700 MB, once)'
Invoke-Checked $venvPython @('-m', 'playwright', 'install', 'chromium')

if (-not (Find-Ghostscript)) {
    Say 'Installing Ghostscript, which makes the print files (Windows asks for permission)'
    try {
        $release = Invoke-RestMethod 'https://api.github.com/repos/ArtifexSoftware/ghostpdl-downloads/releases/latest'
        $asset = $release.assets | Where-Object { $_.name -match '^gs\d+w64\.exe$' } | Select-Object -First 1
        $setup = Join-Path $env:TEMP $asset.name
        Invoke-WebRequest $asset.browser_download_url -OutFile $setup
        # Ask Windows for permission only when this window does not already
        # have it; where no one can answer the prompt, the request would wait forever.
        $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
        $start = @{ FilePath = $setup; ArgumentList = '/S'; PassThru = $true }
        if (-not $admin) { $start.Verb = 'RunAs' }
        $setupProcess = Start-Process @start
        if (-not $setupProcess.WaitForExit(300000)) {
            $setupProcess.Kill()
            throw 'the Ghostscript installer did not finish within 5 minutes'
        }
        Remove-Item $setup -ErrorAction SilentlyContinue
        if (-not (Find-Ghostscript)) { throw "the Ghostscript installer ended (exit $($setupProcess.ExitCode)) without installing it" }
    } catch {
        Write-Warning "Ghostscript was not installed ($($_.Exception.Message)). The book still builds; to print it, install Ghostscript from https://ghostscript.com/releases/gsdnld.html"
    }
}

# A launcher, so no virtual environment has to be activated: ./cookbook studio
$launcher = @(
    '@echo off',
    'rem This book''s cookbook engine, without activating .venv. Upgrade with install.ps1.',
    'setlocal',
    'set PYTHONUTF8=1',
    '"%~dp0.venv\Scripts\cookbook.exe" %*'
)
[System.IO.File]::WriteAllText((Join-Path $dir 'cookbook.cmd'), ($launcher -join "`r`n") + "`r`n")

if (Test-Path 'book\book.yaml') {
    Say 'Updating the guides for AI coding assistants'
    Invoke-Checked .\cookbook.cmd @('agent-files', '--update') | Out-Null
} else {
    Say 'Starting the book'
    $title = Ask "The book's title" 'Our Family Cookbook'
    $family = Ask 'The line under the title, such as "The Smith Family" (Enter to fill it in later)'
    $initArgs = @('init', '--title', $title)
    if ($family) { $initArgs += @('--subtitle', $family) }
    # Continue: under Stop, Windows PowerShell would end the script on init's first stderr line.
    $out = & { $ErrorActionPreference = 'Continue'; & .\cookbook.cmd @initArgs 2>&1 }
    if ($LASTEXITCODE -ne 0) { $out | ForEach-Object { Write-Host $_ }; throw 'cookbook init failed' }
    Write-Host 'Created book\. Its chapters, their order, and colors are in book\book.yaml.'
}

$envFile = Join-Path $dir '.env'
$haveKey = $env:OPENROUTER_API_KEY -or $env:GEMINI_API_KEY -or $env:GOOGLE_API_KEY -or
    ((Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^(OPENROUTER|GEMINI)_API_KEY=.+' -Quiet))
if (-not $haveKey) {
    Say 'AI (optional): it types up photos of recipe cards and makes dish photos'
    Write-Host '  1) OpenRouter (recommended): prepaid credits, no Google billing to set up'
    Write-Host '  2) Google AI Studio: a Gemini API key'
    Write-Host '  3) Skip: no AI for now; add a key to .env later'
    while ($true) {
        $choice = Ask 'Which one' '1'
        if ($choice -in '1', '2', '3') { break }
        Write-Host 'Type 1, 2, or 3.'
    }
    $service = @{
        '1' = @{ Var = 'OPENROUTER_API_KEY'; Url = 'https://openrouter.ai/keys'; Prefix = 'sk-or-' }
        '2' = @{ Var = 'GEMINI_API_KEY'; Url = 'https://aistudio.google.com/apikey'; Prefix = '' }
    }[$choice]
    if ($service) {
        $key = Ask "Paste your key from $($service.Url) (Enter to skip)"
        if ($key) {
            if ($service.Prefix -and -not $key.StartsWith($service.Prefix)) {
                Write-Warning "That does not look like an OpenRouter key (they start $($service.Prefix)); saving it anyway."
            }
            $lines = if (Test-Path $envFile) { @(Get-Content $envFile | Where-Object { $_ -notmatch "^$($service.Var)=" }) } else { @() }
            $lines += "$($service.Var)=$key"
            [System.IO.File]::WriteAllLines($envFile, [string[]]$lines)   # UTF-8 without a byte-order mark
            Write-Host "Saved to .env as $($service.Var)."
        }
    }
}

Say 'Checking this computer'
& .\cookbook.cmd doctor

Write-Host @"

Your cookbook is in $dir. Next:

  cd "$dir"
  ./cookbook studio                  see the book and work on it in your browser
  ./cookbook ingest card.jpg         add a recipe from a photo of the card
  ./cookbook press                   make the two PDFs for the printer
"@
