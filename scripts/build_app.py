"""Optional PyInstaller build. CI does not need to run this.

On macOS (build on a Mac):

    pip install pyinstaller
    python scripts/build_app.py

That writes dist/FormDueBoard.app using assets/icon.icns.

On Windows (build on Windows):

    py -3 -m pip install pyinstaller
    py -3 scripts/build_app.py

That writes dist/FormDueBoard.exe using assets/icon.ico.

On Linux the same command writes a one-folder build under dist/FormDueBoard/.
The windowed .app and .exe bundles have to be produced on those systems;
a Linux CI job can skip this script.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    entry = ROOT / "scripts" / "pyinstaller_entry.py"
    icon = ROOT / "assets" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")
    data_sep = ";" if sys.platform == "win32" else ":"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "FormDueBoard",
        "--paths",
        str(ROOT),
        "--add-data",
        f"{ROOT / 'formdueboard' / 'web'}{data_sep}formdueboard/web",
        "--add-data",
        f"{ROOT / 'assets'}{data_sep}assets",
        "--add-data",
        f"{ROOT / 'config.example.yaml'}{data_sep}.",
        "--collect-submodules",
        "pypdf",
        "--collect-submodules",
        "docx",
    ]
    if sys.platform == "darwin":
        command += [
            "--windowed",
            "--icon",
            str(icon),
            "--osx-bundle-identifier",
            "com.formdueboard.local",
        ]
    elif sys.platform == "win32":
        command += ["--windowed", "--icon", str(icon)]
    elif icon.is_file():
        command += ["--icon", str(ROOT / "assets" / "icon.ico")]
    command.append(str(entry))
    print("Running:", " ".join(command))
    try:
        return subprocess.call(command, cwd=ROOT)
    except FileNotFoundError:
        print("PyInstaller is not installed. Run: pip install pyinstaller")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
