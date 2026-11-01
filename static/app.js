/**
 * Gilgamesh AI Companion - Frontend Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const chatMessages = document.getElementById('chat-messages');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const micBtn = document.getElementById('mic-btn');
  const typingIndicator = document.getElementById('typing-indicator');
  const globalAudio = document.getElementById('global-audio-player');
  


  // Live Call Modal
  const callToggleBtn = document.getElementById('call-toggle-btn');
  const newChatBtn = document.getElementById('new-chat-btn');
  const callModal = document.getElementById('call-modal');
  const endCallBtn = document.getElementById('end-call-btn');
  const callMicToggle = document.getElementById('call-mic-toggle');
  const callTranscriptPreview = document.getElementById('call-transcript-preview');
  const callAvatarStage = document.querySelector('.call-avatar-stage');

  // Noise Filter Quick Toggle & Setting Elements
  const filterToggleBtn = document.getElementById('filter-toggle-btn');
  const filterBtnLabel = document.getElementById('filter-btn-label');
  const noiseFilterCheckbox = document.getElementById('noise-filter-checkbox');
  let isFilterActive = true;

  // Profile & Sanctum PIN Elements
  const profileToggleBtn = document.getElementById('profile-toggle-btn');
  const profileIcon = document.getElementById('profile-icon');
  const profileLabel = document.getElementById('profile-label');
  const pinModal = document.getElementById('pin-modal');
  const closePinModal = document.getElementById('close-pin-modal');
  const vaultPinInput = document.getElementById('vault-pin-input');
  const unlockVaultBtn = document.getElementById('unlock-vault-btn');
  const pinErrorMsg = document.getElementById('pin-error-msg');

  let currentProfile = 'guest'; // 'guest' or 'master'
  let masterPin = '';

  function updateProfileUI(mode) {
    currentProfile = mode;
    if (mode === 'master') {
      if (profileToggleBtn) {
        profileToggleBtn.className = 'icon-btn profile-btn master';
        profileToggleBtn.title = "Master Profile Active (Click to Lock Vault & Switch to Guest)";
      }
      if (profileIcon) profileIcon.textContent = '👑';
      if (profileLabel) profileLabel.textContent = 'Master (Owner)';
    } else {
      if (profileToggleBtn) {
        profileToggleBtn.className = 'icon-btn profile-btn guest';
        profileToggleBtn.title = "Guest Mode Active (Click to Enter Royal PIN for Master Profile)";
      }
      if (profileIcon) profileIcon.textContent = '⚔️';
      if (profileLabel) profileLabel.textContent = 'Guest Mode';
    }
  }

  function updateFilterUI(active) {
    isFilterActive = !!active;
    if (filterBtnLabel) {
      filterBtnLabel.textContent = isFilterActive ? 'Filter: ON' : 'Filter: OFF';
    }
    if (filterToggleBtn) {
      filterToggleBtn.classList.toggle('active', isFilterActive);
      filterToggleBtn.classList.toggle('inactive', !isFilterActive);
    }
    if (noiseFilterCheckbox) {
      noiseFilterCheckbox.checked = isFilterActive;
    }
  }

  async function toggleFilter(newVal) {
    updateFilterUI(newVal);
    try {
      await fetch('/api/set-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ noise_filter: isFilterActive })
      });
    } catch (e) {
      console.error("Failed to toggle filter", e);
    }
  }

  if (filterToggleBtn) {
    filterToggleBtn.addEventListener('click', () => {
      toggleFilter(!isFilterActive);
    });
  }

  if (noiseFilterCheckbox) {
    noiseFilterCheckbox.addEventListener('change', () => {
      toggleFilter(noiseFilterCheckbox.checked);
    });
  }

  let history = [];
  let isRecording = false;
  let mediaRecorder = null;
  let audioChunks = [];
  let isCallActive = false;
  let currentEmotion = 'haughty';

  // Auto-resize chat textarea
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  setTimeout(scrollToBottom, 200);

  // Check initial API status
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      if (typeof data.noise_filter !== 'undefined') {
        updateFilterUI(data.noise_filter);
      }
    })
    .catch(err => console.error('Status check failed', err));

  function scrollToBottom() {
    const container = document.querySelector('.chat-container');
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }

  // Message Formatter: converts *actions* to italic golden text and [emotion] or (emotion) to stylish inline badges
  function formatGilgameshText(raw) {
    const actionRegex = /\*(.*?)\*/g;
    let formatted = raw.replace(actionRegex, '<span class="action">*$1*</span>');

    // Native Fish Audio [...] and ElevenLabs (...) inline stage direction badges
    const emoRegex = /[\[\(]([a-zA-Z\s,]+)[\]\)]/g;
    formatted = formatted.replace(emoRegex, (match, emo) => {
      const lower = emo.trim().toLowerCase();
      let badgeClass = 'haughty';
      if (lower.includes('ang') || lower.includes('furi') || lower.includes('rage') || lower.includes('venom') || lower.includes('fury')) badgeClass = 'angry';
      else if (lower.includes('amus') || lower.includes('laugh') || lower.includes('chuckle')) badgeClass = 'amused';
      else if (lower.includes('calm') || lower.includes('neut')) badgeClass = 'calm';
      else if (lower.includes('solemn') || lower.includes('sigh') || lower.includes('weary')) badgeClass = 'solemn';
      else if (lower.includes('whisp')) badgeClass = 'whispering';
      else if (lower.includes('haught') || lower.includes('proud')) badgeClass = 'haughty';
      else return match; // Leave unmatched text alone

      return `<span class="inline-emotion emo-${badgeClass}">${escapeHTML(lower)}</span>`;
    });

    return `<div class="msg-content">${formatted}</div>`;
  }

  function appendUserMessage(text, scroll = true) {
    const row = document.createElement('div');
    row.className = 'message-row user-row';
    row.innerHTML = `
      <div class="user-avatar-placeholder">M</div>
      <div class="msg-bubble">
        <div class="msg-header">
          <span class="sender-name">You</span>
          <span class="msg-time">Just now</span>
        </div>
        <div class="msg-content">${escapeHTML(text)}</div>
      </div>
    `;
    chatMessages.appendChild(row);
    if (scroll) scrollToBottom();
  }

  function appendGilgameshMessage(replyText, audioUrl, emotion = 'haughty', scroll = true) {
    const row = document.createElement('div');
    row.className = 'message-row gilgamesh-row';
    
    let audioPillHtml = '';
    if (audioUrl) {
      audioPillHtml = `
        <button class="audio-play-pill" onclick="playAudio('${audioUrl}', '${emotion}')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
          </svg>
          Replay Voice
        </button>
      `;
    }

    row.innerHTML = `
      <div class="msg-avatar">
        <img src="/static/avatar.jpg?v=5" alt="Gilgamesh" onerror="this.src='https://api.dicebear.com/7.x/bottts/svg?seed=Gilgamesh'">
      </div>
      <div class="msg-bubble">
        <div class="msg-header">
          <span class="sender-name">Gilgamesh</span>
          <span class="msg-time">Just now</span>
        </div>
        ${formatGilgameshText(replyText)}
        ${audioPillHtml}
      </div>
    `;
    chatMessages.appendChild(row);
    if (scroll) scrollToBottom();
  }

  // Chronicle Export & Import Elements
  const exportChatBtn = document.getElementById('export-chat-btn');
  const importChatBtn = document.getElementById('import-chat-btn');
  const importFileInput = document.getElementById('import-file-input');
  const modalExportBtn = document.getElementById('modal-export-btn');
  const modalImportBtn = document.getElementById('modal-import-btn');

  let savedHistoryItems = [];

  function saveToLocalStorage(chatItems) {
    try {
      localStorage.setItem('gilgamesh_royal_chronicle', JSON.stringify({
        history: chatItems,
        timestamp: Date.now()
      }));
    } catch (e) {
      console.warn("LocalStorage save error:", e);
    }
  }

  function getFromLocalStorage() {
    try {
      const raw = localStorage.getItem('gilgamesh_royal_chronicle');
      if (raw) return JSON.parse(raw);
    } catch (e) {
      console.warn("LocalStorage read error:", e);
    }
    return null;
  }

  function renderFullHistory(items) {
    chatMessages.innerHTML = '';
    history = [];
    savedHistoryItems = [...items];
    items.forEach(item => {
      history.push({ role: item.role, content: item.content });
      if (item.role === 'user') {
        appendUserMessage(item.content, false);
      } else {
        appendGilgameshMessage(item.content, item.audio_url, item.emotion || 'haughty', false);
      }
    });
    setTimeout(scrollToBottom, 150);
  }

  // Profile & PIN Handlers
  if (profileToggleBtn) {
    profileToggleBtn.addEventListener('click', () => {
      if (currentProfile === 'master') {
        const lock = confirm("Lock Master Profile and switch to Guest Mode? Your private memories and chat history will remain securely encrypted in the cloud.");
        if (lock) {
          currentProfile = 'guest';
          masterPin = '';
          sessionStorage.removeItem('gil_master_pin');
          updateProfileUI('guest');
          loadGuestWelcome();
        }
      } else {
        if (pinModal) {
          pinModal.style.display = 'flex';
          if (pinErrorMsg) {
            pinErrorMsg.textContent = '';
          }
          if (vaultPinInput) {
            vaultPinInput.value = '';
            setTimeout(() => vaultPinInput.focus(), 100);
          }
        }
      }
    });
  }

  if (closePinModal) {
    closePinModal.addEventListener('click', () => {
      if (pinModal) pinModal.style.display = 'none';
    });
  }

  // Close modals when clicking backdrop
  window.addEventListener('click', (e) => {
    if (e.target === pinModal) pinModal.style.display = 'none';
    
  });

  async function attemptUnlockVault(pinToTest, isAuto = false) {
    const pin = (pinToTest || (vaultPinInput ? vaultPinInput.value : '')).trim();
    if (!pin) {
      if (pinErrorMsg) pinErrorMsg.textContent = "Please enter your Royal PIN.";
      return;
    }
    if (pinErrorMsg && !isAuto) {
      pinErrorMsg.textContent = "Unsealing the King's Inner Sanctum from GitHub...";
      pinErrorMsg.style.color = "var(--gold-bright)";
    }

    try {
      const res = await fetch('/api/vault/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin: pin })
      });
      const data = await res.json();
      if (!res.ok) {
        if (pinErrorMsg && !isAuto) {
          pinErrorMsg.textContent = data.detail || "Incorrect Royal PIN.";
          pinErrorMsg.style.color = "#ef4444";
        }
        if (isAuto) {
          sessionStorage.removeItem('gil_master_pin');
          const savedSessionPin = sessionStorage.getItem('gil_master_pin');
  if (savedSessionPin) {
    attemptUnlockVault(savedSessionPin, true);
  } else {
    loadHistory();
  }
        }
        return;
      }

      // Success!
      masterPin = pin;
      sessionStorage.setItem('gil_master_pin', pin);
      updateProfileUI('master');
      if (pinModal) pinModal.style.display = 'none';

      if (Array.isArray(data.history) && data.history.length > 0) {
        renderFullHistory(data.history);
      } else {
        chatMessages.innerHTML = `
          <div class="message-row gilgamesh-row">
            <div class="msg-avatar">
              <img src="/static/avatar.jpg?v=5" alt="Gilgamesh" onerror="this.src='https://api.dicebear.com/7.x/bottts/svg?seed=Gilgamesh'">
            </div>
            <div class="msg-bubble">
              <div class="msg-header">
                <span class="sender-name">Gilgamesh 👑</span>
                <span class="msg-time">Inner Sanctum Unlocked</span>
              </div>
              <div class="msg-content">
                <span class="action">*The towering golden gates of Babylon part with an echoing rumble, revealing the King of Heroes reclined upon his throne, a goblet of vintage wine in hand as crimson eyes gleam with cruel amusement.*</span>
                "Hmph. So the mongrel actually remembered the royal seal to bypass my gates. Very well—I permit you past the threshold into my inner sanctum. Speak, then. Let us see if you have brought something worthy of my gaze today."
              </div>
            </div>
          </div>
        `;
        history = [];
        savedHistoryItems = [];
        scrollToBottom();
      }
    } catch (err) {
      if (pinErrorMsg && !isAuto) {
        pinErrorMsg.textContent = "Connection error: " + err.message;
        pinErrorMsg.style.color = "#ef4444";
      }
      if (isAuto) loadHistory();
    }
  }

  if (unlockVaultBtn) {
    unlockVaultBtn.addEventListener('click', () => attemptUnlockVault());
  }

  if (vaultPinInput) {
    vaultPinInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        attemptUnlockVault();
      }
    });
  }

  function loadGuestWelcome() {
    chatMessages.innerHTML = `
      <div class="message-row gilgamesh-row">
        <div class="msg-avatar">
          <img src="/static/avatar.jpg?v=5" alt="Gilgamesh" onerror="this.src='https://api.dicebear.com/7.x/bottts/svg?seed=Gilgamesh'">
        </div>
        <div class="msg-bubble">
          <div class="msg-header">
            <span class="sender-name">Gilgamesh</span>
            <span class="msg-time">Guest Audience</span>
          </div>
          <div class="msg-content">
            <span class="action">*He sits reclined upon a lavish golden throne, a jewel-encrusted goblet of ancient vintage resting casually between his fingers.*</span>
                "You stand in the presence of the King of Heroes. I permit you an audience, mongrel. Speak your mind—let us see if what you bring before my throne can amuse me."
          </div>
        </div>
      </div>
    `;
    history = [];
    savedHistoryItems = [];
    scrollToBottom();
  }

  // Load chat history from backend on initial connection (with LocalStorage failover)
  async function loadHistory() {
    try {
      let savedHistory = [];
      try {
        const res = await fetch('/api/history');
        if (res.ok) {
          savedHistory = await res.json();
        }
      } catch (e) {}

      // If backend was reset (e.g. Render container cold restart), restore from local device
      if (!Array.isArray(savedHistory) || savedHistory.length === 0) {
        const localData = getFromLocalStorage();
        if (localData && Array.isArray(localData.history) && localData.history.length > 0) {
          savedHistory = localData.history;
          // Re-hydrate backend memories and chat history
          fetch('/api/sync-chronicle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ history: savedHistory, memories: localData.memories || null })
          }).catch(e => console.warn("Backend sync notice:", e));
        }
      }

      if (Array.isArray(savedHistory) && savedHistory.length > 0) {
        renderFullHistory(savedHistory);
        saveToLocalStorage(savedHistory);
      }
    } catch (err) {
      console.error("Failed to load conversation history:", err);
      const localData = getFromLocalStorage();
      if (localData && Array.isArray(localData.history)) {
        renderFullHistory(localData.history);
      }
    }
  }

  const savedSessionPin = sessionStorage.getItem('gil_master_pin');
  if (savedSessionPin) {
    attemptUnlockVault(savedSessionPin, true);
  } else {
    loadHistory();
  }

  // Export Chronicle Handler
  async function exportChronicle() {
    try {
      let exportData = {
        history: savedHistoryItems,
        exported_at: new Date().toISOString()
      };
      try {
        const res = await fetch('/api/export-chronicle');
        if (res.ok) {
          const cloudData = await res.json();
          if (cloudData.memories) exportData.memories = cloudData.memories;
          if (Array.isArray(cloudData.history) && cloudData.history.length > 0) {
            exportData.history = cloudData.history;
          }
        }
      } catch (e) {}

      const dateStr = new Date().toISOString().slice(0, 10);
      const filename = `gilgamesh_royal_chronicle_${dateStr}.json`;
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("Failed to export chronicle: " + err.message);
    }
  }

  if (exportChatBtn) exportChatBtn.addEventListener('click', exportChronicle);
  if (modalExportBtn) modalExportBtn.addEventListener('click', exportChronicle);

  // Import Chronicle Handler
  function triggerImport() {
    if (importFileInput) importFileInput.click();
  }

  if (importChatBtn) importChatBtn.addEventListener('click', triggerImport);
  if (modalImportBtn) modalImportBtn.addEventListener('click', triggerImport);

  if (importFileInput) {
    importFileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = async (event) => {
        try {
          const parsed = JSON.parse(event.target.result);
          let historyToRestore = [];
          let memoriesToRestore = null;

          if (Array.isArray(parsed)) {
            historyToRestore = parsed;
          } else if (parsed && typeof parsed === 'object') {
            historyToRestore = parsed.history || [];
            memoriesToRestore = parsed.memories || null;
          }

          if (!historyToRestore || historyToRestore.length === 0) {
            alert("No valid messages found in this file.");
            return;
          }

          // Sync to backend
          await fetch('/api/sync-chronicle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ history: historyToRestore, memories: memoriesToRestore })
          });

          // Render in UI & save to LocalStorage
          renderFullHistory(historyToRestore);
          saveToLocalStorage(historyToRestore);
          alert(`The Royal Chronicle has been restored! The King remembers your ${historyToRestore.length} past messages.`);
        } catch (err) {
          alert("Error importing file: " + err.message);
        } finally {
          importFileInput.value = '';
        }
      };
      reader.readAsText(file);
    });
  }

  // Reset / New Audience Handler
  if (newChatBtn) {
    newChatBtn.addEventListener('click', async () => {
      const confirmReset = confirm("Begin a new audience with the King of Heroes? Your previous conversation will be recorded into the Royal Vault.");
      if (!confirmReset) return;

      try {
        await fetch('/api/reset-chat', { method: 'POST' });
        history = [];
        savedHistoryItems = [];
        localStorage.removeItem('gilgamesh_royal_chronicle');
        chatMessages.innerHTML = `
          <div class="message-row gilgamesh-row">
            <div class="msg-avatar">
              <img src="/static/avatar.jpg?v=5" alt="Gilgamesh" onerror="this.src='https://api.dicebear.com/7.x/bottts/svg?seed=Gilgamesh'">
            </div>
            <div class="msg-bubble">
              <div class="msg-header">
                <span class="sender-name">Gilgamesh</span>
                <span class="msg-time">A New Dawn</span>
              </div>
              <div class="msg-content">
                <span class="action">*He sits reclined upon a lavish golden throne, a jewel-encrusted goblet of ancient vintage resting casually between his fingers as piercing crimson eyes regard you.*</span>
                "You stand once more in the presence of the King of Heroes. I permit you an audience, mongrel. Speak your mind—let us see what you bring before my throne today."
              </div>
            </div>
          </div>
        `;
        scrollToBottom();
      } catch (err) {
        console.error("Failed to reset audience:", err);
      }
    });
  }

  window.playAudio = function(url, emotion = 'haughty') {
    currentEmotion = emotion;
    globalAudio.src = url;
    globalAudio.play();
  };

  // Audio visualizer state for Live Call
  globalAudio.addEventListener('play', () => {
    if (isCallActive) {
      callAvatarStage.classList.add('speaking-active');
      if (currentEmotion === 'angry' || currentEmotion === 'furious') {
        callAvatarStage.classList.add('angry');
      } else {
        callAvatarStage.classList.remove('angry');
      }
    }
  });

  globalAudio.addEventListener('ended', () => {
    callAvatarStage.classList.remove('speaking-active', 'angry');
    if (isCallActive) {
      callTranscriptPreview.textContent = "Listening to you...";
    }
  });

  globalAudio.addEventListener('pause', () => {
    callAvatarStage.classList.remove('speaking-active', 'angry');
  });

  async function sendMessage(text) {
    text = text.trim();
    if (!text) return;

    appendUserMessage(text);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    history.push({ role: "user", content: text });
    typingIndicator.style.display = 'flex';
    scrollToBottom();

    if (isCallActive) {
      callTranscriptPreview.textContent = "The King is considering your words...";
    }

    try {
      const chatPayload = {
        message: text,
        history: history,
        profile: currentProfile
      };
      if (currentProfile === 'master' && masterPin) {
        chatPayload.pin = masterPin;
      }

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(chatPayload)
      });

      const data = await res.json();
      typingIndicator.style.display = 'none';

      if (!res.ok) {
        alert(data.detail || "Error communicating with Groq.");
        return;
      }

      history.push({ role: "assistant", content: data.reply });
      currentEmotion = data.emotion || 'haughty';
      appendGilgameshMessage(data.reply, data.audio_url, currentEmotion);

      // Persist to local device storage automatically
      savedHistoryItems.push({ role: "user", content: text });
      savedHistoryItems.push({
        role: "assistant",
        content: data.reply,
        audio_url: data.audio_url,
        emotion: currentEmotion
      });
      saveToLocalStorage(savedHistoryItems);

      if (data.audio_url) {
        globalAudio.src = data.audio_url;
        globalAudio.play();
      }

      if (isCallActive) {
        // Strip asterisks for the live call preview
        const spoken = data.reply.replace(/\*.*?\*/g, '').trim();
        callTranscriptPreview.textContent = `"${spoken}"`;
      }

    } catch (err) {
      typingIndicator.style.display = 'none';
      console.error(err);
      alert("Failed to reach server.");
    }
  }

  // Input Events
  sendBtn.addEventListener('click', () => sendMessage(chatInput.value));

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(chatInput.value);
    }
  });

  // Microphone Recording via MediaRecorder + Groq Whisper
  async function toggleRecording(btnElement, onTranscribedCallback) {
    if (!isRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
          const formData = new FormData();
          formData.append('file', audioBlob, 'speech.webm');

          if (btnElement) btnElement.classList.remove('recording');

          try {
            if (isCallActive) {
              callTranscriptPreview.textContent = "Transcribing with Whisper...";
            }
            const res = await fetch('/api/transcribe', { method: 'POST', body: formData });
            const data = await res.json();
            if (res.ok && data.text) {
              onTranscribedCallback(data.text);
            }
          } catch (e) {
            console.error("Transcription error", e);
          }
          // Stop all mic tracks
          stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        isRecording = true;
        if (btnElement) btnElement.classList.add('recording');
        if (isCallActive) {
          callTranscriptPreview.textContent = "Listening... (Click mic to send)";
        }
      } catch (err) {
        alert("Microphone access denied: " + err.message);
      }
    } else {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
      }
      isRecording = false;
    }
  }

  micBtn.addEventListener('click', () => {
    toggleRecording(micBtn, (transcript) => {
      chatInput.value = transcript;
      sendMessage(transcript);
    });
  });

  // Live Call Button Events
  callToggleBtn.addEventListener('click', () => {
    isCallActive = true;
    callModal.style.display = 'flex';
    callTranscriptPreview.textContent = "Speak, mongrel. The King grants you his ear.";
  });

  endCallBtn.addEventListener('click', () => {
    isCallActive = false;
    callModal.style.display = 'none';
    globalAudio.pause();
    if (isRecording && mediaRecorder) {
      mediaRecorder.stop();
      isRecording = false;
    }
  });

  callMicToggle.addEventListener('click', () => {
    toggleRecording(callMicToggle, (transcript) => {
      sendMessage(transcript);
    });
  });

  function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, 
      tag => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
      }[tag] || tag)
    );
  }
});
