#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "${SCRIPT_DIR}/magicair_mqtt.py" ]]; then
  echo "Ошибка: положите magicair_mqtt.py в ту же папку, где находится install.sh" >&2
  exit 1
fi

read -r -p "Введите логин для MQTT [mqtt_user]: " MQTT_USER
MQTT_USER="${MQTT_USER:-mqtt_user}"

read -r -s -p "Введите пароль для MQTT: " MQTT_PASS
echo ""
if [[ -z "$MQTT_PASS" ]]; then
  echo "Ошибка: пароль не может быть пустым." >&2
  exit 1
fi

echo "=== 1. Настройка хранения логов journald в RAM (лимит 20M) ==="
sudo sed -i 's/^#Storage=.*/Storage=volatile/' /etc/systemd/journald.conf
sudo sed -i 's/^#RuntimeMaxUse=.*/RuntimeMaxUse=20M/' /etc/systemd/journald.conf
sudo systemctl restart systemd-journald

echo "=== 2. Установка зависимостей ==="
sudo apt update && sudo apt install -y python3 python3-paho-mqtt mosquitto mosquitto-clients

echo "=== 3. Настройка Mosquitto в RAM (без записи на диск) ==="
sudo mosquitto_passwd -c -b /etc/mosquitto/passwd "$MQTT_USER" "$MQTT_PASS"
sudo chown root:mosquitto /etc/mosquitto/passwd
sudo chmod 0640 /etc/mosquitto/passwd

sudo tee /etc/mosquitto/mosquitto.conf >/dev/null <<EOF
persistence false
log_dest stdout
log_type error
log_type warning

listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
EOF

sudo systemctl enable --now mosquitto
sudo systemctl restart mosquitto

echo "=== 4. Настройка udev-правила для TION MagicAir ==="
echo 'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2d45", MODE="0666"' | sudo tee /etc/udev/rules.d/99-tion-magicair.rules >/dev/null
sudo udevadm control --reload-rules && sudo udevadm trigger

echo "=== 5. Сохранение пароля в /etc/magicair.env и установка сервиса ==="
sudo install -m 0755 "${SCRIPT_DIR}/magicair_mqtt.py" /usr/local/bin/magicair_mqtt.py

sudo tee /etc/magicair.env >/dev/null <<EOF
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USER=${MQTT_USER}
MQTT_PASS=${MQTT_PASS}
PUBLISH_INTERVAL=10
EOF
sudo chown root:debian /etc/magicair.env
sudo chmod 0640 /etc/magicair.env

sudo tee /etc/systemd/system/magicair-mqtt.service >/dev/null <<EOF
[Unit]
Description=TION MagicAir USB to MQTT Bridge
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=debian
EnvironmentFile=/etc/magicair.env
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 /usr/local/bin/magicair_mqtt.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now magicair-mqtt.service

echo "=== Установка завершена! IP платы: $(hostname -I) ==="
