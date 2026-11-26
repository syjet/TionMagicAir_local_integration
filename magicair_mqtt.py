#!/usr/bin/env python3
import codecs
import glob
import json
import os
import re
import time
import paho.mqtt.client as mqtt

# --- НАСТРОЙКИ MQTT (из переменных окружения) ---
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

PUBLISH_INTERVAL = 10      # Интервал отправки датчиков TION (сек)
SYS_MONITOR_INTERVAL = 60  # Интервал отправки телеметрии хоста (сек)

RE_BS = re.compile(
    r"LogicDevicesSensorsBS:,\s*obt\s+(-?\d+(?:\.\d+)?),\s*extt\s+(-?\d+(?:\.\d+)?),\s*exth\s+(\d+(?:\.\d+)?)\s*%,\s*co2\s+(\d+)"
)
RE_CO2PLUS = re.compile(
    r"dev\s+CO2\+_1001:[^:\r\n]*?([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}):\s+val:\s+(-?\d+)\s+(\d+)\s+(\d+)"
)

discovered_co2plus = set()

def find_magicair():
    for uevent_path in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
        with open(uevent_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().lower()
        if "0003:00002d45:" in content:
            hidraw_name = os.path.basename(os.path.dirname(os.path.dirname(uevent_path)))
            return f"/dev/{hidraw_name}"
    return None

def send_hid_command(fd, cmd):
    payload = cmd.encode("ascii") + b"\n"
    report = b"\x00" + payload.ljust(64, b"\x00")
    os.write(fd, report)

def get_host_stats():
    stats = {}
    mem_total = 0
    mem_avail = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1])
        if mem_total > 0:
            stats["ram_avail"] = round(mem_avail / 1024.0, 1)
            stats["ram_used_pct"] = round((mem_total - mem_avail) / mem_total * 100.0, 1)
    except Exception:
        pass

    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            stats["load_1m"] = float(f.read().split()[0])
    except Exception:
        pass

    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            stats["uptime_h"] = round(float(f.read().split()[0]) / 3600.0, 1)
    except Exception:
        pass

    return stats

def publish_device_discovery(client, dev):
    dev_id = dev["dev_id"]
    for key, name, unit, dev_class, state_class, entity_cat in dev["sensors"]:
        topic = f"homeassistant/sensor/{dev_id}_{key}/config"
        payload = {
            "name": name,
            "state_topic": dev["state_topic"],
            "value_template": f"{{{{ value_json.{key} }}}}",
            "expire_after": dev["expire_after"],
            "unique_id": f"{dev_id}_{key}",
            "device": {
                "identifiers": [dev_id],
                "name": dev["dev_name"],
                "manufacturer": dev["manufacturer"],
                "model": dev["model"],
            },
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if dev_class:
            payload["device_class"] = dev_class
        if state_class:
            payload["state_class"] = state_class
        if entity_cat:
            payload["entity_category"] = entity_cat

        client.publish(topic, json.dumps(payload, ensure_ascii=False), retain=True)

def publish_static_discovery(client):
    static_devices = [
        {
            "dev_id": "tion_magicair_bs310",
            "dev_name": "TION MagicAir BS310",
            "manufacturer": "TION",
            "model": "MagicAir BS310",
            "state_topic": "tion/tion_magicair_bs310/state",
            "expire_after": 60,
            "sensors": [
                ("co2", "CO2", "ppm", "carbon_dioxide", "measurement", None),
                ("temp", "Температура", "°C", "temperature", "measurement", None),
                ("hum", "Влажность", "%", "humidity", "measurement", None),
            ],
        },
        {
            "dev_id": "bbb_magicair_host",
            "dev_name": "BeagleBone Black (MQTT Host)",
            "manufacturer": "BeagleBoard",
            "model": "BeagleBone Black",
            "state_topic": "tion/bbb_magicair_host/state",
            "expire_after": 180,
            "sensors": [
                ("ram_avail", "Свободная RAM", "MB", "data_size", "measurement", "diagnostic"),
                ("ram_used_pct", "Использование RAM", "%", None, "measurement", "diagnostic"),
                ("load_1m", "Нагрузка CPU (1m)", None, None, "measurement", "diagnostic"),
                ("uptime_h", "Аптайм", "h", "duration", "total_increasing", "diagnostic"),
            ],
        },
    ]
    for dev in static_devices:
        publish_device_discovery(client, dev)

def ensure_co2plus_discovery(client, mac_clean, mac_raw):
    if mac_clean in discovered_co2plus:
        return
    dev_id = f"tion_co2plus_{mac_clean}"
    short_mac = mac_raw[-5:].upper()
    dev = {
        "dev_id": dev_id,
        "dev_name": f"TION CO2+ ({short_mac})",
        "manufacturer": "TION",
        "model": "CO2+ (1001)",
        "state_topic": f"tion/{dev_id}/state",
        "expire_after": 60,
        "sensors": [
            ("co2", "CO2", "ppm", "carbon_dioxide", "measurement", None),
            ("temp", "Температура", "°C", "temperature", "measurement", None),
            ("hum", "Влажность", "%", "humidity", "measurement", None),
        ],
    }
    publish_device_discovery(client, dev)
    discovered_co2plus.add(mac_clean)
    print(f"Зарегистрирован датчик CO2+: {mac_raw} -> {dev_id}", flush=True)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        discovered_co2plus.clear()
        publish_static_discovery(client)

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
    last_sent = {"bs310": 0.0, "host": 0.0}

    try:
        send_hid_command(fd, "logenable")
        while True:
            now = time.monotonic()

            if now - last_sent["host"] >= SYS_MONITOR_INTERVAL:
                stats = get_host_stats()
                if stats:
                    client.publish("tion/bbb_magicair_host/state", json.dumps(stats))
                last_sent["host"] = now

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

                # 1. Базовая станция BS310
                m_bs = RE_BS.search(line)
                if m_bs and (now - last_sent["bs310"] >= PUBLISH_INTERVAL):
                    co2_bs = int(m_bs.group(4))
                    if co2_bs > 0:
                        state = {
                            "temp": float(m_bs.group(2)),
                            "hum": float(m_bs.group(3)),
                            "co2": co2_bs,
                        }
                        client.publish("tion/tion_magicair_bs310/state", json.dumps(state))
                        last_sent["bs310"] = now

                # 2. Внешние датчики CO2+ (все вхождения в строке по MAC-адресу)
                for m_co2 in RE_CO2PLUS.finditer(line):
                    co2_val = int(m_co2.group(4))
                    if co2_val <= 0:
                        continue

                    mac_raw = m_co2.group(1).lower()
                    mac_clean = mac_raw.replace(":", "")
                    sensor_key = f"co2plus_{mac_clean}"

                    if now - last_sent.get(sensor_key, 0.0) >= PUBLISH_INTERVAL:
                        ensure_co2plus_discovery(client, mac_clean, mac_raw)
                        state = {
                            "temp": round(int(m_co2.group(2)) / 10.0, 1),
                            "hum": round(int(m_co2.group(3)) / 10.0, 1),
                            "co2": co2_val,
                        }
                        client.publish(f"tion/tion_co2plus_{mac_clean}/state", json.dumps(state))
                        last_sent[sensor_key] = now

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
