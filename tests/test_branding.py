"""The app icon is on every page, in the desktop app and in the exe build."""

import json
from pathlib import Path

from karaoke.services import active_session, get_setting

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"


def test_every_page_links_the_app_icon() -> None:
    pages = [p for p in TEMPLATES.glob("*.html") if not p.name.startswith("_")]
    assert pages
    for page in pages:
        assert '{% include "_icons.html" %}' in page.read_text(encoding="utf-8"), page.name


def test_icon_files_and_manifest_are_served(client) -> None:
    for name in ["favicon.ico", "karaoke-ticker-icon.svg", "karaoke-ticker-icon-180.png"]:
        assert client.get(f"/static/img/{name}").status_code == 200, name
    manifest = json.loads(client.get("/static/manifest.json").data)
    for icon in manifest["icons"]:
        assert client.get(f"/static/{icon['src']}").status_code == 200, icon["src"]


def test_rendered_pages_show_icon_and_logo(app, client) -> None:
    with app.runtime_state.db.session_scope() as db:
        token = active_session(db).admin_token
        key = get_setting(db, "stage_button_secret")
    for url in [f"/stage?token={token}", f"/mic?key={key}"]:
        page = client.get(url).get_data(as_text=True)
        assert 'rel="apple-touch-icon"' in page and "img/favicon.ico" in page, url
        assert 'class="brand-logo"' in page, url


def test_desktop_app_and_exe_use_the_icon() -> None:
    import gui

    assert gui.APP_ICON.exists() and gui.APP_LOGO.exists()
    assert r"--icon web\static\img\favicon.ico" in (ROOT / "build.bat").read_text()
