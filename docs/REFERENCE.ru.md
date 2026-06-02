# RPi VPN Gateway — Технический справочник

[← README](../README.md) | [Документация на русском](README.ru.md)

---

## Переменные окружения

Источник — локальный `.env` в этом репозитории. `.env` исключён из git; все переменные, кроме `SSH_HOST`, разворачиваются на RPi в `/etc/splitgate/vpn-gateway.env`.

| Переменная | Значение | Описание |
|----------|-------|-------------|
| `SSH_HOST` | `pi4` | SSH-псевдоним из `~/.ssh/config` — используется `deploy.sh` только на macOS; не разворачивается на RPi |
| `RPI_LAN_IP` | `<pi4-ip>` | LAN IP-адрес RPi |
| `KEENETIC_GW` | `<router-ip>` | Шлюз ISP (ваш роутер) |
| `VPN_SERVER_IP` | *(в `.env.secrets`)* | IP endpoint сервера AmneziaWG — хранится как секрет, не коммитится |
| `VPN_IFACE` | `awg0` | Имя интерфейса VPN-туннеля |
| `LAN_SUBNET` | `10.0.0.0/24` | Локальная LAN-подсеть |
| `RU_SUBNET_URL` | `https://russia.iplist.opencck.org/?format=text&data=cidr4` | Источник списка RU CIDR |
| `CRON_UPDATE_HOUR` | `5` | Час (0–23) для ежедневного cron-обновления подсетей |

## Конфигурация клиента AmneziaWG

`src/configs/amnezia.key.txt` — это локальная клиентская конфигурация для self-hosted сервера AmneziaWG. Она должна содержать клиентские параметры AWG 2.0 из профиля, сгенерированного сервером: `Address`, `Jc`, `Jmin`, `Jmax`, `S1`-`S4`, `H1`-`H4`, опциональные непустые `I1`-`I5`, `PublicKey`, `PresharedKey`, `AllowedIPs`, `Endpoint` и `PersistentKeepalive`.

Оставьте `Table = off` в `[Interface]`. Без этого `awg-quick` может установить собственный маршрут по умолчанию из `AllowedIPs = 0.0.0.0/0`; этому проекту нужно, чтобы `routing.sh` устанавливал маршрут по умолчанию только после того, как уже созданы host route до VPN-сервера и RU bypass-маршруты.

---

## Базовая ОС

Рекомендуемая ОС для Raspberry Pi 4 — **Raspberry Pi OS Lite 64-bit**. Deploy ожидает Debian/Raspberry Pi OS arm64 с NetworkManager, systemd, apt и passwordless sudo для SSH-пользователя.

Проверенная базовая runtime-среда:

- Debian GNU/Linux 13 (trixie), ядро Raspberry Pi `6.18.29+rpt-rpi-v8`
- `eth0` на `<pi4-ip>`; Wi-Fi в той же LAN отключён после перевода DHCP gateway/DNS роутера на RPi
- `fake-hwclock` установлен и включён, чтобы handshakes AmneziaWG переживали перезагрузку на Pi без RTC
- `amneziawg-dkms` собран для активного ядра Raspberry Pi

---

## Группы этапов deploy

`deploy.sh` запускает 28 этапов с вашего Mac через SSH. Полный deploy: `bash src/deploy.sh`.

| Группа | Этапы | Что происходит |
|-------|--------|--------------|
| Preflight | 1–3 | Проверяются необходимые локальные файлы, подключаются `.env` + `.env.secrets`, валидируются ключи, проверяется SSH-подключение |
| Установка AmneziaWG | 4 | `src/scripts/install-awg.sh` передаётся по SSH на RPi; сборка DKMS может занять 10–30 мин |
| Namespace Splitgate | 5 | Создаются `/etc/splitgate/` и `/etc/splitgate/logs/` на RPi |
| Deploy конфигурации | 6–10 | Рендерится и разворачивается `awg0.conf` (mode 600), разворачивается `vpn-gateway.env` (mode 644), выполняются проверки файлов после deploy |
| Deploy маршрутизации | 11–12 | `routing.sh` копируется через SCP в `/etc/splitgate/routing.sh`, разворачивается `vpn-routing.service` |
| Автозапуск | 13–14 | Перезагружается systemd, включаются `awg-quick@awg0` + `vpn-routing.service` при boot, разворачивается `update-vpn-routes` |
| Cron + rollback | 15–17 | Записывается `/etc/cron.d/vpn-routes` (ежедневно в `CRON_UPDATE_HOUR:00`), разворачивается `vpn-rollback.sh`, проверяется установка dnsmasq |
| Логирование | 18–20 | Разворачивается `dnsmasq.conf`, включается и запускается dnsmasq, разворачиваются `vpn-status.sh` и `watch-routes.py` |
| Custom routes + NM | 21–22 | Условно разворачиваются `isp-routes-custom.txt`, `vpn-routes-custom.txt` и `ru-list-exclude.txt`, если они есть; разворачивается NM dispatcher `10-vpn-routes` |
| ASN helper | 23 | `asn-lookup.py` разворачивается в `/etc/splitgate/asn-lookup.py` |
| Финальная активация | 24 | Поднимается туннель `awg0` (если ещё не поднят), запускается `routing.sh` для применения всех маршрутов, iptables LOG rules и exception routes |
| Артефакты Splitgate | 25–27 | Разворачивается dispatcher `splitgate` в `/usr/local/bin/splitgate` (chmod +x); разворачивается `logrotate-vpn-gateway`; разворачивается и включается `splitgate-watch.service` |

