# BioAttend — Fingerprint Attendance System
A school attendance system using your phone's fingerprint scanner via WebAuthn.

---

## Setup & Run

### 1. Install dependencies
```
pip install -r requirements.txt
```

### 2. Run the server
```
python app.py
```

You'll see something like:
```
* Running on http://0.0.0.0:5000
```

### 3. Find your laptop's local IP
- **Windows**: Open CMD → type `ipconfig` → look for IPv4 Address (e.g. 192.168.1.5)
- **Mac**: System Settings → Wi-Fi → Details → IP Address

### 4. Open on your phone
Make sure your phone and laptop are on the **same WiFi**.
Open Chrome or Safari on your phone and go to:
```
http://192.168.1.5:5000
```
(Replace with your actual IP)

### 5. Use it!
- Go to **➕ Register** tab → fill in student info → tap fingerprint button → scan
- Go to **📲 Scan In** tab → tap fingerprint → attendance logged!

---

## Files
```
bioattend/
├── app.py           ← Flask server
├── requirements.txt
├── data.json        ← auto-created, stores all data
└── templates/
    └── index.html   ← the web UI
```

## Notes
- Data is saved in `data.json` automatically
- WebAuthn requires HTTPS in production, but HTTP works on local network
- Each student registers on their own phone (fingerprint is device-specific)

---

## Deploy (Render.com)
This project includes a `Procfile` for Render.

- Push this folder to a GitHub repo
- On Render, create a **Web Service** from the repo
- Render will run: `gunicorn app:app` (and provide a permanent HTTPS URL)
