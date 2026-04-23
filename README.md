# Bootcamp Drive Sync

A desktop app that automatically syncs your WBS Coding School Google Drive folder 
to your local machine. Runs daily at 08:00 and 17:00, downloads new files 
automatically, and preserves the original folder structure.

![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

- Connects to a shared Google Drive folder
- Downloads all new files to a local folder of your choice
- Preserves the original folder and subfolder structure
- Runs automatic checks twice a day (08:00 and 17:00)
- Tracks which files have already been downloaded — no duplicates
- Built-in Setup Guide so you never have to read documentation

---

## Requirements

- macOS (tested on macOS with Apple Silicon)
- Python 3.11
- A Google account with access to the shared Drive folder

---

## Installation

**1. Install Python 3.11**

Download from [python.org](https://www.python.org/downloads/) or via Homebrew:
```bash
brew install python@3.11
```

**2. Install dependencies**
```bash
pip3.11 install customtkinter schedule google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

**3. Install Tkinter support (macOS)**
```bash
brew install python-tk@3.11
```

**4. Clone or download this repository**
```bash
git clone https://github.com/Velonaut1974/WBS-Google-Drive-Sync.git
cd WBS-Google-Drive-Sync
```

---

## Google API Setup (do this once)

This is the only complicated part. Follow these steps carefully.

### Step 1 — Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **"New Project"** → give it any name (e.g. `bootcamp-sync`) → **Create**
3. In the search bar, find **"Google Drive API"** → **Enable**

### Step 2 — Configure OAuth Consent Screen

1. Go to **APIs & Services → OAuth Consent Screen**
2. Fill in **App Name** (anything, e.g. `bootcamp-sync`) and your **email address**
3. Under **"Audience"** → click **"Add Users"** → add your Gmail address
4. Save

### Step 3 — Create Credentials

1. Go to **APIs & Services → Credentials**
2. Click **"Create Credentials"** → **"OAuth 2.0 Client ID"**
3. Application type: **Desktop App** → **Create**
4. Click the **download button** (arrow icon) next to your new credential
5. Rename the downloaded file to `credentials.json`
6. Place `credentials.json` in the same folder as `bootcamp_app.py`

> ⚠️ Never share your `credentials.json` with anyone.  
> Never upload it to GitHub or any public location.

---

## Running the App

```bash
python3.11 bootcamp_app.py
```

On first run, a browser window will open asking you to log in with your Google 
account and grant access. This happens only once — after that, the app 
remembers your login automatically.

---

## Configuration (inside the app)

Go to the **Settings** tab and fill in:

| Field | What to enter |
|---|---|
| Google Drive Folder ID | The ID from the shared Drive URL (see below) |
| Local Download Folder | Where you want files saved on your Mac |
| Path to credentials.json | Full path to your credentials.json file |

### How to find the Folder ID

Open the shared Google Drive folder in your browser. The URL looks like this:

https://drive.google.com/drive/folders/1enR0e38ynjUj4iHWB1OjBfOoBUHztZlH

The Folder ID is everything after `/folders/` — in this example:

1enR0e38ynjUj4iHWB1OjBfOoBUHztZlH

Copy only this part into the app. Do not include `?hl=DE` or anything after `?`.

---

## Known Limitations

- **Classroom recordings cannot be downloaded.** This is a Google restriction 
  on Meet/Classroom files — not a bug in this app.
- **Gemini Notes** from Google Meet are also restricted for the same reason.
- The app currently supports macOS only.

---

## Security

The following files are sensitive and must never be shared or uploaded to GitHub:

| File | Contains |
|---|---|
| `credentials.json` | Your Google API credentials |
| `.bootcamp_token.json` | Your personal Google login token |
| `.bootcamp_tracker.json` | List of already downloaded file IDs |

A `.gitignore` file is included in this repository to prevent accidental uploads.

---

## Built with

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — modern UI framework
- [Google Drive API v3](https://developers.google.com/drive/api/v3/about-sdk)
- [Schedule](https://schedule.readthedocs.io/) — automatic sync scheduling

---

## Author

Built by Andy — WBS Coding School, Data Science & AI Bootcamp 2026