---

## Проверка маршрутизации

Выполните на RPi через SSH после deploy. Все команды требуют `sudo` или запуска от root.

### 4 проверки маршрутизации

```bash
# 1. Маршрут по умолчанию должен идти через VPN-туннель
ssh pi4 "ip route show default"
# Ожидаемый вывод содержит: default dev awg0

# 2. Иностранный IP (8.8.8.8) должен маршрутизироваться через VPN
ssh pi4 "ip route get 8.8.8.8"
# Ожидаемый вывод содержит: dev awg0

# 3. Российский IP (77.88.8.8 — Yandex) должен маршрутизироваться через ISP
ssh pi4 "ip route get 77.88.8.8"
# Ожидаемый вывод содержит: via <router-ip>

# 4. IP VPN-сервера должен маршрутизироваться через ISP (предотвращение петли)
ssh pi4 "ip route get <VPN_SERVER_IP>"
# Ожидаемый вывод содержит: via <router-ip>
```

### Проверка iptables LOG rules

```bash
ssh pi4 "sudo iptables-save | grep -c 'LOG --log-prefix'"
# Ожидается: две LOG rules — [VPN] на awg0, [ISP] на eth0
```

### Быстрая проверка vpn-status.sh

После генерации некоторого LAN-трафика:

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh"
```

Пример вывода:

```
TIMESTAMP            SRC-IP             DST-IP             DOMAIN                                   PATH
-------------------- ------------------ ------------------ ---------------------------------------- ----
May 23 11:36:21      <lan-device-ip>  17.248.209.64      apple.com                                VPN
May 23 11:36:22      <lan-device-ip>  77.88.8.8          yandex.ru                                ISP
May 23 11:36:23      <lan-device-ip>  104.64.0.0         store.steampowered.com                   VPN
```

Если в колонке DOMAIN отображаются сырые IP-адреса, установите DNS роутера на `<pi4-ip>` (см. README → Deploy → Router setup).

### Проверки автозапуска

```bash
ssh pi4 "systemctl is-active awg-quick@awg0"       # ожидается: active
ssh pi4 "systemctl is-active vpn-routing.service"  # ожидается: active
ssh pi4 "systemctl is-enabled awg-quick@awg0"      # ожидается: enabled
ssh pi4 "systemctl is-enabled vpn-routing.service" # ожидается: enabled
```

---

## Мониторинг и логи

### vpn-status.sh

`/etc/splitgate/vpn-status.sh` читает journald на предмет iptables LOG-записей `[VPN]`/`[ISP]`, сопоставляет их с
query log dnsmasq, чтобы резолвить IP-адреса назначения в доменные имена (с fallback rDNS через `host`),
и выводит человекочитаемую таблицу соединений. Колонки вывода: `TIMESTAMP SRC-IP DST-IP DOMAIN ORG PATH`.

Колонка `ORG` показывает имя ISP/org для каждого IP назначения через Team Cymru ASN lookup
(формат: `GOOGLE, US (AS15169)` или `-`, если неизвестно). Результаты lookup кэшируются в
`/tmp/vpn-asn-cache.json`; Cymru недоступен → все ячейки ORG показывают `-` (не fatal).

Должен запускаться через `sudo` — читает kernel journal и логи dnsmasq.

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh"
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=vpn --last=100"
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --device=<lan-device-ip> --filter=steam"

# Показать top-20 организаций по количеству соединений, с разделением по VPN/ISP:
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --summary"
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --summary --via=vpn"
```

Все флаги комбинируются: `--last`, `--filter`, `--device`, `--via`, `--summary` можно свободно сочетать.

### watch-routes.py

`/etc/splitgate/watch-routes.py` — это real-time обогатитель iptables-логов. Он запускает `journalctl -f -k` и
парсит строки `[VPN]`/`[ISP]` по мере их появления, резолвя IP-адреса назначения через кэшированные rDNS lookups.
Каждая строка обогащается ` | {org}` через фоновый ASN lookup — новые IP удерживаются в буфере, пока
lookup не завершится (обычно 1–3 с), чтобы каждая напечатанная строка содержала суффикс org. Если lookup
зависает, строка сбрасывается через 6 секунд. Повторяющиеся IP печатаются сразу из кэша. Нажмите Ctrl+C для остановки.

