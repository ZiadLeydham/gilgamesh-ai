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
  
  // Settings modal
  const settingsBtn = document.getElementById('settings-btn');
  const settingsModal = document.getElementById('settings-modal');
  const closeSettings = document.getElementById('close-settings');
  const saveSettingsBtn = document.getElementById('save-settings-btn');
  const groqKeyInput = document.getElementById('groq-key-input');
  const settingsMsg = document.getElementById('settings-msg');

  // Engine selection elements
  const engineRadios = document.querySelectorAll('input[name="voice_engine_choice"]');
  const fishAudioConfig = document.getElementById('fish-audio-config');
  const fishKeyInput = document.getElementById('fish-key-input');
  const fishModelSelect = document.getElementById('fish-model-select');
  const fishCustomModelInput = document.getElementById('fish-custom-model-input');

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

  // Toggle voice engine visibility
  engineRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      fishAudioConfig.style.display = radio.value === 'fish_audio' ? 'block' : 'none';
    });
  });

  fishModelSelect.addEventListener('change', () => {
    fishCustomModelInput.style.display = fishModelSelect.value === 'custom' ? 'block' : 'none';
  });

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
      if (!data.configured) {
        settingsModal.style.display = 'flex';
        settingsMsg.textContent = "Please enter your Groq API Key to awaken the King.";
        settingsMsg.style.color = "#ffd700";
      }

      // Populate voice engine settings
      const engine = data.voice_engine || 'rvc';
      const targetRadio = document.querySelector(`input[name="voice_engine_choice"][value="${engine}"]`);
      if (targetRadio) {
        targetRadio.checked = true;
        fishAudioConfig.style.display = engine === 'fish_audio' ? 'block' : 'none';
      }

      if (data.has_fish_key) {
        fishKeyInput.placeholder = "•••••••••••••••• (Saved in .env)";
      }

      if (data.fish_model) {
        const optionExists = Array.from(fishModelSelect.options).some(o => o.value === data.fish_model);
        if (optionExists) {
          fishModelSelect.value = data.fish_model;
        } else {
          fishModelSelect.value = 'custom';
          fishCustomModelInput.value = data.fish_model;
          fishCustomModelInput.style.display = 'block';
        }
      }

      if (typeof data.noise_filter !== 'undefined') {
        updateFilterUI(data.noise_filter);
      }
    })
    .catch(err => console.error("Status check failed", err));

  // Settings Handlers
  settingsBtn.addEventListener('click', () => {
    settingsModal.style.display = 'flex';
  });

  closeSettings.addEventListener('click', () => {
    settingsModal.style.display = 'none';
  });

  saveSettingsBtn.addEventListener('click', async () => {
    const groqKey = groqKeyInput.value.trim();
    const selectedEngine = document.querySelector('input[name="voice_engine_choice"]:checked')?.value || 'rvc';
    const fishKey = fishKeyInput.value.trim();
    
    let fishModel = fishModelSelect.value;
    if (fishModel === 'custom') {
      fishModel = fishCustomModelInput.value.trim();
    }

    const payload = {
      voice_engine: selectedEngine,
      noise_filter: noiseFilterCheckbox ? noiseFilterCheckbox.checked : isFilterActive
    };
    if (groqKey) payload.groq_api_key = groqKey;
    if (fishKey) payload.fish_api_key = fishKey;
    if (fishModel) payload.fish_model_id = fishModel;

    try {
      const res = await fetch('/api/set-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        settingsMsg.textContent = "Settings saved! The King commands.";
        settingsMsg.style.color = "#10b981";
        setTimeout(() => {
          settingsModal.style.display = 'none';
        }, 1200);
      } else {
        settingsMsg.textContent = data.detail || "Error saving settings.";
        settingsMsg.style.color = "#ef4444";
      }
    } catch (e) {
      settingsMsg.textContent = "Network error.";
      settingsMsg.style.color = "#ef4444";
    }
  });

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
          <span class="sender-name">You (Mongrel)</span>
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

    const emotionBadge = `<span class="emotion-badge badge-${emotion}">${escapeHTML(emotion.toUpperCase())}</span>`;

    row.innerHTML = `
      <div class="msg-avatar">
        <img src="https://images.alphacoders.com/605/thumb-1920-605592.png" alt="Gilgamesh" onerror="this.src='https://api.dicebear.com/7.x/bottts/svg?seed=Gilgamesh'">
      </div>
      <div class="msg-bubble">
        <div class="msg-header">
          <div style="display:flex; align-items:center;">
            <span class="sender-name">Gilgamesh</span>
            ${emotionBadge}
          </div>
          <span class="msg-time">Just now</span>
        </div>
        ${formatGilgameshText(replyText)}
        ${audioPillHtml}
      </div>
    `;
    chatMessages.appendChild(row);
    if (scroll) scrollToBottom();
  }

  // Load chat history from backend on initial connection
  async function loadHistory() {
    try {
      const res = await fetch('/api/history');
      const savedHistory = await res.json();
      if (Array.isArray(savedHistory) && savedHistory.length > 0) {
        chatMessages.innerHTML = ''; // Replace initial greeting with ongoing conversation
        history = [];
        savedHistory.forEach(item => {
          history.push({ role: item.role, content: item.content });
          if (item.role === 'user') {
            appendUserMessage(item.content, false);
          } else {
            appendGilgameshMessage(item.content, item.audio_url, item.emotion || 'haughty', false);
          }
        });
        setTimeout(scrollToBottom, 150);
      }
    } catch (err) {
      console.error("Failed to load conversation history:", err);
    }
  }

  loadHistory();

  // Reset / New Audience Handler
  if (newChatBtn) {
    newChatBtn.addEventListener('click', async () => {
      const confirmReset = confirm("Begin a new audience with the King of Heroes? Your previous conversation will be recorded into the Royal Vault.");
      if (!confirmReset) return;

      try {
        await fetch('/api/reset-chat', { method: 'POST' });
        history = [];
        chatMessages.innerHTML = `
          <div class="message-row gilgamesh-row">
            <div class="msg-avatar">
              <img src="https://images.alphacoders.com/605/thumb-1920-605592.png" alt="Gilgamesh" onerror="this.src='https://api.dicebear.com/7.x/bottts/svg?seed=Gilgamesh'">
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
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: history })
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
