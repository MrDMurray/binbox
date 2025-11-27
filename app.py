#v1
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, jsonify, render_template, request

# GPIO placeholders (disabled for Windows dev / simulator mode)
# import RPi.GPIO as GPIO
# SENSOR_PIN = 18
# def setup_gpio():
#     GPIO.setmode(GPIO.BCM)
#     GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
#     GPIO.add_event_detect(SENSOR_PIN, GPIO.RISING, callback=lambda *_: handle_trigger(), bouncetime=200)
# def cleanup_gpio():
#     GPIO.cleanup()

try:
    import pygame

    PYGAME_AVAILABLE = True
except Exception:
    PYGAME_AVAILABLE = False

try:
    import librosa

    LIBROSA_AVAILABLE = True
except Exception:
    LIBROSA_AVAILABLE = False

try:
    import RPi.GPIO as GPIO

    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

BASE_DIR = Path(__file__).parent
SONGS_DIR = BASE_DIR / "songs"
BPM_CACHE_FILE = SONGS_DIR / "bpms.json"
SETTINGS_FILE = BASE_DIR / "settings.json"
SENSOR_PIN = 4


@dataclass
class Settings:
    cooldown_seconds: float = 10.0
    simulator_mode: bool = True
    theme_color: str = "#5ab0f6"
    head_bob_enabled: bool = True
    analysis_enabled: bool = False
    phase: float = 0.0
    gpio_enabled: bool = GPIO_AVAILABLE

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text())
                return cls(**{**cls().__dict__, **data})
            except Exception:
                pass
        return cls()

    def save(self):
        SETTINGS_FILE.write_text(json.dumps(self.__dict__, indent=2))

    def update(self, data: Dict):
        changed = False
        for key in self.__dict__.keys():
            if key in data:
                value = data[key]
                if isinstance(getattr(self, key), bool):
                    value = str(value).lower() in ("1", "true", "yes", "on")
                try:
                    setattr(self, key, type(getattr(self, key))(value))
                    changed = True
                except Exception:
                    continue
        if changed:
            self.save()
        return changed


