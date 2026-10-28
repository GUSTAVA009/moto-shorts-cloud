# GUSTAVA — переход с Publora на Buffer Free + Cloudflare R2

Статус: **код подготовлен, публикация отключена, подключение владельца требуется**.
Не нужен домашний компьютер, VPN-сервер или прямой YouTube OAuth.

## Что настроено
- GitHub Actions производит оригинальные Shorts и хранит итоговые MP4 в артефактах.
- Ручной workflow `buffer-delivery.yml` берёт существующий MP4 с пройденной речевой проверкой.
- `buffer_autopublish.py` использует ту же директорию `publication-receipts/` в `render-ledger`, что Publora. Поэтому выпуски, уже отправленные любым сервисом, не загружаются повторно.
- После прохождения проверок MP4 отправляется в Cloudflare R2 по ключу SHA-256 и проверяется постоянный публичный HTTPS-адрес; затем Buffer ставит видео в очередь публикации.
- Повтор после неизвестного результата запрещён. Очередь Buffer не означает, что видео уже опубликовано на YouTube.
- Речевая проверка для нового маршрута требует ≥95% распознанного текста **и в исходной озвучке, и в готовом MP4**. Не гарантирует художественное качество тембра или интонации.

## Однократно подключить аккаунты
1. https://buffer.com — бесплатный аккаунт; подключить Google-аккаунт **владельца** канала GUSTAVA Enduro (YouTube ID `UCS0QCodPcFBTjMt4ioEWOUw`).
2. В Buffer создать API-ключ и найти **Buffer channel ID**. Это отдельный идентификатор, не YouTube ID. Инструкция: https://developers.buffer.com/guides/your-first-post.html
3. Cloudflare R2: создать bucket и узкий R2 S3-токен с доступом только к bucket; включить постоянный публичный HTTPS-адрес (лучше custom domain). Учесть, что любой обладатель ссылки сможет открыть исходный MP4.
4. В GitHub Actions Secrets добавить `BUFFER_API_KEY`, `R2_ENDPOINT` (формат `https://<account-id>.r2.cloudflarestorage.com`), `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
5. В GitHub Actions Variables добавить `BUFFER_CHANNEL_ID`, `R2_BUCKET`, `R2_PUBLIC_BASE_URL` и `YOUTUBE_EXPECTED_CHANNEL_ID=UCS0QCodPcFBTjMt4ioEWOUw`.
6. Не включать `BUFFER_AUTO_PUBLISH_ENABLED` до теста с новым **неопубликованным** выпуском и проверки живого поста в YouTube. Даже при включённом переключателе нынешний workflow запускается **только вручную**.
7. Отдельный Publora backlog заблокирован дополнительной переменной `PUBLORA_CATCHUP_ENABLED`, чтобы не расходовать последние публикации. Уже запланированные посты продолжат жить в Publora отдельно.

### Проверка без публикации
Сначала `python3 -m unittest discover -s cloud-shorts -p 'test_buffer_autopublish.py' -v`. Для проверенного неопубликованного MP4 используйте `buffer_autopublish.py --dry-run` с флагами `--episode`, `--video`, `--metadata`, `--voice-qa` и `--mixed-qa`. Без ключей можно подтвердить локальные ограничения; внешнего вызова не будет.

### Ограничения
Buffer Free допускает до 10 роликов **в очереди одновременно**, место освобождается после публикации. Это не 10 публикаций в месяц. Однако YouTube и Buffer имеют антиспам-ограничения. API Buffer не принимает видеофайлы, только общедоступные URL, которые не должны истекать до момента публикации.

Не включайте массовый автопостинг, пока визуальное качество, права на кадры и озвучка не прошли проверку владельца. Для расширения до полностью автономных публикаций потребуется отдельный workflow, который проверяет реальный статус публикации и свободное место в очереди.

Источники: https://developers.buffer.com/examples/create-video-post.html , https://developers.buffer.com/guides/hosting-media .