```bash
ssh pi4 "sudo python3 /etc/splitgate/watch-routes.py"
ssh pi4 "sudo python3 /etc/splitgate/watch-routes.py --src <lan-device-ip> --tag VPN"
ssh pi4 "sudo python3 /etc/splitgate/watch-routes.py --no-asn"   # отключить обогащение org
```

### journald

Прямые kernel log queries без `vpn-status.sh`:

```bash
# Последние 50 kernel routing decisions
ssh pi4 "sudo journalctl -k -n 50 --no-pager | grep -E '\[VPN\]|\[ISP\]'"

# События start/stop vpn-routing.service
ssh pi4 "sudo journalctl -u vpn-routing -n 50 --no-pager"

# Лог ежедневного обновления подсетей (Phase 9: file-based)
ssh pi4 "sudo grep '\[vpn-routes\]' /etc/splitgate/logs/install.log | tail -20"

# События восстановления маршрутов NM dispatcher (carrier-change recovery — всё ещё journald)
ssh pi4 "sudo journalctl -t vpn-routes -n 5 --no-pager"
```

### DNS-примечание

`dnsmasq` на RPi (`<pi4-ip>`) должен быть установлен как DNS-сервер в вашем роутере, чтобы разрешение доменов
работало в `vpn-status.sh`. Без этого все запросы идут напрямую к upstream DNS resolver,
минуя query log dnsmasq, и колонка DOMAIN будет показывать сырые IP-адреса.

---

## Пользовательские переопределения маршрутов

Два файла позволяют переопределять автоматически скачанный RU list без его изменения:

| Файл | Назначение | Приоритет |
|------|---------|----------|
| `isp-routes-custom.txt` | Дополнительные CIDR, маршрутизируемые через ISP (bypass VPN) | Добавляются поверх RU list |
| `vpn-routes-custom.txt` | CIDR, принудительно направляемые через VPN, даже если они есть в RU list | Наивысший — переопределяет всё |

Если один и тот же CIDR присутствует в обоих файлах, побеждает `vpn-routes-custom.txt`.

Локальные override-файлы исключены из git и опциональны. Начинайте с файлов `.example` только тогда, когда реальное
исключение маршрутизации найдено в `splitgate status` или `splitgate watch`.

---

### Пользовательские маршруты ISP-bypass

Используйте, когда трафик, который должен выходить через ISP, маршрутизируется через VPN. Типичный случай: игровой сервер,
CDN или стриминговая платформа, IP-диапазон которой отсутствует в RU CIDR list.

**Шаг 1: Определите трафик, выходящий через VPN, который должен использовать ISP**

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=vpn"
```

Найдите домены или IP-адреса, которые должны маршрутизироваться через ISP. Запишите их IP назначения.

**Шаг 2: Преобразуйте IP в CIDR**

```bash
whois <destination-ip>
# Ищите поле "route:" или "CIDR:" — например, 23.55.0.0/16
```

Альтернатива: `https://ipinfo.io/<destination-ip>`

**Шаг 3: Создайте файл**

```bash
cp src/configs/isp-routes-custom.txt.example src/configs/isp-routes-custom.txt
```

Отредактируйте и добавьте CIDR (по одному на строку, только комментарии на всю строку, без inline-комментариев):

```
23.55.0.0/16
95.181.176.0/22
```

Примечание: `src/configs/isp-routes-custom.txt` исключён из git — никогда не коммитьте его.

**Шаг 4: Deploy**

```bash
bash src/deploy.sh
```

Этап 21 копирует файл через SCP в `/etc/splitgate/isp-routes-custom.txt`. Этап 5b в `routing.sh` загружает маршруты при активации.

**Шаг 5: Проверка**

```bash
ssh pi4 "ip route get <your-exception-ip>"
# Ожидаемый вывод содержит: via <router-ip>

ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=isp"
# Ваш exception traffic должен появиться здесь
```

---

### Пользовательские маршруты VPN-force

Используйте, когда CIDR находится в RU list, но вы всё равно хотите, чтобы он выходил через VPN (например, RU CDN nodes, отдающие
foreign content, или конкретные диапазоны, для которых нужен geo-shift).

