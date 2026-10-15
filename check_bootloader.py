"""Used by build.bat: is PyInstaller's launcher (bootloader) one compiled on this PC?

PyInstaller's prebuilt launcher is in thousands of programs, real malware among them, so
some antivirus scanners flag any exe that contains it. build.bat compiles its own copy.
Exit 0 = locally compiled, 1 = the stock prebuilt launcher or PyInstaller not installed yet,
2 = PyInstaller version not listed below (look up the stock hash and add it).
"""

import hashlib
import sys
from pathlib import Path

# SHA-256 of the prebuilt Windows-64bit-intel/runw.exe shipped with each PyInstaller release.
STOCK_RUNW_SHA256 = {
    "6.22.3": "2291f269c3a3804fde1079462239e09a8b32fffbeeaa8f628a531faf5be77d41",
}


def main() -> int:
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller is not installed yet")
        return 1
    runw = Path(PyInstaller.__file__).parent / "bootloader" / "Windows-64bit-intel" / "runw.exe"
    stock = STOCK_RUNW_SHA256.get(PyInstaller.__version__)
    if stock is None:
        print(f"PyInstaller {PyInstaller.__version__}: stock launcher hash unknown; add it to check_bootloader.py")
        return 2
    actual = hashlib.sha256(runw.read_bytes()).hexdigest()
    if actual == stock:
        print("PyInstaller launcher is the stock prebuilt one")
        return 1
    print(f"PyInstaller launcher compiled locally ({actual[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
