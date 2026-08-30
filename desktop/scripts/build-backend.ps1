# Freeze the FastAPI backend to a self-contained PyInstaller --onedir bundle so
# the packaged app needs no system Python (issue #47; docs/adr/0016 §5).
#
#   in :  ../backend  (deps synced once with `uv sync`) + scripts/backend_entry.py
#   out:  desktop/backend-dist/deadparrots-backend/deadparrots-backend.exe (+ libs)
#
# electron-builder.yml (extraResources) copies that tree to the installer's
# resources/backend/. Run this on a Windows build machine that has `uv`; the
# TARGET machine needs neither Python nor `uv`.
#
# --onedir, not --onefile: no per-launch self-extract, and fewer antivirus
# false positives on an unsigned binary.

$ErrorActionPreference = "Stop"

$scriptDir  = $PSScriptRoot
$desktopDir = Split-Path -Parent $scriptDir
$repoRoot   = Split-Path -Parent $desktopDir
$backendDir = Join-Path $repoRoot "backend"
$entry      = Join-Path $scriptDir "backend_entry.py"
$outDir     = Join-Path $desktopDir "backend-dist"
$workDir    = Join-Path $desktopDir "backend-build"

if (Test-Path $outDir)  { Remove-Item -Recurse -Force $outDir }
if (Test-Path $workDir) { Remove-Item -Recurse -Force $workDir }

Push-Location $backendDir
try {
    # `uv run --with pyinstaller` pulls PyInstaller into the build only — it is
    # not a project dependency. `--collect-*` is a first cut: the dynamic
    # importers (uvicorn's protocol/loop autodetect, duckdb's native lib,
    # nflreadpy -> polars/pyarrow) are the usual gaps to widen on the first real
    # build. PyInstaller's warn-*.txt in the work dir lists what it missed.
    uv run --with pyinstaller pyinstaller `
        --noconfirm --clean `
        --name deadparrots-backend `
        --distpath $outDir `
        --workpath $workDir `
        --specpath $workDir `
        --paths src `
        --console `
        --collect-all deadparrots `
        --collect-all uvicorn `
        --collect-all duckdb `
        --collect-all apscheduler `
        --collect-submodules nflreadpy `
        --collect-submodules pydantic `
        $entry
}
finally {
    Pop-Location
}

$exe = Join-Path $outDir "deadparrots-backend\deadparrots-backend.exe"
if (-not (Test-Path $exe)) {
    throw "PyInstaller finished but $exe is missing"
}
Write-Host "backend frozen -> $exe"
