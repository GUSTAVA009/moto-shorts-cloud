# GUSTAVA Enduro — автономный конвейер YouTube через Buffer

**Канонический контракт:** [FACTORY_CONTRACT_RU.md](docs/FACTORY_CONTRACT_RU.md), [factory_contract.json](cloud-shorts/factory_contract.json), [AGENTS.md](AGENTS.md). Публикация только через **Buffer**, голос только оригинальный GUSTAVA DEEP (`voice_id="deep"`, `voice_engine="aidocmaker_deep"`). Исторические результаты подключения — не доказательство ежедневной автопубликации.
Старый сторонний загрузчик, его GitHub Actions и тесты удалены. Его опубликованные
ранее ролики и исторические квитанции остаются нетронутыми, чтобы не создавать дубликаты.

## Рабочий путь

1. `.github/workflows/continuous-stories.yml` — дважды в сутки исследует только
   мототематику (эндуро, мотокросс, мотоэкипировка и реальная мототехника).
   Исследование НЕ превращается автоматически в видео без сценария и прав на кадры.
2. `.github/workflows/daily-preview.yml` — до 16 производственных окон в день (каждые 90 минут) с целью **до 10 новых уникальных Shorts/сутки** и проверяемым запасом **10 QA-MP4**:
   оригинальный сценарий и лицензионные видеокадры, русская озвучка, музыка, монтаж.
3. `voice_qa.py` и `mixed_audio_qa.py` — проверяют полноту слов и финальный звук.
   `channel_focus.py`, `editorial_guard.py` и `publication_safety.py` запрещают
   посторонние темы, повторные видео, ошибки метаданных и нарушения лицензий.
4. `.github/workflows/buffer-backlog.yml` — запускается после успешного рендера
   и дополнительно четыре раза в сутки. Отбирает **один** оригинальный MP4 со
   статусом `auto_publish:true`, только проверенным оригинальным GUSTAVA DEEP, `voice_engine="aidocmaker_deep"`, `voice_id="deep"`, подтверждённым QA
   и без квитанции о прежнем выпуске. Публикация по умолчанию разрешена; экстренная
   остановка: GitHub Actions variable `BUFFER_AUTO_PUBLISH_ENABLED=false`.
5. `buffer_autopublish.py` сверяет реальный YouTube-канал
   `UCS0QCodPcFBTjMt4ioEWOUw`, загружает проверенный MP4 в **GitHub Releases**
   и передаёт постоянную HTTPS-ссылку в Buffer для постановки в очередь.
   В случае неопределённого ответа API повторная отправка запрещена.
6. Buffer публикует запланированный Shorts на **GUSTAVA Enduro (@gustava009)**.

## Историческая проверка подключения и текущие блокеры

Проверка 29 октября была разовой и **не означает работающую очередь**. На 31 октября последний прямой GitHub Action сообщил `BUFFER_RESERVE_UNDER_MINIMUM: 0/7`, `BUFFER_BACKLOG_EMPTY`. Источник новых DEEP-записей не имеет подтверждённого автономного API; сценарный резерв не заменяет готовые MP4.

- `BUFFER_API_KEY` установлен как GitHub Actions Secret — не выводить его значение.
- GitHub Releases → Buffer проверены на **тестовом черновике**; черновик удалён.
- Конфигурация Buffer имеет рабочие слоты; GitHub Actions подтвердил состояние
  `BUFFER_CREDENTIAL_STATUS READY` и `BUFFER_READINESS ENABLED`.
- В последнем запуске `buffer-backlog.yml` новых квалифицированных оригинальных
  MP4 не нашлось: **публикация не выполнялась**. Успех workflow означает успешную
  проверку, не наличие нового ролика в Buffer.
- Ранее опубликованные видео остаются в YouTube без изменений. Не удалять
  записи о старых публикациях из `render-ledger/publication-receipts/` —
  они нужны для предотвращения повторных загрузок.

## Правило 9 → новый запас, а не ожидание 7

В Buffer цель — **10** реальных запланированных роликов, лимит — **10**. Когда там остаётся **9 или меньше**, запускается подготовка следующей десятки; отдельно требуется **10 готовых, проверенных визуально MP4**. Порог **7** — лишь аварийный сигнал недостатка очереди, а не правило начала пополнения. `rolling-ten.yml` может подтвердить пополнение *сценариев*; никогда не записывайте его как создание и отправку MP4.

## Быстрые проверки

- [Buffer publishing workflow](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/buffer-backlog.yml)
- [Buffer authentication and queue](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/buffer-readiness.yml)
- [Rendering](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/daily-preview.yml)
- [Quality and safety tests](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/validate-pipeline.yml)
- [Buffer publishing queue](https://publish.buffer.com/channels/6ae238b32f1f5ed648ff9011/schedule?tab=queue)

## Ограничения и безопасность

- **Только мототемы**. Архивные эксперименты о самолётах, воде, погоде,
  осьминогах и промышленности имеют `auto_preview:false` и
  `auto_publish:false`. Сам редакционный фильтр также блокирует их.
- Видео не выходят, если нет нового лицензированного исходника,
  успешно проверенной озвучки или подтверждения уникальности.
- Ни личные видеозаписи с Windows-ПК, ни локальная Music Studio не используются.
- Для монетизации нужны реальные квалифицированные метрики YouTube Studio.
  Автопубликация сама по себе не гарантирует 10 млн просмотров, 4 тыс. часов
  или конкретный доход.
- API-ключ, ранее пересланный в чате, следует ротировать и обновить GitHub Secret
  без записи значения в репозиторий.
