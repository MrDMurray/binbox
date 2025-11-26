import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Raspberry Pi IR obstacle sensor wiring (commented out for Windows development)
# import RPi.GPIO as GPIO
# SENSOR_PIN = 18  # example BCM pin
# def setup_gpio():
#     GPIO.setmode(GPIO.BCM)
#     GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
#     GPIO.add_event_detect(SENSOR_PIN, GPIO.RISING, callback=handle_sensor_event, bouncetime=200)
#
# def cleanup_gpio():
#     GPIO.cleanup()

try:
    import pygame

    PYGAME_AVAILABLE = True
except Exception:
    PYGAME_AVAILABLE = False


SONGS_DIR = Path(__file__).parent / "songs"
SIMULATOR_MODE = True  # Toggle to False when running on hardware with the sensor enabled

app = Flask(__name__)


class MusicPlayer:
    """Lightweight sequencer that advances on sensor triggers."""

    def __init__(self, songs_dir: Path):
        self.songs_dir = songs_dir
        self.lock = threading.Lock()
        self.songs = self._load_songs()
        self.current_index = -1
        self.current_song = None
        self.next_song = None
        self._mixer_ready = self._init_mixer()
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()
        self._refresh_next()

    def _init_mixer(self) -> bool:
        if not PYGAME_AVAILABLE:
            return False
        try:
            pygame.mixer.init()
            return True
        except Exception:
            return False

    def _load_songs(self):
        return sorted(self.songs_dir.glob("*.mp3"))

    def _refresh_next(self):
        if not self.songs:
            self.next_song = None
            return
        # When nothing has played, the first song is next
        if self.current_index == -1:
            self.next_song = self.songs[0]
        else:
            self.next_song = self.songs[(self.current_index + 1) % len(self.songs)]

    def refresh_library(self):
        with self.lock:
            self.songs = self._load_songs()
            if self.songs:
                self.current_index = min(self.current_index, len(self.songs) - 1)
            else:
                self.current_index = -1
                self.current_song = None
            self._refresh_next()

    def _play_song(self, song_path: Path):
        if not self._mixer_ready:
            return
        try:
            pygame.mixer.music.load(song_path.as_posix())
            pygame.mixer.music.play()
        except Exception:
            # If playback fails, we still update UI state but avoid crashing
            pass

    def trigger_next(self):
        """Advance to the next song in sequence when the sensor fires."""
        with self.lock:
            if not self.songs:
                self.refresh_library()
            if not self.songs:
                return
            if self.current_index == -1:
                self.current_index = 0
            else:
                self.current_index = (self.current_index + 1) % len(self.songs)
            self.current_song = self.songs[self.current_index]
            self._play_song(self.current_song)
            self._refresh_next()

    def _monitor(self):
        """Advance automatically when a track finishes."""
        last_busy = False
        while True:
            time.sleep(0.5)
            if not self._mixer_ready or not self.current_song:
                continue
            busy = pygame.mixer.music.get_busy()
            # Track finished naturally
            if last_busy and not busy:
                with self.lock:
                    if self.songs:
                        self.current_index = (self.current_index + 1) % len(self.songs)
                        self.current_song = self.songs[self.current_index]
                        self._play_song(self.current_song)
                        self._refresh_next()
            last_busy = busy

    def state(self):
        with self.lock:
            return {
                "current_song": self.current_song.name if self.current_song else None,
                "next_song": self.next_song.name if self.next_song else None,
                "songs_available": len(self.songs),
                "mixer_ready": self._mixer_ready,
            }


player = MusicPlayer(SONGS_DIR)
sensor_state = {"last_triggered": None, "count": 0}


def handle_sensor_event():
    sensor_state["last_triggered"] = time.time()
    sensor_state["count"] += 1
    player.trigger_next()


@app.route("/")
def index():
    return render_template(
        "index.html",
        simulator_mode=SIMULATOR_MODE,
    )


@app.route("/api/state")
def api_state():
    triggered_recently = False
    if sensor_state["last_triggered"]:
        triggered_recently = time.time() - sensor_state["last_triggered"] < 2.0
    return jsonify(
        {
            "triggered": triggered_recently,
            "count": sensor_state["count"],
            "simulatorMode": SIMULATOR_MODE,
            **player.state(),
        }
    )


@app.route("/api/trigger", methods=["POST"])
def api_trigger():
    handle_sensor_event()
    return api_state()


if __name__ == "__main__":
    # setup_gpio()  # Enable when running on Raspberry Pi hardware
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
    finally:
        pass
        # cleanup_gpio()

