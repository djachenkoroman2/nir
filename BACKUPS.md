# Резервное копирование

Документ описывает создание, проверку, автоматическую ротацию и восстановление резервных копий приложения «Учёт показателей НИР кафедры». Команды для сервера соответствуют развёртыванию из [DEPLOY.md](DEPLOY.md): приложение находится в `/opt/nir` и работает от пользователя `nir`.

## 1. Что копируется и как создать копию вручную

Команда `backup` сохраняет базу данных и `.env` (секретный ключ Django и пароль базы). Статические файлы, `.venv` и служебные файлы SQLite (`-wal`, `-journal`) не копируются: статика пересобирается через `collectstatic`, окружение — через `uv pip sync`.

Для разработки из корня проекта:

```bash
uv run python manage.py backup
```

На сервере:

```bash
cd /opt/nir
sudo -u nir /opt/nir/.venv/bin/python manage.py backup
```

По умолчанию создаются файлы в `backups/` в корне проекта (на сервере — `/opt/nir/backups/`). Новый каталог создаётся автоматически с правами `700`:

- SQLite: `db-ГГГГ-ММ-ДД.sqlite3` — консистентная копия через SQLite Online Backup API, её можно создавать без остановки сайта;
- PostgreSQL: `nir-ГГГГ-ММ-ДД.dump` — дамп в формате custom через `pg_dump -Fc`;
- в обоих режимах: `env-ГГГГ-ММ-ДД`; копии базы и `.env` получают права `600`.

Путь к исходной базе и параметры подключения берутся из `DATABASES`, то есть учитывается нестандартный `DB_NAME`. Для PostgreSQL на сервере нужен клиент (`sudo apt install -y postgresql-client`); пароль передаётся `pg_dump` через переменную окружения `PGPASSWORD` и не включается в командную строку.

Параметры команды:

```bash
# Другой каталог, например на отдельном диске
sudo -u nir /opt/nir/.venv/bin/python manage.py backup --output-dir /srv/nir-backups

# Срок хранения вместо 30 дней по умолчанию
sudo -u nir /opt/nir/.venv/bin/python manage.py backup --keep 60
```

Пользователь `nir` должен иметь право записи в выбранный каталог. Повторный запуск в тот же день **перезаписывает** одноимённые копии. Метка времени в имени не используется, чтобы имена и ротация оставались простыми. Запись ведётся во временный файл, а итоговый заменяется только после успешного создания и проверки: сбой повторного запуска не портит прежнюю копию, частичный дамп не остаётся. Если `.env` отсутствует, команда завершается ошибкой. При успехе выводятся пути и размеры созданных файлов и число удалённых старых копий; код `0` возвращается только при успехе, поэтому cron и systemd зафиксируют сбой по ненулевому коду.

## 2. Проверка целостности и ротация

После копирования SQLite открывается отдельным соединением и проверяется `PRAGMA integrity_check`. При ошибке проверки или результате, отличном от `ok`, непроверенная копия удаляется, а команда завершается с ошибкой. Для PostgreSQL консистентность обеспечивает `pg_dump`; успешное завершение процесса обязательно.

После создания копии та же команда удаляет файлы базы и `.env` старше срока `--keep` по дате **в имени файла**. По умолчанию хранятся копии за последние 30 дней. Свежие копии, файлы с другими именами и подкаталоги не затрагиваются. `--keep 0` оставляет только сегодняшние копии. Отдельный `find -delete` не нужен.

## 3. Ежедневное копирование через systemd timer (основной вариант)

Timer выбран основным, потому что на сервере уже используется systemd: он пишет вывод в журнал, показывает сбой как failed-задачу и с `Persistent=true` выполняет пропущенное копирование после включения сервера.

Создайте `/etc/systemd/system/nir-backup.service`:

```ini
[Unit]
Description=NIR database and environment backup
After=network.target

[Service]
Type=oneshot
User=nir
Group=nir
WorkingDirectory=/opt/nir
UMask=0077
ExecStart=/opt/nir/.venv/bin/python /opt/nir/manage.py backup --keep 30
```

