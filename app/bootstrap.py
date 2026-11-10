"""Windows installer/launcher. Standard library only; no global Python packages required."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import socket
import sysconfig
import subprocess
import sys
import urllib.request
import venv
import zipfile
from pathlib import Path

APP = Path(__file__).resolve().parent
# The BAT starts Python in isolated mode, which omits the script directory.
sys.path.insert(0, str(APP))
from core.java_runtime import java_executable

ROOT = APP.parent
RUNTIME = ROOT / ".runtime"
PYTHON = RUNTIME / "python" / "Scripts" / "python.exe"
ELECTRON_VERSION = "34.5.8"
ELECTRON_FILE = f"electron-v{ELECTRON_VERSION}-win32-x64.zip"
ELECTRON_SHA256 = "ac880c62339b91c6833b3edaabbb62d9148b27f01b410a3b2100cb4ce92b7b11"
ELECTRON = RUNTIME / "electron" / "electron.exe"
REQ = APP / "requirements.txt"


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def check_system():
    if (sysconfig.get_platform() != "win-amd64"
            or not (3, 12) <= sys.version_info[:2] <= (3, 14)
            or sysconfig.get_config_var("Py_GIL_DISABLED")):
        raise RuntimeError("Necesitas Python 3.12, 3.13 o 3.14 para Windows x64.")
    for name in ["frontend/dist/index.html", "ffdec/ffdec.jar", "ffdec/flashlib/playerglobal32_0.swc", "tools/ffdec_add_class/com/naw/ffdec/AddAs3Classes.class", "static/ruffle/ruffle.js"]:
        if not (APP / name).is_file():
            raise RuntimeError(f"La descarga del proyecto esta incompleta: falta app/{name}")


def local_python_works():
    if not PYTHON.is_file():
        return False
    try:
        return subprocess.run(
            [str(PYTHON), "-I", "-c", "import sys, sysconfig; assert (3,12) <= sys.version_info[:2] <= (3,14) and sysconfig.get_platform() == 'win-amd64' and not sysconfig.get_config_var('Py_GIL_DISABLED')"],
            capture_output=True,
        ).returncode == 0
    except OSError:
        return False


def dependencies_ready():
    check = """
import importlib.metadata
import sys
from packaging.requirements import Requirement
from packaging.version import Version

with open(sys.argv[1], encoding="utf-8") as lock:
    for line in lock:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker is None or requirement.marker.evaluate():
            assert Version(importlib.metadata.version(requirement.name)) in requirement.specifier