**Шаг 1: Определите трафик, выходящий через ISP, который должен использовать VPN**

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=isp"
```

Найдите домены или IP-адреса, которые должны маршрутизироваться через VPN. Запишите их IP назначения.

**Шаг 2: Преобразуйте IP в CIDR**

```bash
whois <destination-ip>
# Ищите поле "route:" или "CIDR:" — например, 77.88.0.0/18
```

**Шаг 3: Создайте файл**

```bash
cp src/configs/vpn-routes-custom.txt.example src/configs/vpn-routes-custom.txt
```

Отредактируйте и добавьте CIDR (по одному на строку, только комментарии на всю строку, без inline-комментариев):

```
77.88.0.0/18
5.255.255.0/24
```

Примечание: `src/configs/vpn-routes-custom.txt` исключён из git — никогда не коммитьте его.

**Шаг 4: Deploy**

```bash
bash src/deploy.sh
```

Этап 21b копирует файл через SCP в `/etc/splitgate/vpn-routes-custom.txt`. Этап 5c в `routing.sh` удаляет ISP routes, покрытые каждым VPN-force CIDR, включая более специфичные host routes, и добавляет принудительный CIDR через `awg0`.

**Шаг 5: Проверка**

```bash
ssh pi4 "ip route get <your-vpn-force-ip>"
# Ожидаемый вывод содержит: dev awg0

ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=vpn"
# Ваш forced traffic должен появиться здесь
```

---

## Фильтр исключения RU IP list

Используйте это, когда диапазон CIDR ошибочно включён в RU IP list (например, диапазон Google или Cloudflare,
который iplist помечает как RU), и вы хотите маршрутизировать его через VPN.

В отличие от custom exceptions, которые добавляют ISP-bypass routes поверх скачанного списка, exclusion
filter удаляет CIDR из скачанного списка на источнике — они никогда не появляются в
`/etc/splitgate/white-list.txt` и следуют default route (VPN).

**Как это работает:** когда присутствует `/etc/splitgate/ru-list-exclude.txt`, `update-vpn-routes` добавляет
query parameters `&exclude[cidr4]=CIDR` к `RU_SUBNET_URL` перед вызовом curl. Сервис iplist
фильтрует эти диапазоны на стороне сервера. Если файл отсутствует или пуст, поведение не меняется.

**Шаг 1: Определите CIDR для исключения**

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=isp"
```

Найдите трафик, который должен маршрутизироваться через VPN, но выходит через ISP. Преобразуйте IP назначения в его
network block с помощью `whois` или `ipinfo.io`.

**Шаг 2: Создайте файл исключений**

```bash
cp src/configs/ru-list-exclude.txt.example src/configs/ru-list-exclude.txt
```

Отредактируйте и добавьте CIDR:

```
# Исключить диапазоны Google, ошибочно указанные как RU
142.250.0.0/16
142.251.0.0/16
```

Примечание: `src/configs/ru-list-exclude.txt` исключён из git — никогда не коммитьте его.

**Шаг 3: Deploy**

```bash
bash src/deploy.sh
```

Этап 22c копирует `src/configs/ru-list-exclude.txt` через SCP в `/etc/splitgate/ru-list-exclude.txt`.

**Шаг 4: Запустите пересборку маршрутов**

```bash
ssh pi4 "sudo /etc/splitgate/update-vpn-routes"
ssh pi4 "sudo grep '\[vpn-routes\]' /etc/splitgate/logs/install.log | tail -10"
# ожидается: "Excluding: CIDR1, CIDR2, ..." followed by rebuild log
```

**Шаг 5: Проверка**

```bash
ssh pi4 "ip route get <excluded-cidr-ip>"
# Ожидаемый вывод содержит: dev awg0  (маршрутизируется через VPN, не ISP)
```

---

## Rollback

`/etc/splitgate/vpn-rollback.sh` полностью откатывает VPN gateway одной идемпотентной командой.

```bash
ssh pi4 "sudo /etc/splitgate/vpn-rollback.sh"
```

### Что rollback удаляет

- Останавливает и отключает `vpn-routing.service` и `awg-quick@awg0`
- Останавливает и отключает `dnsmasq`
- Очищает все маршруты на `awg0` и host route VPN-сервера
- Удаляет iptables MASQUERADE rules на `awg0` + `eth0`
- Удаляет iptables FORWARD ACCEPT и LOG rules
- Удаляет `/etc/cron.d/vpn-routes`
- Восстанавливает default route через `KEENETIC_GW` (`<router-ip>`)
- Удаляет `/usr/local/bin/splitgate`
- Полностью удаляет дерево `/etc/splitgate/` — scripts, data files, env

### Что rollback сохраняет

- `/etc/amnezia/amneziawg/awg0.conf` (mode 600) — сохраняется для повторной активации
- Пакеты AmneziaWG — не удаляются
- `/etc/dnsmasq.conf` — остаётся на диске (system file); dnsmasq остановлен

### После rollback

Верните DHCP gateway роутера обратно на `<router-ip>`:

1. `http://<router-ip>` → Home network → Segments → Default → IP parameters
2. Очистите поле Gateway address (или установите `<router-ip>`) → Save

### Повторная активация после rollback

```bash
bash src/deploy.sh
```

---

## Структура файловой системы на RPi

```
/etc/splitgate/
├── routing.sh
├── vpn-rollback.sh
├── vpn-status.sh
├── update-vpn-routes
├── watch-routes.py
├── asn-lookup.py
├── vpn-gateway.env
├── white-list.txt              (генерируется во время runtime)
├── isp-routes-custom.txt       (опционально — пользовательские ISP-bypass routes)
├── vpn-routes-custom.txt       (опционально — пользовательские VPN-force routes; included commented candidate block)
├── ru-list-exclude.txt         (опционально — server-side исключения RU list)
└── logs/
    ├── install.log             (вывод routing.sh и update-vpn-routes)
    ├── watch-YYYY-MM-DD.log    (ежедневный connection log, записываемый splitgate-watch.service)
    └── watch-error.log         (stderr от watch-routes.py --daemon)

/usr/local/bin/splitgate         (dispatcher CLI)
/etc/systemd/system/splitgate-watch.service  (daemon наблюдения за маршрутами)
/etc/logrotate.d/vpn-gateway     (ротирует install.log; удаляет watch-*.log файлы старше 14 дней)
```

