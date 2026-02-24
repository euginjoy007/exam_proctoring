from flask import Blueprint, render_template, request, redirect, session
import sqlite3

auth = Blueprint("auth", __name__)

# ---------------- STUDENT LOGIN ----------------
@auth.route("/", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect("proctoring.db")
        cur = conn.cursor()

        cur.execute("""
        SELECT role FROM users
        WHERE username=? AND password=? AND role='student'
        """, (u, p))

        user = cur.fetchone()
        conn.close()

        if user:
            session["user"] = u
            session["role"] = "student"
            return redirect("/student-dashboard")

    return render_template("student_login.html")


# ---------------- ADMIN LOGIN ----------------
@auth.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect("proctoring.db")
        cur = conn.cursor()

        cur.execute("""
        SELECT role FROM users
        WHERE username=? AND password=? AND role='admin'
        """, (u, p))

        admin = cur.fetchone()
        conn.close()

        if admin:
            session["user"] = u
            session["role"] = "admin"
            return redirect("/admin-dashboard")

    return render_template("admin_login.html")


# ---------------- STUDENT REGISTER ----------------
@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect("proctoring.db")
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO users(username,password,role)
        VALUES (?,?, 'student')
        """, (u, p))

        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("register.html")


# ---------------- LOGOUT ----------------
@auth.route("/logout")
def logout():
    session.clear()
    return redirect("/")
