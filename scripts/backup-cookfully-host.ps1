[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$DataRoot,
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$DestinationRoot,
    [string]$TaskName = "Cookfully host data backup",
    [ValidatePattern("^(?:[01]\d|2[0-3]):[0-5]\d$")]
    [string]$Time = "03:00",
    [switch]$Install,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed: docker $($Arguments -join ' ')"
    }
}

function Copy-CookfullyFolder([string]$Name) {
    $source = Join-Path $resolvedDataRoot $Name
    if (-not (Test-Path -LiteralPath $source)) {
        Write-Warning "Skipping missing Cookfully folder: $source"
        return
    }
    $destination = Join-Path $resolvedDestinationRoot $Name
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    & robocopy $source $destination /E /COPY:DAT /DCOPY:DAT /FFT /R:2 /W:2 /XJ /NFL /NDL /NP
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed while copying $Name (exit code $LASTEXITCODE)."
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "deploy/compose.yaml"
$resolvedDataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$resolvedDestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot)

if ([string]::Equals($resolvedDataRoot.TrimEnd('\', '/'), $resolvedDestinationRoot.TrimEnd('\', '/'), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "DestinationRoot must be a different folder or disk from DataRoot."
}

if ($Install) {
    $scriptPath = $PSCommandPath.Replace("'", "''")
    $dataArgument = $resolvedDataRoot.Replace("'", "''")
    $destinationArgument = $resolvedDestinationRoot.Replace("'", "''")
    $taskArguments = "-NoProfile -ExecutionPolicy Bypass -File '$scriptPath' -DataRoot '$dataArgument' -DestinationRoot '$destinationArgument' -TaskName '$TaskName' -Time '$Time' -RunOnce"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArguments
    $trigger = New-ScheduledTaskTrigger -Daily -At ([DateTime]::ParseExact($Time, "HH:mm", $null))
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "Copies Cookfully database dumps, media, model caches, and erasure ledger to a second local disk." -Force | Out-Null
    Write-Host "Installed daily task '$TaskName' for $Time. Run it once now with this same command plus -RunOnce."
    return
}

if (-not $RunOnce) {
    throw "Use -Install to register the daily task, or -RunOnce to perform one backup now."
}

if (-not (Test-Path -LiteralPath $resolvedDataRoot)) {
    throw "Cookfully data root does not exist: $resolvedDataRoot"
}

New-Item -ItemType Directory -Force -Path $resolvedDestinationRoot | Out-Null
Invoke-Docker @("compose", "-f", $composeFile, "exec", "-T", "backup", "cookfully-database-backup", "run")

# PostgreSQL's live data directory is intentionally excluded. The preceding
# logical dump is consistent while the app remains online; raw database files
# are not safe to copy from a running server.
foreach ($folder in "backups", "media", "erasure-ledger", "exports", "semantic-models", "intelligence-models") {
    Copy-CookfullyFolder $folder
}

Write-Host "Cookfully host backup completed at $resolvedDestinationRoot."