Файлы, которые остаются в системных расположениях (требуется consuming daemon):

- `/etc/systemd/system/vpn-routing.service` — systemd требует точный path
- `/etc/cron.d/vpn-routes` — cron daemon требует точный path
- `/etc/dnsmasq.conf` — dnsmasq требует точный path
- `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — NM dispatcher требует точный path
- `/etc/iptables/rules.v4` — iptables-persistent требует точный path
- `/etc/amnezia/amneziawg/awg0.conf` — AmneziaWG требует точный path

---

## Справочник CLI скриптов

### src/deploy.sh

**Synopsis:** `bash src/deploy.sh [--no-run]`

Запускается с вашего Mac. Подключается к RPi через `SSH_HOST=pi4` (из `.env`, резолвится через `~/.ssh/config`). 28 этапов.
Подключает `.env` и `.env.secrets`; валидирует ключи перед любой удалённой операцией.

| Флаг | Описание |
|------|-------------|
| `--no-run` | Развернуть все файлы, но пропустить поднятие `awg-quick` и активацию `routing.sh`. Используйте при тестировании изменений конфигурации без активации маршрутов. |

```bash
bash src/deploy.sh              # полный deploy + поднять awg0 + активировать routing
bash src/deploy.sh --no-run     # только deploy — активировать вручную позже
ssh pi4 "sudo awg-quick up awg0 && sudo /etc/splitgate/routing.sh"
```

---

### routing.sh (разворачивается в /etc/splitgate/routing.sh)

**Synopsis:** `sudo /etc/splitgate/routing.sh [--no-update]`

Очищает и пересобирает split-tunnel routing. Идемпотентен — безопасно запускать повторно в любое время.

При каждом запуске: скачивает RU CIDR с ограниченными curl timeout и fallback к существующему списку → очищает существующие VPN routes → добавляет/заменяет host route VPN-сервера →
добавляет RU CIDR routes через `KEENETIC_GW` → загружает `isp-routes-custom.txt` (Stage 5b, если присутствует) →
загружает `vpn-routes-custom.txt` (Stage 5c, если присутствует — удаляет покрытые ISP routes и переопределяет их через VPN) →
устанавливает/заменяет default route через `awg0` → удаляет duplicate legacy FORWARD/LOG rules → настраивает MASQUERADE и ровно две iptables LOG rules → сохраняет через `iptables-save`.

| Флаг | Описание |
|------|-------------|
| `--no-update` | Пропустить скачивание свежих RU subnets; использовать существующий `/etc/splitgate/white-list.txt`. Используется `update-vpn-routes` после atomic file swap, чтобы избежать double-download. |

```bash
ssh pi4 "sudo /etc/splitgate/routing.sh"             # полный запуск со скачиванием
ssh pi4 "sudo /etc/splitgate/routing.sh --no-update" # пересборка без скачивания
ssh pi4 "ip route show default"     # ожидается: default dev awg0
ssh pi4 "ip route get 8.8.8.8"      # ожидается: dev awg0
ssh pi4 "ip route get 77.88.8.8"    # ожидается: via <router-ip>
```

---

### vpn-status.sh (разворачивается в /etc/splitgate/vpn-status.sh)

**Synopsis:** `sudo /etc/splitgate/vpn-status.sh [--last=N] [--filter=STRING] [--device=IP] [--via=vpn|isp] [--summary]`

Читает journald `[VPN]`/`[ISP]` LOG-записи, сопоставляет их с dnsmasq query log для разрешения доменов,
использует fallback к rDNS (`host`). Колонки вывода: `TIMESTAMP SRC-IP DST-IP DOMAIN ORG PATH`.

Колонка `ORG` показывает `{org} (AS{asn})` через Team Cymru bulk-whois или `-`, если не удалось разрешить.
Результаты кэшируются в `/tmp/vpn-asn-cache.json` (mode 0666, общий для root и non-root).

Должен запускаться через `sudo`.

| Флаг | Описание |
|------|-------------|
| `--last=N` | Показать последние N kernel entries journald (по умолчанию: 50) |
| `--filter=STRING` | Case-insensitive частичное совпадение по колонке DOMAIN |
| `--device=IP` | Фильтр по IP исходного LAN-устройства (поле SRC) |
| `--via=vpn\|isp` | Показать только соединения, маршрутизируемые через VPN или ISP |
| `--summary` | Вывести aggregate table top-20 ORG (ORG \| VPN_COUNT \| ISP_COUNT \| TOTAL) вместо построчной таблицы |

Все флаги свободно комбинируются.

```bash
sudo /etc/splitgate/vpn-status.sh
sudo /etc/splitgate/vpn-status.sh --via=vpn --last=100
sudo /etc/splitgate/vpn-status.sh --device=<lan-device-ip> --filter=steam
sudo /etc/splitgate/vpn-status.sh --summary
sudo /etc/splitgate/vpn-status.sh --summary --device=<lan-device-ip> --via=vpn
sudo /etc/splitgate/vpn-status.sh --last=200   # расширить окно, когда вывод пустой
```

---

### vpn-rollback.sh (разворачивается в /etc/splitgate/vpn-rollback.sh)

**Synopsis:** `sudo /etc/splitgate/vpn-rollback.sh`

Без флагов. Полностью идемпотентен — безопасно запускать повторно.

```bash
ssh pi4 "sudo /etc/splitgate/vpn-rollback.sh"
ssh pi4 "ip route show default"  # ожидается: default via <router-ip>
bash src/deploy.sh               # повторная активация после rollback
```

---

### update-vpn-routes (разворачивается в /etc/splitgate/update-vpn-routes)

**Synopsis:** `sudo /etc/splitgate/update-vpn-routes`

Обычно вызывается cron ежедневно в `CRON_UPDATE_HOUR:00` (по умолчанию 5:00 AM). Можно запускать вручную.

Поведение:
- Собирает `EFFECTIVE_URL` из `RU_SUBNET_URL`; добавляет `&exclude[cidr4]=CIDR` для каждой строки в
  `/etc/splitgate/ru-list-exclude.txt` (если присутствует)
- Логирует domain источника скачивания, фактически исключённые CIDR и количество скачанных маршрутов в `install.log`
- Скачивает список RU subnet и SHA256-сравнивает с существующим `/etc/splitgate/white-list.txt`
- Если hash совпадает: выходит 0 (без rebuild)
- Если hash отличается: атомарно заменяет файл, затем запускает `routing.sh --no-update`
- Если скачивание не удалось: выходит 0 (существующие маршруты остаются нетронутыми); проверяет отсутствующий host
  route VPN-сервера и пересобирает, если он отсутствует (carrier-change recovery)

Логирует в `/etc/splitgate/logs/install.log` (tag `[vpn-routes]`).

```bash
ssh pi4 "sudo /etc/splitgate/update-vpn-routes"
ssh pi4 "sudo grep vpn-routes /etc/splitgate/logs/install.log | tail -10"
ssh pi4 "sudo cat /etc/cron.d/vpn-routes"
```

---

### watch-routes.py (разворачивается в /etc/splitgate/watch-routes.py)

**Synopsis:** `sudo python3 /etc/splitgate/watch-routes.py [--src IP] [--no-dns] [--tag {VPN,ISP,both}] [--no-asn] [--daemon]`

Real-time обогатитель iptables-логов. Запускает `journalctl -f -k --no-pager -o short-iso` и
парсит строки `[VPN]`/`[ISP]` по мере их появления. Резолвит IP-адреса назначения через кэшированные rDNS lookups
(in-memory cache, 2-second timeout). Строки для новых IP назначения буферизуются, пока ASN lookup
не завершится (обычно 1–3 с), чтобы каждая напечатанная строка содержала ` | {org}`. Повторяющиеся IP сразу печатаются
из кэша. Зависшие lookups сбрасываются через 6 секунд.

В режиме `--daemon` поле статуса соединения (✓/✗) добавляется в каждую строку после `[TAG]`:
- `✓` = ESTABLISHED или TIME_WAIT найдено в `/proc/net/nf_conntrack` после 3-секундной задержки
- `✗` = не найдено в conntrack (UDP-соединения всегда показывают `✗`)

Формат вывода в daemon mode:
```
2026-05-29T10:14:00 [ISP] ✓ <lan-device-ip> → yandex.ru TCP:443 | TELETECH, RU
2026-05-29T10:14:05 [ISP] ✗ <lan-device-ip> → github.com TCP:443 | FASTLY, US
```

Файлы логов: `/etc/splitgate/logs/watch-YYYY-MM-DD.log`. Новый dated file открывается в полночь.
Файлы старше 14 дней удаляются postrotate hook `logrotate-vpn-gateway`.

Требует Python 3 (только stdlib — без pip dependencies).

| Флаг | Описание |
|------|-------------|
| `--src IP` | Показать только записи, где SRC совпадает с этим IP-адресом |
| `--no-dns` | Пропустить reverse DNS lookups; показывать сырые IP назначения |
| `--tag VPN\|ISP\|both` | Фильтр по routing tag (по умолчанию: both) |
| `--no-asn` | Отключить фоновое ASN/org enrichment. В daemon mode поле статуса опускается |
| `--daemon` | Писать в dated log file `/etc/splitgate/logs/watch-YYYY-MM-DD.log` вместо stdout. Используется `splitgate-watch.service` |

```bash
sudo python3 /etc/splitgate/watch-routes.py
sudo python3 /etc/splitgate/watch-routes.py --src <lan-device-ip> --tag VPN
sudo python3 /etc/splitgate/watch-routes.py --no-dns
sudo python3 /etc/splitgate/watch-routes.py --tag ISP --no-dns --no-asn
# Запуск как daemon (обычно делается systemd, но можно запустить вручную):
sudo python3 /etc/splitgate/watch-routes.py --daemon
```

**Полезные grep patterns:**
```bash
# ISP routes, которые не смогли established (может потребоваться VPN forcing)
grep "[ISP] ✗" /etc/splitgate/logs/watch-$(date +%F).log

