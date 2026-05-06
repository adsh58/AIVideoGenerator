// State
let state = {
  photoPath: null,
  voicePath: null,
  videoType: 'short',
  currentJobId: null,
  pollInterval: null,
};

// Tab switching
function showTab(tab) {
  ['create', 'gallery'].forEach(t => {
    document.getElementById(`panel-${t}`).classList.toggle('hidden', t !== tab);
    const btn = document.getElementById(`tab-${t}`);
    if (t === tab) {
      btn.classList.add('tab-active');
      btn.classList.remove('text-white/60');
    } else {
      btn.classList.remove('tab-active');
      btn.classList.add('text-white/60');
    }
  });
  if (tab === 'gallery') loadVideos();
}

// Video type selection
function selectType(type) {
  state.videoType = type;
  ['short', 'reel', 'long'].forEach(t => {
    document.getElementById(`type-${t}`).classList.toggle('selected', t === type);
  });
  // Adjust slider range
  const slider = document.getElementById('durationSlider');
  const ranges = { short: [15, 60], reel: [30, 90], long: [60, 600] };
  const [min, max] = ranges[type];
  slider.min = min;
  slider.max = max;
  slider.value = Math.min(Math.max(slider.value, min), max);
  document.getElementById('durationLabel').textContent = slider.value + 's';
  const labels = document.querySelectorAll('.flex.justify-between.text-xs.text-white\\/30 span');
  if (labels.length >= 2) {
    labels[0].textContent = min + 's';
    labels[1].textContent = max < 120 ? max + 's' : Math.floor(max / 60) + 'min';
  }
}

function setBackground(text) {
  document.getElementById('backgroundPrompt').value = text;
}

// Photo upload
async function handlePhotoUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const zone = document.getElementById('photoZone');
  zone.classList.add('active');
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/upload/photo', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      state.photoPath = data.path;
      document.getElementById('photoPath').value = data.path;
      // Show preview
      const reader = new FileReader();
      reader.onload = e => {
        document.getElementById('photoImg').src = e.target.result;
        document.getElementById('photoName').textContent = file.name;
        document.getElementById('photoPreview').classList.remove('hidden');
        document.getElementById('photoPlaceholder').classList.add('hidden');
      };
      reader.readAsDataURL(file);
      showToast('Photo uploaded!', 'success');
    } else {
      showToast('Upload failed: ' + (data.detail || 'Unknown error'), 'error');
    }
  } catch (e) {
    showToast('Upload failed: ' + e.message, 'error');
  }
  zone.classList.remove('active');
}

// Voice upload
async function handleVoiceUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const zone = document.getElementById('voiceZone');
  zone.classList.add('active');
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/upload/voice', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      state.voicePath = data.path;
      document.getElementById('voicePath').value = data.path;
      document.getElementById('voiceName').textContent = file.name;
      document.getElementById('voicePlayer').src = URL.createObjectURL(file);
      document.getElementById('voicePreview').classList.remove('hidden');
      document.getElementById('voicePlaceholder').classList.add('hidden');
      showToast('Voice sample uploaded!', 'success');
    } else {
      showToast('Upload failed: ' + (data.detail || 'Unknown error'), 'error');
    }
  } catch (e) {
    showToast('Upload failed: ' + e.message, 'error');
  }
  zone.classList.remove('active');
}

// Preview script
async function previewScript() {
  const prompt = document.getElementById('scriptPrompt').value.trim();
  if (!prompt) { showToast('Enter a script prompt first', 'error'); return; }
  const box = document.getElementById('scriptPreviewBox');
  const textEl = document.getElementById('scriptPreviewText');
  box.classList.remove('hidden');
  textEl.textContent = 'Generating script...';
  textEl.classList.add('shimmer');
  try {
    const res = await fetch('/api/generate/script-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        script_prompt: prompt,
        video_type: state.videoType,
        video_length: parseInt(document.getElementById('durationSlider').value),
      }),
    });
    const data = await res.json();
    textEl.textContent = data.script || 'No script generated.';
  } catch (e) {
    textEl.textContent = 'Could not generate script. Make sure Ollama is running.';
  }
  textEl.classList.remove('shimmer');
}

