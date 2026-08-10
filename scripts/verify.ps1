$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )
    Write-Host "`n==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$root = Split-Path -Parent $PSScriptRoot
$baseCompose = Join-Path $root 'deploy/compose.yaml'
$productionCompose = Join-Path $root 'deploy/compose.production.yaml'
$performanceCompose = Join-Path $root 'deploy/compose.performance.yaml'
$generatedClient = 'frontend/src/app/api/generated/schema.ts'
$requirements = Join-Path ([IO.Path]::GetTempPath()) 'vigor-vine-audit-requirements.txt'

Push-Location $root
try {
    Invoke-Checked 'Locked backend install' { uv sync --project backend --locked --all-extras --dev }
    Invoke-Checked 'Backend format' { uv run --directory backend ruff format --check . }
    Invoke-Checked 'Backend lint' { uv run --directory backend ruff check . }
    Invoke-Checked 'Backend typing' { uv run --directory backend mypy src }
    Invoke-Checked 'SBOM and license policy' { uv run --directory backend python ../scripts/generate-sbom.py --verify-only }
    Invoke-Checked 'SC-008 independent-agent proxy evidence' { uv run --directory backend vigor-vine usability-study validate-proxy --input ../artifacts/usability-proxy-data.json --output ../artifacts/usability-proxy-summary.json --require-pass }
    Invoke-Checked 'Export audited production requirements' { uv export --project backend --locked --all-extras --no-dev --no-hashes --no-emit-project --output-file $requirements }
    Invoke-Checked 'Backend vulnerability audit' { uvx pip-audit -r $requirements --strict }

    Invoke-Checked 'Compose stop for offline/destructive tests' { docker compose -f $baseCompose stop api worker outbox retention }
    Invoke-Checked 'Backend unit/integration/contract/security/accuracy/performance tests' { uv run --directory backend pytest }
    Invoke-Checked '50-recipe nutrition corpus' { uv run --directory backend vigor-vine nutrition-corpus run --require-pass --output ../artifacts/nutrition-release-report.json }

    Invoke-Checked 'Locked frontend install' { pnpm --dir frontend install --frozen-lockfile }
    Invoke-Checked 'Frontend vulnerability audit' { pnpm --dir frontend audit --audit-level high }
    Invoke-Checked 'Frontend lint' { pnpm --dir frontend lint }
    Invoke-Checked 'Frontend typing' { pnpm --dir frontend typecheck }
    Invoke-Checked 'Frontend unit tests' { pnpm --dir frontend test --run }
    Invoke-Checked 'Frontend production build' { pnpm --dir frontend build }
    Invoke-Checked 'Frontend desktop/mobile Playwright' { pnpm --dir frontend exec playwright test }

    Invoke-Checked 'Regenerate OpenAPI client' { & (Join-Path $root 'scripts/generate-api-client.ps1') }
    Invoke-Checked 'Generated OpenAPI client drift' { git diff --exit-code -- $generatedClient }

    Invoke-Checked 'Development Compose validation' { docker compose -f $baseCompose config --quiet }
    $developmentCookieSecure = $env:VV_COOKIE_SECURE
    $developmentPublicBaseUrl = $env:VV_PUBLIC_BASE_URL
    $developmentApiBaseUrl = $env:VV_API_BASE_URL
    $developmentTrustedProxies = $env:VV_TRUSTED_PROXY_CIDRS
    try {
        $env:VV_COOKIE_SECURE = 'true'
        $env:VV_PUBLIC_BASE_URL = 'https://planner.example.test'
        $env:VV_API_BASE_URL = 'https://planner.example.test'
        $env:VV_TRUSTED_PROXY_CIDRS = '172.31.250.10/32'
        Invoke-Checked 'Production Compose validation' { docker compose -f $baseCompose -f $productionCompose config --quiet }
        Invoke-Checked 'Production image build' { docker compose -f $baseCompose -f $productionCompose build }
    }
    finally {
        $env:VV_COOKIE_SECURE = $developmentCookieSecure
        $env:VV_PUBLIC_BASE_URL = $developmentPublicBaseUrl
        $env:VV_API_BASE_URL = $developmentApiBaseUrl
        $env:VV_TRUSTED_PROXY_CIDRS = $developmentTrustedProxies
    }
    Invoke-Checked 'Self-hosted stack start' { docker compose -f $baseCompose -f $performanceCompose --profile performance up --build -d postgres redis api worker outbox retention web }

    $env:VV_PERFORMANCE_REPORT_CONTAINER = '/app/artifacts/performance-release-report.json'
    Invoke-Checked 'Reference performance profile' { docker compose -f $baseCompose -f $performanceCompose --profile performance build benchmark }
    Invoke-Checked 'Reference performance execution' { docker compose -f $baseCompose -f $performanceCompose --profile performance run --no-deps --rm benchmark }

    Write-Host "`n==> Docker smoke"
    $health = Invoke-RestMethod 'http://127.0.0.1:8080/api/v1/health'
    if ($health.status -ne 'ok' -or $health.database -ne 'ok' -or $health.broker -ne 'ok') {
        throw "Docker smoke health failed: $($health | ConvertTo-Json -Compress)"
    }
    $expected = 'postgres', 'redis', 'api', 'worker', 'outbox', 'retention', 'web'
    $running = docker compose -f $baseCompose -f $performanceCompose --profile performance ps --services --status running
    if ($LASTEXITCODE -ne 0) { throw 'Docker service inspection failed.' }
    $missing = $expected | Where-Object { $_ -notin $running }
    if ($missing) { throw "Docker services not running: $($missing -join ', ')" }
    Write-Host 'Docker health and seven-service process smoke passed.'
}
finally {
    if (Test-Path -LiteralPath $requirements) {
        Remove-Item -LiteralPath $requirements -Force
    }
    Pop-Location
}
