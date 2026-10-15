"""Build files stay in step with the changelog."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exe_file_version_matches_newest_changelog_entry() -> None:
    newest = re.search(r"^## v(\d+\.\d+\.\d+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    info = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    assert newest, "CHANGELOG.md has no version heading"
    version = newest.group(1)
    numbers = ", ".join(version.split(".")) + ", 0"
    assert f"filevers=({numbers})" in info and f"prodvers=({numbers})" in info
    assert f"StringStruct('FileVersion', '{version}')" in info
    assert f"StringStruct('ProductVersion', '{version}')" in info
