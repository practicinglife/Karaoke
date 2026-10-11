"""The desktop GUI module must at least import (catches syntax errors the web tests miss)."""


def test_gui_module_imports() -> None:
    import gui

    assert hasattr(gui, "KaraokeTickerGUI")
