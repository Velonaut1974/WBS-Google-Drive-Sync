import json
import time
import threading
import schedule
import logging
import webbrowser
from pathlib import Path
from datetime import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import io

# ── Konfiguration ──────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CONFIG_FILE = Path.home() / ".bootcamp_config.json"
TRACKER_FILE = Path.home() / ".bootcamp_tracker.json"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Config laden/speichern ─────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {
        "folder_id": "",
        "local_dir": str(Path.home() / "Desktop/Bootcamp"),
        "credentials_path": str(Path.home() / "Desktop/Bootcamp/credentials.json"),
    }


def save_config(config: dict):
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


# ── Drive Logik ────────────────────────────────────────────
def get_drive_service(credentials_path: str):
    creds = None
    token_path = Path.home() / ".bootcamp_token.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def list_all_files(service, folder_id: str, current_path: Path = Path("")) -> list:
    results = []
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None

    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
            pageToken=page_token,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()

        for item in response.get("files", []):
            if item["mimeType"] == "application/vnd.google-apps.folder":
                subfolder_path = current_path / item["name"]
                results.extend(list_all_files(service, item["id"], subfolder_path))
            else:
                item["local_path"] = current_path
                results.append(item)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def download_file(service, file_id: str, file_name: str, dest_dir: Path, log_fn):
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file_name

    EXPORT_MAP = {
        "application/vnd.google-apps.document":
            ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet":
            ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
        "application/vnd.google-apps.presentation":
            ("application/pdf", ".pdf"),
    }

    try:
        meta = service.files().get(
            fileId=file_id, fields="mimeType", supportsAllDrives=True
        ).execute()
        original_mime = meta["mimeType"]

        if original_mime in EXPORT_MAP:
            export_mime, ext = EXPORT_MAP[original_mime]
            if not dest_path.suffix:
                dest_path = dest_path.with_suffix(ext)
            request = service.files().export_media(
                fileId=file_id, mimeType=export_mime
            )
        else:
            request = service.files().get_media(
                fileId=file_id, supportsAllDrives=True
            )

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        dest_path.write_bytes(buffer.getvalue())
        log_fn(f"✓  {dest_dir.name}/{file_name}")

    except Exception as e:
        log_fn(f"✗  {file_name} (skipped)")


def load_tracker() -> set:
    if TRACKER_FILE.exists():
        return set(json.loads(TRACKER_FILE.read_text()))
    return set()


def save_tracker(seen_ids: set):
    TRACKER_FILE.write_text(json.dumps(list(seen_ids)))