Создайте `/etc/systemd/system/nir-backup.timer`:

```ini
[Unit]
Description=Daily NIR backup at 03:00

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Включите расписание и проверьте его:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nir-backup.timer
systemctl list-timers nir-backup.timer

# Ручной запуск и проверка результата
sudo systemctl start nir-backup.service
sudo systemctl status nir-backup.service
sudo journalctl -u nir-backup.service -n 50 --no-pager
```

Лог находится в journald; успешный запуск содержит пути, размеры копий и итог ротации. При ненулевом коде команды сервис получает статус `failed`.

## 4. Альтернатива: cron

Если systemd timer не используется, создайте каталог для лога и добавьте строку через `sudo -u nir crontab -e`:

```bash
sudo -u nir mkdir -p /opt/nir/logs
```

```cron
0 3 * * * cd /opt/nir && umask 077 && /opt/nir/.venv/bin/python manage.py backup --keep 30 >> /opt/nir/logs/backup.log 2>&1
```

Это тот же ежедневный запуск в 03:00 с ротацией, но вывод пишется в `/opt/nir/logs/backup.log`. Не включайте cron и timer одновременно.

## 5. Восстановление SQLite

Восстановление выполняется только вручную. В командах ниже используется путь по умолчанию `/opt/nir/db.sqlite3`; если в `.env` задан `DB_NAME`, вместо него укажите этот путь.

1. Остановите приложение:

   ```bash
   sudo systemctl stop nir
   ```

2. Скопируйте выбранную копию на место рабочей базы (замените дату):

   ```bash
   sudo -u nir cp /opt/nir/backups/db-2026-11-02.sqlite3 /opt/nir/db.sqlite3
   ```

3. Если восстанавливается также `.env`, скопируйте `env-ГГГГ-ММ-ДД` в `/opt/nir/.env` и установите права `600` до запуска приложения.
4. Запустите приложение и проверьте вход в систему и основные разделы:

   ```bash
   sudo systemctl start nir
   sudo systemctl status nir
   ```

## 6. Восстановление PostgreSQL

Пример соответствует настройкам из [DEPLOY.md, раздел 4](DEPLOY.md#4-переход-на-postgresql) (`nir`, пользователь `nir`, `localhost`). При других значениях используйте параметры из `.env`.

1. Остановите приложение:

   ```bash
   sudo systemctl stop nir
   ```

2. Восстановите выбранный дамп. Опция `-W` запросит пароль пользователя базы, чтобы не сохранять его в истории команд:

   ```bash
   sudo -u nir pg_restore -W --host=localhost --port=5432 --username=nir \
       --clean --if-exists --dbname=nir /opt/nir/backups/nir-2026-11-02.dump
   ```

3. При необходимости восстановите `.env`, как описано выше, затем запустите приложение, проверьте вход и основные разделы:

   ```bash
   sudo systemctl start nir
   sudo systemctl status nir
   ```

## 7. Проверка восстановления и хранение копий

Периодически проверяйте не только создание, но и **восстановление на отдельной тестовой копии**: SQLite — в отдельный файл и тестовое окружение, PostgreSQL — в отдельную тестовую базу. Не восстанавливайте дамп поверх рабочей базы для проверки и не запускайте `seed_demo` на рабочих данных. Для PostgreSQL тестовую базу можно создать так:

```bash
sudo -u postgres createdb -O nir nir_restore_test
sudo -u nir pg_restore -W --host=localhost --username=nir \
    --dbname=nir_restore_test /opt/nir/backups/nir-2026-11-02.dump
# Проверьте данные через тестовое окружение, затем удалите тестовую базу:
sudo -u postgres dropdb nir_restore_test
```

Копии базы и особенно `.env` содержат секретные данные. Ограничьте доступ к каталогу копий (`sudo -u nir chmod 700 /opt/nir/backups`), не коммитьте его в git (`backups/` добавлен в `.gitignore`) и храните копии также за пределами сервера на защищённом носителе. Каталог, заданный через `--output-dir` вне `/opt/nir`, не входит в репозиторий проекта; права доступа к нему настройте так же.
