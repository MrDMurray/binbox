import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("RPi.GPIO not available; run this on a Raspberry Pi.")
    raise SystemExit(1)

SENSOR_PIN = 4


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    print("Listening on GPIO4 for rising edge (digital IR sensor)... Ctrl+C to exit")
    try:
        while True:
            value = GPIO.input(SENSOR_PIN)
            if value:
                print("Sensor HIGH detected!")
                time.sleep(0.2)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