class Player:
    def __init__(self, songs_dir: Path):
        self.songs_dir = songs_dir
        self.lock = threading.Lock()
        self.songs = self._load_songs()
        self.current_index = -1
        self.current_song: Optional[Path] = None
        self.next_song: Optional[Path] = None
        self.is_playing = False
        self._mixer_ready = self._init_mixer()
        self.tempo_cache: Dict[str, float] = {}
        self.analysis_running = False
        self.analysis_error: Optional[str] = None
        self.analysis_last: Optional[str] = None
        self._load_bpm_cache()
        self._refresh_next()
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()

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

    def refresh_library(self):
        with self.lock:
            self.songs = self._load_songs()
            if self.songs and self.current_index == -1:
                self.current_index = 0
                self.current_song = self.songs[0]
            self._refresh_next()

    def _refresh_next(self):
        if not self.songs:
            self.next_song = None
            return
        if self.current_index == -1:
            self.next_song = self.songs[0]
        else:
            self.next_song = self.songs[(self.current_index + 1) % len(self.songs)]

    def _play(self, song: Path):
        if not self._mixer_ready:
            return
        try:
            pygame.mixer.music.load(song.as_posix())
            pygame.mixer.music.play()
            self.is_playing = True
        except Exception:
            self.is_playing = False

    def trigger(self):
        with self.lock:
            if not self.songs:
                self.refresh_library()
            if not self.songs:
                return False
            self.current_index = 0 if self.current_index == -1 else (self.current_index + 1) % len(self.songs)
            self.current_song = self.songs[self.current_index]
            self._play(self.current_song)
            self._refresh_next()
            return True

    def stop(self):
        with self.lock:
            if self._mixer_ready:
                try:
                    pygame.mixer.music.fadeout(250)
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
                except Exception:
                    pass
            self.is_playing = False
            self.current_song = None
            self._refresh_next()
            return True

    def _monitor(self):
        last_busy = False
        while True:
            time.sleep(0.5)
            if not self._mixer_ready or not self.current_song:
                continue
            busy = pygame.mixer.music.get_busy()
            if last_busy and not busy:
                self.is_playing = False
            last_busy = busy

    def _load_bpm_cache(self):
        if not BPM_CACHE_FILE.exists():
            return
        try:
            data = json.loads(BPM_CACHE_FILE.read_text())
            for name, entry in data.items():
                if isinstance(entry, dict) and "bpm" in entry:
                    bpm_val = float(entry.get("bpm", 0))
                    delay = float(entry.get("kickInDelay", 0))
                else:
                    bpm_val = float(entry)
                    delay = 0.0
                self.tempo_cache[name] = {"bpm": bpm_val, "kickInDelay": delay}
        except Exception:
            pass

    def _save_bpm_cache(self):
        try:
            serialized = {}
            for name, entry in self.tempo_cache.items():
                if isinstance(entry, dict):
                    serialized[name] = {
                        "bpm": float(entry.get("bpm", 0)),
                        "kickInDelay": float(entry.get("kickInDelay", 0)),
                    }
                else:
                    serialized[name] = {"bpm": float(entry), "kickInDelay": 0.0}
            BPM_CACHE_FILE.write_text(json.dumps(serialized, indent=2))
        except Exception:
            pass

    def analyze_all(self):
        if not LIBROSA_AVAILABLE:
            self.analysis_error = "librosa not installed"
            return False
        if self.analysis_running:
            return True
        self.analysis_running = True
        self.analysis_error = None

        def worker():
            try:
                for song in self._load_songs():
                    self.analysis_last = song.name
                    try:
                        y, sr = librosa.load(song.as_posix(), sr=None, mono=True, duration=60)
                        if y is None or len(y) == 0:
                            continue
                        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                        if tempo and tempo > 0:
                            self.tempo_cache[song.name] = {"bpm": float(tempo), "kickInDelay": 0.0}
                    except Exception as exc:
                        self.analysis_error = str(exc)
                self._save_bpm_cache()
            finally:
                self.analysis_running = False

        threading.Thread(target=worker, daemon=True).start()
        return True

    def state(self):
        with self.lock:
            return {
                "current_song": self.current_song.name if self.current_song else None,
                "next_song": self.next_song.name if self.next_song else None,
                "songs_available": len(self.songs),
                "is_playing": self.is_playing,
                "current_bpm": (
                    (self.tempo_cache.get(self.current_song.name) or {}).get("bpm")
                    if self.current_song and isinstance(self.tempo_cache.get(self.current_song.name), dict)
                    else (self.tempo_cache.get(self.current_song.name) if self.current_song else None)
                ),
                "kick_delay": (
                    (self.tempo_cache.get(self.current_song.name) or {}).get("kickInDelay", 0.0)
                    if self.current_song and isinstance(self.tempo_cache.get(self.current_song.name), dict)
                    else 0.0
                ),
                "analysis": {
                    "librosa_available": LIBROSA_AVAILABLE,
                    "running": self.analysis_running,
                    "last": self.analysis_last,
                    "error": self.analysis_error,
                    "cached": len(self.tempo_cache),
                    "total": len(self.songs),
                    "cache_exists": BPM_CACHE_FILE.exists(),
                },
            }


app = Flask(__name__)
settings = Settings.load()
player = Player(SONGS_DIR)
sensor_state = {"count": 0, "last_trigger": None}
gpio_initialized = False
gpio_thread: Optional[threading.Thread] = None
sensor_diag = {
    "last_raw_state": None,
    "last_change": None,
    "last_rising": None,
    "last_falling": None,
    "last_error": None,
    "polling_active": False,
    "poll_interval": 0.02,
}


def handle_trigger(from_sensor: bool = False):
    now = time.time()
    last = sensor_state["last_trigger"]
    cooldown = max(0.0, float(settings.cooldown_seconds or 0))
    if last and cooldown and now - last < cooldown:
        return False
    if from_sensor:
        sensor_diag["last_rising"] = now
        sensor_diag["last_change"] = now
        sensor_diag["last_raw_state"] = True
    sensor_state["count"] += 1
    sensor_state["last_trigger"] = now
    return player.trigger()


