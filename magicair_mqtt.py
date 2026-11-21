#!/usr/bin/env python3
import codecs
import glob
import json
import os
import re
import time
import paho.mqtt.client as mqtt

# --- НАСТРОЙКИ ИЗ ОКРУЖЕНИЯ ---
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL", "10"))

RE_BS = re.compile(
    r"LogicDevicesSensorsBS:,\s*obt\s+(-?\d+(?:\.\d+)?),\s*extt\s+(-?\d+(?:\.\d+)?),\s*exth\s+(\d+(?:\.\d+)?)\s*%,\s*co2\s+(\d+)"
)
RE_CO2PLUS = re.compile(
    r"dev\s+CO2\+_1001:.*?([0-9A-Fa-f:]{17}):\s+val:\s+(-?\d+)\s+(\d+)\s+(\d+)"
)


def find_magicair():
    for uevent_path in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
        with open(uevent_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().lower()
        if "0003:00002d45:" in content:
            hidraw_name = uevent_path.split("/")
            return f"/dev/{hidraw_name}"
    return None


def send_hid_command(fd, cmd):
    payload = cmd.encode("ascii") + b"\n"
    report = b"\x00" + payload.ljust(64, b"\x00")
    os.write(fd, report)


def publish_discovery(client):
    devices = [
        {
            "dev_id": "tion_magicair_bs310",
            "dev_name": "TION MagicAir BS310",
            "model": "MagicAir BS310",
            "sensors": [
                ("co2", "CO2", "ppm", "carbon_dioxide"),
                ("temp", "Температура", "°C", "temperature"),
                ("hum", "Влажность", "%", "humidity"),
            ],
        },
        {
            "dev_id": "tion_magicair_co2plus",
            "dev_name": "TION Датчик CO2+",
            "model": "CO2+ (1001)",
            "sensors": [
                ("co2", "CO2", "ppm", "carbon_dioxide"),
                ("temp", "Температура", "°C", "temperature"),
                ("hum", "Влажность", "%", "humidity"),
            ],
        },
    ]

    for dev in devices:
        dev_id = dev["dev_id"]
        for key, name, unit, dev_class in dev["sensors"]:
            topic = f"homeassistant/sensor/{dev_id}_{key}/config"
            payload = {
                "name": name,
                "state_topic": f"tion/{dev_id}/state",
                "value_template": f"{{{{ value_json.{key} }}}}",
                "unit_of_measurement": unit,
                "device_class": dev_class,
                "state_class": "measurement",
                "unique_id": f"{dev_id}_{key}",
                "device": {
                    "identifiers": [dev_id],
                    "name": dev["dev_name"],
                    "manufacturer": "TION",
                    "model": dev["model"],
                },
            }
            client.publish(topic, json.dumps(payload, ensure_ascii=False), retain=True)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        publish_discovery(client)


def main():
    device_path = find_magicair()
    if not device_path:
        raise RuntimeError("Станция TION MagicAir не найдена в /dev/hidraw*")

    client = mqtt.Client(client_id="magicair_bbb_bridge")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    fd = os.open(device_path, os.O_RDWR)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buffer = ""
    last_sent = {"bs310": 0.0, "co2plus": 0.0}

    try:
        send_hid_command(fd, "logenable")
        while True:
            raw = os.read(fd, 64)
            if not raw:
                break
            cleaned = raw.replace(b"\x00", b"").replace(b"\xff", b"")
            buffer += decoder.decode(cleaned)

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                now = time.monotonic()

                m_bs = RE_BS.search(line)
                if m_bs and (now - last_sent["bs310"] >= PUBLISH_INTERVAL):
                    state = {
                        "temp": float(m_bs.group(2)),
                        "hum": float(m_bs.group(3)),
                        "co2": int(m_bs.group(4)),
                    }
                    client.publish("tion/tion_magicair_bs310/state", json.dumps(state))
                    last_sent["bs310"] = now
                    continue

                m_co2 = RE_CO2PLUS.search(line)
                if m_co2 and (now - last_sent["co2plus"] >= PUBLISH_INTERVAL):
                    state = {
                        "temp": round(int(m_co2.group(2)) / 10.0, 1),
                        "hum": round(int(m_co2.group(3)) / 10.0, 1),
                        "co2": int(m_co2.group(4)),
                    }
                    client.publish("tion/tion_magicair_co2plus/state", json.dumps(state))
                    last_sent["co2plus"] = now
    finally:
        os.close(fd)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print(f"Ошибка: {e}. Перезапуск через 5 сек...", flush=True)
            time.sleep(5)