function useGeneratedScript() {
  const script = document.getElementById('scriptPreviewText').textContent;
  document.getElementById('scriptPrompt').value = script;
  document.getElementById('scriptPreviewBox').classList.add('hidden');
  showToast('Script applied!', 'success');
}

// Generate video
async function generateVideo() {
  const photoPath = state.photoPath;
  const voicePath = state.voicePath;
  const scriptPrompt = document.getElementById('scriptPrompt').value.trim();
  const backgroundPrompt = document.getElementById('backgroundPrompt').value.trim();
  const duration = parseInt(document.getElementById('durationSlider').value);
  const title = document.getElementById('videoTitle').value.trim() || 'My Video';

  if (!photoPath) { showToast('Please upload your photo first', 'error'); return; }
  if (!voicePath) { showToast('Please upload a voice sample first', 'error'); return; }
  if (!scriptPrompt) { showToast('Please enter a script prompt', 'error'); return; }
  if (!backgroundPrompt) { showToast('Please describe the background scene', 'error'); return; }

  const btn = document.getElementById('generateBtn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  showProgress(true);
  updateProgress(5, 'Submitting job...', 'Initializing pipeline');

  try {
    const res = await fetch('/api/generate/video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        photo_path: photoPath,
        voice_path: voicePath,
        script_prompt: scriptPrompt,
        background_prompt: backgroundPrompt,
        video_type: state.videoType,
        video_length: duration,
      }),
    });
    const data = await res.json();
    if (data.success) {
      state.currentJobId = data.job_id;
      showToast('Video generation started!', 'success');
      startPolling(data.job_id);
    } else {
      throw new Error(data.detail || 'Failed to start');
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Generate Video';
    showProgress(false);
  }
}

function startPolling(jobId) {
  if (state.pollInterval) clearInterval(state.pollInterval);
  state.pollInterval = setInterval(() => pollJob(jobId), 5000);
}

const STATUS_LABELS = {
  pending:           { label: 'Queued...',               step: 'Waiting to start', pct: 5 },
  generating_script: { label: 'Writing your script',     step: 'AI is crafting the perfect script for your topic', pct: 20 },
  generating_audio:  { label: 'Generating speech',       step: 'Converting script to natural-sounding audio', pct: 45 },
  animating_face:    { label: 'Animating your face',     step: 'SadTalker is generating lip-sync (may take 5-15 min on CPU)', pct: 70 },
  composing_video:   { label: 'Composing final video',   step: 'Merging face, background & captions', pct: 88 },
  completed:         { label: 'Done!',                   step: 'Your video is ready to download', pct: 100 },
  failed:            { label: 'Generation failed',       step: 'See error below', pct: 0 },
};

async function pollJob(jobId) {
  try {
    const res = await fetch(`/api/videos/${jobId}`);
    const job = await res.json();
    const info = STATUS_LABELS[job.status] || { label: job.status, step: '', pct: job.progress };
    updateProgress(info.pct, info.label, info.step);

    if (job.status === 'completed') {
      clearInterval(state.pollInterval);
      showVideoReady(job);
    } else if (job.status === 'failed') {
      clearInterval(state.pollInterval);
      showToast('Generation failed: ' + (job.error_message || 'Unknown error'), 'error');
      document.getElementById('progressStep').textContent = job.error_message || 'Unknown error';
      document.getElementById('generateBtn').disabled = false;
      document.getElementById('generateBtn').textContent = 'Try Again';
    }
  } catch (e) {
    console.error('Poll error:', e);
  }
}

