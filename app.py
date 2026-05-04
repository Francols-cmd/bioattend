from flask import Flask, render_template, request, jsonify, session
import json, os, uuid
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "bioattend-secret-key-2024"

DATA_FILE = "data.json"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # Change this in production!
ABSENT_FINE_AMOUNT = 10

# ── helpers ──────────────────────────────────────────────────
def load():
    if not os.path.exists(DATA_FILE):
        return {"students": [], "logs": [], "courses": [], "sections": [], "yearLevels": ["1st Year","2nd Year","3rd Year","4th Year"], "activities": []}
    with open(DATA_FILE) as f:
        data = json.load(f)
    if "courses" not in data: data["courses"] = []
    if "sections" not in data: data["sections"] = []
    if "yearLevels" not in data: data["yearLevels"] = ["1st Year","2nd Year","3rd Year","4th Year"]
    if "activities" not in data: data["activities"] = []
    if "students" not in data: data["students"] = []
    # Data migration: ensure fines fields exist
    for s in data["students"]:
        if "fineBalance" not in s:
            s["fineBalance"] = 0
        if "fineHistory" not in s:
            s["fineHistory"] = []
    return data

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def _add_fine(data, student_id: str, activity_id: str, reason: str, amount: int = ABSENT_FINE_AMOUNT):
    student = next((s for s in data.get("students", []) if s.get("studentId") == student_id), None)
    if not student:
        return False
    student["fineBalance"] = int(student.get("fineBalance") or 0) + int(amount)
    hist = student.get("fineHistory") or []
    hist.insert(0, {
        "id": str(uuid.uuid4()),
        "amount": int(amount),
        "reason": reason,
        "activityId": activity_id,
        "createdAt": datetime.now().isoformat()
    })
    student["fineHistory"] = hist
    return True

def _ensure_activity_attendance(activity):
    if "attendance" not in activity or not isinstance(activity["attendance"], list):
        activity["attendance"] = []
    # normalize records
    for r in activity["attendance"]:
        if "fineApplied" not in r:
            r["fineApplied"] = False

def _finalize_activity_absences(data, activity):
    _ensure_activity_attendance(activity)
    present_ids = {r.get("studentId") for r in activity["attendance"] if r.get("studentId")}
    added_absent = 0
    fined = 0
    for s in data.get("students", []):
        sid = s.get("studentId")
        if not sid:
            continue
        if sid in present_ids:
            continue
        # create an absent record (only once)
        existing = next((r for r in activity["attendance"] if r.get("studentId") == sid), None)
        if existing:
            # if they exist but were set absent later, fine if not applied
            if existing.get("status") == "absent" and not existing.get("fineApplied"):
                if _add_fine(data, sid, activity.get("id", ""), f"Absent in {activity.get('name','activity')}"):
                    existing["fineApplied"] = True
                    fined += 1
            continue
        rec = {
            "studentId": sid,
            "name": s.get("name", ""),
            "course": s.get("course", ""),
            "yearLevel": s.get("yearLevel", ""),
            "section": s.get("section", ""),
            "status": "absent",
            "time": "",
            "markedAt": datetime.now().isoformat(),
            "fineApplied": False
        }
        # apply fine immediately for absence
        if _add_fine(data, sid, activity.get("id", ""), f"Absent in {activity.get('name','activity')}"):
            rec["fineApplied"] = True
            fined += 1
        activity["attendance"].append(rec)
        added_absent += 1
    return {"addedAbsent": added_absent, "fined": fined}

