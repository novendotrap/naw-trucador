"""Windows installer/launcher. Standard library only; no global Python packages required."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
import urllib.request
import venv
import zipfile
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
RUNTIME = ROOT / ".runtime"
PYTHON = RUNTIME / "python" / "Scripts" / "python.exe"
ELECTRON_VERSION = "34.5.8"
ELECTRON_FILE = f"electron-v{ELECTRON_VERSION}-win32-x64.zip"
ELECTRON_SHA256 = "ac880c62339b91c6833b3edaabbb62d9148b27f01b410a3b2100cb4ce92b7b11"
ELECTRON = RUNTIME / "electron" / "electron.exe"
MARKER = RUNTIME / "installed.json"
REQ = APP / "requirements.txt"


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def check_system():
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("Necesitas Windows y Python de 64 bits.")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Instala Python 3.12 de 64 bits: https://www.python.org/downloads/windows/")
    java = shutil.which("java")
    if not java:
        raise RuntimeError("Falta Java 17 o superior en PATH. Descarga: https://adoptium.net/temurin/releases/?version=17")
    result = subprocess.run([java, "-version"], capture_output=True, text=True, errors="replace")
    import re
    match = re.search(r'version "([0-9]+)', result.stderr + result.stdout)
    if result.returncode or not match or int(match[1]) < 17:
        raise RuntimeError("Necesitas Java 17 o superior. Verifica con: java -version")
    for name in ["frontend/dist/index.html", "ffdec/ffdec.jar", "ffdec/flashlib/playerglobal32_0.swc", "tools/ffdec_add_class/com/naw/ffdec/AddAs3Classes.class", "static/ruffle/ruffle.js"]:
        if not (APP / name).is_file():
            raise RuntimeError(f"La descarga del proyecto esta incompleta: falta app/{name}")


def expected():
    return {"requirements": hashlib.sha256(REQ.read_bytes()).hexdigest(), "electron": ELECTRON_VERSION, "python": "3.12", "root": str(ROOT)}


def installed():
    try:
        return MARKER.is_file() and json.loads(MARKER.read_text()) == expected() and PYTHON.is_file() and ELECTRON.is_file()
    except (OSError, ValueError):
        return False


def install_electron():
    if ELECTRON.is_file():
        version = subprocess.run([str(ELECTRON), "--version"], capture_output=True, text=True, env={key: value for key, value in os.environ.items() if key != "ELECTRON_RUN_AS_NODE"})
        # Presence alone is not the installation marker. The download is verified below on a clean install.
        if version.returncode == 0 and version.stdout.strip() == f"v{ELECTRON_VERSION}":
            return
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


def install():
    check_system()
    RUNTIME.mkdir(exist_ok=True)
    print("[1/3] Preparando Python local...", flush=True)
    if not PYTHON.exists():
        venv.EnvBuilder(with_pip=True).create(RUNTIME / "python")
    print("[2/3] Instalando librerias... La primera vez puede tardar varios minutos.", flush=True)
    run([PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "-r", REQ])
    run([PYTHON, "-m", "pip", "check"])
    print("[3/3] Preparando la ventana de escritorio...", flush=True)
    install_electron()
    verify()
    MARKER.write_text(json.dumps(expected(), indent=2), encoding="utf-8")
    print("Instalacion completada. Ya podes usar Abrir naw.bat.", flush=True)


def verify():
    run([PYTHON, "-c", "import flask, mitmproxy, requests, urllib3, PIL, imagehash, numpy, onnxruntime, huggingface_hub, cv2; print('Librerias OK')"])
    helper = subprocess.run(["java", "-cp", str(APP / "tools/ffdec_add_class") + os.pathsep + str(APP / "ffdec/lib/*"), "com.naw.ffdec.AddAs3Classes"], capture_output=True, text=True, errors="replace")
    if helper.returncode != 2 or "Usage: AddAs3Classes" not in helper.stderr:
        raise RuntimeError(f"El motor Java no se puede iniciar: {helper.stderr}")
    print("Motor Java OK", flush=True)


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
    check_system()
    if not installed():
        install()
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
        if args.action == "install": install()
        elif args.action == "verify": check_system(); verify()
        else: launch(smoke=args.action == "smoke")
    except (OSError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"\n[ERROR] {error}\nLa operacion no se completo. Corregi el problema y volve a ejecutar Instalar.bat.", file=sys.stderr, flush=True)
        sys.exit(1)
