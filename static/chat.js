const socket = io();
const statusBox = document.getElementById('status');
const startBtn = document.getElementById('start');
const nextBtn = document.getElementById('next');
const leaveBtn = document.getElementById('leave');
const localVideo = document.getElementById('localVideo');
const remoteVideo = document.getElementById('remoteVideo');
const messages = document.getElementById('messages');

let localStream = null;
let pc = null;
let room = null;
let partnerEmail = 'unknown';

const config = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
};

function status(t) {
  statusBox.textContent = t;
}

function addMessage(name, msg) {
  const p = document.createElement('p');
  const b = document.createElement('strong');
  b.textContent = name + ': ';
  p.append(b, document.createTextNode(msg));
  messages.append(p);
  messages.scrollTop = messages.scrollHeight;
}

async function getMedia() {
  if (!localStream && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    localVideo.srcObject = localStream;
  }
}

function closePeer() {
  if (pc) {
    pc.close();
    pc = null;
  }
  remoteVideo.srcObject = null;
  room = null;
  partnerEmail = 'unknown';
}

function makePeer() {
  pc = new RTCPeerConnection(config);
  if (localStream) {
    localStream.getTracks().forEach((t) => pc.addTrack(t, localStream));
  }
  pc.ontrack = (e) => {
    remoteVideo.srcObject = e.streams[0];
  };
  pc.onicecandidate = (e) => {
    if (e.candidate) {
      socket.emit('signal', { candidate: e.candidate });
    }
  };
}

startBtn.onclick = async () => {
  try {
    await getMedia();
  } catch (e) {
    status('Camera/microphone permission is required for video. You can still use text chat after allowing access.');
  }
  startBtn.disabled = true;
  nextBtn.disabled = false;
  status('Searching for another verified MSRUAS student...');
  socket.emit('join_queue');
};

nextBtn.onclick = () => {
  closePeer();
  messages.innerHTML = '';
  status('Finding another student...');
  socket.emit('next_chat');
};

if (leaveBtn) {
  leaveBtn.onclick = () => {
    closePeer();
    socket.emit('leave_chat');
    status('You left the conversation.');
    startBtn.disabled = false;
    nextBtn.disabled = true;
  };
}

socket.on('notice', (d) => status(d.message));

socket.on('matched', async (d) => {
  room = d.room;
  partnerEmail = d.partnerEmail || 'unknown';
  status('Connected! Say hello.');
  makePeer();
  if (d.initiator) {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socket.emit('signal', { description: pc.localDescription });
  }
});

socket.on('signal', async (d) => {
  if (!pc) makePeer();
  if (d.description) {
    await pc.setRemoteDescription(d.description);
    if (d.description.type === 'offer') {
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      socket.emit('signal', { description: pc.localDescription });
    }
  } else if (d.candidate) {
    try {
      await pc.addIceCandidate(d.candidate);
    } catch (e) {
      console.warn(e);
    }
  }
});

socket.on('partner_left', () => {
  closePeer();
  status('The other student left. Click Next student to find someone else.');
});

document.getElementById('messageForm').onsubmit = (e) => {
  e.preventDefault();
  const input = document.getElementById('message');
  const msg = input.value.trim();
  if (msg) {
    addMessage('You', msg);
    socket.emit('chat_message', { message: msg });
    input.value = '';
  }
};

socket.on('chat_message', (d) => addMessage(d.name, d.message));

document.getElementById('report').onclick = async () => {
  if (confirm('Report this student for inappropriate behaviour?')) {
    await fetch('/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: partnerEmail, reason: 'Reported from chat interface' })
    });
    status('Report submitted. Thank you for helping keep the community safe.');
  }
};

window.addEventListener('beforeunload', () => {
  if (localStream) {
    localStream.getTracks().forEach((t) => t.stop());
  }
});
