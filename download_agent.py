# =============================================================
# BOOTCAMP DOWNLOAD AGENT
# Automatically syncs the WBS Google Drive folder to your Mac.
# Runs daily at 08:00 and 17:00 as long as terminal is open.
# =============================================================
#
# ── FIRST TIME SETUP (do this once) ──────────────────────────
#
# 1. INSTALL DEPENDENCIES
#    Open terminal and run:
#    pip3.11 install schedule google-api-python-client google-auth-httplib2 google-auth-oauthlib
#
# 2. CREATE A GOOGLE CLOUD PROJECT
#    Go to: https://console.cloud.google.com
#    → Create a new project (name it anything, e.g. "bootcamp-agent")
#    → Search for "Google Drive API" → Enable it
#
# 3. CREATE CREDENTIALS
#    → APIs & Services → Credentials
#    → Create Credentials → OAuth 2.0 Client ID
#    → Application type: Desktop App → Create
#    → Download the JSON file → rename it to: credentials.json
#    → Place credentials.json in your ~/Desktop/Bootcamp/ folder
#
# 4. CONFIGURE OAUTH CONSENT SCREEN
#    → APIs & Services → OAuth Consent Screen
#    → Fill in App Name (anything) and your email
#    → Under "Audience" → Add your Gmail address as a test user
#
# 5. RUN THE AGENT (first run opens browser for Google login)
#    python3.11 ~/Desktop/Bootcamp/download_agent.py
#
# ── DAILY USE ─────────────────────────────────────────────────
#    Just run the command above. The token is saved after the
#    first login — no browser popup from then on.
#
# ── NOTES ─────────────────────────────────────────────────────
#    - credentials.json and .bootcamp_token.json are yours only.
#      Never share them. Do not push them to GitHub.
#    - Classroom recordings cannot be downloaded (Google restriction).
#    - The Bootcamp folder ID is the same for everyone.
# =============================================================
# Command for the terminal: python3.11 ~/Desktop/Bootcamp/download_agent.py
import json
import time
import schedule
import logging
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import io

# ── Konfiguration ──────────────────────────────────────────
SHARED_FOLDER_ID = "1enR0e38ynjUj4iHWB1OjBfOoBUHztZlH"
LOCAL_BOOTCAMP_DIR = Path.home() / "Desktop/Bootcamp"
TRACKER_FILE = Path.home() / ".bootcamp_tracker.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)
log = logging.getLogger(__name__)


# ── Authentifizierung ──────────────────────────────────────
def get_drive_service():
    creds = None
    token_path = Path.home() / ".bootcamp_token.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                Path.home() / "Desktop/Bootcamp/credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


# ── Tracker ────────────────────────────────────────────────
def load_tracker() -> set:
    if TRACKER_FILE.exists():
        return set(json.loads(TRACKER_FILE.read_text()))
    return set()


def save_tracker(seen_ids: set):
    TRACKER_FILE.write_text(json.dumps(list(seen_ids)))


# ── Drive Ordner rekursiv auflisten (mit Pfad) ────────────
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
                # Rekursiv mit erweitertem Pfad
                subfolder_path = current_path / item["name"]
                results.extend(list_all_files(service, item["id"], subfolder_path))
            else:
                # Pfad am File mitgeben
                item["local_path"] = current_path
                results.append(item)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


# ── Datei herunterladen ────────────────────────────────────
def download_file(service, file_id: str, file_name: str, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file_name

    EXPORT_MAP = {
        "application/vnd.google-apps.document":     ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet":  ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
        "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    }

    try:
        meta = service.files().get(
            fileId=file_id,
            fields="mimeType",
            supportsAllDrives=True
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
                fileId=file_id,
                supportsAllDrives=True
            )

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        dest_path.write_bytes(buffer.getvalue())
        log.info(f"  ✓ {dest_dir.relative_to(LOCAL_BOOTCAMP_DIR) / file_name}")

    except Exception as e:
        log.warning(f"  ✗ {file_name}: {e}")


# ── Haupt-Check ────────────────────────────────────────────
def check_for_updates():
    log.info("── Checking for new files ──────────────────")
    try:
        service = get_drive_service()
        seen_ids = load_tracker()
        all_files = list_all_files(service, SHARED_FOLDER_ID)

        new_files = [f for f in all_files if f["id"] not in seen_ids]

        if not new_files:
            log.info("Nichts Neues.")
            return

        log.info(f"{len(new_files)} neue Datei(en) gefunden:")
        for f in new_files:
            dest_dir = LOCAL_BOOTCAMP_DIR / f["local_path"]
            download_file(service, f["id"], f["name"], dest_dir)
            seen_ids.add(f["id"])

        save_tracker(seen_ids)
        log.info(f"Fertig. Gespeichert in: {LOCAL_BOOTCAMP_DIR}")

    except Exception as e:
        log.error(f"Fehler: {e}")


# ── Scheduler ──────────────────────────────────────────────
if __name__ == "__main__":
    LOCAL_BOOTCAMP_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Bootcamp-Agent gestartet.")
    check_for_updates()

    schedule.every().day.at("08:00").do(check_for_updates)
    schedule.every().day.at("17:00").do(check_for_updates)

    while True:
        schedule.run_pending()
        time.sleep(60)