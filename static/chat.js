const socket = io();

const statusEl = document.getElementById("status");
const messages = document.getElementById("messages");
const input = document.getElementById("message");
const send = document.getElementById("send");
const start = document.getElementById("start");
const next = document.getElementById("next");
const leave = document.getElementById("leave");

let connected = false;

function addMessage(text, mine = false) {
  const item = document.createElement("div");
  item.className = "message" + (mine ? " mine" : "");
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

function setChatEnabled(enabled) {
  connected = enabled;
  input.disabled = !enabled;
  send.disabled = !enabled;
  next.disabled = !enabled;
  leave.disabled = !enabled;
  start.disabled = enabled;
}

socket.on("connect", () => {
  statusEl.textContent = "Connected to server. Find a student to start.";
});

socket.on("connect_error", () => {
  statusEl.textContent = "Could not connect to server. Refresh and try again.";
});

start.addEventListener("click", () => {
  messages.replaceChildren();
  setChatEnabled(false);
  start.disabled = true;
  statusEl.textContent = "Searching for another student...";
  socket.emit("find_match");
});

socket.on("searching", data => {
  statusEl.textContent = data.message;
});

socket.on("matched", data => {
  setChatEnabled(true);
  statusEl.textContent = data.message;
  input.focus();
});

function sendMessage() {
  const message = input.value.trim();
  if (!message || !connected) return;
  addMessage("You: " + message, true);
  socket.emit("send_message", { message });
  input.value = "";
  input.focus();
}

send.addEventListener("click", sendMessage);
input.addEventListener("keydown", event => {
  if (event.key === "Enter") sendMessage();
});

socket.on("receive_message", data => {
  addMessage("Student: " + data.message);
});

socket.on("partner_left", data => {
  setChatEnabled(false);
  start.disabled = false;
  statusEl.textContent = data.message;
  addMessage(data.message);
});

function leaveCurrentChat() {
  socket.emit("leave_chat");
  setChatEnabled(false);
  start.disabled = false;
}

next.addEventListener("click", () => {
  leaveCurrentChat();
  messages.replaceChildren();
  statusEl.textContent = "Click Find random student to search again.";
});

leave.addEventListener("click", () => {
  leaveCurrentChat();
  statusEl.textContent = "You left the chat.";
});
