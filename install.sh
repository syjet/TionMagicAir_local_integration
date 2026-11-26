#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_USER="${SUDO_USER:-debian}"
TARGET_HOME="$(eval echo "~${TARGET_USER}")"

echo "=== 1. Установка зависимостей ==="
sudo apt-get update -qq
sudo apt-get install -y python3-paho-mqtt mosquitto mosquitto-clients

echo "=== 2. Копирование скрипта ==="
sudo cp "${SCRIPT_DIR}/magicair_mqtt.py" "${TARGET_HOME}/magicair_mqtt.py"
sudo chown "${TARGET_USER}:${TARGET_USER}" "${TARGET_HOME}/magicair_mqtt.py"
sudo chmod +x "${TARGET_HOME}/magicair_mqtt.py"

echo "=== 3. Настройка /etc/magicair.env ==="
if [ ! -f /etc/magicair.env ]; then
    sudo cp "${SCRIPT_DIR}/magicair.env.example" /etc/magicair.env
    sudo chown "root:${TARGET_USER}" /etc/magicair.env
    sudo chmod 640 /etc/magicair.env
    echo "Создан /etc/magicair.env из шаблона. Не забудьте прописать в нем актуальный пароль!"
else
    echo "Файл /etc/magicair.env уже существует, оставлен без изменений."
fi

echo "=== 4. Настройка udev для TION MagicAir (VID 2d45) ==="
echo 'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2d45", MODE="0666"' | sudo tee /etc/udev/rules.d/99-magicair.rules > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "=== 5. Оптимизация journald (логи только в RAM до 20 МБ) ==="
sudo mkdir -p /etc/systemd/journald.conf.d
cat << 'EOF' | sudo tee /etc/systemd/journald.conf.d/volatile.conf > /dev/null
[Journal]
Storage=volatile
RuntimeMaxUse=20M
EOF
sudo systemctl restart systemd-journald

echo "=== 6. Настройка systemd-сервиса ==="
cat << EOF | sudo tee /etc/systemd/system/magicair-mqtt.service > /dev/null
[Unit]
Description=TION MagicAir USB to MQTT Bridge
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=${TARGET_USER}
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/etc/magicair.env
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 ${TARGET_HOME}/magicair_mqtt.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable magicair-mqtt.service
sudo systemctl restart magicair-mqtt.service

echo "=== Готово! Статус службы: ==="
sudo systemctl status magicair-mqtt.service --no-pager
