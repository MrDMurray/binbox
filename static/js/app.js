const sensorText = document.getElementById("sensor-text");
const countEl = document.getElementById("count");
const currentSongEl = document.getElementById("current-song");
const nextSongEl = document.getElementById("next-song");
const songCountEl = document.getElementById("song-count");
const sensorStatus = document.getElementById("sensor-status");
const bpmEl = document.getElementById("bpm");
const analysisStatus = document.getElementById("analysis-status");
const headEl = document.getElementById("robot-head");
const stopBtn = document.getElementById("stop-btn");
let COOLDOWN_TOTAL = 10;
let HEAD_BOB_ENABLED = true;
let bopPhase = 0; // 0-1
let bopTimer = null;
let kickDelay = 0;
let lastBopDuration = 0.8;
let prevPlaying = null;
let prevBpm = null;
let prevKick = null;
let prevSong = null;
let storedPhase = localStorage.getItem("binbox_phase");
if (storedPhase !== null) {
  bopPhase = Math.min(1, Math.max(0, parseFloat(storedPhase)));
}
setTheme(typeof THEME_COLOR !== "undefined" ? THEME_COLOR : null);

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    renderState(data);
  } catch (err) {
    sensorText.textContent = "Unable to reach server";
    sensorStatus.classList.add("alert");
    console.error("State fetch failed", err);
  }
}

function renderState(state) {
  if (state.triggered) {
    sensorStatus.classList.add("alert");
    sensorText.textContent = "Triggered!";
  } else {
    sensorStatus.classList.remove("alert");
    sensorText.textContent = "Listening...";
  }
  countEl.textContent = state.count;
  console.debug("State songs_available", state.songs_available);
  songCountEl.textContent = `${state.songs_available || 0} songs in queue`;
  currentSongEl.textContent = state.current_song || (state.songs_available ? "Waiting for trigger..." : "Drop .mp3 files into /songs");
  nextSongEl.textContent = state.next_song || "Add songs to /songs";
  COOLDOWN_TOTAL = state.cooldown_seconds || COOLDOWN_TOTAL;
  HEAD_BOB_ENABLED = state.head_bob_enabled !== false;
  kickDelay = state.kick_delay || 0;
  renderBpm(state.current_bpm);
  renderAnalysis(state.analysis);
  const changed =
    prevPlaying !== state.is_playing ||
    prevBpm !== state.current_bpm ||
    prevKick !== kickDelay ||
    prevSong !== state.current_song;
  prevPlaying = state.is_playing;
  prevBpm = state.current_bpm;
  prevKick = kickDelay;
  if (changed) {
    const forceRestart = prevSong !== state.current_song;
    prevSong = state.current_song;
    toggleHead(state.is_playing, state.current_bpm, kickDelay, forceRestart);
  }
}

async function triggerSensor() {
  try {
    await fetch("/api/trigger", { method: "POST" });
  } catch (err) {
    console.error("Trigger failed", err);
  }
}

async function stopMusic() {
  try {
    await fetch("/api/stop", { method: "POST" });
    await fetchState();
  } catch (err) {
    console.error("Stop failed", err);
  }
}

const allowSim = typeof SIMULATOR_MODE === "undefined" ? false : !!SIMULATOR_MODE;
if (allowSim) {
  window.addEventListener(
    "keydown",
    (event) => {
      const isSpace =
        event.code === "Space" || event.key === " " || event.key === "Spacebar";
      const target = event.target;
      const isInput =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if (isSpace && !isInput) {
        event.preventDefault();
        event.stopPropagation();
        console.debug("Spacebar trigger fired");
        triggerSensor();
      }
    },
    true
  );
}

if (stopBtn) {
  stopBtn.addEventListener("click", stopMusic);
}

function toggleHead(isPlaying, bpm, delaySeconds = 0, forceRestart = false) {
  if (!headEl) return;
  if (bopTimer) {
    clearTimeout(bopTimer);
    bopTimer = null;
  }
  if (forceRestart) {
    headEl.classList.remove("bopping");
    headEl.style.removeProperty("--bop-duration");
    headEl.style.removeProperty("animation-delay");
  }
  if (isPlaying && HEAD_BOB_ENABLED) {
    const start = () => {
      headEl.classList.add("bopping");
      const duration = bpm && bpm > 0 ? Math.max(0.3, 60 / bpm) : 0.8;
      lastBopDuration = duration;
      headEl.style.setProperty("--bop-duration", `${duration}s`);
      const delay = -(bopPhase * duration);
      headEl.style.setProperty("animation-delay", `${delay}s`);
      fetch("/api/log_bop", { method: "POST" }).catch(() => {});
    };
    if (delaySeconds && delaySeconds > 0) {
      headEl.style.setProperty("animation-delay", `${-delaySeconds}s`);
      bopTimer = setTimeout(start, delaySeconds * 1000);
    } else {
      start();
    }
  } else {
    headEl.classList.remove("bopping");
    headEl.style.removeProperty("--bop-duration");
    headEl.style.removeProperty("animation-delay");
  }
}

function setTheme(color) {
  if (!color) return;
  document.documentElement.style.setProperty("--accent", color);
  document.documentElement.style.setProperty("--accent-2", color);
}

function renderBpm(bpm) {
  if (!bpmEl) return;
  bpmEl.textContent = bpm ? Math.round(bpm) : "--";
}

function renderAnalysis(analysis) {
  if (!analysisStatus || !analysis) return;
  const available = analysis.librosa_available ? "librosa ready" : "librosa not installed";
  const cacheText = analysis.cache_exists ? "cached BPMs available" : "no BPM cache";
  const running = analysis.running ? " | running" : "";
  const last = analysis.last ? ` | last: ${analysis.last}` : "";
  const err = analysis.error ? ` | error: ${analysis.error}` : "";
  analysisStatus.textContent = `${available}; ${cacheText}${running}${last}${err}`;
}

fetchState();
setInterval(fetchState, 1000);