# ══════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════
class BootcampApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self.is_running = False
        self.scheduler_thread = None

        self.title("Bootcamp Drive Sync")
        self.geometry("780x680")
        self.resizable(False, False)

        self._build_ui()

    # ── UI aufbauen ────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color=("#1a1a2e", "#0f0f1a"), height=80, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="☁  Bootcamp Drive Sync",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#4fc3f7"
        ).place(x=28, y=22)

        ctk.CTkLabel(
            header,
            text="Automatic Google Drive → Local Folder",
            font=ctk.CTkFont(size=12),
            text_color="#7ab8c8"
        ).place(x=31, y=52)

        # Tab view
        self.tabs = ctk.CTkTabview(self, width=740, height=540)
        self.tabs.pack(padx=20, pady=(16, 0))

        self.tabs.add("Sync")
        self.tabs.add("Settings")
        self.tabs.add("Setup Guide")

        self._build_sync_tab()
        self._build_settings_tab()
        self._build_guide_tab()

    # ── Sync Tab ───────────────────────────────────────────
    def _build_sync_tab(self):
        tab = self.tabs.tab("Sync")

        # Status card
        status_frame = ctk.CTkFrame(tab, fg_color=("#1e2a3a", "#111827"))
        status_frame.pack(fill="x", padx=10, pady=(16, 10))

        ctk.CTkLabel(
            status_frame,
            text="STATUS",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#4fc3f7"
        ).pack(anchor="w", padx=16, pady=(10, 2))

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Ready — press Sync Now to start",
            font=ctk.CTkFont(size=13),
            text_color="#a0c4d8"
        )
        self.status_label.pack(anchor="w", padx=16, pady=(0, 10))

        # Buttons
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        self.sync_btn = ctk.CTkButton(
            btn_row,
            text="⬇  Sync Now",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#0e7490",
            hover_color="#0891b2",
            height=44,
            command=self._start_sync
        )
        self.sync_btn.pack(side="left", padx=(0, 10))

        self.clear_btn = ctk.CTkButton(
            btn_row,
            text="🔄  Reset Tracker",
            font=ctk.CTkFont(size=13),
            fg_color="#374151",
            hover_color="#4b5563",
            height=44,
            command=self._reset_tracker
        )
        self.clear_btn.pack(side="left")

        ctk.CTkLabel(
            btn_row,
            text="Auto-sync: 08:00 & 17:00 daily",
            font=ctk.CTkFont(size=11),
            text_color="#4b5563"
        ).pack(side="right", padx=8)

        # Log area
        ctk.CTkLabel(
            tab,
            text="LOG",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#4fc3f7"
        ).pack(anchor="w", padx=14)

        self.log_box = ctk.CTkTextbox(
            tab,
            height=280,
            font=ctk.CTkFont(family="Courier", size=12),
            fg_color=("#0d1117", "#0d1117"),
            text_color="#a0c4d8",
            border_color="#1e3a4a",
            border_width=1
        )
        self.log_box.pack(fill="x", padx=10, pady=(4, 10))
        self.log_box.configure(state="disabled")

    # ── Settings Tab ───────────────────────────────────────
    def _build_settings_tab(self):
        tab = self.tabs.tab("Settings")

        def row(parent, label, value, browse_fn=None):
            ctk.CTkLabel(
                parent,
                text=label,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#7ab8c8"
            ).pack(anchor="w", padx=16, pady=(14, 2))

            row_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_frame.pack(fill="x", padx=16)

            entry = ctk.CTkEntry(
                row_frame,
                font=ctk.CTkFont(size=12),
                height=36,
                fg_color="#111827",
                border_color="#1e3a4a"
            )
            entry.insert(0, value)
            entry.pack(side="left", fill="x", expand=True)

            if browse_fn:
                ctk.CTkButton(
                    row_frame,
                    text="Browse",
                    width=80,
                    height=36,
                    fg_color="#374151",
                    hover_color="#4b5563",
                    command=lambda e=entry: browse_fn(e)
                ).pack(side="left", padx=(8, 0))

            return entry

        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)

        self.folder_id_entry = row(
            frame,
            "Google Drive Folder ID",
            self.config_data.get("folder_id", "")
        )

        def browse_dir(entry):
            path = filedialog.askdirectory()
            if path:
                entry.delete(0, "end")
                entry.insert(0, path)

        def browse_file(entry):
            path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
            if path:
                entry.delete(0, "end")
                entry.insert(0, path)

        self.local_dir_entry = row(
            frame,
            "Local Download Folder",
            self.config_data.get("local_dir", ""),
            browse_fn=browse_dir
        )

        self.credentials_entry = row(
            frame,
            "Path to credentials.json",
            self.config_data.get("credentials_path", ""),
            browse_fn=browse_file
        )

        ctk.CTkLabel(
            frame,
            text="The folder ID is the last part of your Google Drive URL:\nhttps://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE",
            font=ctk.CTkFont(size=11),
            text_color="#4b5563",
            justify="left"
        ).pack(anchor="w", padx=16, pady=(16, 0))

        ctk.CTkButton(
            frame,
            text="💾  Save Settings",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0e7490",
            hover_color="#0891b2",
            height=40,
            command=self._save_settings
        ).pack(anchor="w", padx=16, pady=(24, 0))

    # ── Setup Guide Tab ────────────────────────────────────
    def _build_guide_tab(self):
        tab = self.tabs.tab("Setup Guide")

        guide_text = """
STEP 1 — INSTALL DEPENDENCIES
Open your terminal and run:
pip3.11 install customtkinter schedule google-api-python-client google-auth-httplib2 google-auth-oauthlib


STEP 2 — CREATE A GOOGLE CLOUD PROJECT
→ Go to: https://console.cloud.google.com
→ Click "New Project" → give it any name (e.g. "bootcamp-agent") → Create
→ In the search bar, find "Google Drive API" → Enable it


STEP 3 — SET UP OAUTH CONSENT SCREEN
→ APIs & Services → OAuth Consent Screen
→ Fill in App Name (anything) and your email address
→ Under "Audience" → Add your Gmail address as a Test User
→ Save


STEP 4 — CREATE CREDENTIALS
→ APIs & Services → Credentials
→ Create Credentials → OAuth 2.0 Client ID
→ Application Type: Desktop App → Create
→ Download the JSON file
→ Rename it to: credentials.json
→ Place it in your download folder (or anywhere you like)


STEP 5 — CONFIGURE THIS APP
→ Go to the Settings tab
→ Paste your Google Drive Folder ID
  (the last part of the folder URL in your browser)
→ Choose your local download folder
→ Select your credentials.json file
→ Click Save Settings


STEP 6 — FIRST RUN
→ Click "Sync Now" on the Sync tab
→ A browser window will open → log in with your Google account
→ After login, syncing starts automatically
→ From now on, no browser popup needed


NOTE: Classroom recordings cannot be downloaded.
This is a Google restriction — not a bug.
"""
        box = ctk.CTkTextbox(
            tab,
            font=ctk.CTkFont(family="Courier", size=12),
            fg_color="#0d1117",
            text_color="#a0c4d8",
            border_color="#1e3a4a",
            border_width=1
        )
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("end", guide_text)
        box.configure(state="disabled")

        ctk.CTkButton(
            tab,
            text="🌐  Open Google Cloud Console",
            font=ctk.CTkFont(size=12),
            fg_color="#374151",
            hover_color="#4b5563",
            height=36,
            command=lambda: webbrowser.open("https://console.cloud.google.com")
        ).pack(pady=(0, 10))

    # ── Aktionen ───────────────────────────────────────────
    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{timestamp}]  {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str, color: str = "#a0c4d8"):
        self.status_label.configure(text=text, text_color=color)

    def _save_settings(self):
        self.config_data["folder_id"] = self.folder_id_entry.get().strip()
        self.config_data["local_dir"] = self.local_dir_entry.get().strip()
        self.config_data["credentials_path"] = self.credentials_entry.get().strip()
        save_config(self.config_data)
        self._log("Settings saved.")
        messagebox.showinfo("Saved", "Settings saved successfully.")

    def _reset_tracker(self):
        if TRACKER_FILE.exists():
            TRACKER_FILE.unlink()
        self._log("Tracker reset — all files will be re-downloaded on next sync.")
        self._set_status("Tracker reset.", "#f4a83a")

    def _start_sync(self):
        if self.is_running:
            return
        thread = threading.Thread(target=self._run_sync, daemon=True)
        thread.start()

    def _run_sync(self):
        self.is_running = True
        self.sync_btn.configure(state="disabled", text="⏳  Syncing...")
        self._set_status("Connecting to Google Drive...", "#4fc3f7")

        folder_id = self.config_data.get("folder_id", "").strip()
        local_dir = Path(self.config_data.get("local_dir", ""))
        credentials_path = self.config_data.get("credentials_path", "")

        if not folder_id:
            self._log("ERROR: No Folder ID set. Go to Settings.")
            self._set_status("Error — check settings.", "#f4713a")
            self._finish_sync()
            return

        if not Path(credentials_path).exists():
            self._log("ERROR: credentials.json not found. Check Settings path.")
            self._set_status("Error — credentials.json missing.", "#f4713a")
            self._finish_sync()
            return

        try:
            service = get_drive_service(credentials_path)
            seen_ids = load_tracker()
            local_dir.mkdir(parents=True, exist_ok=True)

            self._set_status("Scanning Drive folder...", "#4fc3f7")
            all_files = list_all_files(service, folder_id)
            new_files = [f for f in all_files if f["id"] not in seen_ids]

            if not new_files:
                self._log("Nothing new — all files are up to date.")
                self._set_status("Up to date ✓", "#00e0a8")
            else:
                self._log(f"Found {len(new_files)} new file(s). Downloading...")
                self._set_status(f"Downloading {len(new_files)} file(s)...", "#4fc3f7")

                for f in new_files:
                    dest_dir = local_dir / f["local_path"]
                    download_file(service, f["id"], f["name"], dest_dir, self._log)
                    seen_ids.add(f["id"])

                save_tracker(seen_ids)
                self._log(f"Done. Files saved to: {local_dir}")
                self._set_status(f"Sync complete ✓ — {len(new_files)} file(s) downloaded", "#00e0a8")

        except Exception as e:
            self._log(f"ERROR: {e}")
            self._set_status("Sync failed — see log.", "#f4713a")

        self._finish_sync()

    def _finish_sync(self):
        self.is_running = False
        self.sync_btn.configure(state="normal", text="⬇  Sync Now")

    def _start_scheduler(self):
        schedule.every().day.at("08:00").do(self._start_sync)
        schedule.every().day.at("17:00").do(self._start_sync)
        while True:
            schedule.run_pending()
            time.sleep(30)


# ── Start ──────────────────────────────────────────────────
if __name__ == "__main__":
    app = BootcampApp()

    scheduler_thread = threading.Thread(target=app._start_scheduler, daemon=True)
    scheduler_thread.start()

    app.mainloop()