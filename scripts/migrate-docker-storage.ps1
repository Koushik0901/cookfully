[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$DataRoot,
    [string]$ProjectName = "cookfully",
    [switch]$Resume
)

$ErrorActionPreference = "Stop"

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed: docker $($Arguments -join ' ')"
    }
}

function Test-DockerVolume([string]$Name) {
    & docker volume inspect $Name *> $null
    return $LASTEXITCODE -eq 0
}

function Assert-VolumeMatchesHostPath([string]$SourceVolume, [string]$Destination) {
    Invoke-Docker @(
        "run", "--rm",
        "--mount", "type=volume,source=$SourceVolume,target=/source,readonly",
        "--mount", "type=bind,source=$Destination,target=/target,readonly",
        "alpine:3.21",
        "sh", "-c", "diff -rq /source /target"
    )
}

function Test-EmptyDirectory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $true
    }
    return -not (Get-ChildItem -LiteralPath $Path -Force | Select-Object -First 1)
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "deploy/compose.yaml"
if (-not (Test-Path -LiteralPath $composeFile)) {
    throw "Cookfully Compose file was not found at $composeFile."
}

$resolvedDataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$driveRoot = [System.IO.Path]::GetPathRoot($resolvedDataRoot)
if ([string]::Equals($resolvedDataRoot.TrimEnd('\', '/'), $driveRoot.TrimEnd('\', '/'), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Choose a dedicated folder, not a drive root. For example: D:\Cookfully"
}

$volumeMap = [ordered]@{
    "postgres" = "postgres-data"
    "redis" = "redis-data"
    "intelligence-models" = "intelligence-model-data"
    "media" = "media-data"
    "semantic-models" = "semantic-model-data"
    "exports" = "export-data"
    "erasure-ledger" = "erasure-ledger-data"
}

Invoke-Docker @("version", "--format", "{{.Server.Version}}")

$migrationTargets = foreach ($entry in $volumeMap.GetEnumerator()) {
    $target = Join-Path $resolvedDataRoot $entry.Key
    $isEmpty = Test-EmptyDirectory $target
    if (-not $isEmpty -and -not $Resume) {
        throw "Refusing to overwrite non-empty destination '$target'. Choose a new empty folder or inspect it before migrating."
    }
    [pscustomobject]@{
        Folder = $entry.Key
        SourceVolume = "$ProjectName`_$($entry.Value)"
        Destination = $target
        Exists = Test-DockerVolume "$ProjectName`_$($entry.Value)"
        IsEmpty = $isEmpty
    }
}

$availableSources = @($migrationTargets | Where-Object { $_.Exists -and $_.IsEmpty })
$resumedFolders = @($migrationTargets | Where-Object { -not $_.IsEmpty } | ForEach-Object { $_.Folder })
if ($availableSources.Count -eq 0) {
    Write-Warning "No empty migration destinations with matching Cookfully named volumes were found for project '$ProjectName'. This cannot recover a volume that has already been deleted."
}

New-Item -ItemType Directory -Force -Path $resolvedDataRoot | Out-Null
foreach ($target in $migrationTargets) {
    New-Item -ItemType Directory -Force -Path $target.Destination | Out-Null
}

Write-Host "Stopping Cookfully writers before copying the old volumes..."
Invoke-Docker @("compose", "--project-name", $ProjectName, "-f", $composeFile, "stop")

foreach ($target in $availableSources) {
    Write-Host "Copying $($target.SourceVolume) to $($target.Destination)..."
    Invoke-Docker @(
        "run", "--rm",
        "--mount", "type=volume,source=$($target.SourceVolume),target=/source,readonly",
        "--mount", "type=bind,source=$($target.Destination),target=/target",
        "alpine:3.21",
        "sh", "-c", "cd /source && tar cf - . | (cd /target && tar xpf -)"
    )
    Assert-VolumeMatchesHostPath $target.SourceVolume $target.Destination
}

foreach ($target in ($migrationTargets | Where-Object { $_.Exists -and -not $_.IsEmpty })) {
    Write-Host "Verifying existing host copy for $($target.SourceVolume)..."
    Assert-VolumeMatchesHostPath $target.SourceVolume $target.Destination
}

$report = [ordered]@{
    migratedAt = (Get-Date).ToUniversalTime().ToString("o")
    projectName = $ProjectName
    dataRoot = $resolvedDataRoot
    copied = @($availableSources | ForEach-Object { $_.Folder })
    resumedExistingFolders = $resumedFolders
    verifiedFolders = @($migrationTargets | Where-Object Exists | ForEach-Object { $_.Folder })
    missingSourceVolumes = @($migrationTargets | Where-Object { -not $_.Exists } | ForEach-Object { $_.SourceVolume })
    rollback = "The original Docker volumes have deliberately been preserved. Do not delete them until a restore drill succeeds."
}
$report | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $resolvedDataRoot "migration-report.json") -Encoding utf8

Write-Host "Migration copy complete. Original Docker volumes were not removed."
Write-Host "Set COOKFULLY_DATA_ROOT=$resolvedDataRoot in deploy/.env, then start Cookfully:"
Write-Host "docker compose --project-name $ProjectName -f deploy/compose.yaml up -d --build"
