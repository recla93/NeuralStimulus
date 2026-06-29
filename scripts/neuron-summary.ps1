<#
.SYNOPSIS
  Neuron v3.1 - Semantic graph summary (Turso vector search + semantic/feature hashing embedding).
  Reads graph.db directly (no LLM, zero context tokens).
#>

$NSDir = if (Test-Path "$env:LOCALAPPDATA\Programs\neuron\graph.db") {
    "$env:LOCALAPPDATA\Programs\neuron"
} else {
    Split-Path $PSCommandPath -Parent
}

$DB = "$NSDir\graph.db"
if (-not (Test-Path $DB)) {
    Write-Host "  No database found." -ForegroundColor Yellow
    Write-Host "  Create a graph with neuron_store_turn before using neuron-summary." -ForegroundColor Yellow
    exit 0
}

$Python = if (Test-Path "$NSDir\.venv\Scripts\python.exe") {
    "$NSDir\.venv\Scripts\python.exe"
} else { "python" }

Write-Host "`n  ===== Neuron -- Graph Summary =====" -ForegroundColor Cyan
Write-Host ""

$output = & $Python "$NSDir\scripts\neuron_summary_query.py" "$DB" 2>&1
if ($LASTEXITCODE) {
    Write-Host "  ERROR: unable to read database" -ForegroundColor Red
    $output | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
} else {
    $output | ForEach-Object { Write-Host $_ }
}
Write-Host "  =============================================`n" -ForegroundColor Cyan
