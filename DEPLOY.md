# Детальный план развертывания CalTG бота

## Часть 1: Получение Telegram Bot Token

### Шаг 1: Создание бота в Telegram

1. Откройте Telegram и найдите пользователя **@BotFather** (официальный бот для создания ботов)
2. Отправьте команду `/newbot`
3. Введите имя бота (например: `CalTG Bot`)
4. Введите уникальный username бота (должен заканчиваться на `bot`, например: `caltg_calorie_bot`)
5. **BotFather** выдаст вам HTTP API token — сохраните его

```
Пример токена: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### Шаг 2: Настройка бота (опционально)

- Отправьте `/setdescription` — установите описание бота
- Отправьте `/setabouttext` — установите "о себе"
- Отправьте `/setuserpic` — установите фото профиля

---

## Часть 2: Получение API ключей

### OpenRouter API (для ИИ-распознавания еды)

1. Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai)
2. После регистрации перейдите в раздел **Keys**
3. Создайте новый ключ: **Create Key**
4. Скопируйте ключ (он будет показан один раз)
5. Выберите модель в настройках (по умолчанию: `gpt-4.2-mini`)

### USDA FoodData Central API (для данных о питании)

1. Зарегистрируйтесь на [fdc.nal.usda.gov](https://fdc.nal.usda.gov/api-guide.html)
2. После регистрации перейдите в **API Quick Guide**
3. Нажмите **Request API Key**
4. Заполните форму: Name, Email, Organization (можно указать Personal)
5. Ключ придет на email

---

## Часть 3: Подготовка проекта к развертыванию

### Шаг 1: Клонируйте репозиторий

```bash
git clone <ваш-репозиторий>
cd caltg
```

### Шаг 2: Создайте файл `.env`

```env
# Telegram
TELEGRAM_BOT_TOKEN=ваш_токен_от_botfather

# Database (будет создана на Render)
DATABASE_URL=postgresql+asyncpg://caltg_user:пароль@хост:5432/caltg

# OpenRouter
OPENROUTER_API_KEY=ваш_ключ_openrouter
OPENROUTER_MODEL=gpt-4.2-mini

# USDA
USDA_API_KEY=ваш_ключ_usda
```

### Шаг 3: Зафиксируйте изменения

```bash
git add .
git commit -m "Add .env configuration"
git push origin main
```

---

## Часть 4: Развертывание на Render

### Шаг 1: Регистрация на Render

1. Перейдите на [render.com](https://render.com)
2. Зарегистрируйтесь через GitHub

### Шаг 2: Подключение репозитория

1. Нажмите **New** → **Web Service**
2. Выберите ваш репозиторий с проектом
3. Настройте параметры:

| Параметр | Значение                                                                     |
| ---------------- | ------------------------------------------------------------------------------------ |
| Name             | `caltg`                                                                            |
| Environment      | `Python`                                                                           |
| Build Command    | `pip install -r requirements.txt`                                                  |
| Start Command    | `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT` |

### Шаг 3: Настройка переменных окружения

В секции **Environment Variables** добавьте:

```
TELEGRAM_BOT_TOKEN=ваш_токен
OPENROUTER_API_KEY=ваш_ключ
OPENROUTER_MODEL=gpt-4.2-mini
USDA_API_KEY=ваш_ключ
DATABASE_URL= (будет предоставлен после создания БД)
```

### Шаг 4: Создание базы данных

1. Нажмите **New** → **PostgreSQL**
2. Настройте:
   - Name: `поддрживает ли мо`
   - Database Name: `caltg`
   - User: `caltg_user`
3. После создания скопируйте **Internal Database URL**
4. Добавьте его в переменные окружения веб-сервиса

### Шаг 5: Деплой

1. Нажмите **Create Web Service**
2. Дождитесь сборки (5-10 минут)
3. После успешного деплоя проверьте `https://caltg.onrender.com/health`

---

## Часть 5: Настройка Webhook для Telegram

После развертывания, установите webhook:

```bash
curl -X POST "https://api.telegram.org/bot<ВАШ_TOKEN>/setWebhook" \
     -d "url=https://ваше-приложение.onrender.com/webhook"
```

Замените:

- `<ВАШ_TOKEN>` — ваш токен от BotFather
- `ваше-приложение.onrender.com` — URL вашего приложения на Render

---

## Часть 6: Проверка работоспособности

1. Откройте Telegram и найдите вашего бота
2. Отправьте `/start`
3. Бот должен ответить приветственным сообщением

---

## Структура файла [`render.yaml`](render.yaml)

```yaml
services:
  - type: web
    name: caltg
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
    envVars:
      - key: PYTHONPATH
        value: .
      - key: PORT
        value: 10000
databases:
  - name: caltg-db
    databaseName: caltg
    user: caltg_user
```

---

## Troubleshooting

| Проблема                   | Решение                                                                    |
| ---------------------------------- | --------------------------------------------------------------------------------- |
| Бот не отвечает       | Проверьте webhook:`https://api.telegram.org/bot<TOKEN>/getWebhookInfo` |
| Ошибка БД                  | Проверьте `DATABASE_URL` в переменных окружения    |
| Ошибка 500 на /health      | Проверьте все API ключи                                          |
| Бот не запускается | Проверьте логи в панели Render                                |
