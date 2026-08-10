$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$contract = Join-Path $root "specs/001-nutrition-recipe-planner/contracts/openapi.yaml"
$output = Join-Path $root "frontend/src/app/api/generated/schema.ts"
$versionLine = Select-String -LiteralPath $contract -Pattern '^  version: 0\.2\.[0-9]+$'

if (-not $versionLine) {
    throw "OpenAPI contract must remain on compatibility line 0.2.x"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $output) | Out-Null
Push-Location (Join-Path $root "frontend")
try {
    pnpm exec openapi-typescript $contract --output $output
    if ($LASTEXITCODE -ne 0) {
        throw "OpenAPI TypeScript generation failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Output "Generated committed client schema from OpenAPI 3.1 contract for API v0.2.x."
