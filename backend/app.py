from flask import Flask, render_template, session, redirect
from database import init_db
from auth import auth
from flask import request
from exam_manager import get_exam_questions, calculate_score
import sqlite3
from datetime import datetime
import csv
import base64
import os
import uuid


app = Flask(__name__)
app.secret_key = "exam_secret"

init_db()
app.register_blueprint(auth)


# ✅ Student Dashboard
@app.route("/student-dashboard")
def student_dashboard():
    if "user" not in session or session["role"] != "student":
        return redirect("/")
    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT exam_attempts.exam_code, exams.title, exam_attempts.score, exam_attempts.timestamp
        FROM exam_attempts
        LEFT JOIN exams ON exam_attempts.exam_code = exams.exam_code
        WHERE exam_attempts.user = ?
        ORDER BY exam_attempts.timestamp DESC
    """, (session["user"],))
    attempts = cur.fetchall()
    attempted_exam_codes = {row[0] for row in attempts if row[0]}

    selected_exam = None
    if session.get("selected_exam"):
        cur.execute("SELECT exam_code, title, description FROM exams WHERE exam_code = ?", (session["selected_exam"],))
        selected_exam = cur.fetchone()

    conn.close()
    return render_template(
        "student_dashboard.html",
        user=session["user"],
        attempts=attempts,
        selected_exam=selected_exam,
        selected_exam_attempted=bool(selected_exam and selected_exam[0] in attempted_exam_codes),
        date_str=datetime.now().strftime("%A, %B %d, %Y"),
        message=session.pop("message", None),
    )


# ✅ Admin Dashboard
@app.route("/admin-dashboard")
def admin_dashboard():
    if "user" not in session or session["role"] != "admin":
        return redirect("/admin-login")
    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()

    cur.execute("SELECT exam_code, title, description FROM exams ORDER BY id DESC")
    exams = cur.fetchall()

    cur.execute("""
        SELECT users.username, COUNT(exam_attempts.id) AS attempts, MAX(exam_attempts.timestamp) AS last_attempt
        FROM users
        LEFT JOIN exam_attempts ON users.username = exam_attempts.user
        WHERE users.role = 'student'
        GROUP BY users.username
        ORDER BY users.username
    """)
    students = cur.fetchall()

    cur.execute("""
        SELECT user, type, COUNT(*) as count
        FROM violations
        GROUP BY user, type
    """)
    violation_rows = cur.fetchall()

    # Risk scoring aligned to weighted suspicious action categories.
    severity_map = {
        # Face absence: No face detected > 5 sec
        "no_face": 15,

        # Eye/head movement: Looking away repeatedly
        "gaze_left": 5,
        "gaze_right": 5,

        # Multiple persons: Multiple faces detected
        "multiple_faces": 25,

        # Camera tampering: Camera blocked/covered or denied
        "permissions_blocked": 20,
        "fullscreen_denied": 20,

        # Tab switching: Leaving exam window
        "tab_hidden": 15,

        # External apps: Opening new software / moving focus outside exam
        "window_blur": 20,
        "fullscreen_exit": 20,

        # Phone detection: Mobile phone visible
        "phone_detected": 30,

        # Notes detection: Book/paper seen (future/optional detectors)
        "notes_detected": 25,
        "book_detected": 25,
        "paper_detected": 25,

        # Audio anomaly: Background voice/noise
        "audio_noise": 10,
    }
    risk_scores = {}
    for user, vtype, count in violation_rows:
        risk_scores[user] = risk_scores.get(user, 0) + severity_map.get(vtype, 1) * count

    conn.close()

    return render_template(
        "admin_dashboard.html",
        exams=exams,
        students=students,
        risk_scores=risk_scores,
        message=session.pop("message", None),
    )


@app.route("/admin/students/<username>")
def admin_student_detail(username):
    if "user" not in session or session["role"] != "admin":
        return redirect("/admin-login")

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT exam_attempts.exam_code, exams.title, exam_attempts.score, exam_attempts.timestamp
        FROM exam_attempts
        LEFT JOIN exams ON exam_attempts.exam_code = exams.exam_code
        WHERE exam_attempts.user = ?
        ORDER BY exam_attempts.timestamp DESC
    """, (username,))
    attempts = cur.fetchall()

    cur.execute(
        """
        SELECT exam_code, COUNT(*)
        FROM violations
        WHERE user = ?
        GROUP BY exam_code
        """,
        (username,),
    )
    violation_counts = {row[0] or "N/A": row[1] for row in cur.fetchall()}

    cur.execute("""
        SELECT type, timestamp, screenshot_path, exam_code
        FROM violations
        WHERE user = ?
        ORDER BY timestamp DESC
    """, (username,))
    violations = cur.fetchall()

    conn.close()

    return render_template(
        "admin_student_detail.html",
        student=username,
        attempts=attempts,
        violations=violations,
        violation_counts=violation_counts,
    )


