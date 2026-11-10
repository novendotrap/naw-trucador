"""Locate a Java runtime for the FFDec tools."""
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def java_executable() -> str:
    name = "java.exe" if os.name == "nt" else "java"
    candidates = []
    if home := os.environ.get("JAVA_HOME"):
        candidates.append(Path(home.strip('"')) / "bin" / name)
    if java := shutil.which(name):
        candidates.append(Path(java))
    candidates.extend(Path(entry.strip('"')) / name for entry in os.get_exec_path() if entry)

    if os.name == "nt":
        for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if not (root := os.environ.get(variable)):
                continue
            for vendor in ("Java", "Eclipse Adoptium", "Microsoft", "Amazon Corretto", "BellSoft", "Zulu", "Programs/Eclipse Adoptium"):
                candidates.extend((Path(root) / vendor).glob(f"*/bin/{name}"))

    for candidate in dict.fromkeys(candidates):
        if not candidate.is_file():
            continue
        try:
            result = subprocess.run([str(candidate), "-version"], capture_output=True,
                                    text=True, errors="replace", timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        version = re.search(r'version "(?:1\.)?(\d+)', result.stderr + result.stdout)
        if result.returncode == 0 and version and int(version[1]) >= 8:
            return str(candidate)

    raise RuntimeError("naw-trucador requiere Java 8 o superior para FFDec. Configura JAVA_HOME o agrega Java a PATH.")
