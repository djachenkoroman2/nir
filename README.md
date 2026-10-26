# Учёт показателей НИР кафедры

Веб-приложение на Django для учёта показателей научно-исследовательской работы (НИР) кафедры вуза.

Сейчас это первый этап: каркас приложения с многопользовательским входом. Предметные разделы (публикации, гранты, конференции и т.п.) будут добавлены позже.

## Возможности

- вход в систему по логину и паролю;
- приветственная страница для вошедшего пользователя;
- управление пользователями через админку Django (`/admin/`).

Регистрации через сайт нет: пользователей заводит администратор.

## Быстрый старт (разработка)

Нужен [uv](https://docs.astral.sh/uv/). Python 3.12+ он установит сам.

```bash
uv venv --python 3.12
uv pip sync requirements.txt

cp .env.example .env              # затем задайте DJANGO_SECRET_KEY и DJANGO_DEBUG=True
uv run python manage.py migrate
uv run python manage.py create_admin     # создаёт admin / 123
uv run python manage.py runserver
```

Откройте http://127.0.0.1:8000/ и войдите как `admin` / `123`.

> **Внимание:** `admin` / `123` подходят только для разработки. Перед вводом в эксплуатацию смените пароль (см. [DEPLOY.md](DEPLOY.md)).

Запуск тестов:

```bash
uv run python manage.py test
```

Развёртывание на сервере описано в [DEPLOY.md](DEPLOY.md).

## Структура проекта

```
.
├── apps/
│   ├── accounts/                 # пользователи: модель User (AbstractUser), админка
│   │   └── management/commands/
│   │       └── create_admin.py   # создание/сброс суперпользователя
│   └── core/                     # главная страница, общие представления
├── config/                       # настройки проекта (settings, urls, wsgi)
├── templates/
│   ├── base.html                 # базовый шаблон с шапкой
│   ├── registration/login.html   # страница входа
│   └── core/home.html            # приветствие
├── static/vendor/bootstrap/      # Bootstrap 5 (локальная копия)
├── .env.example                  # пример переменных окружения
├── requirements.txt
├── DEPLOY.md                     # инструкция по развёртыванию
└── manage.py
```

Новые предметные модули добавляйте как отдельные приложения в `apps/`:

```bash
mkdir apps/<имя> && uv run python manage.py startapp <имя> apps/<имя>
```

Затем в `apps/<имя>/apps.py` укажите `name = 'apps.<имя>'` и добавьте `'apps.<имя>'` в `INSTALLED_APPS`.