@app.route("/admin/exams", methods=["POST"])
def create_exam():
    if "user" not in session or session["role"] != "admin":
        return redirect("/admin-login")

    exam_code = request.form.get("exam_code", "").strip().upper()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()

    if not exam_code or not title:
        session["message"] = "Exam code and title are required."
        return redirect("/admin-dashboard")

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO exams(exam_code, title, description) VALUES (?, ?, ?)",
            (exam_code, title, description),
        )
        conn.commit()
        session["message"] = f"Exam {exam_code} created."
    except sqlite3.IntegrityError:
        session["message"] = f"Exam code {exam_code} already exists."
    finally:
        conn.close()

    return redirect("/admin-dashboard")


@app.route("/admin/questions", methods=["POST"])
def add_question():
    if "user" not in session or session["role"] != "admin":
        return redirect("/admin-login")

    exam_code = request.form.get("exam_code", "").strip().upper()
    question = request.form.get("question", "").strip()
    option1 = request.form.get("option1", "").strip()
    option2 = request.form.get("option2", "").strip()
    option3 = request.form.get("option3", "").strip()
    option4 = request.form.get("option4", "").strip()
    answer = request.form.get("answer", "").strip()

    if not all([exam_code, question, option1, option2, option3, option4, answer]):
        session["message"] = "All question fields are required."
        return redirect("/admin-dashboard")

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM exams WHERE exam_code = ?", (exam_code,))
    exam_exists = cur.fetchone()
    if not exam_exists:
        conn.close()
        session["message"] = f"Exam code {exam_code} not found. Create the exam first."
        return redirect("/admin-dashboard")

    cur.execute(
        """
        INSERT INTO questions(question, option1, option2, option3, option4, answer, exam_code)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (question, option1, option2, option3, option4, answer, exam_code),
    )
    conn.commit()
    conn.close()

    session["message"] = f"Question added to exam {exam_code}."
    return redirect("/admin-dashboard")


@app.route("/admin/upload-form", methods=["POST"])
def upload_form():
    if "user" not in session or session["role"] != "admin":
        return redirect("/admin-login")

    exam_code = request.form.get("exam_code", "").strip().upper()
    form_file = request.files.get("form_file")

    if not exam_code or not form_file:
        session["message"] = "Exam code and CSV file are required."
        return redirect("/admin-dashboard")

    if not form_file.filename.lower().endswith(".csv"):
        session["message"] = "Only CSV files are supported for form uploads."
        return redirect("/admin-dashboard")

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM exams WHERE exam_code = ?", (exam_code,))
    exam_exists = cur.fetchone()
    if not exam_exists:
        conn.close()
        session["message"] = f"Exam code {exam_code} not found. Create the exam first."
        return redirect("/admin-dashboard")

    decoded = form_file.stream.read().decode("utf-8").splitlines()
    reader = csv.DictReader(decoded)
    required_fields = {"question", "option1", "option2", "option3", "option4", "answer"}
    if not required_fields.issubset(reader.fieldnames or set()):
        conn.close()
        session["message"] = "CSV must include question, option1, option2, option3, option4, answer headers."
        return redirect("/admin-dashboard")

    added = 0
    for row in reader:
        if not row.get("question"):
            continue
        cur.execute(
            """
            INSERT INTO questions(question, option1, option2, option3, option4, answer, exam_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("question", "").strip(),
                row.get("option1", "").strip(),
                row.get("option2", "").strip(),
                row.get("option3", "").strip(),
                row.get("option4", "").strip(),
                row.get("answer", "").strip(),
                exam_code,
            ),
        )
        added += 1

    conn.commit()
    conn.close()

    session["message"] = f"Uploaded {added} questions to exam {exam_code}."
    return redirect("/admin-dashboard")

