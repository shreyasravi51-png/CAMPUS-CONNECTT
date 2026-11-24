import os
import random
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "campusconnect-msruas-secret-key-2026")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///campusconnect.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

COLLEGE_DOMAIN = "msruas.ac.in"
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

waiting = []
active = {}
sid_to_user = {}


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, nullable=False)
    reported_email = db.Column(db.String(160), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


def send_otp(email, otp):
    host = os.getenv("SMTP_HOST")
    if not host:
        return False
    msg = EmailMessage()
    msg["Subject"] = "CampusConnect Verification Code"
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"] = email
    msg.set_content(f"Your CampusConnect verification code is {otp}. It expires in 10 minutes.")
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)
    return True


def _end_active_chat(sid):
    if sid in waiting:
        waiting.remove(sid)
    info = active.pop(sid, None)
    if info:
        peer = info["peer"]
        active.pop(peer, None)
        socketio.emit("partner_left", {}, to=peer)


@app.route("/")
def home():
    student = Student.query.get(session.get("student_id")) if session.get("student_id") else None
    return render_template("index.html", student=student)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or len(password) < 8:
            flash("Enter your name and a password with at least 8 characters.")
            return redirect(url_for("register"))
        if not email.endswith("@" + COLLEGE_DOMAIN):
            flash("Use your official @msruas.ac.in college email address.")
            return redirect(url_for("register"))
        if Student.query.filter_by(email=email).first():
            flash("This email is already registered. Please log in.")
            return redirect(url_for("login"))

        otp = f"{random.randint(0, 999999):06d}"
        session["pending"] = {
            "name": name,
            "email": email,
            "password": generate_password_hash(password),
            "otp": otp,
            "expires": (datetime.utcnow() + timedelta(minutes=10)).timestamp(),
        }
        sent = False
        try:
            sent = send_otp(email, otp)
        except Exception:
            sent = False

        if not sent and not DEMO_MODE:
            session.pop("pending", None)
            flash("Email delivery is not configured. Please try again later.")
            return redirect(url_for("register"))
        if not sent:
            session["demo_otp"] = otp
        return redirect(url_for("verify"))

    return render_template("register.html")


@app.route("/verify", methods=["GET", "POST"])
def verify():
    pending = session.get("pending")
    if not pending:
        return redirect(url_for("register"))
    if request.method == "POST":
        if datetime.utcnow().timestamp() > pending["expires"]:
            session.pop("pending", None)
            flash("Code expired. Please register again.")
            return redirect(url_for("register"))
        if secrets.compare_digest(request.form.get("otp", "").strip(), pending["otp"]):
            student = Student(
                name=pending["name"],
                email=pending["email"],
                password=pending["password"],
                verified=True,
            )
            db.session.add(student)
            db.session.commit()
            session.pop("pending", None)
            session.pop("demo_otp", None)
            session["student_id"] = student.id
            return redirect(url_for("home"))
        flash("Incorrect verification code.")
    return render_template("verify.html", demo_otp=session.get("demo_otp"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        student = Student.query.filter_by(email=email).first()
        if student and student.verified and check_password_hash(student.password, request.form.get("password", "")):
            session["student_id"] = student.id
            return redirect(url_for("home"))
        flash("Invalid login or account not verified.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/report", methods=["POST"])
def report():
    if not session.get("student_id"):
        return jsonify(ok=False), 401
    data = request.get_json(silent=True) or {}
    target = (data.get("email") or "unknown")[:160]
    reason = (data.get("reason") or "Inappropriate behaviour")[:500]
    db.session.add(Report(reporter_id=session["student_id"], reported_email=target, reason=reason))
    db.session.commit()
    return jsonify(ok=True)


@app.route("/chat")
def chat():
    student = Student.query.get(session.get("student_id")) if session.get("student_id") else None
    if not student:
        flash("Please log in with your verified college account.")
        return redirect(url_for("login"))
    return render_template("chat.html", student=student)


@socketio.on("join_queue")
def on_join_queue():
    student = Student.query.get(session.get("student_id"))
    if not student or not student.verified:
        emit("notice", {"message": "Please sign in with a verified MSRUAS account."})
        return

    sid_to_user[request.sid] = student.email
    if request.sid in waiting or request.sid in active:
        return

    waiting[:] = [sid for sid in waiting if sid in sid_to_user]

    if waiting:
        peer = waiting.pop(0)
        if peer == request.sid:
            waiting.append(peer)
            return

        room = secrets.token_urlsafe(10)
        active[request.sid] = {"peer": peer, "room": room}
        active[peer] = {"peer": request.sid, "room": room}

        join_room(room)
        socketio.server.enter_room(peer, room, namespace="/")

        emit("matched", {"room": room, "initiator": True, "partnerEmail": sid_to_user.get(peer, "unknown")}, to=request.sid)
        socketio.emit("matched", {"room": room, "initiator": False, "partnerEmail": student.email}, to=peer)
    else:
        waiting.append(request.sid)
        emit("notice", {"message": "Looking for another verified student..."})


@socketio.on("signal")
def on_signal(data):
    info = active.get(request.sid)
    if info:
        emit("signal", data, to=info["peer"])


@socketio.on("chat_message")
def on_chat_message(data):
    info = active.get(request.sid)
    student = Student.query.get(session.get("student_id"))
    if info and student:
        msg = (data.get("message") or "").strip()[:1000]
        if msg:
            emit("chat_message", {"name": student.name, "message": msg}, to=info["peer"])


@socketio.on("next_chat")
def on_next():
    _end_active_chat(request.sid)
    on_join_queue()


@socketio.on("leave_chat")
def on_leave_chat():
    _end_active_chat(request.sid)


@socketio.on("disconnect")
def on_disconnect():
    _end_active_chat(request.sid)
    sid_to_user.pop(request.sid, None)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
