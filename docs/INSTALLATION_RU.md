# Установка и запуск GUSTAVA Shorts Factory — проверяемая инструкция

> **Статус на 01.11.2026: beta / production BLOCKED.** В репозитории
> есть код, аудио/видео/Buffer-QA и GitHub Actions, но нет подтверждения
> полного бесперебойного цикла. Документация не является обещанием
> 400 опубликованных Shorts в месяц.

## 1. Что делает завод

`сценарий → доказательство прав и соответствия кадров → оригинальная
озвучка → FFmpeg (9:16) → независимая проверка русского ASR → визуальное
QA → отдельное одобрение → архив/релиз MP4 → очередь Buffer →
Buffer sent → публичный URL YouTube`.

**Сценарий, запущенный workflow, сгенерированный WAV и даже Buffer sent —
разные статусы**. Считать опубликованным Shorts можно только после
подтверждения публичной ссылки, а его качество — после просмотра MP4.

## 2. Системные требования

- GitHub-репозиторий с доступными **Actions**, GitHub Releases и
  правом записи `GITHUB_TOKEN` в Actions; секреты не коммитить.
- Python **3.11+**, FFmpeg/ffprobe и Git; для локального тестирования
  Pillow 11.3.0; для полного ролика дополнительные пакеты из workflow.
- **Buffer с подключённым YouTube-каналом**, доступным API и достаточной
  доступной очередью. В демонстрационном коде жёстко закреплены
  `@gustava009`, YouTube ID `UCS0QCodPcFBTjMt4ioEWOUw` и ID канала
  Buffer. **Не используйте исходный репозиторий для публикации в ЧУЖОЙ
  канал без явного перенастроенного контракта, всех ID и тестов.**
- Минимум один действительно работающий сервер TTS с фиксированным
  разрешённым эталоном, русским WAV и HTTPS: собственный облачный Qwen3,
  собственный Windows-PC через стабильный туннель либо отдельно
  размещённый Chatterbox Multilingual V3. **Наличие адреса не равно
  способности генерировать голос.**
- Источники новых клипов с правом коммерческого использования:
  официальная Pexels API (ключ выдаётся бесплатно, но доступ и лимиты
  регулирует Pexels), поштучно вручную проверенный список либо
  Wikimedia Commons CC0. Не копируйте систематически стоки, нарушая
  их условия. Подключение бесплатной библиотеки не гарантирует
  поставку 400 уникальных сюжетных клипов.
- Предусмотрите место под MP4, кэш моделей, WAV и GitHub Actions
  artifacts. Если ролики генерируются локально, ПК должен работать,
  пока выполняется его маршрут.

Видеоформат: 720×1280, вертикальный 9:16. Цель для 30-дневного месяца —
минимум **400**, ориентир **14 Shorts/сутки**; в феврале с 28 днями —
**15/сутки**; максимум 16 уникальных слотов/сутки. Бесплатный Buffer
допускает не более десяти одновременно запланированных постов в этой
архитектуре. Обычное пополнение при 9, экстренная TTS/рендер-поставка
при 0–1; это запрос на работу, не 10 готовых MP4.

## 3. Локальная проверка кода — без публикации

В PowerShell Windows:

```powershell
git clone https://github.com/GUSTAVA009/moto-shorts-cloud.git
cd moto-shorts-cloud
py -3 -m pip install Pillow==11.3.0
py -3 -m pip install -r voice-studio/requirements.txt
py -3 -m unittest discover -s cloud-shorts -p "test_*.py" -v
py -3 -m unittest discover -s voice-studio/tests -p "test_*.py" -v
```

В Linux используйте `python3` вместо `py -3`; установите `ffmpeg`
через пакетный менеджер. Это проверяет логику и безопасность, **но не
отправляет ни одного ролика**. Из интерфейса GitHub в
Actions запустите `Shorts Factory - Fast Code and Episode Checks`.
На компьютере не нужно запускать Music Studio для GitHub workflow;
личные видеозаписи с ПК запрещено подхватывать.

## 4. Настройка GitHub Actions

Откройте GitHub → Settings → Secrets and variables → Actions.

**Secrets (вставлять значения только в GitHub, не в чат и не в Git):**

| Секрет | Для чего |
|---|---|
| `BUFFER_API_KEY` | Доступ к согласованному YouTube-каналу Buffer |
| `GUSTAVA_VOICE_API_KEY` | API-ключ основного HAPYCH Qwen3 |
| `GUSTAVA_LOCAL_VOICE_API_KEY` | Отдельный ключ Windows Qwen3, если резерв доступен |
| `GUSTAVA_TERTIARY_VOICE_API_KEY` | Отдельный ключ Chatterbox, если резерв доступен |
| `PEXELS_API_KEY` | **Опционально**: официальный поиск видеоматериалов |
| `OPENAI_API_KEY`, `OPENROUTER_API_KEY` | Опционально; не активируйте платные API при нулевом бюджете |

**Variables:**

