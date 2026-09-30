"""CustomTkinter operator GUI for Karaoke Ticker."""

from __future__ import annotations

import logging
import os
import tkinter.messagebox as messagebox
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import customtkinter as ctk
import qrcode

from app import create_app, create_runtime_state, start_server_thread
from config import AppConfig
from karaoke.services import (
    active_session,
    create_session,
    get_setting,
    set_external_application_path,
    set_playback_mode,
    set_setting,
    stop_session,
)
from karaoke.utils import get_lan_ip

logger = logging.getLogger(__name__)


class KaraokeTickerGUI(ctk.CTk):
    """Main operator GUI."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Karaoke Ticker")
        self.geometry("760x760")
        self.resizable(True, True)

        self.config_obj = AppConfig()
        self.runtime_state = create_runtime_state(self.config_obj)
        self.flask_app = create_app(self.runtime_state, self.config_obj)
        self.server_thread = None

        self._build_ui()
        self._refresh_state()
        self._schedule_status_refresh()
        self.after(350, self._run_first_launch_setup)

    def _build_ui(self) -> None:
        ctk.CTkLabel(self, text="KARAOKE TICKER", font=("Arial", 32, "bold")).pack(pady=20)

        self.status_var = ctk.StringVar(value="STOPPED")
        self.house_code_var = ctk.StringVar(value="------")
        self.url_var = ctk.StringVar(value="Not started")
        self.index_status_var = ctk.StringVar(value="Idle")
        self.index_compare_var = ctk.StringVar(value="No snapshot yet")
        self.index_last_run_var = ctk.StringVar(value="Never")
        self.index_progress_text_var = ctk.StringVar(value="Idle")

        panel = ctk.CTkFrame(self)
        panel.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(panel, text="Session Status:", anchor="w").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, textvariable=self.status_var, anchor="w").grid(row=0, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, text="House Code:", anchor="w").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, textvariable=self.house_code_var, anchor="w").grid(row=1, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, text="Guest URL:", anchor="w").grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, textvariable=self.url_var, anchor="w", wraplength=560).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, text="Index Status:", anchor="w").grid(row=3, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, textvariable=self.index_status_var, anchor="w", wraplength=560).grid(row=3, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, text="Index Compare:", anchor="w").grid(row=4, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, textvariable=self.index_compare_var, anchor="w", wraplength=560).grid(row=4, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, text="Last Index Run:", anchor="w").grid(row=5, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, textvariable=self.index_last_run_var, anchor="w").grid(row=5, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(panel, text="Index Progress:", anchor="w").grid(row=6, column=0, padx=8, pady=8, sticky="w")
        self.index_progress_bar = ctk.CTkProgressBar(panel, mode="determinate", width=360)
        self.index_progress_bar.grid(row=6, column=1, padx=8, pady=8, sticky="w")
        self.index_progress_bar.set(0)
        ctk.CTkLabel(panel, textvariable=self.index_progress_text_var, anchor="w").grid(row=7, column=1, padx=8, pady=(0, 8), sticky="w")

        btns = ctk.CTkScrollableFrame(self, height=300)
        btns.pack(fill="both", expand=True, padx=24, pady=16)

        buttons = [
            ("START HOUSE", self.start_house),
            ("STOP HOUSE", self.stop_house),
            ("SHOW QR CODE", self.show_qr_code),
            ("SHOW KIOSK QR", self.show_kiosk_qr),
            ("SHOW TICKER QR", self.show_ticker_qr),
            ("OPEN KIOSK", self.open_kiosk),
            ("OPEN ADMIN", self.open_admin),
            ("OPEN TICKER", self.open_ticker),
            ("REFRESH KARAOKE LIBRARY", self.refresh_library),
            ("COMPARE LIBRARY SNAPSHOT", self.compare_library_snapshot),
            ("SETTINGS", self.open_settings_dialog),
            ("EXIT", self.destroy),
        ]
        for idx, (label, command) in enumerate(buttons):
            ctk.CTkButton(btns, text=label, command=command, height=42).grid(
                row=idx // 2, column=idx % 2, padx=10, pady=10, sticky="ew"
            )
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

    def _ensure_server_running(self, port: int) -> None:
        if not (1 <= int(port) <= 65535):
            raise ValueError("Configured port must be between 1 and 65535.")
        if self.server_thread and self.server_thread.is_alive():
            return
        logger.info("Starting embedded web server host=%s port=%s", self.config_obj.host, port)
        self.server_thread = start_server_thread(self.flask_app, self.config_obj.host, port)

    def _refresh_state(self) -> None:
        with self.runtime_state.db.session_scope() as db:
            record = active_session(db)
            port = int(get_setting(db, "web_server_port") or "8080")
            ip = get_lan_ip()
            if record:
                self.status_var.set("RUNNING")
                self.house_code_var.set(record.house_code)
                self.url_var.set(f"http://{ip}:{port}/join?code={record.house_code}")
            else:
                self.status_var.set("STOPPED")
                self.house_code_var.set("------")
                self.url_var.set(f"http://{ip}:{port}")

        self.index_status_var.set(getattr(self.runtime_state, "index_status", "Idle"))
        self.index_compare_var.set(getattr(self.runtime_state, "index_compare_summary", "No snapshot yet"))
        self.index_last_run_var.set(getattr(self.runtime_state, "index_last_run", "Never"))
        progress_value = float(getattr(self.runtime_state, "index_progress", 0.0) or 0.0)
        if progress_value < 0.0:
            progress_value = 0.0
        if progress_value > 1.0:
            progress_value = 1.0
        self.index_progress_bar.set(progress_value)
        self.index_progress_text_var.set(getattr(self.runtime_state, "index_progress_text", "Idle"))


    def start_house(self) -> None:
        try:
            with self.runtime_state.db.session_scope() as db:
                port = int(get_setting(db, "web_server_port") or "8080")
                self._ensure_server_running(port)
                house_name = get_setting(db, "house_name") or "Karaoke Ticker"
                record = create_session(db, house_name)
                ip = get_lan_ip()
                self.runtime_state.current_house_code = record.house_code
                self.runtime_state.current_session_id = record.id
                self.runtime_state.admin_token = record.admin_token
                self.runtime_state.guest_url = f"http://{ip}:{port}/join?code={record.house_code}"
                self._create_qr(self.runtime_state.guest_url)
                # Also create kiosk QR (link to /kiosk)
                kiosk_url = f"http://{ip}:{port}/kiosk"
                self._create_kiosk_qr(kiosk_url)
                # Also create ticker QR (tokenized ticker endpoint)
                ticker_url = f"http://{ip}:{port}/ticker?token={record.ticker_token}"
                self._create_ticker_qr(ticker_url)
        except Exception as exc:
            logger.exception("Failed to start house")
            messagebox.showerror("Start Error", f"Unable to start house: {exc}")
            return
        self._refresh_state()
        messagebox.showinfo("House Started", "House is now running.")

    def stop_house(self) -> None:
        with self.runtime_state.db.session_scope() as db:
            record = active_session(db)
            if not record:
                messagebox.showinfo("Stop House", "No active house session.")
                return
            stop_session(db, record.id)
        self._refresh_state()
        messagebox.showinfo("House Stopped", "Session stopped. Users and songs were preserved.")

    def _create_qr(self, url: str) -> None:
        output = Path("data") / "guest_qr.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        img = qrcode.make(url)
        img.save(output)
        self.runtime_state.qr_path = str(output.resolve())

    def _create_kiosk_qr(self, url: str) -> None:
        output = Path("data") / "kiosk_qr.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            img = qrcode.make(url)
            img.save(output)
            self.runtime_state.kiosk_qr_path = str(output.resolve())
        except Exception:
            # don't crash GUI if QR generation fails
            self.runtime_state.kiosk_qr_path = ""

    def _create_ticker_qr(self, url: str) -> None:
        output = Path("data") / "ticker_qr.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            img = qrcode.make(url)
            img.save(output)
            self.runtime_state.ticker_qr_path = str(output.resolve())
        except Exception:
            # don't crash GUI if QR generation fails
            self.runtime_state.ticker_qr_path = ""

    def show_qr_code(self) -> None:
        if not self.runtime_state.qr_path:
            messagebox.showwarning("QR Code", "Start a house first.")
            return
        webbrowser.open(Path(self.runtime_state.qr_path).as_uri())

    def show_kiosk_qr(self) -> None:
        if not self.runtime_state.kiosk_qr_path:
            messagebox.showwarning("Kiosk QR", "Start a house first.")
            return
        webbrowser.open(Path(self.runtime_state.kiosk_qr_path).as_uri())

    def show_ticker_qr(self) -> None:
        if not self.runtime_state.ticker_qr_path:
            messagebox.showwarning("Ticker QR", "Start a house first.")
            return
        webbrowser.open(Path(self.runtime_state.ticker_qr_path).as_uri())

    def _active_admin_urls(self) -> tuple[str, str]:
        with self.runtime_state.db.session_scope() as db:
            record = active_session(db)
            if not record:
                raise ValueError("No active session.")
            port = int(get_setting(db, "web_server_port") or "8080")
            ip = get_lan_ip()
            admin_url = f"http://{ip}:{port}/admin?token={record.admin_token}"
            ticker_url = f"http://{ip}:{port}/ticker?token={record.ticker_token}"
            return admin_url, ticker_url

    def open_admin(self) -> None:
        try:
            admin_url, _ = self._active_admin_urls()
            webbrowser.open(admin_url)
        except Exception as exc:
            messagebox.showwarning("Admin", str(exc))

    def open_kiosk(self) -> None:
        try:
            # kiosk does not require a token; open guest-facing kiosk page
            with self.runtime_state.db.session_scope() as db:
                port = int(get_setting(db, "web_server_port") or "8080")
                ip = get_lan_ip()
                kiosk_url = f"http://{ip}:{port}/kiosk"
                webbrowser.open(kiosk_url)
        except Exception as exc:
            messagebox.showwarning("Kiosk", str(exc))

    def open_ticker(self) -> None:
        try:
            _, ticker_url = self._active_admin_urls()
            webbrowser.open(ticker_url)
        except Exception as exc:
            messagebox.showwarning("Ticker", str(exc))

    def refresh_library(self) -> None:
        # Request a background re-index. Indexer will skip indexing while a house session is running.
        indexer = getattr(self.runtime_state, "indexer", None)
        if not indexer:
            messagebox.showwarning("Library", "Background indexer not available.")
            return
        # Ensure folder is configured before requesting an index pass
        with self.runtime_state.db.session_scope() as db:
            folder = get_setting(db, "karaoke_folder")
            if not folder:
                messagebox.showwarning("Library", "Set Karaoke Folder in Settings first.")
                return
        try:
            indexer.request_index()
            messagebox.showinfo(
                "Library",
                "Index refresh requested. If house is running, build will defer and run after house stops.",
            )
        except Exception as exc:
            logger.exception("Failed to request karaoke index refresh")
            messagebox.showerror("Library Error", f"Failed to request index: {exc}")

    def compare_library_snapshot(self) -> None:
        indexer = getattr(self.runtime_state, "indexer", None)
        if not indexer:
            messagebox.showwarning("Library", "Background indexer not available.")
            return
        with self.runtime_state.db.session_scope() as db:
            folder = get_setting(db, "karaoke_folder")
            if not folder:
                messagebox.showwarning("Library", "Set Karaoke Folder in Settings first.")
                return
        try:
            indexer.request_compare()
            messagebox.showinfo("Library", "Snapshot compare requested. Check Index Compare for results.")
        except Exception as exc:
            logger.exception("Failed to request library snapshot compare")
            messagebox.showerror("Library Error", f"Failed to request compare: {exc}")

    def _schedule_status_refresh(self) -> None:
        self._refresh_state()
        self.after(1500, self._schedule_status_refresh)

    def _run_first_launch_setup(self) -> None:
        try:
            with self.runtime_state.db.session_scope() as db:
                first_run_completed = get_setting(db, "first_run_completed") == "1"
            if first_run_completed:
                return
            messagebox.showinfo(
                "Welcome to Karaoke Ticker",
                "Karaoke Ticker is ready to run standalone with the built-in player. Configure your first-run settings now.",
            )
            self.open_settings_dialog(first_run=True)
        except Exception:
            logger.exception("Failed to start first-run setup flow")

    def open_settings_dialog(self, *, first_run: bool = False) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Welcome to Karaoke Ticker" if first_run else "Settings")
        dialog.geometry("680x460")
        fields: dict[str, ctk.CTkEntry] = {}
        rows = [
            ("house_name", "House Name"),
            ("karaoke_folder", "Karaoke Folder"),
            ("karaoke_manifest_path", "Manifest JSON Path"),
            ("external_application_path", "External Application Path (optional)"),
            ("web_server_port", "Port"),
            ("ticker_upcoming_count", "Upcoming Singers"),
        ]

        with self.runtime_state.db.session_scope() as db:
            values = {key: get_setting(db, key) for key, _ in rows}
            rotation_value = get_setting(db, "singer_rotation_on")
            playback_mode = get_setting(db, "playback_mode") or "built_in"

        if first_run:
            ctk.CTkLabel(
                dialog,
                text="Configure your karaoke folder and defaults. Built-In Player is recommended.",
                wraplength=620,
                justify="left",
            ).grid(row=0, column=0, columnspan=2, padx=10, pady=(8, 0), sticky="w")

        start_row = 1 if first_run else 0
        for idx, (key, label) in enumerate(rows):
            ctk.CTkLabel(dialog, text=label).grid(row=start_row + idx, column=0, padx=10, pady=8, sticky="w")
            entry = ctk.CTkEntry(dialog, width=440)
            entry.insert(0, values.get(key, ""))
            entry.grid(row=start_row + idx, column=1, padx=10, pady=8, sticky="ew")
            fields[key] = entry

        playback_mode_var = ctk.StringVar(value=playback_mode)
        ctk.CTkLabel(dialog, text="Playback Mode").grid(row=start_row + len(rows), column=0, padx=10, pady=8, sticky="w")
        ctk.CTkOptionMenu(
            dialog,
            variable=playback_mode_var,
            values=["built_in", "system_default", "external_application"],
            width=440,
        ).grid(row=start_row + len(rows), column=1, padx=10, pady=8, sticky="w")

        rotation_var = ctk.BooleanVar(value=rotation_value == "1")
        ctk.CTkCheckBox(dialog, text="Singer Rotation", variable=rotation_var).grid(
            row=start_row + len(rows) + 1, column=1, padx=10, pady=10, sticky="w"
        )

        def save() -> None:
            try:
                house_name = fields["house_name"].get().strip()
                if not house_name:
                    messagebox.showerror("Settings Error", "House Name is required.")
                    return

                port_text = fields["web_server_port"].get().strip()
                if not port_text.isdigit() or not (1 <= int(port_text) <= 65535):
                    messagebox.showerror("Settings Error", "Port must be between 1 and 65535.")
                    return

                external_path = fields["external_application_path"].get().strip()
                playback_mode = playback_mode_var.get().strip().lower()
                if playback_mode == "external_application":
                    if not external_path:
                        messagebox.showerror("Settings Error", "External application path is required for External Application mode.")
                        return
                    external_path_obj = Path(external_path).expanduser()
                    if not external_path_obj.exists():
                        messagebox.showerror("Settings Error", "External application path does not exist.")
                        return
                    if os.name == "nt" and external_path_obj.suffix.lower() not in {".exe", ".bat", ".cmd", ".com"}:
                        messagebox.showerror("Settings Error", "On Windows, external application must be an executable file.")
                        return

                with self.runtime_state.db.session_scope() as db:
                    for key, entry in fields.items():
                        if key == "external_application_path":
                            set_external_application_path(db, entry.get().strip())
                        else:
                            set_setting(db, key, entry.get().strip())
                    set_playback_mode(db, playback_mode_var.get().strip())
                    set_setting(db, "singer_rotation_on", "1" if rotation_var.get() else "0")
                    set_setting(db, "first_run_completed", "1")

                dialog.destroy()
                self._refresh_state()
                if first_run and fields["karaoke_folder"].get().strip():
                    if messagebox.askyesno("Build Karaoke Index", "Build karaoke index now?"):
                        self.refresh_library()
                messagebox.showinfo("Settings", "Settings saved.")
            except Exception as exc:
                logger.exception("Failed saving settings")
                messagebox.showerror("Settings Error", str(exc))

        ctk.CTkButton(dialog, text="Save", command=save).grid(
            row=start_row + len(rows) + 2, column=1, padx=10, pady=10, sticky="e"
        )


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = KaraokeTickerGUI()
    app.mainloop()
