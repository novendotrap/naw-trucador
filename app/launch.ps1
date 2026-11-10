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

$probe = 'import sys,sysconfig; print(sys.version.split()[0], sysconfig.get_platform(), "free-threaded" if sysconfig.get_config_var("Py_GIL_DISABLED") else "standard"); raise SystemExit(not ((3,12) <= sys.version_info[:2] <= (3,14) and sysconfig.get_platform() == "win-amd64" and not sysconfig.get_config_var("Py_GIL_DISABLED")))'
$candidates = [System.Collections.Generic.List[string]]::new()
$runtime = Join-Path $root '.runtime'
$privateVersion = '3.14.7'
$privateRoot = Join-Path $runtime "cpython-$privateVersion"
$privatePython = Join-Path $privateRoot 'tools\python.exe'
$candidates.Add((Join-Path $runtime 'python\Scripts\python.exe'))
$candidates.Add($privatePython)
if ($env:NAW_PYTHON) { $candidates.Add($env:NAW_PYTHON) }

$launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($launcher) {
    foreach ($line in (& $launcher.Source -0p 2>$null)) {
        if ($line -match '\s([A-Za-z]:\\.*python[^\\]*\.exe)\s*$') {
            $candidates.Add($Matches[1])
        }
    }
}
$pythonCommands = @('python.exe', 'python3.exe') + @(12..15 | ForEach-Object { "python3.$_.exe" })
foreach ($command in (Get-Command $pythonCommands -CommandType Application -All -ErrorAction SilentlyContinue)) {
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
    $details = $probe | & $python -I - 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $python -I $bootstrap $Action
        exit $LASTEXITCODE
    }
    if ($details) { Write-Host "Python detectado: $details ($python)" }
}

if (-not [Environment]::Is64BitOperatingSystem) {
    Write-Host '[ERROR] naw-trucador requiere Windows de 64 bits.'
    exit 1
}

$staging = Join-Path $runtime ('cpython-download-' + [guid]::NewGuid().ToString('N'))
try {
    Write-Host "Descargando Python $privateVersion x64 solo para naw-trucador..."
    New-Item -ItemType Directory -Path $staging -ErrorAction Stop | Out-Null
    $archive = Join-Path $staging 'python.zip'
    $url = "https://api.nuget.org/v3-flatcontainer/python/$privateVersion/python.$privateVersion.nupkg"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive -TimeoutSec 120 -ErrorAction Stop
    $sha256 = '46A4DA5529A92D18FF894911F6E6033A8253198D705B8161BF28C9123C87D46B'
    $hasher = [Security.Cryptography.SHA256]::Create()
    $inputStream = [IO.File]::OpenRead($archive)
    try {
        $actualHash = [BitConverter]::ToString($hasher.ComputeHash($inputStream)).Replace('-', '')
    } finally {
        $inputStream.Dispose()
        $hasher.Dispose()
    }
    if ($actualHash -ne $sha256) {
        throw 'El SHA-256 del paquete de Python no coincide.'
    }
    $extracted = Join-Path $staging 'package'
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $extracted)
    $candidate = Join-Path $extracted 'tools\python.exe'
    $probe | & $candidate -I -
    if ($LASTEXITCODE -ne 0) { throw 'El Python descargado no pudo iniciar.' }
    if (Test-Path -LiteralPath $privateRoot) {
        $null = $probe | & $privatePython -I - 2>$null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $privatePython -PathType Leaf)) {
            [IO.Directory]::Move($privateRoot, ($privateRoot + '-' + [guid]::NewGuid().ToString('N')))
        }
    }
    if (-not (Test-Path -LiteralPath $privateRoot)) {
        try {
            [IO.Directory]::Move($extracted, $privateRoot)
        } catch {
            if (-not (Test-Path -LiteralPath $privatePython -PathType Leaf)) { throw }
        }
    }
} catch {
    Write-Host "[ERROR] No se pudo preparar Python local: $_"
    Write-Host 'Revisa la conexion o instala Python 3.12, 3.13 o 3.14 x64 estandar.'
    Write-Host 'https://www.python.org/downloads/windows/'
    exit 1
} finally {
    if (Test-Path -LiteralPath $staging) {
        $resolvedStaging = (Resolve-Path -LiteralPath $staging).ProviderPath
        $resolvedRuntime = (Resolve-Path -LiteralPath $runtime).ProviderPath
        if ((Split-Path -Parent $resolvedStaging) -eq $resolvedRuntime -and
            (Split-Path -Leaf $resolvedStaging) -match '^cpython-download-[0-9a-f]{32}$') {
            Remove-Item -LiteralPath $resolvedStaging -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

& $privatePython -I $bootstrap $Action
exit $LASTEXITCODE