# ---------------- EXAM PAGE ----------------
@app.route("/exam", methods=["GET", "POST"])
def exam():
    if "user" not in session or session["role"] != "student":
        return redirect("/")

    exam_code = session.get("selected_exam")
    if not exam_code:
        session["message"] = "Please search and select an exam before starting."
        return redirect("/student-dashboard")

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM exam_attempts WHERE user = ? AND exam_code = ? LIMIT 1",
        (session["user"], exam_code),
    )
    already_attempted = cur.fetchone() is not None
    conn.close()

    if already_attempted:
        session["message"] = f"You have already attempted exam {exam_code}. Only one attempt is allowed."
        return redirect("/student-dashboard")

    # Load questions
    if request.method == "GET":
        questions = get_exam_questions(exam_code)
        if not questions:
            session["message"] = f"No questions found for exam code {exam_code}."
            return redirect("/student-dashboard")
        return render_template("exam.html", questions=questions)

    # Submit exam
    if request.method == "POST":
        score = calculate_score(request.form)

        # Save attempt
        conn = sqlite3.connect("proctoring.db")
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO exam_attempts(user, score, exam_code) VALUES (?, ?, ?)",
            (session["user"], score, exam_code)
        )
        conn.commit()
        conn.close()

        return render_template("result.html", score=score)


@app.route("/search-exam", methods=["POST"])
def search_exam():
    if "user" not in session or session["role"] != "student":
        return redirect("/")

    exam_code = request.form.get("exam_code", "").strip().upper()
    if not exam_code:
        session["message"] = "Please enter a valid exam code."
        return redirect("/student-dashboard")

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    cur.execute("SELECT exam_code, title, description FROM exams WHERE exam_code = ?", (exam_code,))
    exam = cur.fetchone()
    conn.close()

    if not exam:
        session["message"] = f"No exam found for code {exam_code}."
        session.pop("selected_exam", None)
        return redirect("/student-dashboard")

    session["selected_exam"] = exam[0]
    session["message"] = f"Exam {exam[0]} loaded. Review details below and start when ready."
    return redirect("/student-dashboard")


@app.route("/permissions", methods=["GET"])
def permissions_check():
    if "user" not in session or session["role"] != "student":
        return redirect("/")

    exam_code = session.get("selected_exam")
    if not exam_code:
        session["message"] = "Please search and select an exam before starting."
        return redirect("/student-dashboard")

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    cur.execute("SELECT exam_code, title, description FROM exams WHERE exam_code = ?", (exam_code,))
    exam = cur.fetchone()
    conn.close()

    return render_template(
        "permissions_check.html",
        user=session["user"],
        exam=exam,
        message=session.pop("message", None),
    )


