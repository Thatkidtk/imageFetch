Param(
    [switch]$Quiet
)

function Write-Info($msg) {
    if (-not $Quiet) { Write-Host $msg }
}

# Discover Python user Scripts directories (where console scripts go)
$scriptsPath = $null

foreach ($cmd in @(
    { python -c "import site, os; print(os.path.join(site.USER_BASE, 'Scripts'))" },
    { py -c "import site, os; print(os.path.join(site.USER_BASE, 'Scripts'))" }
)) {
    try {
        $out = & $cmd 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $scriptsPath = ($out | Select-Object -First 1).Trim()
            break
        }
    } catch {}
}

# Build a list of candidate script dirs
$candidates = @()
if ($scriptsPath) { $candidates += $scriptsPath }
$pyRoot = Join-Path $env:APPDATA 'Python'
$candidates += (Join-Path $pyRoot 'Scripts')
if (Test-Path $pyRoot) {
    Get-ChildItem -Path $pyRoot -Directory -Filter 'Python*' | ForEach-Object {
        $candidates += (Join-Path $_.FullName 'Scripts')
    }
}

# De-duplicate
$candidates = $candidates | Where-Object { $_ } | Select-Object -Unique

Write-Info ("Candidate Scripts paths:`n - " + ($candidates -join "`n - "))

# Add each existing candidate to User PATH and current session PATH
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
$userParts = $userPath.Split(';') | Where-Object { $_ }
$sessionParts = $env:Path.Split(';') | Where-Object { $_ }

$addedAny = $false
foreach ($cand in $candidates) {
    if (-not (Test-Path $cand)) { continue }
    $lc = $cand.Trim().ToLower()
    if (-not ($userParts | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ -eq $lc })) {
        $userPath = ($userPath.TrimEnd(';'))
        if ($userPath) { $userPath += ';' }
        $userPath += $cand
        $addedAny = $true
    }
    if (-not ($sessionParts | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ -eq $lc })) {
        $env:Path += ";$cand"
    }
}

if ($addedAny) {
    [Environment]::SetEnvironmentVariable('Path', $userPath, 'User')
    Write-Info "Updated user PATH. Open a new terminal to pick it up."
} else {
    Write-Info "User PATH already contained the Scripts path(s)."
}

# Update Git Bash ~/.bashrc with the first existing candidate
try {
    $bashrc = Join-Path $env:USERPROFILE ".bashrc"
    $first = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($first) {
        $drive = $first.Substring(0,1).ToLower()
        $rest = $first.Substring(2).Replace('\\','/')
        $bashPath = "/$drive/$rest"
        $exportLine = 'export PATH="' + $bashPath + ':$PATH"'

        $needsWrite = $true
        if (Test-Path $bashrc) {
            $content = Get-Content -Path $bashrc -Raw
            if ($content -match [Regex]::Escape($bashPath)) { $needsWrite = $false }
        }
        if ($needsWrite) {
            Add-Content -Path $bashrc -Value "# Added by add_imagefetch_to_path.ps1`n$exportLine"
            Write-Info "Updated ~/.bashrc for Git Bash. Run: source ~/.bashrc"
        } else {
            Write-Info "Git Bash ~/.bashrc already includes Scripts path."
        }
    }
} catch {
    Write-Info "Skipped Git Bash ~/.bashrc update ($_)."
}

Write-Info "Done. Try running: imageFetch (or imgFetch)"
