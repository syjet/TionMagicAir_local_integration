# TION MagicAir USB to MQTT Bridge (BeagleBone Black)

Локальный мост для считывания данных со станции **TION MagicAir BS310** и любого количества беспроводных датчиков **TION CO2+** по USB (HID) и публикации их в **Home Assistant** через MQTT Auto Discovery.

Дополнительно скрипт отправляет диагностическую телеметрию самой платы **BeagleBone Black** (свободная/занятая RAM, Load Average, аптайм).

## Возможности
- Автоматический поиск станции TION MagicAir по USB VID `2d45` (`/dev/hidraw*`).
- **Мульти-поддержка датчиков CO2+:** автоматическое обнаружение и регистрация в Home Assistant каждого привязанного датчика по его уникальному MAC-адресу (`tion_co2plus_<mac>`).
- Передача показаний CO₂, температуры и влажности базовой станции `BS310` и датчиков `CO2+` каждые 10 секунд (`expire_after: 60`).
- Диагностика хоста BeagleBone Black в Home Assistant каждые 60 секунд (`expire_after: 180`).
- Хранение учетных данных MQTT вне кода (`/etc/magicair.env`).
- Защита флеш-памяти (eMMC / microSD) от износа: логи `journald` переведены в оперативную память (`Storage=volatile`, лимит `20M`).

## Структура топиков MQTT
- `tion/tion_magicair_bs310/state` — показания базовой станции (`temp`, `hum`, `co2`).
- `tion/tion_co2plus_<mac>/state` — показания каждого датчика CO2+ без двоеточий в MAC (`temp`, `hum`, `co2`).
- `tion/bbb_magicair_host/state` — диагностика платы (`ram_avail`, `ram_used_pct`, `load_1m`, `uptime_h`).

## Установка

1. Клонируйте репозиторий на BeagleBone Black:
   ```bash
   git clone <URL_вашего_репозитория>
   cd <папка_репозитория>
   ```

2. Запустите установочный скрипт:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

3. Укажите актуальный логин и пароль от MQTT-брокера в `/etc/magicair.env` и перезапустите службу:
   ```bash
   sudo nano /etc/magicair.env
   sudo systemctl restart magicair-mqtt.service
   ```
