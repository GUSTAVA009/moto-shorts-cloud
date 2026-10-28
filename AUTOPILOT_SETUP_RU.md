# GUSTAVA Enduro: активация автоматической публикации MP4

Производство, контроль звука и загрузчик подключены в `moto-shorts-cloud`.
**Автопубликация через GitHub пока отключена**: для неё нужны отдельный Publora API key
и явная настройка GitHub Actions. Ни секреты, ни ключи в этот репозиторий не записывать.

## Единственная настройка владельца

1. Открой **[Publora](https://app.publora.com/dashboard)** → боковое меню **API** →
   **Generate API Key**. Убедись, что авторизован именно аккаунт с подключённым
   YouTube-каналом GUSTAVA Enduro (`youtube-UCS0QCodPcFBTjMt4ioEWOUw`).
2. В GitHub открой **[Actions secrets](https://github.com/GUSTAVA009/moto-shorts-cloud/settings/secrets/actions)** →
   **New repository secret**. Имя: `PUBLORA_API_KEY`; значение: созданный ключ
   (начинается с `sk_`). Никому не отправляй его сообщением.
3. В том же GitHub открой **[Actions variables](https://github.com/GUSTAVA009/moto-shorts-cloud/settings/variables/actions)** →
   **New repository variable**. Имя: `PUBLORA_AUTO_PUBLISH_ENABLED`, значение: `true`.
4. Проверь `GUSTAVA - Autopublish Readiness (No Publication)` в
   [GitHub Actions](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/autopublish-readiness.yml).
   Он не публикует ничего и показывает только **YES/NO** без значения ключа.

## Как устроен дальнейший конвейер

`daily-preview.yml` собирает один новый уникальный Shorts за запуск — максимум три запуска
в день. `voice_qa.py` проверяет русскую речь относительно точного сценария,
в том числе окончания, возраст, годы. Если `voice_qa.passed != true`, видео остаётся
предпросмотром — **не загружается публично**.

`publora_autopublish.py` проверяет только созданный и ещё не опубликованный выпуск
(`auto_publish:true`), лицензионные и редакторские свидетельства, канал, квоту,
результаты QA. Только затем отправляет новый MP4 в подключённый Publora и запускает
публикацию YouTube. До внешнего вызова записывает постоянную бронь
`render-ledger/publication-receipts/`, чтобы не продублировать ролик при сбое.

`publora-backlog.yml` каждые три часа пытается найти только уже проверенный,
готовый, ещё не отправленный MP4; неизвестные исходы требуют сверки с Publora.

## Текущие ограничения

- Publora Starter: **15 постов в месяц и 3 отложенных**. Этого недостаточно
  для регулярных двух-трёх выпусков ежедневно. По документированным тарифам,
  Pro: **без фиксированного месячного лимита публикаций при соблюдении политики добросовестного использования**; стоимость, регион и условия
  нужно проверить в интерфейсе владельца.
- Уточнить настоящую страну AdSense/YPP. Рост просмотров не гарантирует выплаты.
- Нельзя массово публиковать повторяющиеся нарезки или неподтверждённые
  документальные реконструкции: защита YouTube от шаблонного и повторно
  используемого контента остаётся критичной.
- Уже опубликованные видео не пересоздаются. Три запланированных
  на 28–30 октября 2026 года выпуска не изменяются.

## Проверенные источники

- https://docs.publora.com/README
- https://docs.publora.com/endpoints/upload-media
- https://docs.publora.com/endpoints/update-post
