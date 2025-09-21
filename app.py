import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_from_directory, flash, g
)
from werkzeug.utils import secure_filename
from datetime import datetime

# ---------------- Config ----------------
APP_SECRET = "ms_sameer_secret_2025"   # production में env var से बदल दें
ADMIN_USER = "SAMEER MESRA"
ADMIN_PASS = "MS3561"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "ms_sameer.db")

ALLOWED_EXT = {"pdf", "docx", "pptx", "ppt", "jpg", "jpeg", "png", "txt", "zip"}

SUBJECTS = ["History", "Political Science", "Hindi", "English", "IT", "PCA"]

# ensure uploads and subject folders exist
os.makedirs(UPLOAD_ROOT, exist_ok=True)
for s in SUBJECTS:
    os.makedirs(os.path.join(UPLOAD_ROOT, s.lower().replace(" ", "_")), exist_ok=True)

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config["UPLOAD_ROOT"] = UPLOAD_ROOT

# --------------- Database helpers ---------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            created_at TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            filename TEXT,
            downloaded_at TEXT
        );
    """)
    db.commit()
    db.close()

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# initialize DB
init_db()

# --------------- utility functions ---------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def create_user(username, password):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                    (username, password, datetime.utcnow().isoformat()))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(username, password):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    return cur.fetchone() is not None

def list_subject_files():
    result = {}
    for s in SUBJECTS:
        folder = os.path.join(UPLOAD_ROOT, s.lower().replace(" ", "_"))
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        result[s] = sorted(files)
    return result

def record_download(subject, filename):
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO downloads (subject, filename, downloaded_at) VALUES (?, ?, ?)",
                (subject, filename, datetime.utcnow().isoformat()))
    db.commit()

# ---------------- Routes ----------------

@app.route("/")
def index():
    return render_template("index.html", subjects=SUBJECTS)

# signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Please enter username and password", "danger")
            return redirect(url_for("signup"))
        created = create_user(username, password)
        if not created:
            flash("Username already taken", "danger")
            return redirect(url_for("signup"))
        flash("Account created. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

# login (student or admin)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        # admin check
        if username == ADMIN_USER and password == ADMIN_PASS:
            session["user"] = username
            session["role"] = "admin"
            return redirect(url_for("admin"))
        # student check
        if verify_user(username, password):
            session["user"] = username
            session["role"] = "student"
            return redirect(url_for("student_dashboard"))
        flash("Invalid credentials", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

# logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("index"))

# admin panel (upload)
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    if request.method == "POST":
        subject = request.form.get("subject")
        file = request.files.get("file")
        if not subject or subject not in SUBJECTS:
            flash("Please select a valid subject", "danger")
            return redirect(url_for("admin"))
        if not file or file.filename == "":
            flash("Please select a file", "danger")
            return redirect(url_for("admin"))
        if not allowed_file(file.filename):
            flash("File type not allowed", "danger")
            return redirect(url_for("admin"))
        filename = secure_filename(file.filename)
        dest_folder = os.path.join(UPLOAD_ROOT, subject.lower().replace(" ", "_"))
        os.makedirs(dest_folder, exist_ok=True)
        save_path = os.path.join(dest_folder, filename)
        file.save(save_path)
        flash(f"Uploaded {filename} to {subject}", "success")
        return redirect(url_for("admin"))
    # GET
    files_by_subject = list_subject_files()
    return render_template("admin.html", subjects=SUBJECTS, files_by_subject=files_by_subject)

# student dashboard (list subjects + files)
@app.route("/student")
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("login"))
    files_by_subject = list_subject_files()
    return render_template("student_dashboard.html", user=session.get("user"), files_by_subject=files_by_subject)

# show single subject files (optional)
@app.route("/subject/<subject>")
def subject_files(subject):
    if subject not in SUBJECTS:
        flash("Invalid subject", "danger")
        return redirect(url_for("student_dashboard"))
    folder = os.path.join(UPLOAD_ROOT, subject.lower().replace(" ", "_"))
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    return render_template("subject_files.html", subject=subject, files=sorted(files))

# download file (student)
@app.route("/download/<subject>/<filename>")
def download(subject, filename):
    if session.get("role") not in ("student", "admin"):
        return redirect(url_for("login"))
    folder = os.path.join(UPLOAD_ROOT, subject.lower().replace(" ", "_"))
    if not os.path.exists(os.path.join(folder, filename)):
        flash("File not found", "danger")
        return redirect(url_for("student_dashboard"))
    record_download(subject, filename)
    return send_from_directory(folder, filename, as_attachment=True)

# admin can delete file (bonus)
@app.route("/admin/delete/<subject>/<filename>", methods=["POST"])
def admin_delete(subject, filename):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    folder = os.path.join(UPLOAD_ROOT, subject.lower().replace(" ", "_"))
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        os.remove(path)
        flash("File deleted", "info")
    else:
        flash("File not found", "danger")
    return redirect(url_for("admin"))

# ---------------- Run ----------------
if __name__ == "__main__":
    # debug=True for local only
    app.run(host="0.0.0.0", port=5000, debug=True)