"""
    return subprocess.run([str(PYTHON), "-I", "-c", check, str(REQ)], capture_output=True).returncode == 0


def libraries_work():
    return subprocess.run(
        [str(PYTHON), "-I", "-c", "import flask, mitmproxy, requests, urllib3, PIL, imagehash, numpy, onnxruntime, huggingface_hub, cv2"],
        capture_output=True,
    ).returncode == 0


def electron_ready():
    folder = ELECTRON.parent
    try:
        return (
            (folder / "version").read_text().strip().lstrip("v") == ELECTRON_VERSION
            and all((folder / name).stat().st_size > 0 for name in (
                "electron.exe", "icudtl.dat", "resources.pak", "chrome_100_percent.pak",
                "chrome_200_percent.pak", "ffmpeg.dll", "v8_context_snapshot.bin",
                "locales/en-US.pak",
            ))
        )
    except (OSError, UnicodeError):
        return False


def install_electron():
    url = f"https://github.com/electron/electron/releases/download/v{ELECTRON_VERSION}/{ELECTRON_FILE}"
    archive = RUNTIME / ELECTRON_FILE
    partial = archive.with_suffix(".part")
    print("Descargando el motor de escritorio Electron...", flush=True)
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "naw-trucador-installer"})
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
        if digest.hexdigest() != ELECTRON_SHA256:
            raise RuntimeError("La descarga de Electron no coincide con su SHA-256 oficial. Reintenta la instalacion.")
        partial.replace(archive)
        destination = RUNTIME / "electron"
        destination.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise RuntimeError("Ruta invalida dentro de la descarga de Electron")
            package.extractall(destination)
    finally:
        partial.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)


def prepare():
    check_system()
    verify_java()
    RUNTIME.mkdir(exist_ok=True)
    if not local_python_works():
        print("Preparando el entorno local de Python...", flush=True)
        # Keep a broken environment recoverable while building a replacement.
        if PYTHON.parent.parent.exists():
            import uuid
            PYTHON.parent.parent.rename(RUNTIME / f"python-anterior-{uuid.uuid4().hex[:8]}")
        venv.EnvBuilder(with_pip=True).create(RUNTIME / "python")

    pins_match = dependencies_ready()
    if not pins_match or not libraries_work():
        print("Reparando o instalando las librerias necesarias...", flush=True)
        if subprocess.run([str(PYTHON), "-m", "pip", "--version"], capture_output=True).returncode:
            run([PYTHON, "-m", "ensurepip"])
        options = ["--force-reinstall"] if pins_match else []
        run([PYTHON, "-m", "pip", "install", "--disable-pip-version-check", *options, "-r", REQ])
        run([PYTHON, "-m", "pip", "check"])
        if not dependencies_ready() or not libraries_work():
            raise RuntimeError("No se pudieron verificar las librerias de Python.")

    if not electron_ready():
        install_electron()
        if not electron_ready():
            raise RuntimeError("La instalacion de Electron quedo incompleta.")


def install():
    prepare()
    print("Motor Java OK", flush=True)
    print("Instalacion lista. Ya podes usar Abrir naw.bat.", flush=True)


def verify_java():
    helper = subprocess.run([java_executable(), "-cp", str(APP / "tools/ffdec_add_class") + os.pathsep + str(APP / "ffdec/lib/*"), "com.naw.ffdec.AddAs3Classes"], capture_output=True, text=True, errors="replace", timeout=15)
    if helper.returncode != 2 or "Usage: AddAs3Classes" not in helper.stderr:
        raise RuntimeError(f"El motor Java no se puede iniciar: {helper.stderr}")


def choose_port():
    for port in range(5500, 5520):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.2) as response:
                if json.load(response).get("root") == str(APP):
                    return port
        except (OSError, ValueError):
            pass
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError("No hay un puerto local libre entre 5500 y 5519.")


def launch(smoke=False):
    prepare()
    env = {**os.environ, "PYTHON": str(PYTHON), "PYTHONUNBUFFERED": "1", "PORT": str(choose_port())}
    env.pop("ELECTRON_RUN_AS_NODE", None)
    command = [ELECTRON, APP / "desktop/main.cjs"]
    result_path = RUNTIME / "smoke-result.json"
    if smoke:
        result_path.unlink(missing_ok=True)
        env["NAW_SMOKE_RESULT"] = str(result_path)
        command.append("--smoke-test")
    run(command, cwd=APP, env=env)
    if smoke:
        if not result_path.is_file() or not json.loads(result_path.read_text()).get("rendered"):
            raise RuntimeError("Electron no completo la verificacion de la interfaz")
        print("NAW_SMOKE_OK: ambos iniciadores y la interfaz funcionan.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "open", "verify", "smoke"])
    args = parser.parse_args()
    try:
        if args.action == "install":
            install()
        elif args.action == "verify":
            check_system()
            if not local_python_works() or not dependencies_ready() or not libraries_work() or not electron_ready():
                raise RuntimeError("La instalacion local necesita reparacion.")
            verify_java()
            print("Motor Java OK", flush=True)
        else:
            launch(smoke=args.action == "smoke")
    except (OSError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"\n[ERROR] {error}\nLa operacion no se completo. Corregi el problema y volve a ejecutar Instalar.bat.", file=sys.stderr, flush=True)
        sys.exit(1)