# ── auth ──────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    body = request.json
    if body.get("username") == ADMIN_USERNAME and body.get("password") == ADMIN_PASSWORD:
        session["admin"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("admin", None)
    return jsonify({"ok": True})

@app.route("/api/me")
def me():
    return jsonify({"admin": bool(session.get("admin"))})

# ── pages ──────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ── students ───────────────────────────────────────────────────
@app.route("/api/students", methods=["GET"])
def get_students():
    return jsonify(load()["students"])

@app.route("/api/students", methods=["POST"])
def add_student():
    data = load()
    body = request.json
    cred_id = body.get("credentialId", "").strip()
    duplicate = next((s for s in data["students"] if s["credentialId"] == cred_id), None)
    flagged = bool(cred_id) and duplicate is not None
    full_name = " ".join(filter(None,[
        body.get("firstName","").strip(),
        body.get("middleName","").strip(),
        body.get("lastName","").strip(),
        body.get("suffix","").strip()
    ]))
    student = {
        "id": str(uuid.uuid4()),
        "firstName": body.get("firstName","").strip(),
        "middleName": body.get("middleName","").strip(),
        "lastName": body.get("lastName","").strip(),
        "suffix": body.get("suffix","").strip(),
        "name": full_name,
        "studentId": body["studentId"],
        "phone": body.get("phone",""),
        "course": body.get("course",""),
        "yearLevel": body.get("yearLevel",""),
        "section": body.get("section",""),
        "credentialId": cred_id,
        "flagged": flagged,
        "flagReason": f"Same device as {duplicate['name']} ({duplicate['studentId']})" if flagged else "",
        "registeredAt": datetime.now().isoformat(),
        "fineBalance": 0,
        "fineHistory": []
    }
    data["students"].append(student)
    save(data)
    return jsonify(student), 201

@app.route("/api/students/<uid>", methods=["PUT"])
@admin_required
def update_student(uid):
    data = load()
    body = request.json
    for s in data["students"]:
        if s["id"] == uid:
            s["firstName"] = body.get("firstName", s.get("firstName",""))
            s["middleName"] = body.get("middleName", s.get("middleName",""))
            s["lastName"] = body.get("lastName", s.get("lastName",""))
            s["suffix"] = body.get("suffix", s.get("suffix",""))
            s["name"] = " ".join(filter(None,[s["firstName"],s["middleName"],s["lastName"],s["suffix"]]))
            s["studentId"] = body.get("studentId", s["studentId"])
            s["course"] = body.get("course", s.get("course",""))
            s["yearLevel"] = body.get("yearLevel", s.get("yearLevel",""))
            s["section"] = body.get("section", s.get("section",""))
            break
    save(data)
    return jsonify({"ok": True})

@app.route("/api/students/<uid>", methods=["DELETE"])
@admin_required
def delete_student(uid):
    data = load()
    data["students"] = [s for s in data["students"] if s["id"] != uid]
    save(data)
    return jsonify({"ok": True})

# ── courses ────────────────────────────────────────────────────
@app.route("/api/courses", methods=["GET"])
def get_courses():
    return jsonify(load()["courses"])

@app.route("/api/courses", methods=["POST"])
@admin_required
def add_course():
    data = load()
    name = request.json.get("name","").strip()
    if name and name not in data["courses"]:
        data["courses"].append(name)
        save(data)
    return jsonify(data["courses"])

@app.route("/api/courses", methods=["DELETE"])
@admin_required
def delete_course():
    data = load()
    name = request.json.get("name","")
    data["courses"] = [c for c in data["courses"] if c != name]
    save(data)
    return jsonify(data["courses"])

# ── sections ───────────────────────────────────────────────────
@app.route("/api/sections", methods=["GET"])
def get_sections():
    return jsonify(load()["sections"])

@app.route("/api/sections", methods=["POST"])
@admin_required
def add_section():
    data = load()
    name = request.json.get("name","").strip()
    if name and name not in data["sections"]:
        data["sections"].append(name)
        save(data)
    return jsonify(data["sections"])

@app.route("/api/sections", methods=["DELETE"])
@admin_required
def delete_section():
    data = load()
    name = request.json.get("name","")
    data["sections"] = [s for s in data["sections"] if s != name]
    save(data)
    return jsonify(data["sections"])

# ── year levels ────────────────────────────────────────────────
@app.route("/api/yearlevels", methods=["GET"])
def get_yearlevels():
    return jsonify(load()["yearLevels"])

@app.route("/api/yearlevels", methods=["POST"])
@admin_required
def add_yearlevel():
    data = load()
    name = request.json.get("name","").strip()
    if name and name not in data["yearLevels"]:
        data["yearLevels"].append(name)
        save(data)
    return jsonify(data["yearLevels"])

@app.route("/api/yearlevels", methods=["DELETE"])
@admin_required
def delete_yearlevel():
    data = load()
    name = request.json.get("name","")
    data["yearLevels"] = [y for y in data["yearLevels"] if y != name]
    save(data)
    return jsonify(data["yearLevels"])

# ── logs ───────────────────────────────────────────────────────
@app.route("/api/logs", methods=["GET"])
def get_logs():
    date = request.args.get("date")
    logs = load()["logs"]
    if date:
        logs = [l for l in logs if l["date"] == date]
    return jsonify(logs)

@app.route("/api/logs", methods=["POST"])
def add_log():
    data = load()
    body = request.json
    entry = {
        "studentId": body["studentId"],
        "name": body["name"],
        "course": body.get("course",""),
        "yearLevel": body.get("yearLevel",""),
        "section": body.get("section",""),
        "time": body["time"],
        "date": body["date"],
        "status": "present"
    }
    data["logs"].insert(0, entry)
    save(data)
    return jsonify(entry), 201

@app.route("/api/logs", methods=["DELETE"])
@admin_required
def clear_logs():
    data = load()
    data["logs"] = []
    save(data)
    return jsonify({"ok": True})

# ── activities ─────────────────────────────────────────────────
@app.route("/api/activities", methods=["GET"])
@admin_required
def get_activities():
    return jsonify(load()["activities"])

@app.route("/api/activities", methods=["POST"])
@admin_required
def create_activity():
    data = load()
    body = request.json
    activity = {
        "id": str(uuid.uuid4()),
        "name": body.get("name","").strip(),
        "description": body.get("description","").strip(),
        "date": body.get("date", datetime.now().strftime("%Y-%m-%d")),
        "location": body.get("location","").strip(),
        "createdAt": datetime.now().isoformat(),
        "attendance": [],
        "active": False
    }
    data["activities"].insert(0, activity)
    save(data)
    return jsonify(activity), 201

@app.route("/api/activities/<aid>", methods=["PUT"])
@admin_required
def update_activity(aid):
    data = load()
    body = request.json
    for a in data["activities"]:
        if a["id"] == aid:
            a["name"] = body.get("name", a["name"])
            a["description"] = body.get("description", a.get("description",""))
            a["date"] = body.get("date", a["date"])
            a["location"] = body.get("location", a.get("location",""))
            break
    save(data)
    return jsonify({"ok": True})

@app.route("/api/activities/<aid>", methods=["DELETE"])
@admin_required
def delete_activity(aid):
    data = load()
    data["activities"] = [a for a in data["activities"] if a["id"] != aid]
    save(data)
    return jsonify({"ok": True})

@app.route("/api/activities/<aid>/attendance", methods=["GET"])
@admin_required
def get_activity_attendance(aid):
    data = load()
    activity = next((a for a in data["activities"] if a["id"] == aid), None)
    if not activity:
        return jsonify({"error": "Activity not found"}), 404
    return jsonify(activity.get("attendance", []))

@app.route("/api/activities/<aid>/attendance", methods=["POST"])
@admin_required
def add_activity_attendance(aid):
    data = load()
    activity = next((a for a in data["activities"] if a["id"] == aid), None)
    if not activity:
        return jsonify({"error": "Activity not found"}), 404
    _ensure_activity_attendance(activity)
    body = request.json
    # Support single or bulk
    entries = body if isinstance(body, list) else [body]
    added = 0
    already = 0
    for entry in entries:
        sid = entry.get("studentId","")
        existing = next((r for r in activity["attendance"] if r["studentId"] == sid), None)
        if existing:
            already += 1
        else:
            record = {
                "studentId": sid,
                "name": entry.get("name",""),
                "course": entry.get("course",""),
                "yearLevel": entry.get("yearLevel",""),
                "section": entry.get("section",""),
                "status": entry.get("status","present"),
                "time": entry.get("time", datetime.now().strftime("%I:%M:%S %p")),
                "markedAt": datetime.now().isoformat(),
                "fineApplied": False
            }
            activity["attendance"].append(record)
            added += 1
    save(data)
    return jsonify({"ok": True, "added": added, "already": already, "attendance": activity["attendance"]}), 201

@app.route("/api/activities/<aid>/attendance/<sid>", methods=["PUT"])
@admin_required
def update_activity_attendance(aid, sid):
    data = load()
    activity = next((a for a in data["activities"] if a["id"] == aid), None)
    if not activity:
        return jsonify({"error": "Activity not found"}), 404
    _ensure_activity_attendance(activity)
    body = request.json
    for rec in activity["attendance"]:
        if rec["studentId"] == sid:
            prev = rec.get("status", "present")
            rec["status"] = body.get("status", rec.get("status", "present"))
            # If an admin sets a record to absent, apply fine once.
            if rec["status"] == "absent" and not rec.get("fineApplied"):
                if _add_fine(data, sid, activity.get("id", ""), f"Absent in {activity.get('name','activity')}"):
                    rec["fineApplied"] = True
            break
    save(data)
    return jsonify({"ok": True})

@app.route("/api/activities/<aid>/attendance/<sid>", methods=["DELETE"])
@admin_required
def remove_activity_attendance(aid, sid):
    data = load()
    activity = next((a for a in data["activities"] if a["id"] == aid), None)
    if not activity:
        return jsonify({"error": "Activity not found"}), 404
    activity["attendance"] = [r for r in activity["attendance"] if r["studentId"] != sid]
    save(data)
    return jsonify({"ok": True})

# ── activities (active / student attendance) ───────────────────
@app.route("/api/activities/active", methods=["GET"])
def get_active_activity():
    data = load()
    active = next((a for a in data["activities"] if a.get("active")), None)
    if not active:
        return jsonify({})
    return jsonify({
        "id": active.get("id"),
        "name": active.get("name",""),
        "description": active.get("description",""),
        "date": active.get("date",""),
        "location": active.get("location","")
    })

@app.route("/api/activities/<aid>/toggle-active", methods=["POST"])
@admin_required
def toggle_activity_active(aid):
    data = load()
    target = next((a for a in data["activities"] if a.get("id") == aid), None)
    if not target:
        return jsonify({"error": "Activity not found"}), 404
    # If turning OFF the currently active activity, finalize absences & apply fines.
    turning_on = not bool(target.get("active"))
    for a in data["activities"]:
        a["active"] = False
    target["active"] = turning_on
    finalize = None
    if not turning_on:
        finalize = _finalize_activity_absences(data, target)
    save(data)
    return jsonify({"ok": True, "active": bool(target.get("active")), "finalize": finalize})

@app.route("/api/activities/active/attend", methods=["POST"])
def student_attend_active_activity():
    data = load()
    active = next((a for a in data["activities"] if a.get("active")), None)
    if not active:
        return jsonify({"error": "No active activity"}), 400
    _ensure_activity_attendance(active)
    body = request.json or {}
    sid = (body.get("studentId") or "").strip()
    if not sid:
        return jsonify({"error": "Missing studentId"}), 400
    if next((r for r in active["attendance"] if r.get("studentId") == sid and r.get("status") == "present"), None):
        return jsonify({"ok": True, "already": True})
    # If an absent record was pre-created (on close), flip it to present and remove fine flag?
    # We keep the fine as-is because the absence fine should only be applied on close.
    rec = next((r for r in active["attendance"] if r.get("studentId") == sid), None)
    now = datetime.now()
    if rec:
        rec["status"] = "present"
        rec["time"] = now.strftime("%I:%M:%S %p")
        rec["markedAt"] = now.isoformat()
    else:
        active["attendance"].append({
            "studentId": sid,
            "name": body.get("name",""),
            "course": body.get("course",""),
            "yearLevel": body.get("yearLevel",""),
            "section": body.get("section",""),
            "status": "present",
            "time": now.strftime("%I:%M:%S %p"),
            "markedAt": now.isoformat(),
            "fineApplied": False
        })
    save(data)
    return jsonify({"ok": True, "already": False})

# ── run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
