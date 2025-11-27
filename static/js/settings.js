const form = document.getElementById("settings-form");
const statusEl = document.getElementById("save-status");
const analyzeBtn = document.getElementById("analyze-btn");
const analysisStatus = document.getElementById("analysis-status");
const phaseSlider = document.getElementById("phase-slider");
const phaseValue = document.getElementById("phase-value");
const sensorTestBtn = document.getElementById("sensor-test-btn");
const sensorTestStatus = document.getElementById("sensor-test-status");
const sensorTestOutput = document.getElementById("sensor-test-output");
let sensorTestTimer = null;

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = {
    cooldown_seconds: parseFloat(form.cooldown_seconds.value) || 0,
    theme_color: form.theme_color.value,
    simulator_mode: form.simulator_mode.checked,
    analysis_enabled: form.analysis_enabled.checked,
    head_bob_enabled: form.head_bob_enabled.checked,
    phase: parseFloat(phaseSlider.value) / 100,
  };
  statusEl.textContent = "Saving...";
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed");
    statusEl.textContent = "Saved!";
  } catch (err) {
    statusEl.textContent = "Error saving settings";
  }
});

async function refreshAnalysis(stopWhenDone = false) {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    const a = data.analysis || {};
    const available = a.librosa_available ? "librosa ready" : "librosa not installed";
    const cacheText = a.cache_exists ? "cached BPMs available" : "no BPM cache yet";
    const running = a.running ? " | running" : "";
    const last = a.last ? ` | last: ${a.last}` : "";
    const err = a.error ? ` | error: ${a.error}` : "";
    analysisStatus.textContent = `Status: ${available}; ${cacheText}${running}${last}${err}`;
    if (stopWhenDone && !a.running) {
      clearIntervalPoll();
    }
  } catch (err) {
    analysisStatus.textContent = "Status: unable to load analysis state";
    clearIntervalPoll();
  }
}

let poll = null;
function clearIntervalPoll() {
  if (poll) {
    clearInterval(poll);
    poll = null;
  }
}

analyzeBtn.addEventListener("click", async () => {
  analysisStatus.textContent = "Status: starting analysis...";
  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analysis_enabled: true }),
    });
    const res = await fetch("/api/analyze", { method: "POST" });
    const data = await res.json();
    const a = data.analysis || {};
    const available = a.librosa_available ? "librosa ready" : "librosa not installed";
    analysisStatus.textContent = `Status: ${available}; started=${data.started}`;
    if (data.started) {
      if (!poll) poll = setInterval(() => refreshAnalysis(true), 1000);
    }
  } catch (err) {
    console.error(err);
    analysisStatus.textContent = "Status: error starting analysis";
  }
});

refreshAnalysis();

// Phase slider persistence
const storedPhase = localStorage.getItem("binbox_phase");
if (storedPhase !== null) {
  const val = Math.min(1, Math.max(0, parseFloat(storedPhase)));
  phaseSlider.value = Math.round(val * 100);
  phaseValue.textContent = `${phaseSlider.value}%`;
} else {
  phaseValue.textContent = `${phaseSlider.value}%`;
}
phaseSlider.addEventListener("input", () => {
  phaseValue.textContent = `${phaseSlider.value}%`;
  localStorage.setItem("binbox_phase", (parseFloat(phaseSlider.value) / 100).toString());
});

// Sensor test / diagnostics
function fmtTime(ts) {
  if (ts === null || typeof ts === "undefined") return "never";
  const date = new Date(ts * 1000);
  const ageMs = Date.now() - date.getTime();
  const age = ageMs >= 0 ? `${(ageMs / 1000).toFixed(1)}s ago` : "in future?";
  return `${date.toLocaleTimeString()} (${age})`;
}

function fmtBool(v) {
  if (v === null || typeof v === "undefined") return "unknown";
  return v ? "HIGH / True" : "LOW / False";
}

async function pollSensorTest() {
  if (!sensorTestOutput) return;
  try {
    const res = await fetch("/api/sensor_test");
    const data = await res.json();
    renderSensorTest(data);
    if (sensorTestStatus) sensorTestStatus.textContent = "Polling...";
  } catch (err) {
    if (sensorTestStatus) sensorTestStatus.textContent = "Error polling sensor";
    sensorTestOutput.textContent = `Error: ${err}`;
    stopSensorTest(null);
  }
}

function renderSensorTest(data) {
  const lines = [];
  lines.push(`GPIO available: ${data.gpio_available}`);
  lines.push(`Setting enabled: ${data.gpio_enabled_setting}`);
  lines.push(`Initialized: ${data.gpio_initialized}`);
  lines.push(`Ready: ${data.ready}`);
  lines.push(`Polling active: ${data.polling_active} (thread alive: ${data.gpio_thread_alive})`);
  lines.push(`Sensor pin: ${data.sensor_pin}`);
  lines.push(`Raw read now: ${fmtBool(data.current_read)}`);
  lines.push(`Last raw state: ${fmtBool(data.last_raw_state)}`);
  lines.push(`Last change: ${fmtTime(data.last_change)} (Δ ${typeof data.since_last_change === "number" ? data.since_last_change.toFixed(2) + "s" : "n/a"})`);
  lines.push(`Last rising edge: ${fmtTime(data.last_rising)} (Δ ${typeof data.since_last_rising === "number" ? data.since_last_rising.toFixed(2) + "s" : "n/a"})`);
  lines.push(`Last falling edge: ${fmtTime(data.last_falling)} (Δ ${typeof data.since_last_falling === "number" ? data.since_last_falling.toFixed(2) + "s" : "n/a"})`);
  lines.push(`App trigger count: ${data.trigger_count}`);
  lines.push(`Last trigger: ${fmtTime(data.last_trigger)} (Δ ${typeof data.since_last_trigger === "number" ? data.since_last_trigger.toFixed(2) + "s" : "n/a"})`);
  lines.push(`Cooldown seconds: ${data.cooldown_seconds}`);
  lines.push(`Simulator mode: ${data.simulator_mode}`);
  lines.push(`Poll interval: ${data.poll_interval}s`);
  lines.push(`Status note: ${data.status_note || "none"}`);
  lines.push(`Last error: ${data.last_error || "none"}`);
  sensorTestOutput.textContent = lines.join("\n");
}

function startSensorTest() {
  if (sensorTestTimer) return;
  if (sensorTestStatus) sensorTestStatus.textContent = "Polling...";
  if (sensorTestBtn) sensorTestBtn.textContent = "Stop sensor test";
  pollSensorTest();
  sensorTestTimer = setInterval(pollSensorTest, 800);
}

function stopSensorTest(statusText = "Idle") {
  if (sensorTestTimer) {
    clearInterval(sensorTestTimer);
    sensorTestTimer = null;
  }
  if (sensorTestBtn) sensorTestBtn.textContent = "Start sensor test";
  if (sensorTestStatus && statusText !== null) sensorTestStatus.textContent = statusText;
}

if (sensorTestBtn) {
  sensorTestBtn.addEventListener("click", () => {
    if (sensorTestTimer) {
      stopSensorTest();
    } else {
      startSensorTest();
    }
  });
}
