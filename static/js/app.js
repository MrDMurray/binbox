const sensorDot = document.getElementById("sensor-dot");
const sensorText = document.getElementById("sensor-text");
const countEl = document.getElementById("count");
const currentSongEl = document.getElementById("current-song");
const nextSongEl = document.getElementById("next-song");
const songCountEl = document.getElementById("song-count");
const sensorStatus = document.getElementById("sensor-status");

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    renderState(data);
  } catch (err) {
    sensorText.textContent = "Unable to reach server";
    sensorStatus.classList.add("alert");
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
  songCountEl.textContent = `${state.songs_available || 0} songs in queue`;
  currentSongEl.textContent = state.current_song
    ? state.current_song
    : state.songs_available
    ? "Waiting for trigger..."
    : "Drop .mp3 files into /songs";
  nextSongEl.textContent = state.next_song ? state.next_song : "Add songs to /songs";
}

async function triggerSensor() {
  try {
    await fetch("/api/trigger", { method: "POST" });
  } catch (err) {
    console.error("Trigger failed", err);
  }
}

if (SIMULATOR_MODE) {
  document.addEventListener("keydown", (event) => {
    if (event.code === "Space") {
      event.preventDefault();
      triggerSensor();
    }
  });
}

fetchState();
setInterval(fetchState, 1000);