# Весь трафик от конкретного устройства
grep "<lan-device-ip>" /etc/splitgate/logs/watch-$(date +%F).log
```

---

### splitgate-watch.service

**Location:** `/etc/systemd/system/splitgate-watch.service`

Запускает `watch-routes.py --daemon` как постоянный фоновый сервис при boot. Автоматически перезапускается при сбое.

| Команда | Что делает |
|---------|-------------|
| `systemctl status splitgate-watch` | Показать статус сервиса и последние записи лога |
| `systemctl start splitgate-watch` | Запустить daemon |
| `systemctl stop splitgate-watch` | Остановить daemon |
| `systemctl restart splitgate-watch` | Перезапустить (например, после обновления watch-routes.py) |
| `systemctl is-enabled splitgate-watch` | Проверить, включён ли при boot |

```bash
# Проверить статус сервиса
ssh pi4 "systemctl status splitgate-watch"

# Посмотреть connection logs
ssh pi4 "tail -f /etc/splitgate/logs/watch-$(date +%F).log"

# Посмотреть ошибки daemon (startup failures, Python exceptions)
ssh pi4 "cat /etc/splitgate/logs/watch-error.log"

# Проверить autostart
ssh pi4 "systemctl is-enabled splitgate-watch"   # ожидается: enabled
```

Разворачивается `deploy.sh` на Stage 28. `vpn-rollback.sh` останавливает и отключает сервис как часть rollback.

---

### asn-lookup.py (разворачивается в /etc/splitgate/asn-lookup.py)

**Synopsis:** `python3 /etc/splitgate/asn-lookup.py [IPs...]`

Общий helper Team Cymru bulk-whois. Читает IPv4-адреса из stdin (по одному на строку) или из
positional arguments, запрашивает `whois.cymru.com:43` в одной пакетной TCP-сессии и пишет
JSON dict `{"<ip>": {"asn": "<digits>", "org": "<name>"}}` в stdout.

Результаты кэшируются в `/tmp/vpn-asn-cache.json` (mode 0666 — читается и root, и non-root).
Cymru недоступен → возвращает `{}` (или частичные результаты), exit 0. Никогда не fatal при network errors.

```bash
printf "8.8.8.8\n1.1.1.1\n" | python3 /etc/splitgate/asn-lookup.py
python3 /etc/splitgate/asn-lookup.py 8.8.8.8
rm -f /tmp/vpn-asn-cache.json && printf "8.8.8.8\n" | python3 /etc/splitgate/asn-lookup.py
```

---

## Troubleshooting & Known Gotchas

Каждый пункт: **Симптом → Причина → Исправление**.

---

**LAN-устройства вообще не могут выйти в интернет (FORWARD chain DROP)**

Симптом: весь трафик LAN-устройств молча отбрасывается после того, как RPi установлен как gateway. `sudo iptables -L FORWARD -n` показывает default policy `DROP` без ACCEPT rules.

Причина: Docker (если установлен на RPi) устанавливает default policy FORWARD chain в DROP.

Исправление: повторно запустите `sudo /etc/splitgate/routing.sh` — Stage 7c добавляет rules `FORWARD -i eth0 ACCEPT` и `FORWARD RELATED,ESTABLISHED ACCEPT`.

---

**В journald не появляются записи [VPN] или [ISP]**

Симптом: `journalctl -k | grep -E '\[VPN\]|\[ISP\]'` ничего не возвращает даже после того, как LAN-трафик идёт через RPi.

Причина: LOG rules должны быть добавлены в FORWARD chain **до** ACCEPT rules. LOG — non-terminating; ACCEPT — terminating. Если ACCEPT стоит первым, до LOG выполнение никогда не доходит.

Исправление: повторно запустите `sudo /etc/splitgate/routing.sh` — Stage 7b добавляет LOG rules до того, как Stage 7c добавляет ACCEPT rules.

---

**Router web UI / app становится недоступным с LAN-устройств**

Симптом: невозможно открыть `http://<router-ip>` с LAN-устройств после настройки RPi как gateway.

