# GUSTAVA — переход с Publora на Buffer Free + Cloudflare R2

Статус на 28 октября 2026: **Buffer Free и YouTube GUSTAVA Enduro подключены, электронная почта подтверждена; Buffer MCP подключён к Codex и авторизован OAuth; Cloudflare R2 и GitHub Secrets не подключены, публикация выключена**.
Не нужен домашний компьютер, VPN-сервер или прямой YouTube OAuth.

## Что настроено
- GitHub Actions производит оригинальные Shorts и хранит итоговые MP4 в артефактах.
- Ручной workflow `buffer-delivery.yml` берёт существующий MP4 с пройденной речевой проверкой.
- `buffer_autopublish.py` использует ту же директорию `publication-receipts/` в `render-ledger`, что Publora. Поэтому выпуски, уже отправленные любым сервисом, не загружаются повторно.
- После прохождения проверок MP4 отправляется в Cloudflare R2 по ключу SHA-256 и проверяется постоянный публичный HTTPS-адрес; затем Buffer ставит видео в очередь публикации.
- Повтор после неизвестного результата запрещён. Очередь Buffer не означает, что видео уже опубликовано на YouTube.
- Речевая проверка для нового маршрута требует ≥95% распознанного текста **и в исходной озвучке, и в готовом MP4**. Не гарантирует художественное качество тембра или интонации.

## Однократно подключить аккаунты
1. **Выполнено:** Buffer Free зарегистрирован, Google-канал GUSTAVA Enduro подключён и визуально проверен. YouTube ID `UCS0QCodPcFBTjMt4ioEWOUw`, Buffer channel ID `6ae238b32f1f5ed648ff9011` (уже закреплён в исходном коде).
2. **Ожидается обязательное действие владельца:** подтвердить адрес электронной почты из письма Buffer. Раздел https://publish.buffer.com/settings/api показывает `Get started by verifying your email`, поэтому ключ пока создать нельзя. После перехода по ссылке из письма обновить страницу и создать один личный API-ключ. Не вставлять его в чат, публичный репозиторий или консольный лог; сохранить в GitHub Actions Secret `BUFFER_API_KEY`. Ранее созданная авторизация YouTube останется.
2a. После появления ключа запустить безопасную **read-only** проверку через workflow `buffer-readiness.yml`, она проверит YouTube ID и занятость очереди без публикаций.
3. Cloudflare R2: создать bucket и узкий R2 S3-токен с доступом только к bucket; включить постоянный публичный HTTPS-адрес (лучше custom domain). Учесть, что любой обладатель ссылки сможет открыть исходный MP4.
4. В GitHub Actions Secrets добавить `BUFFER_API_KEY`, `R2_ENDPOINT` (формат `https://<account-id>.r2.cloudflarestorage.com`), `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
5. В GitHub Actions Variables добавить `R2_BUCKET`, `R2_PUBLIC_BASE_URL` и `YOUTUBE_EXPECTED_CHANNEL_ID=UCS0QCodPcFBTjMt4ioEWOUw`. Переменная `BUFFER_CHANNEL_ID` **не требуется**: проверенный ID уже записан в коде.
6. Не включать `BUFFER_AUTO_PUBLISH_ENABLED` до теста с новым **неопубликованным** выпуском и проверки живого поста в YouTube. Даже при включённом переключателе нынешний workflow запускается **только вручную**.
7. Отдельный Publora backlog заблокирован дополнительной переменной `PUBLORA_CATCHUP_ENABLED`, чтобы не расходовать последние публикации. Уже запланированные посты продолжат жить в Publora отдельно.

### Проверка без публикации
Сначала `python3 -m unittest discover -s cloud-shorts -p 'test_buffer_autopublish.py' -v`. Для проверенного неопубликованного MP4 используйте `buffer_autopublish.py --dry-run` с флагами `--episode`, `--video`, `--metadata`, `--voice-qa` и `--mixed-qa`. Без ключей можно подтвердить локальные ограничения; внешнего вызова не будет.

### Ограничения
Buffer Free допускает до 10 роликов **в очереди одновременно**, место освобождается после публикации. Это не 10 публикаций в месяц. Однако YouTube и Buffer имеют антиспам-ограничения. API Buffer не принимает видеофайлы, только общедоступные URL, которые не должны истекать до момента публикации.

Не включайте массовый автопостинг, пока визуальное качество, права на кадры и озвучка не прошли проверку владельца. Для расширения до полностью автономных публикаций потребуется отдельный workflow, который проверяет реальный статус публикации и свободное место в очереди.

Источники: https://developers.buffer.com/examples/create-video-post.html , https://developers.buffer.com/guides/hosting-media .


## Исправления в API
- Для YouTube Buffer требует `metadata.youtube.title` и `metadata.youtube.categoryId` при создании видео. Включено: категория `2` (Autos & Vehicles), отдельный заголовок, privacy `public`, madeForKids `false`.
- Целевой Buffer channel ID жёстко закреплён в коде и проверяется; публикация в другом канале запрещена.
- Автопубликация защищена проверкой 95% ASR и прежним общим журналом (Publora + Buffer).
- GitHub CI `buffer-tests.yml` запускает тесты без доступа к API и публикации.

## 28.10.2026 — Codex MCP и безопасность ключей
- Установлено `codex mcp add buffer --url https://mcp.buffer.com/mcp` на авторизованном ПК; OAuth вернул `Successfully logged in`.
- `codex mcp list` подтверждает `buffer https://mcp.buffer.com/mcp enabled OAuth`; повторная регистрация Buffer не требуется. Локальный MCP **не** предоставляет GitHub Actions автоматически управляемые облачные OAuth credentials.
- После подтверждения email Buffer открывает создание персонального API-ключа. В UI появился ключ `GUSTAVA-Shorts-Cloud-GitHub` с годичным сроком действия; ключ **не передан** в GitHub Actions, не размещён в коде и не используется. До эксплуатации **нужно убедиться, что у него минимально необходимые permissions**; интерфейс первоначально включает все 12 прав, включая account:write/engagements:write. Более безопасно отозвать излишне широкий ключ и создать новый с минимальными правами `account:read`, `posts:read`, `posts:write` и при необходимости `channels:write`.
- В Buffer Free API текущие тарифные лимиты на странице API: 150 запросов за 15 минут, 600 за 24 часа, 1000 за 30 дней. Без постоянных polling-циклов; проверять очередь только перед выпуском и раз в день.
- Для GitHub Actions использовать только ограниченный API-ключ в GitHub Actions Secret `BUFFER_API_KEY`, не в репозитории и не в чате. Выданный на год ключ потребует безопасной ротации не позднее октября 2027.
- Cloudflare R2 bucket и публичный MP4 URL по-прежнему нужны: Buffer API/MCP принимает HTTPS URL, а не байты MP4. Проверка на уже опубликованном тестовом клипе — только **черновик**, без отправки в очередь, пока подключение не завершено.
