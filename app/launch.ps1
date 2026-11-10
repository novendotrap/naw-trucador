param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install', 'open', 'smoke')]
    [string]$Action
)

$root = Split-Path -Parent $PSScriptRoot
$bootstrap = Join-Path $PSScriptRoot 'bootstrap.py'
if (-not (Test-Path -LiteralPath $bootstrap -PathType Leaf)) {
    Write-Host '[ERROR] Falta app\bootstrap.py. Extrae el ZIP completo.'
    exit 1
}

$probe = 'import sys,sysconfig; raise SystemExit(not ((3,12) <= sys.version_info[:2] <= (3,14) and sysconfig.get_platform() == "win-amd64"))'
$candidates = [System.Collections.Generic.List[string]]::new()
$candidates.Add((Join-Path $root '.runtime\python\Scripts\python.exe'))

$launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($launcher) {
    foreach ($line in (& $launcher.Source -0p 2>$null)) {
        if ($line -match '\s([A-Za-z]:\\.*python\.exe)\s*$') {
            $candidates.Add($Matches[1])
        }
    }
}
foreach ($command in (Get-Command python.exe, python3.exe -CommandType Application -All -ErrorAction SilentlyContinue)) {
    if ($command.Source -notmatch '\\Microsoft\\WindowsApps\\') {
        $candidates.Add($command.Source)
    }
}
foreach ($key in @('HKCU:\Software\Python', 'HKLM:\Software\Python')) {
    foreach ($company in (Get-ChildItem -LiteralPath $key -ErrorAction SilentlyContinue)) {
        foreach ($tag in (Get-ChildItem -LiteralPath $company.PSPath -ErrorAction SilentlyContinue)) {
            $location = Get-Item -LiteralPath (Join-Path $tag.PSPath 'InstallPath') -ErrorAction SilentlyContinue
            if ($location) {
                $executable = $location.GetValue('ExecutablePath')
                if (-not $executable -and $location.GetValue('')) {
                    $executable = Join-Path ($location.GetValue('')) 'python.exe'
                }
                if ($executable) { $candidates.Add($executable) }
            }
        }
    }
}
foreach ($version in @('312', '313', '314')) {
    $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe"))
    $candidates.Add((Join-Path $env:ProgramFiles "Python$version\python.exe"))
}

foreach ($python in ($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { continue }
    # Pass the probe on stdin to avoid native quoting differences in Windows PowerShell.
    $probe | & $python -I - 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $python -I $bootstrap $Action
        exit $LASTEXITCODE
    }
}

Write-Host '[ERROR] No encontre Python 3.12, 3.13 o 3.14 para Windows x64.'
Write-Host 'Si solo tenes Python 3.11 o anterior, podes instalar Python 3.12 al lado del que ya usas.'
Write-Host 'https://www.python.org/downloads/windows/'
exit 1