| Переменная | Значение/условие |
|---|---|
| `YOUTUBE_EXPECTED_CHANNEL_ID` | `UCS0QCodPcFBTjMt4ioEWOUw` |
| `BUFFER_AUTO_PUBLISH_ENABLED` | Сначала `false`; включить `true` только после end-to-end QA |
| `GUSTAVA_TTS_PROVIDER` | `gustava_selfhosted_qwen3` только когда есть хотя бы один доступный проверенный узел |
| `GUSTAVA_VOICE_REFERENCE_SHA256` | Реальный 64-значный SHA-256 закреплённого WAV (не выдуманный) |
| `GUSTAVA_SELFHOSTED_TTS_ENABLED` | `1` после успешного теста облачного узла |
| `GUSTAVA_VOICE_API_URL` | `https://voice.hapychrust.ru/v1/audio/speech`, если DNS/сервер готовы |
| `GUSTAVA_VOICE_APPROVED_HOST` | `voice.hapychrust.ru` |
| `GUSTAVA_LOCAL_TTS_ENABLED` | `1` только после реального HTTPS-доступа к Windows |
| `GUSTAVA_LOCAL_VOICE_API_URL` / `GUSTAVA_LOCAL_VOICE_APPROVED_HOST` | Точный внешний HTTPS endpoint / hostname своего ПК |
| `GUSTAVA_TERTIARY_TTS_ENABLED` | `1` только при отдельном живом Chatterbox-сервере |
| `GUSTAVA_TERTIARY_VOICE_API_URL` / `GUSTAVA_TERTIARY_VOICE_APPROVED_HOST` | Точный HTTPS endpoint / hostname третьего сервера |
| `GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED` | `1` только после ручного прослушивания, русского ASR и подтверждения тембра |
| `GUSTAVA_ORIGINAL_VOICE_APPROVED` | Управляемое редакционное разрешение, не снимать QA |

**Не смешивайте каналы** `@gustava009` и `@motobratr1`.
Исторические WAV `aidocmaker_deep` с `voice_id=deep` остаются
неизменными. Новые озвучки получают provenance и источник `provider_route`.

## 5. Развёртывание HAPYCH Voice Studio

Исходники и строгая авторизация: [voice-studio/README_RU.md](../voice-studio/README_RU.md).
Облачный Qwen3 требует ARM64/CPU ресурсов, постоянного приватного
хранилища, отдельного TTS-движка, закрытых admin-ключей, DNS и HTTPS.
Локальный Windows Qwen3 работает лишь при доступной машине, установленной
модели, собственном API и защищённом постоянном туннеле. Третья независимая
машина: [TERTIARY_SETUP_RU.md](../voice-studio/TERTIARY_SETUP_RU.md).

**Нельзя** считать случайный сайт на бесплатном статическом хостинге
работающим TTS, если там отсутствуют модель, постоянный кэш и реальная
генерация WAV. Нельзя автоматически копировать голос между разными
движками и выдавать его за идентичный без контроля.

## 6. Контроль включения публикации

1. Запустите `validate-pipeline.yml` и `voice-studio-ci.yml` — должны
   завершиться успешно без отключения тестов.
2. `autofill-motorcycle.yml`: добавляет **новую** тему, основанную на двух
   разных реальных действиях разных авторов. Если пишет
   `NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS`, это настоящий блокер.
3. `daily-preview.yml`: должен произвести MP4 и три валидных отчёта
   `voice_qa.json`, `mixed_audio_qa.json`, `visual_qa.json`.
   Артефакт должен быть доступен и фактически просмотрен. При
   `QUEUE_EMPTY` ролика нет.
4. Предварительно сверить SHA/голос/кадры, убедиться, что выпуск новый,
   материал не нарушает права и не создан из одинаковых коротких петель.
   Только потом разрешить `auto_publish:true` конкретному эпизоду.
5. `buffer-backlog.yml`: проверить **настоящий** Buffer Post ID и
   расписание, очередь должна стать >0.
6. После выхода проверить `Buffer sent` и отдельную **публичную ссылку**
   `youtube.com/shorts/…` именно нужного канала. Успех Actions
   и статус `sent` не заменяют проверку YouTube.
7. Лишь при нескольких реальных успешных циклах можно включать
   `BUFFER_AUTO_PUBLISH_ENABLED=true` и продолжать прогон
   на 14–16 окон; следить за лимитами GitHub Actions и стоков.

**Остановка:** `BUFFER_AUTO_PUBLISH_ENABLED=false` (GitHub variable).
Старые `render-ledger` квитанции и реестры использованных источников
не удалять — иначе возникнет повторная публикация.

## 7. Диагностика

- [Последние GitHub Actions](https://github.com/GUSTAVA009/moto-shorts-cloud/actions)
- [Источник нового контента](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/autofill-motorcycle.yml)
- [Сборка MP4](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/daily-preview.yml)
- [Очередь Buffer](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/workflows/buffer-backlog.yml)
- [Реальная очередь на Buffer](https://publish.buffer.com/channels/6ae238b32f1f5ed648ff9011/schedule?tab=queue)
- [Канал YouTube](https://www.youtube.com/@gustava009/shorts)

**Важное ограничение по монетизации:** бесплатность лицензии на сток
не означает, что переработка является достаточно оригинальной для YPP.
Автоматически повторяющиеся, шаблонные и некачественные Shorts могут
не соответствовать требованиям YouTube. Техническая цель 400 в месяц
не отменяет редакционную ценность каждого выпуска.
