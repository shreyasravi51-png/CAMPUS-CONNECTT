CAMPUSCONNECT - TEXT CHAT ONLY DEMO

Files:
- app.py
- requirements.txt
- templates/chat.html
- static/chat.js

IMPORTANT:
This is a standalone chat-only demo. Replacing your existing app.py and chat.html
will remove/replace existing registration, login, verification, and other routes.
It does not verify that users are MSRUAS students.

For a Render demo:
Build command: pip install -r requirements.txt
Start command: python app.py

Use one running web-service instance because the matching queue is stored in memory.
The queue is temporary and resets when the service restarts.
