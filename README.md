# Binbox

Cute robot UI for a Raspberry Pi bin that plays music when the sensor fires. Simulator mode lets you trigger with the spacebar on your PC.

## Quick start (simulator / PC)

1. Install deps (prefer a venv):
   ```bash
   pip install -r requirements.txt
   ```
2. Drop `.mp3` files into `songs/`.
3. Run:
   ```bash
   python app.py
   ```
4. Open http://localhost:5000 and press Space to trigger playback. Settings at http://localhost:5000/settings.

## Beat prep workflow

- On your PC with `librosa` installed, enable “Allow in-app beat analysis” in settings and click **Analyze songs**. This writes BPMs to `songs/bpms.json`.
- Copy `songs/` (including `bpms.json`) to the Pi. On the Pi, leave analysis disabled; the UI will show BPMs from the cache without running librosa.
- The BPM cache entries now look like `{ "YourSong.mp3": { "bpm": 120.0, "kickInDelay": 0.0 } }`. You can manually set `kickInDelay` (seconds) to delay head bobbing if a track has a long intro; defaults to 0.

## Notes

- The app plays one track per trigger; the queue is ordered alphabetically by filename.
- Robot head bops while music plays (if enabled in settings).
- GPIO sensor code is stubbed; enable and wire on the Pi as needed. In simulator mode, Space triggers `/api/trigger`.
