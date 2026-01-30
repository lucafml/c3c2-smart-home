import time
from typing import Dict, Any


class _BME680Unavailable(Exception):
    pass


def _load_driver():
    try:
        # Treiber erst bei Bedarf importieren (läuft sonst auf Nicht-RPi nicht)
        import board  # type: ignore
        import adafruit_bme680  # type: ignore
        return board, adafruit_bme680
    except Exception as e:
        raise _BME680Unavailable(str(e))


def read_bme680(sea_level_pressure_hpa: float = 1013.25) -> Dict[str, Any]:
    try:
        board, adafruit_bme680 = _load_driver()
    except _BME680Unavailable as e:
        return {
            "available": False,
            "error": f"BME680 unavailable: {e}",
        }

    try:
        # Sensor per I2C ansprechen und Werte lesen
        i2c = board.I2C()
        sensor = adafruit_bme680.Adafruit_BME680_I2C(i2c)
        sensor.sea_level_pressure = sea_level_pressure_hpa
        temperature_c = float(sensor.temperature)
        temperature_f = (temperature_c * 9 / 5) + 32
        humidity = float(sensor.humidity)
        pressure_hpa = float(sensor.pressure)
        gas_ohms = float(sensor.gas)

        return {
            "available": True,
            "temperature_c": round(temperature_c, 2),
            "temperature_f": round(temperature_f, 2),
            "humidity": round(humidity, 2),
            "pressure_hpa": round(pressure_hpa, 2),
            "gas_ohms": round(gas_ohms, 0),
            "timestamp": int(time.time()),
        }
    except Exception as e:
        return {
            "available": False,
            "error": f"BME680 read failed: {e}",
        }
