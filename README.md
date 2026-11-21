# Интеграция TION MagicAir (BS310 / BS410) и CO₂+ в Home Assistant по USB

Локальный мост на базе **BeagleBone Black (Debian 11)** для передачи данных со станции TION MagicAir и беспроводного датчика CO₂+ в Home Assistant по протоколу MQTT (с поддержкой **MQTT Discovery**) без использования облака TION.

Все компоненты настроены на работу **строго в оперативной памяти (RAM)** без записи логов и баз на встроенную флеш-память (eMMC / SD).

## Состав проекта
* `README.md` — данная инструкция.
* `magicair_mqtt.py` — фоновый Python-мост для чтения `/dev/hidraw*` и отправки данных в MQTT.
* `install.sh` — скрипт автоматической установки и настройки системы.

---

## Быстрая установка на чистую плату

1. Положите файлы `install.sh` и `magicair_mqtt.py` в одну папку (например, `/home/debian/`).
2. Подключите станцию MagicAir **data-кабелем** в полноразмерный разъем **USB Type-A** платы BeagleBone Black.
3. Запустите установщик (он запросит имя пользователя и пароль для создаваемого MQTT-брокера):
   ```bash
   chmod +x install.sh magicair_mqtt.py
   ./install.sh
   ```

---

## Подключение в Home Assistant

1. Закрепите IP за MAC-адресом платы в DHCP сервере вашего роутера.
2. В Home Assistant откройте **Настройки → Устройства и службы → Добавить интеграцию → MQTT**.
3. Введите:
   * **Брокер:** IP-адрес BeagleBone Black *(не используйте доменное имя `.local` если HA в Docker, так как внутри контейнера нет mDNS)*
   * **Порт:** `1883`
   * **Имя пользователя и пароль:** те, что вы указали при запуске `install.sh`
4. После подключения в разделе MQTT автоматически появятся **2 устройства** (`TION MagicAir BS310` и `TION Датчик CO2+`) с 6 датчиками.

---

## Полезные команды обслуживания

* **Статус сервиса:** `sudo systemctl status magicair-mqtt.service`
* **Логи сервиса (в реальном времени):** `journalctl -u magicair-mqtt.service -f`
* **Просмотр потока сообщений MQTT с отметками времени:**
  ```bash
  sudo bash -c 'source /etc/magicair.env && mosquitto_sub -h 127.0.0.1 -u "\(MQTT_USER" -P "\)MQTT_PASS" -t "tion/#" -F "%I | %t | %p"'
  ```
* **Смена пароля MQTT:** отредактируйте `/etc/magicair.env`, обновите пароль в Mosquitto (`sudo mosquitto_passwd -c /etc/mosquitto/passwd <user>`) и перезапустите службы (`sudo systemctl restart mosquitto magicair-mqtt`).