function showVideoReady(job) {
  const panel = document.getElementById('progressPanel');
  panel.innerHTML = `
    <div class="text-center py-4">
      <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-green-500/20 flex items-center justify-center">
        <svg class="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
        </svg>
      </div>
      <h3 class="text-xl font-bold text-white mb-1">Video Ready!</h3>
      <p class="text-white/50 text-sm mb-5">${job.title}</p>
      <div class="flex gap-3 justify-center">
        <a href="/api/videos/${job.id}/download" download class="btn-primary px-6 py-3 rounded-xl font-medium text-sm flex items-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
          Download Video
        </a>
        <button onclick="resetForm()" class="px-6 py-3 rounded-xl font-medium text-sm border border-white/15 hover:bg-white/5 transition-colors">
          Make Another
        </button>
      </div>
    </div>
  `;
  document.getElementById('generateBtn').disabled = false;
  document.getElementById('generateBtn').textContent = 'Generate Video';
  showToast('Your video is ready!', 'success');
}

function resetForm() {
  state.currentJobId = null;
  document.getElementById('progressPanel').classList.add('hidden');
  document.getElementById('generateBtn').disabled = false;
  document.getElementById('generateBtn').textContent = 'Generate Video';
  // Re-render progress panel for next use
  document.getElementById('progressPanel').innerHTML = `
    <div class="flex items-center gap-4 mb-5">
      <div class="relative">
        <div class="w-12 h-12 rounded-full bg-purple-600/30 flex items-center justify-center">
          <div class="pulse-ring absolute inset-0 rounded-full bg-purple-500/30"></div>
          <svg class="w-5 h-5 text-purple-400 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        </div>
      </div>
      <div>
        <p class="font-semibold text-white" id="progressLabel">Generating your video...</p>
        <p class="text-sm text-white/50" id="progressStep">This may take 3–8 minutes</p>
      </div>
    </div>
    <div class="bg-white/5 rounded-full h-2 overflow-hidden">
      <div id="progressBar" class="progress-bar h-full rounded-full bg-gradient-to-r from-purple-600 to-indigo-500" style="width: 0%"></div>
    </div>
    <div class="flex justify-between text-xs text-white/40 mt-2">
      <span id="progressPct">0%</span><span>100%</span>
    </div>
  `;
}

function showProgress(visible) {
  document.getElementById('progressPanel').classList.toggle('hidden', !visible);
}

function updateProgress(pct, label, step) {
  const bar = document.getElementById('progressBar');
  const pctEl = document.getElementById('progressPct');
  const labelEl = document.getElementById('progressLabel');
  const stepEl = document.getElementById('progressStep');
  if (bar) bar.style.width = pct + '%';
  if (pctEl) pctEl.textContent = pct + '%';
  if (labelEl) labelEl.textContent = label;
  if (stepEl) stepEl.textContent = step;
}

// Gallery
async function loadVideos() {
  const container = document.getElementById('videosList');
  container.innerHTML = '<p class="text-center text-white/30 py-8">Loading...</p>';
  try {
    const res = await fetch('/api/videos');
    const data = await res.json();
    if (!data.videos.length) {
      container.innerHTML = '<p class="text-center text-white/30 py-12">No videos yet. Create your first video!</p>';
      return;
    }
    container.innerHTML = data.videos.map(v => videoCard(v)).join('');
  } catch (e) {
    container.innerHTML = `<p class="text-center text-red-400/70 py-8">Could not load videos: ${e.message}</p>`;
  }
}

