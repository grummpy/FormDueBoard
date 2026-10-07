import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LAUNCHERS = {
    "Launch FormDueBoard.command": True,
    "launch.sh": True,
    "Launch FormDueBoard.bat": False,
    "formdueboard.desktop": True,
}


def test_launcher_files_exist_and_point_at_the_module():
    for name, executable in LAUNCHERS.items():
        path = ROOT / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        if name.endswith(".desktop"):
            assert "launch.sh" in text
            assert "FormDueBoard" in text
        else:
            assert "python -m formdueboard" in text
            assert "https://www.python.org/downloads/" in text
            assert "3.11" in text
        if executable:
            mode = path.stat().st_mode
            assert mode & stat.S_IXUSR, name
    assert "python -m formdueboard" in (ROOT / "launch.sh").read_text(encoding="utf-8")
    assert os.access(ROOT / "Launch FormDueBoard.command", os.X_OK)
    assert os.access(ROOT / "launch.sh", os.X_OK)


def test_shell_launchers_pass_bash_syntax_check():
    for name in ("Launch FormDueBoard.command", "launch.sh"):
        subprocess.run(["bash", "-n", str(ROOT / name)], check=True)


def test_icons_and_cover_exist():
    svg = (ROOT / "assets" / "icon.svg").read_text(encoding="utf-8")
    assert "<svg" in svg
    assert _png_size(ROOT / "assets" / "icon-512.png") == (512, 512)
    assert _png_size(ROOT / "assets" / "icon-1024.png") == (1024, 1024)
    assert _png_size(ROOT / "assets" / "icon.png") == (1024, 1024)
    ico = (ROOT / "assets" / "icon.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00"
    icns = (ROOT / "assets" / "icon.icns").read_bytes()
    assert icns[:4] == b"icns"
    cover = (ROOT / "docs" / "cover.jpg").read_bytes()
    assert cover[:3] == b"\xff\xd8\xff"
    assert len(cover) > 20_000
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/cover.jpg" in readme
    assert "Quick start" in readme
    assert "double-click" in readme.lower()


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height
