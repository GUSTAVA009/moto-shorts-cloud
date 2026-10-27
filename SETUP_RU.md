# Прямая загрузка на YouTube — бесплатный облачный проект

**Сделано (27.10.2026):** отдельный GitHub-проект с Actions, оригинальная фоновая музыка, русский голос, видеорендер, Google Cloud Moto Shorts Factory с включённым YouTube Data API v3, создан OAuth Desktop-клиент и защищённый загрузчик с реестром дублей.

**Осталось:** владелец должен один раз согласовать Google OAuth, установить GitHub Secrets и пройти необходимый аудит YouTube API для публичных загрузок. Новых роликов через собственный API пока не публиковали.

## 1. Согласие владельца канала

Открой Google Cloud: https://console.cloud.google.com/auth/overview?project=moto-shorts-factory

- Audience → Test users: проверь фактический адрес в https://myaccount.google.com/ и добавь именно его. В предыдущем тестовом адресе были перепутаны две буквы (BMW/BWM). После добавления правильного адреса удали ошибочный. Не публикуй этот адрес, client JSON или OAuth-токены в GitHub.
- Clients → Moto Shorts Desktop Uploader: скачай JSON Desktop OAuth client; храни его только приватно, никогда не загружай в GitHub.
- Один раз, только для OAuth на доверенном компьютере, открой терминал в папке проекта и выполни:

    python -m pip install google-auth-oauthlib
    python cloud-shorts/oauth_bootstrap.py --google-client-json путь_к_скачанному_client_secret.json

- В браузере Google внимательно выбери владельца канала и предоставь права YouTube upload + readonly. Скрипт сохранит refresh token в домашней папке. Не присылай ключи, JSON и токены в чат.
- Производство и монтаж по-прежнему происходят на GitHub Actions, а не на домашнем компьютере.

## 2. Привязка к GitHub Actions

Secrets: https://github.com/GUSTAVA009/moto-shorts-cloud/settings/secrets/actions

Нужны три Repository secrets (значения нигде не публикуются):
- YOUTUBE_CLIENT_ID — из Desktop client JSON
- YOUTUBE_CLIENT_SECRET — из Desktop client JSON
- YOUTUBE_REFRESH_TOKEN — из приватного файла OAuth bootstrap

Variables: https://github.com/GUSTAVA009/moto-shorts-cloud/settings/variables/actions
- YOUTUBE_EXPECTED_CHANNEL_ID — точный ID разрешённого YouTube-канала
- YOUTUBE_API_AUDITED — false, пока официального успешного YouTube API Compliance Audit нет

Все эти значения относятся только к этому проекту. Старые ключи, пользователи и базы других проектов не изменяются.

## 3. Приватный тест и публикация

GitHub Actions: https://github.com/GUSTAVA009/moto-shorts-cloud/actions

- Выбери YouTube Shorts - Direct API Upload (free, opt-in).
- Запусти Run workflow лишь с ID нового проверенного рендера, разрешив privacy=private.
- Не загружай повторно ролик, который ранее уже был опубликован в Publora.
- Результат проверяй в YouTube Studio. Переводить видео в публичный режим автоматически до завершения API-аудита не следует.

## 4. Реальные лимиты и ограничения

- Официальная документация YouTube API, актуальная на октябрь 2026 года: отдельная стандартная квота до 100 вызовов videos.insert в день на проект. Это не гарантия 100 загрузок в день для самого канала.
- API-проекты, созданные после 28 июля 2020 года без Compliance Audit, по официальным правилам ограничены приватными загрузками.
- Внешнее OAuth-приложение в Testing обычно выдаёт refresh token на 7 дней; для долговременного доступа нужно решить статус In production и необходимые проверки Google.
- Сейчас в рендерере один тестовый творческий сюжет: для выпуска 30–60 оригинальных роликов ежемесячно нужен набор новых лицензированных источников и уникальных сценариев. Механическое дублирование под монетизацию не подходит.
- Нет оплачиваемых API и нет обязательной подписки Publora. Доход и просмотры не гарантированы.

## 5. Дубли и описания

Отдельная ветка GitHub upload-ledger хранит только хеш, ID канала и статус отправки, без OAuth-секретов. Резервирует файл до отправки. Если результат неизвестен, повторную загрузку блокирует до проверки YouTube Studio.

Никаких ссылок в публичных описаниях. Источники остаются отдельно во внутренних полях metadata для подтверждения лицензий.

## Официальные руководства

- https://developers.google.com/youtube/data/determine_quota_cost
- https://developers.google.com/youtube/data/revision_history
- https://developers.google.com/youtube/data/guides/quota_and_compliance_audits
- https://developers.google.com/identity/protocols/oauth2

## 6. Статус после включения двухэтапной защиты — 28 октября 2026

- Двухэтапная аутентификация **включена и распознана YouTube Studio**; предупреждение из раздела монетизации исчезло.
- [Безопасная диагностика прямой загрузки](.github/workflows/youtube-api-readiness.yml) проверена 28.10: GitHub Secrets `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` и `YOUTUBE_REFRESH_TOKEN` **отсутствуют**; `YOUTUBE_EXPECTED_CHANNEL_ID` не соответствует каналу или ещё не создана; флаг прохождения YouTube API-аудита отсутствует.
- Проверка показывает только имена незаполненных настроек — не читает и не выводит токены; **на YouTube ничего не загружает**.
- Пока прямой канал загрузки заблокирован, действуют три публикации, уже запланированные через Publora: **28, 29 и 30 октября в 16:45 UTC**. Их повторно загружать через API **нельзя**.
- Следующий шаг для обхода лимита Publora — один раз завершить согласие владельца Google OAuth, безопасно заполнить три Repository Secrets и `YOUTUBE_EXPECTED_CHANNEL_ID=UCS0QCodPcFBTjMt4ioEWOUw` в GitHub. **Никогда не отправлять секреты в сообщения.** Для публичной загрузки через новый Google API-проект также необходим предусмотренный правилами YouTube аудит.