function videoCard(v) {
  const statusColors = {
    completed: 'text-green-400 bg-green-400/10',
    failed: 'text-red-400 bg-red-400/10',
    pending: 'text-yellow-400 bg-yellow-400/10',
    generating_script: 'text-blue-400 bg-blue-400/10',
    generating_audio: 'text-blue-400 bg-blue-400/10',
    animating_face: 'text-purple-400 bg-purple-400/10',
    composing_video: 'text-purple-400 bg-purple-400/10',
  };
  const statusColor = statusColors[v.status] || 'text-white/40 bg-white/5';
  const typeEmoji = { short: '📱', reel: '🎬', long: '🖥️' }[v.video_type] || '🎥';
  const date = v.created_at ? new Date(v.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

  return `
  <div class="video-card rounded-2xl p-5">
    <div class="flex items-start justify-between mb-3">
      <div class="flex items-center gap-3">
        <span class="text-2xl">${typeEmoji}</span>
        <div>
          <h3 class="font-semibold text-white text-sm">${v.title}</h3>
          <p class="text-xs text-white/30">${date} • ${v.video_length}s</p>
        </div>
      </div>
      <span class="text-xs px-2.5 py-1 rounded-full font-medium ${statusColor}">${v.status.replace(/_/g, ' ')}</span>
    </div>
    ${v.status !== 'completed' && v.status !== 'failed' ? `
      <div class="bg-white/5 rounded-full h-1.5 overflow-hidden mb-3">
        <div class="h-full rounded-full bg-gradient-to-r from-purple-600 to-indigo-500 transition-all" style="width: ${v.progress}%"></div>
      </div>
    ` : ''}
    ${v.generated_script ? `<p class="text-xs text-white/40 leading-relaxed mb-3 line-clamp-2">${v.generated_script.substring(0, 120)}...</p>` : ''}
    ${v.error_message ? `<p class="text-xs text-red-400/70 mb-3">${v.error_message}</p>` : ''}
    <div class="flex gap-2">
      ${v.final_video_url ? `
        <a href="${v.final_video_url}" download class="btn-primary text-xs px-4 py-2 rounded-lg flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
          Download
        </a>
      ` : ''}
      <button onclick="deleteVideo(${v.id})" class="text-xs px-4 py-2 rounded-lg border border-white/10 hover:bg-red-500/10 hover:border-red-500/30 text-white/40 hover:text-red-400 transition-colors">
        Delete
      </button>
    </div>
  </div>`;
}

async function deleteVideo(id) {
  if (!confirm('Delete this video?')) return;
  try {
    await fetch(`/api/videos/${id}`, { method: 'DELETE' });
    loadVideos();
    showToast('Video deleted', 'success');
  } catch (e) {
    showToast('Delete failed', 'error');
  }
}

// Toast notifications
let toastTimer;
function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  const colors = { success: 'bg-green-500/90 text-white', error: 'bg-red-500/90 text-white', info: 'bg-purple-600/90 text-white' };
  toast.className = `fixed bottom-6 right-6 px-5 py-3.5 rounded-xl text-sm font-medium shadow-xl z-50 max-w-xs ${colors[type]}`;
  toast.textContent = message;
  toast.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add('hidden'), 3500);
}

// Drag and drop for photo
const photoZone = document.getElementById('photoZone');
photoZone.addEventListener('dragover', e => { e.preventDefault(); photoZone.classList.add('active'); });
photoZone.addEventListener('dragleave', () => photoZone.classList.remove('active'));
photoZone.addEventListener('drop', e => {
  e.preventDefault();
  photoZone.classList.remove('active');
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) {
    const dt = new DataTransfer();
    dt.items.add(file);
    document.getElementById('photoInput').files = dt.files;
    handlePhotoUpload(document.getElementById('photoInput'));
  }
});

const voiceZone = document.getElementById('voiceZone');
voiceZone.addEventListener('dragover', e => { e.preventDefault(); voiceZone.classList.add('active'); });
voiceZone.addEventListener('dragleave', () => voiceZone.classList.remove('active'));
voiceZone.addEventListener('drop', e => {
  e.preventDefault();
  voiceZone.classList.remove('active');
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('audio/')) {
    const dt = new DataTransfer();
    dt.items.add(file);
    document.getElementById('voiceInput').files = dt.files;
    handleVoiceUpload(document.getElementById('voiceInput'));
  }
});
