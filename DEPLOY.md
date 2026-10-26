# Развёртывание приложения «Учёт показателей НИР кафедры»

Инструкция описывает развёртывание без контейнеров: для разработки на локальной машине и для эксплуатации на сервере Ubuntu (Gunicorn + systemd + Nginx).

Python и зависимости ставятся через [uv](https://docs.astral.sh/uv/). uv сам скачивает нужную версию Python, поэтому системные пакеты `python3-venv` и `python3-pip` не нужны.

## 1. Системные требования

- ОС: Linux (проверено на Ubuntu 22.04/24.04); для разработки подходят также macOS и Windows;
- uv 0.5 или новее;
- Python 3.12 или новее (uv установит его сам, если в системе нет подходящего);
- для сервера: Nginx, при необходимости PostgreSQL 14+;
- Git, curl.

### Установка uv

Для одного пользователя (разработка):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Для всех пользователей сервера (в `/usr/local/bin`):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
```

Проверка: `uv --version`.

## 2. Развёртывание для разработки

```bash
git clone <адрес-репозитория> nir
cd nir

uv venv --python 3.12               # создаёт .venv; при необходимости скачивает Python
uv pip sync requirements.txt        # ставит ровно те версии, что в requirements.txt

cp .env.example .env
```

Активировать окружение не обязательно: `uv run` сам находит `.venv` в каталоге проекта.

В `.env` задайте как минимум:

```ini
DJANGO_SECRET_KEY=<случайная строка>
DJANGO_DEBUG=True
```

Сгенерировать ключ:

```bash
uv run python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Создайте базу данных и администратора и запустите сервер:

```bash
uv run python manage.py migrate
uv run python manage.py create_admin      # логин admin, пароль 123
uv run python manage.py runserver
```

Приложение доступно по адресу http://127.0.0.1:8000/, админка — http://127.0.0.1:8000/admin/.

### Доступ с других компьютеров по IP

По умолчанию `runserver` слушает только `127.0.0.1`, и приложение открывается лишь на той же машине. Как открыть его для локальной сети, описано в разделе 7.1.

### Изменение зависимостей

Добавьте пакет в окружение и зафиксируйте точные версии в `requirements.txt`:

```bash
uv pip install <пакет>
uv pip freeze > requirements.txt
```

### Команда `create_admin`

Стандартная `createsuperuser` не принимает простой пароль `123` из-за проверки сложности паролей, поэтому в проекте есть своя команда:

```bash
uv run python manage.py create_admin                                   # admin / 123
uv run python manage.py create_admin --username admin --password 'Новый_сложный_пароль'
```

Если пользователь уже существует, команда сбрасывает его пароль и выдаёт права суперпользователя. Так её можно использовать и для восстановления доступа.

> **Важно.** Учётные данные `admin` / `123` предназначены только для разработки. Перед вводом в эксплуатацию обязательно смените пароль (раздел 3.7).

## 3. Развёртывание на сервере Ubuntu

Ниже предполагается:
- приложение лежит в `/opt/nir`;
- работает от системного пользователя `nir`;
- uv установлен для всех пользователей (`/usr/local/bin/uv`, см. раздел 1);
- сайт открывается по имени `nir.example.ru` (замените на своё).

### 3.1. Пользователь, код и окружение

```bash
sudo apt update
sudo apt install -y git nginx curl

sudo adduser --system --group --home /opt/nir nir
sudo -u nir git clone <адрес-репозитория> /opt/nir
cd /opt/nir
sudo -u nir uv venv --python 3.12
sudo -u nir uv pip sync requirements.txt
```

Если Python скачивает uv, он сохраняет его в домашнем каталоге пользователя `nir` (`/opt/nir/.local/share/uv/python`). Не удаляйте этот каталог: на него ссылается `.venv`.

### 3.2. Настройки окружения

```bash
sudo -u nir cp .env.example .env
sudo chmod 600 .env
sudo -u nir nano .env
```

Значения для продакшена:

```ini
DJANGO_SECRET_KEY=<новый случайный ключ, не тот, что при разработке>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=nir.example.ru
DJANGO_CSRF_TRUSTED_ORIGINS=http://nir.example.ru
DJANGO_SECURE_COOKIES=False
DB_ENGINE=sqlite
```

После настройки HTTPS (раздел 3.6) замените `http://` на `https://` в `DJANGO_CSRF_TRUSTED_ORIGINS` и установите `DJANGO_SECURE_COOKIES=True`.

### 3.3. База данных, статика, администратор

```bash
cd /opt/nir
sudo -u nir uv run python manage.py migrate
sudo -u nir uv run python manage.py collectstatic --noinput
sudo -u nir uv run python manage.py create_admin --password '<сложный пароль>'
sudo -u nir uv run python manage.py check --deploy
```

`collectstatic` собирает статические файлы в каталог `/opt/nir/staticfiles`, откуда их отдаёт Nginx.

### 3.4. Gunicorn как systemd-сервис

Сервис запускает Gunicorn напрямую из `.venv`, так что для работы приложения uv не нужен. Он нужен только для установки и обновления.

Создайте файл `/etc/systemd/system/nir.service`:

```ini
[Unit]
Description=NIR Django application (gunicorn)
After=network.target

[Service]
User=nir
Group=www-data
WorkingDirectory=/opt/nir
RuntimeDirectory=nir
ExecStart=/opt/nir/.venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/nir/gunicorn.sock \
    --umask 007 \
    config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nir
sudo systemctl status nir
```

Журнал: `sudo journalctl -u nir -f`.

### 3.5. Nginx как обратный прокси

Создайте файл `/etc/nginx/sites-available/nir`:

```nginx
server {
    listen 80;
    server_name nir.example.ru;

    client_max_body_size 20M;

    location /static/ {
        alias /opt/nir/staticfiles/;
    }

    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://unix:/run/nir/gunicorn.sock;
    }
}
```

Включите сайт:

```bash
sudo ln -s /etc/nginx/sites-available/nir /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Nginx должен иметь право читать `/opt/nir/staticfiles`: `sudo chmod o+rx /opt/nir /opt/nir/staticfiles`.

### 3.5.1. Доступ по IP-адресу без доменного имени

Если у сервера нет доменного имени, сайт можно открыть по IP-адресу. Все шаги описаны в разделе 7.2.

### 3.6. HTTPS (необязательно, но рекомендуется)

Если у сервера есть публичное доменное имя, можно получить бесплатный сертификат Let's Encrypt:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d nir.example.ru
```

Если в вузе есть свой сертификат, укажите его в конфигурации Nginx (`listen 443 ssl; ssl_certificate ...; ssl_certificate_key ...;`).

Затем в `.env` укажите `DJANGO_CSRF_TRUSTED_ORIGINS=https://nir.example.ru` и `DJANGO_SECURE_COOKIES=True` и перезапустите приложение: `sudo systemctl restart nir`.

### 3.7. Чек-лист безопасности

- [ ] `DJANGO_DEBUG=False`;
- [ ] уникальный `DJANGO_SECRET_KEY`, файл `.env` с правами `600`;
- [ ] в `DJANGO_ALLOWED_HOSTS` указаны только реальные имена сервера;
- [ ] **пароль `admin` изменён** — через админку (`/admin/` → Пользователи → admin → «Изменить пароль») или командой
      `sudo -u nir uv run python manage.py changepassword admin`;
- [ ] настроен HTTPS, `DJANGO_SECURE_COOKIES=True`;
- [ ] проверен вывод `manage.py check --deploy`. Без HTTPS команда показывает предупреждения W004, W008, W012 и W016, это ожидаемо. W012 и W016 исчезнут после установки `DJANGO_SECURE_COOKIES=True`. W004 и W008 (HSTS и редирект на HTTPS) лучше закрыть на стороне Nginx.

## 4. Переход на PostgreSQL

1. Установите PostgreSQL и создайте базу:

   ```bash
   sudo apt install -y postgresql
   sudo -u postgres psql -c "CREATE USER nir WITH PASSWORD '<пароль>';"
   sudo -u postgres psql -c "CREATE DATABASE nir OWNER nir;"
   ```

2. Добавьте драйвер в зависимости (лучше на машине разработчика, с коммитом изменённого `requirements.txt`):

   ```bash
   uv pip install "psycopg[binary]"
   uv pip freeze > requirements.txt
   ```

   и установите его на сервере:

   ```bash
   sudo -u nir uv pip sync requirements.txt
   ```

3. Если в SQLite уже есть данные, выгрузите их (пока ещё работает старая база):

   ```bash
   sudo -u nir uv run python manage.py dumpdata --natural-foreign --natural-primary \
       -e contenttypes -e auth.permission -e sessions --indent 2 > /tmp/nir-data.json
   ```

4. Поменяйте `.env`:

   ```ini
   DB_ENGINE=postgresql
   DB_NAME=nir
   DB_USER=nir
   DB_PASSWORD=<пароль>
   DB_HOST=localhost
   DB_PORT=5432
   ```

5. Создайте таблицы, загрузите данные и перезапустите приложение:

   ```bash
   sudo -u nir uv run python manage.py migrate
   sudo -u nir uv run python manage.py loaddata /tmp/nir-data.json   # если выгружали
   sudo systemctl restart nir
   ```

Код менять не нужно, база выбирается переменной `DB_ENGINE`.

## 5. Обновление приложения

```bash
cd /opt/nir
sudo -u nir git pull
sudo -u nir uv pip sync requirements.txt
sudo -u nir uv run python manage.py migrate
sudo -u nir uv run python manage.py collectstatic --noinput
sudo systemctl restart nir
```

`uv pip sync` приводит окружение точно к `requirements.txt`: недостающие пакеты ставит, лишние удаляет.

Обновление самого uv: `sudo uv self update` (если uv ставился скриптом установки).

Перед обновлением сделайте резервную копию базы (раздел 6).

## 6. Резервное копирование

### SQLite

```bash
sudo -u nir sqlite3 /opt/nir/db.sqlite3 ".backup '/opt/nir/backups/db-$(date +%F).sqlite3'"
```

(Нужен пакет `sqlite3`: `sudo apt install -y sqlite3`. Каталог `/opt/nir/backups` создайте заранее.)

Восстановление: остановите сервис (`sudo systemctl stop nir`), скопируйте файл копии на место `db.sqlite3` и запустите сервис.

### PostgreSQL

```bash
sudo -u postgres pg_dump -Fc nir > /opt/nir/backups/nir-$(date +%F).dump
```

Восстановление:

```bash
sudo systemctl stop nir
sudo -u postgres pg_restore --clean -d nir /opt/nir/backups/nir-<дата>.dump
sudo systemctl start nir
```

### Автоматизация

Пример ежедневной копии в 03:00 (для SQLite), строка для `sudo crontab -u nir -e`:

```
0 3 * * * sqlite3 /opt/nir/db.sqlite3 ".backup '/opt/nir/backups/db-$(date +\%F).sqlite3'" && find /opt/nir/backups -mtime +30 -delete
```

Храните копии также за пределами сервера.

Кроме базы, сохраняйте файл `.env`: в нём секретный ключ и пароли.

## 7. Доступ по IP-адресу

Этот раздел нужен, когда приложение должно открываться с других компьютеров по IP-адресу, например `http://172.17.13.88:8000/`, а не только на той машине, где оно запущено.

Для доступа по IP обязательно настроить две вещи и открыть порт в файрволе:

| Что | Зачем | Ошибка, если не настроить |
|---|---|---|
| Сервер слушает внешний интерфейс (`0.0.0.0`) | иначе подключения из сети не принимаются | браузер не может подключиться (таймаут или «соединение отклонено») |
| IP в `DJANGO_ALLOWED_HOSTS` | Django отвечает только на разрешённые имена и адреса | `400 Bad Request`, в журнале `DisallowedHost: Invalid HTTP_HOST header` |

Переменная `DJANGO_CSRF_TRUSTED_ORIGINS` при обычной работе по HTTP не обязательна: Django сам сверяет адрес страницы с адресом сервера. Она нужна, если адрес в браузере отличается от того, что видит Django. Например, когда прокси не передаёт заголовок `Host` или меняет схему (`https` → `http`). Тогда кнопка «Войти» даёт `403 Forbidden (CSRF)`. Прописать её заранее не вредно.

### 7.1. Режим разработки (`runserver`)

**Шаг 1. Узнайте IP-адрес машины.**

```bash
ip -4 addr          # Linux
ipconfig            # Windows
```

Нужен адрес сетевого интерфейса локальной сети (например, `ens160` или `eth0`), а не `127.0.0.1`, не `docker0` и не адреса VPN-туннелей (`tun0`). Например: `inet 172.17.13.88/23` → адрес `172.17.13.88`.

**Шаг 2. Пропишите адрес в `.env`.**

```ini
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,172.17.13.88
DJANGO_CSRF_TRUSTED_ORIGINS=http://172.17.13.88:8000
```

Обратите внимание на формат, это частая причина ошибок:

- в `DJANGO_ALLOWED_HOSTS` указывается **только адрес, без порта и без `http://`**. Неправильно: `172.17.13.88:8000`, `http://172.17.13.88`;
- в `DJANGO_CSRF_TRUSTED_ORIGINS` (необязательна, см. выше), наоборот, указывается **полный адрес со схемой и портом**, ровно так, как он набирается в браузере: `http://172.17.13.88:8000`;
- несколько значений разделяются запятыми без пробелов;
- проверьте цифры адреса: опечатка (`171.` вместо `172.`) не вызывает ошибок при запуске, но адрес не будет работать.

**Шаг 3. Запустите сервер на всех интерфейсах.**

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

`0.0.0.0` означает «принимать подключения на любом адресе машины». Команда `runserver` без адреса слушает только `127.0.0.1`.

Если сервер уже был запущен, **остановите его (Ctrl+C) и запустите снова**: изменения в `.env` читаются только при старте. Если сервер был приостановлен (Ctrl+Z), сначала верните его командой `fg`, затем остановите Ctrl+C. Иначе он продолжит занимать порт, и новый запуск завершится ошибкой `That port is already in use`.

**Шаг 4. Откройте порт в файрволе** (если он включён):

```bash
sudo ufw status            # проверить, включён ли файрвол
sudo ufw allow 8000/tcp
```

В Windows разрешите входящие подключения для Python, когда система об этом спросит, или добавьте правило для порта 8000 в «Брандмауэре Защитника Windows».

**Шаг 5. Проверьте.**

На этой же машине:

```bash
curl -I http://172.17.13.88:8000/login/
```

Ожидается `HTTP/1.1 200 OK`. Затем откройте `http://172.17.13.88:8000/` в браузере на другом компьютере той же сети и войдите в систему.

> `runserver` предназначен только для разработки и демонстрации. Для постоянной работы используйте Gunicorn и Nginx (раздел 3 и 7.2).

### 7.2. Сервер (Gunicorn + Nginx)

Здесь Gunicorn слушает только локальный сокет, а подключения из сети принимает Nginx на порту 80. Поэтому порт в адресе не указывается: сайт открывается как `http://<IP-сервера>/`.

**Шаг 1. Узнайте IP-адрес сервера:** `ip -4 addr` (см. шаг 1 раздела 7.1).

**Шаг 2. Пропишите адрес в `/opt/nir/.env`.**

```ini
DJANGO_ALLOWED_HOSTS=172.17.13.88
DJANGO_CSRF_TRUSTED_ORIGINS=http://172.17.13.88
DJANGO_SECURE_COOKIES=False
```

`DJANGO_CSRF_TRUSTED_ORIGINS` здесь страховочная: она нужна, если прокси искажает адрес (см. начало раздела 7). Порт 80 стандартный, поэтому в ней он не пишется. Если Nginx слушает нестандартный порт (например, `listen 8080;`), укажите его: `http://172.17.13.88:8080`. Чтобы сайт открывался и по IP, и по доменному имени, перечислите оба через запятую в обеих переменных.

**Шаг 3. Укажите адрес в конфигурации Nginx** `/etc/nginx/sites-available/nir`:

```nginx
server_name 172.17.13.88;
```

Вариант `server_name _;` принимает запросы на любой адрес сервера. Он удобен, если на сервере нет других сайтов.

**Шаг 4. Примените изменения.**

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl restart nir          # чтобы приложение перечитало .env
```

**Шаг 5. Откройте порт 80 в файрволе:**

```bash
sudo ufw allow 'Nginx HTTP'
```

Если сервер находится в сети вуза, порт может закрывать и внешний сетевой файрвол. В этом случае обратитесь к администратору сети.

**Шаг 6. Проверьте:**

```bash
curl -I http://172.17.13.88/login/
```

Ожидается `HTTP/1.1 200 OK`.

**HTTPS при доступе по IP.** Let's Encrypt не выдаёт сертификаты на IP-адреса. HTTPS в этом случае настраивается только с сертификатом вуза (раздел 3.6). Пока HTTPS нет, оставьте `DJANGO_SECURE_COOKIES=False`, иначе вход в систему перестанет работать: браузер не будет отправлять cookies по HTTP.

### 7.3. Если не работает

| Симптом | Причина и решение |
|---|---|
| `400 Bad Request`, в журнале `Invalid HTTP_HOST header: '172.17.13.88:8000'` | Адреса нет в `DJANGO_ALLOWED_HOSTS`, либо он записан с портом. Укажите адрес без порта и перезапустите сервер. |
| Адрес в `.env` правильный, но ошибка 400 остаётся | Сервер не перезапускали после правки `.env`, либо работает другой, старый экземпляр сервера. Остановите все запущенные `runserver` (`pgrep -af runserver`) и запустите заново. |
| `403 Forbidden (CSRF verification failed)` при нажатии «Войти» | Адрес в браузере не совпадает с тем, что видит Django. Проверьте, что Nginx передаёт `proxy_set_header Host $host;` и `X-Forwarded-Proto` (раздел 3.5). Добавьте адрес из браузера в `DJANGO_CSRF_TRUSTED_ORIGINS`, сверив схему (`http`/`https`), цифры адреса и порт. Также помогает обновить страницу входа перед повторной попыткой: устаревшая форма тоже даёт эту ошибку. |
| Браузер не может подключиться, а `curl` на самом сервере работает | Закрыт порт в файрволе (`sudo ufw status`), либо `runserver` запущен без `0.0.0.0`. |
| `curl` на самом сервере не подключается | Сервер не запущен. Проверьте `sudo systemctl status nir` и `sudo systemctl status nginx`, журналы: `sudo journalctl -u nir -n 50`, `/var/log/nginx/error.log`. |
| `That port is already in use` | Порт занят другим процессом, часто приостановленным (Ctrl+Z) `runserver`. Найдите его (`ss -ltnp \| grep :8000`), верните `fg` и остановите Ctrl+C, или запустите на другом порту (`0.0.0.0:8001`). |
| Вход не работает, ошибок нет, после ввода пароля снова открывается страница входа | `DJANGO_SECURE_COOKIES=True` при работе по HTTP. Установите `False` или настройте HTTPS. |

О переменных окружения в терминале VS Code. VS Code может подставлять в терминал копию значений из `.env`, сделанную при открытии терминала. В проекте значения из файла `.env` всегда важнее таких переменных (`load_dotenv(..., override=True)` в `config/settings.py`). Поэтому после правки `.env` достаточно перезапустить сервер, терминал перезапускать не нужно.