@app.route("/start-exam", methods=["POST"])
def start_exam():
    if "user" not in session or session["role"] != "student":
        return redirect("/")

    signature = request.form.get("signature", "").strip()
    if not signature:
        session["message"] = "Please sign the honor code before continuing."
        return redirect("/permissions")

    focus_verified = request.form.get("focus_check_verified") == "true"
    audio_verified = request.form.get("audio_check_verified") == "true"
    if not (focus_verified and audio_verified):
        session["message"] = "Complete system readiness checks (focus + audio device scan) before starting the exam."
        return redirect("/permissions")

    exam_code = session.get("selected_exam")
    if exam_code:
        conn = sqlite3.connect("proctoring.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM exam_attempts WHERE user = ? AND exam_code = ? LIMIT 1",
            (session["user"], exam_code),
        )
        already_attempted = cur.fetchone() is not None
        conn.close()
        if already_attempted:
            session["message"] = f"You have already attempted exam {exam_code}. Only one attempt is allowed."
            return redirect("/student-dashboard")

    return redirect("/exam")


@app.route("/proctor/analyze", methods=["POST"])
def proctor_analyze():
    if "user" not in session or session["role"] != "student":
        return {"violations": [], "score": 0}, 403

    payload = request.get_json()
    if not payload or "image" not in payload:
        return {"violations": [], "score": 0}, 400

    import numpy as np
    import cv2
    from proctor_ai.violation_engine import analyze_frame

    image_data = payload["image"].split(",")[-1]
    decoded = base64.b64decode(image_data)
    np_arr = np.frombuffer(decoded, np.uint8)
    image_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image_bgr is None:
        return {"violations": [], "score": 0}, 400

    enable_phone = bool(payload.get("enable_phone", True))
    violations, score = analyze_frame(image_bgr, enable_phone=enable_phone)
    return {"violations": violations, "score": score}




@app.route("/proctor/heartbeat", methods=["POST"])
def proctor_heartbeat():
    if "user" not in session or session["role"] != "student":
        return {"status": "unauthorized"}, 403

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO proctor_health(user, exam_code, last_seen)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (session["user"], session.get("selected_exam")),
    )
    conn.commit()
    conn.close()

    return {"status": "ok"}

@app.route("/proctor/violation", methods=["POST"])
def proctor_violation():
    if "user" not in session or session["role"] != "student":
        return {"status": "unauthorized"}, 403

    payload = request.get_json() or {}
    violation_type = payload.get("type", "unknown")
    screenshot_path = None

    severe_types = {
        "phone_detected",
        "multiple_faces",
        "no_face",
        "permissions_blocked",
        "fullscreen_exit",
        "fullscreen_denied",
        "tab_hidden",
        "window_blur",
        "notes_detected",
        "book_detected",
        "paper_detected",
    }

    screenshot_data = payload.get("screenshot")
    if screenshot_data and violation_type in severe_types:
        # Keep only one screenshot for phone_detected per user+exam.
        if violation_type == "phone_detected":
            conn = sqlite3.connect("proctoring.db")
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1
                FROM violations
                WHERE user = ? AND exam_code = ? AND type = 'phone_detected' AND screenshot_path IS NOT NULL
                LIMIT 1
                """,
                (session["user"], session.get("selected_exam")),
            )
            phone_screenshot_exists = cur.fetchone() is not None
            conn.close()
            if phone_screenshot_exists:
                screenshot_data = None

        if screenshot_data:
            try:
                image_b64 = screenshot_data.split(",")[-1]
                image_bytes = base64.b64decode(image_b64)
                snaps_dir = os.path.join(app.static_folder, "violation_snaps")
                os.makedirs(snaps_dir, exist_ok=True)
                filename = f"{session['user']}_{uuid.uuid4().hex}.jpg"
                file_path = os.path.join(snaps_dir, filename)
                with open(file_path, "wb") as f:
                    f.write(image_bytes)
                screenshot_path = f"/static/violation_snaps/{filename}"
            except Exception:
                screenshot_path = None

    conn = sqlite3.connect("proctoring.db")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO violations(user, exam_code, type, screenshot_path)
        VALUES (?, ?, ?, ?)
        """,
        (session["user"], session.get("selected_exam"), violation_type, screenshot_path),
    )
    conn.commit()
    conn.close()

    return {"status": "ok"}

if __name__ == "__main__":
    # Keep server in foreground on Windows terminals and avoid silent parent exit from the reloader.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
