# HAPYCH YouTube Factory — контрольная точка восстановления

> **ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ ПЕРЕД ЛЮБЫМ ИЗМЕНЕНИЕМ ЗАВОДА.**
> Актуальный основной тикет: [GitHub issue #80](https://github.com/GUSTAVA009/moto-shorts-cloud/issues/80).
> Точка продолжения: 2026-11-01 14:24 UTC; последний известный SHA `6d8be23fff0a1ba15deaf6e14f7fa7de543b4907` (PR #79). Все очередные итоги и новый стартовый шаг фиксировать **и здесь, и в issue #80**.

## Цель заказчика (НЕ снижать требования без согласования)

Полностью автономный YouTube Factory для уже действующего канала GUSTAVA: 400 оригинальных Shorts/месяц как целевая мощность, 10 реальных подтверждённых публикаций Buffer в очереди + 10 готовых прошедших QA MP4 в резерве; пополнение при 9, срочный запуск при 1, только реально разрешённые кадры, десятки тысяч разных сюжетов без повторов, диктор с утверждённым Deep-тембром (без Silero/Kokoro/V6), русское произношение, ASR и соответствие монтажа смыслу; 35% факты / 25% истории / 25% эксперименты / 15% зрелища; семь направлений стратегии — `docs/SEVEN_PILLARS_GROWTH_RU.md`.

**Сценарий ≠ озвучка ≠ QA-проверенный MP4 ≠ запись в Buffer ≠ опубликованный Shorts.** Не приписывать успех тестам или старым квитанциям. Никаких локальных видео пользователя, не затрагивать VPN и другие сервисы на действующем VPS. Не расходовать платные API.

## Проверено лично по реальным сервисам (01.11.2026)

- Рабочий SentinelX VPS: `hapych-eu-de-01`, `host_1716a611b8e82469`, 4 CPU, 8 ГБ RAM, ~105 ГБ свободно в начале. Desktop Commander Windows — **OFFLINE** (последнее устройство WIN-MFKU10DKMMC).
- На VPS (изолированный каталог `/opt/hapych-factory-voice`) установлен CPU-движок Qwen3-TTS C 0.6B, исходный Git commit `ef339be58a778b062e1c14382347964552eae007`, модель 2,4 ГБ, OpenBLAS. Референс из трёх исторических одобренных Deep MP3, проверенных SHA; итоговый эталон `ed27b23b9f86345c45263ab28957e96fd2d399379b3ea90ed9fbc75be183a3cc` (30,528 с). Референс и owner token **никогда не публиковать**.
- Реальная генерация русского WAV: 7,68 секунды за 9,9 с вычислений (не доказано соответствие тембру Deep). Отдельный реальный запрос POST `http://127.0.0.1:8077/v1/audio/speech`: ответ 200 WAV 410924 bytes, 403 без авторизации, SHA и голосовые заголовки совпали, повторный запрос отдал тот же WAV за 0,004 секунды.
- Изолированные systemd `hapych-factory-tts.service` и `hapych-factory-voice-tunnel.service` **active**, автозапуск, лимиты CPU/памяти. Обособленный Cloudflare named tunnel `d00af8ee-a8ef-4a5b-a401-541daecf8ccf`; существующая VPN Cloudflare служба `cloudflared.service` тоже active, конфиг не менялся.
- Публичный `https://voice.hapychrust.ru/health` через Cloudflare отвечает 200 `tts_ready_for_private_request:true`. HTTPS API `/v1/audio/speech` должен допускать только signer-verified GitHub Actions OIDC основного репозитория + `main` или невидимый приватный gvk token.
- PR #79 объединён в main (commit `6d8be23fff0a1ba15deaf6e14f7fa7de543b4907`), базовые тесты Qwen Studio и Factory успешны.

## Блокирующие баги в момент фиксации

1. **Actions OIDC HTTPS canary сломан**: [Run 41315937719](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315937719) `TTS_REJECTED_cloud_403`. Получен временный токен от GitHub, но приватный сервер отклонил. Сначала проверить только БЕЗОПАСНЫЕ boolean-поля реального JWT (`nbf` присутствует? `workflow_ref`, `repository_id`, `ref`, `iss`, `aud` соответствуют?). Не логировать токен, подпись, bearer headers. Не ослаблять проверку подписи или открывать endpoint.
2. **Поставка кадров сломана**: [Run 41315947994](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315947994) `NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS`; ключ Pexels отсутствует, Commons 1 запрос/цикл, пары разных действий двух авторов нет. Нужны новые реальные клипы с проверенной лицензией и соответствием сценарию. Не подменять скрипты новыми MP4.
3. **Renderer QUEUE_EMPTY**: [Run 41315937698](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315937698); не готов новый кандидат, существующие 19 historical «ready» записей не являются новыми задачами.
4. **Buffer и резерв пустые**: [Run 41315966563](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315966563): `buffer_scheduled_posts=0`, `unqueued_reviewed_mp4_reserve=0`, `voice_ready_unrendered_episodes=0`, `configured_owner_voice_routes=['cloud']`, `voice_live_verified=false`, подготовлено 10 скриптов, старые 26 Buffer receipts, **нет подтверждённых новых публичных Shorts**.
5. Windows и Chatterbox fallback-сервисы пока не подключены; допуск только к тому же проверенному Deep-тембру, без замены голоса.

## Порядок продолжения (отмечать галочки ТОЛЬКО по фактическому результату)

- [ ] Проверить OIDC подпись/claims в живом GitHub Actions canary, устранить HTTP 403, запустить реальный WAV через `https://voice.hapychrust.ru/v1/audio/speech`; фиксировать run id, SHA и продолжительность без утечки JWT.
- [ ] Найти/подтвердить минимум 2 новых лицензированных клипа с двумя различимыми действиями, разными авторами, правами и оригинальным сюжетом. Не выдумывать разрешения. Защитить от повтора по source ID.
- [ ] Запустить из Actions `autofill-motorcycle.yml` и `daily-preview.yml`; получить настоящий MP4, подтверждённые source/mixed ASR и visual QA. Провести отдельную проверку схожести с Deep; не запускать в паблик чужой голос.
- [ ] После QA, не раньше: Buffer queue >0, действительный Buffer Post ID и sent; затем независимо подтверждённый публичный YouTube Shorts ID.
- [ ] Проверить надёжное автоматическое пополнение реальных MP4 и очереди, 3 маршрута при возможности, без скрытых остановок. Проверить долгосрочную мощность 400/месяц по фактической статистике.
- [ ] Обновлять issue #80 и этот документ с новым run id, SHA, действиями и единственной следующей операцией; делать PR + тесты; никакого «всё работает» без опубликованного Shorts.

## Быстрая процедура диагностики после нового чата

1. GitHub: открыть [issue #80](https://github.com/GUSTAVA009/moto-shorts-cloud/issues/80), `AGENTS.md`, `factory_contract.json`, `docs/SEVEN_PILLARS_GROWTH_RU.md`.
2. Проверить последние GitHub Actions: `voice-live-smoke.yml`, `autofill-motorcycle.yml`, `daily-preview.yml`, `rolling-ten.yml`, Buffer delivery и YouTube confirmation.
3. SentinelX `host_1716a611b8e82469`: `systemctl is-active hapych-factory-tts.service`, `systemctl is-active hapych-factory-voice-tunnel.service`, `curl -fsS https://voice.hapychrust.ru/health`; `journalctl -u hapych-factory-tts.service --since today` читать **только без токенов**. Чужие VPS/VPN сервисы не перезапускать.
4. Последняя незакрытая галочка выше — точка продолжения. Каждый PR обновляет issue и фиксирует следующую точку.

_Примечание: авторский Deep голос ещё не прошёл независимого прослушивания нового клона, задача по качеству озвучки открыта. Цель 400 роликов/месяц не достигнута._
