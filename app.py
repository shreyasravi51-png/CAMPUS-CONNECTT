import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "demo-secret-change-me")
socketio = SocketIO(app, cors_allowed_origins="*")

waiting = []
partners = {}

@app.route("/")
def home():
    return render_template("chat.html")

@socketio.on("find_match")
def find_match(data=None):
    sid = request.sid
    if sid in partners or sid in waiting:
        return

    while waiting:
        other = waiting.pop(0)
        if other != sid and other not in partners:
            room = f"{sid}_{other}"
            partners[sid] = (other, room)
            partners[other] = (sid, room)
            join_room(room)
            emit("matched", {"message": "Student connected!"}, to=sid)
            emit("matched", {"message": "Student connected!"}, to=other)
            return

    waiting.append(sid)
    emit("searching", {"message": "Searching for a student..."})

@socketio.on("send_message")
def send_message(data):
    sid = request.sid
    if sid not in partners:
        return
    message = str((data or {}).get("message", "")).strip()[:2000]
    if not message:
        return
    other, room = partners[sid]
    emit("receive_message", {"message": message}, to=room, include_self=False)

@socketio.on("leave_chat")
def leave_chat():
    remove_user(request.sid)

@socketio.on("disconnect")
def disconnect():
    remove_user(request.sid)

def remove_user(sid):
    if sid in waiting:
        waiting.remove(sid)
    if sid in partners:
        other, room = partners.pop(sid)
        partners.pop(other, None)
        emit("partner_left", {"message": "Student left the chat."}, to=other)
        leave_room(room, sid=sid)
        leave_room(room, sid=other)

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        allow_unsafe_werkzeug=True
    )
