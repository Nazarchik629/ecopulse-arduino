"""Читает строки Arduino через USB и добавляет измерения в Supabase."""
import os
import time

import requests
import serial

PORT = os.getenv("ECOPULSE_SERIAL", "COM5")
BAUD = int(os.getenv("ECOPULSE_BAUD", "9600"))
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
DEVICE_TOKEN = os.environ["ECOPULSE_DEVICE_TOKEN"]
ENDPOINT = f"{SUPABASE_URL}/rest/v1/rpc/ingest_reading"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

print(f"Читаю Arduino на {PORT}, скорость {BAUD}. Остановка: Ctrl+C")
last_sent = 0.0
while True:
    try:
        with serial.Serial(PORT, BAUD, timeout=3) as device:
            time.sleep(2)  # При открытии COM Arduino перезапускается.
            print("USB подключён; отправляю показания в облачную базу.")
            while True:
                line = device.readline().decode("utf-8", errors="ignore").strip()
                parts = line.split(",")
                if len(parts) != 2:
                    continue
                try:
                    temperature, humidity = map(float, parts)
                except ValueError:
                    continue
                if not (-40 <= temperature <= 85 and 0 <= humidity <= 100):
                    print(f"Строка вне допустимого диапазона: {line}")
                    continue
                if last_sent and time.monotonic() - last_sent < 60:
                    continue
                try:
                    payload = {"p_token": DEVICE_TOKEN, "p_temperature": temperature, "p_humidity": humidity}
                    result = requests.post(ENDPOINT, headers=HEADERS, json=payload, timeout=15)
                    result.raise_for_status()
                    last_sent = time.monotonic()
                    print(f"Отправлено: {temperature:.1f} °C · влажность {humidity:.0f}%")
                except requests.RequestException as error:
                    print(f"Не удалось отправить данные: {error}")
                    time.sleep(4)
    except serial.SerialException as error:
        print(f"Не могу открыть {PORT}: {error}. Повтор через 5 секунд.")
        time.sleep(5)
    except KeyboardInterrupt:
        print("Передача остановлена.")
        break