Причина: unconstrained MASQUERADE rule на `eth0` переписывает source IP для всего outbound traffic — включая intra-LAN traffic к `<router-ip>`. Роутер видит все запросы от `<pi4-ip>` и блокирует их.

Исправление: Stage 7 в `routing.sh` использует `! -d LAN_SUBNET` в eth0 MASQUERADE rule. Повторно запустите `sudo /etc/splitgate/routing.sh`, чтобы восстановить правильное rule.

---

**dnsmasq не запускается или конфликтует с существующей конфигурацией**

Симптом: Stage 17/18 в `deploy.sh` завершается ошибкой; `systemctl status dnsmasq` показывает config parse error или port conflict.

Причина: если config dnsmasq развёрнут до установки пакета, `apt-get install dnsmasq` перезаписывает развёрнутую конфигурацию.

Исправление: повторно запустите `bash src/deploy.sh` — Stage 18 всегда устанавливает `dnsmasq` до того, как Stage 19 разворачивает config.

---

**Поднятие туннеля не удаётся или `awg-quick up awg0` возвращает "already exists"**

Симптом: `sudo awg-quick up awg0` завершается ошибкой "RTNETLINK answers: File exists".

Причина: `awg-quick up` не идемпотентен. `deploy.sh` защищается от этого, проверяя, существует ли уже `awg0`, перед запуском `awg-quick up`.