def sensor_snapshot():
    now = time.time()
    sample = None
    sample_error = None
    status_note = None
    if not GPIO_AVAILABLE:
        status_note = "RPi.GPIO not installed or not running on a Pi."
    elif not settings.gpio_enabled:
        status_note = "gpio_enabled is false in settings; enable to poll the sensor."
    elif not gpio_initialized:
        status_note = "GPIO available but not initialized; waiting for setup."
    if GPIO_AVAILABLE and gpio_initialized:
        try:
            sample = bool(GPIO.input(SENSOR_PIN))
        except Exception as exc:
            sample_error = str(exc)
    last_trigger = sensor_state["last_trigger"]
    last_change = sensor_diag["last_change"]
    last_rising = sensor_diag["last_rising"]
    last_falling = sensor_diag["last_falling"]
    return {
        "gpio_available": GPIO_AVAILABLE,
        "gpio_enabled_setting": settings.gpio_enabled,
        "gpio_initialized": gpio_initialized,
        "gpio_thread_alive": gpio_thread.is_alive() if gpio_thread else False,
        "ready": GPIO_AVAILABLE and gpio_initialized,
        "polling_active": False,
        "poll_interval": sensor_diag["poll_interval"],
        "sensor_pin": SENSOR_PIN,
        "current_read": sample,
        "last_raw_state": sensor_diag["last_raw_state"],
        "last_change": last_change,
        "since_last_change": (now - last_change) if last_change else None,
        "last_rising": last_rising,
        "since_last_rising": (now - last_rising) if last_rising else None,
        "last_falling": last_falling,
        "since_last_falling": (now - last_falling) if last_falling else None,
        "last_error": sample_error or sensor_diag["last_error"],
        "trigger_count": sensor_state["count"],
        "last_trigger": last_trigger,
        "since_last_trigger": (now - last_trigger) if last_trigger else None,
        "cooldown_seconds": settings.cooldown_seconds,
        "simulator_mode": settings.simulator_mode,
        "status_note": status_note,
    }


def setup_gpio():
    global gpio_initialized, gpio_thread
    if not GPIO_AVAILABLE:
        sensor_diag["last_error"] = "RPi.GPIO not available."
        return False
    if gpio_initialized:
        return True
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(SENSOR_PIN, GPIO.RISING, callback=lambda *_: handle_trigger(from_sensor=True), bouncetime=200)
        sensor_diag["last_raw_state"] = bool(GPIO.input(SENSOR_PIN))
        sensor_diag["last_change"] = time.time()
        sensor_diag["last_error"] = None
        gpio_initialized = True
        return True
    except Exception as exc:
        sensor_diag["last_error"] = str(exc)
        gpio_initialized = False
        return False


def cleanup_gpio():
    global gpio_initialized
    if GPIO_AVAILABLE and gpio_initialized:
        gpio_initialized = False
        try:
            GPIO.cleanup()
        except Exception:
            pass


# Initialize GPIO if requested and available (auto-enabled on a Pi)
if GPIO_AVAILABLE:
    setup_gpio()


@app.route("/")
def index():
    return render_template("index.html", simulator_mode=settings.simulator_mode, theme_color=settings.theme_color)


@app.route("/settings")
def settings_page():
    return render_template("settings.html", settings=settings.__dict__)


@app.route("/api/state")
def api_state():
    if not player.songs:
        player.refresh_library()
    triggered_recently = False
    if sensor_state["last_trigger"]:
        triggered_recently = time.time() - sensor_state["last_trigger"] < 1.5
    return jsonify(
        {
            "triggered": triggered_recently,
            "count": sensor_state["count"],
            "cooldown_seconds": settings.cooldown_seconds,
            "simulatorMode": settings.simulator_mode,
            "head_bob_enabled": settings.head_bob_enabled,
            "theme_color": settings.theme_color,
            "phase": settings.phase,
            "gpio_enabled": settings.gpio_enabled and GPIO_AVAILABLE,
            "gpio_available": GPIO_AVAILABLE,
            **player.state(),
        }
    )


@app.route("/api/sensor_test")
def api_sensor_test():
    if settings.gpio_enabled and GPIO_AVAILABLE and not gpio_initialized:
        setup_gpio()
    return jsonify(sensor_snapshot())


@app.route("/api/trigger", methods=["POST"])
def api_trigger():
    return jsonify({"accepted": handle_trigger(), **player.state()})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    return jsonify({"stopped": player.stop(), **player.state()})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.get_json(force=True, silent=True) or {}
    settings.update(data)
    if "gpio_enabled" in data:
        if settings.gpio_enabled and GPIO_AVAILABLE:
            setup_gpio()
        else:
            cleanup_gpio()
    return jsonify(settings.__dict__)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    if not settings.analysis_enabled:
        return jsonify({"started": False, "message": "Enable analysis in settings", **player.state()})
    started = player.analyze_all()
    return jsonify({"started": started, "message": "started" if started else "failed", **player.state()})


@app.route("/api/log_bop", methods=["POST"])
def api_log_bop():
    print("Head Bop Activated!")
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
