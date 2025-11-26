# binbox

A Raspberry Pi + litter bin that plays rubbish music if you give it rubish.

This repository hosts a small Flask app that powers the Binbox display and a lightweight music sequencer. It supports two modes:

- **Simulator mode (default on Windows):** Press spacebar to mimic the IR obstacle sensor.
- **Pi mode:** Uses the IR sensor on a Raspberry Pi 3 (GPIO code is included but commented out for Windows development).

## Getting started (simulator)

1. Install dependencies:
   ```bash
   pip install flask pygame
   ```
2. Add some `.mp3` files to the `songs/` folder.
3. Run the app:
   ```bash
   python app.py
   ```
4. Open http://localhost:5000 and press **Space** to simulate litter hitting the sensor.

## Hardware notes

- Pi-specific GPIO setup is commented out in `app.py` under the "Raspberry Pi IR obstacle sensor wiring" section. Uncomment and adjust the pin number for your wiring, then set `SIMULATOR_MODE = False`.
- The sensor trigger calls `handle_sensor_event()`, which increments the bin count and advances the playlist.

## Behavior

- Songs in `songs/` (sorted alphabetically) play in sequence. Dropping litter (or pressing space) skips to the next track.
- The UI shows: sensor activity, number of items detected, the current song, and the upcoming track.
- When a track ends naturally, playback advances to the next song automatically; the only way to skip is to trigger the sensor again.