Исправление:
```bash
ssh pi4 "sudo awg-quick down awg0 && sudo awg-quick up awg0"
# или:
ssh pi4 "sudo systemctl restart awg-quick@awg0"
```

---

**vpn-status.sh не показывает записей даже после просмотра веб-страниц**

Симптом: вывод `vpn-status.sh` показывает `(no connections matched — try --last=200 or remove filters)`.

Причина A: dnsmasq не настроен как DNS-сервер в вашем роутере — queries обходят RPi.

Причина B: LAN-устройство не обновило DHCP lease после изменения gateway на роутере.

Исправление: в web UI роутера установите Gateway address в `<pi4-ip>` и DNS server в `<pi4-ip>`. Затем обновите DHCP lease на LAN-устройстве (отключить/подключить Wi-Fi или `ipconfig /renew` на Windows).

---

**Колонка DOMAIN в vpn-status.sh показывает сырые IP вместо hostnames**

Симптом: колонка DOMAIN показывает IP-адреса вместо доменных имён.

Причина: dnsmasq не является DNS-сервером для LAN-устройств — DNS queries обходят query log dnsmasq.

Исправление: установите DNS server роутера в `<pi4-ip>` (см. README → Deploy → Router setup).

---

**Keenetic сообщает об ARP-конфликте для Wi-Fi IP Raspberry Pi**

Симптом: в логах Keenetic появляется предупреждение вида `network conflict: hosts <eth-mac> and <wifi-mac> have the same IPv4 address <wifi-ip>`.

Причина: на RPi одновременно активны `eth0` и `wlan0` в одной LAN. Linux может отвечать на ARP-запросы к Wi-Fi-адресу через Ethernet MAC, поэтому роутер видит один IPv4-адрес за двумя MAC-адресами. После перевода DHCP gateway/DNS роутера на RPi сама Pi также может получить собственный адрес как DHCP gateway, если `eth0` остаётся DHCP-managed.

Исправление: держите gateway-Pi на проводном `eth0`, сделайте `eth0` статическим и отключите Wi-Fi autoconnect в той же LAN.

```bash
ssh pi4 "sudo nmcli connection modify netplan-eth0 ipv4.method manual ipv4.addresses <pi4-ip>/24 ipv4.gateway <router-ip> ipv4.dns <router-ip>"
ssh pi4 "sudo nmcli connection modify netplan-wlan0-nebo connection.autoconnect no"
ssh pi4 "sudo nmcli connection down netplan-wlan0-nebo || true"
ssh pi4 "sudo nmcli connection up netplan-eth0 && sudo /etc/splitgate/routing.sh --no-update"
```

---

**Split-tunnel routes исчезают после перезагрузки роутера (NM carrier-change)**

Симптом: VPN routing ломается после перезагрузки роутера или падения eth0 link. `ip route show | wc -l` падает примерно до 2. `ip route get 8.8.8.8` больше не показывает `dev awg0`.

Причина: когда роутер перезагружается, eth0 link падает. NetworkManager очищает все eth0 routes при событии link-down — включая все ~1360 RU CIDR routes и host route VPN-сервера. Когда eth0 поднимается обратно, NM восстанавливает только local link route. Без host route VPN-сервера (`<VPN_SERVER_IP>/32 via <router-ip>`) трафик к VPN endpoint резолвится через `awg0`, создавая routing loop.

Исправление: Stage 23 в `deploy.sh` разворачивает `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — NM dispatcher script, который восстанавливает routes запуском `routing.sh --no-update`, когда обнаруживается `eth0 up`.

```bash
ssh pi4 "sudo journalctl -t vpn-routes -n 5 --no-pager"
# Ожидается: "eth0 up — restoring VPN split-tunnel routes"
```

Ручное восстановление, если маршруты сейчас отсутствуют:
```bash
ssh pi4 "sudo /etc/splitgate/routing.sh"
```
