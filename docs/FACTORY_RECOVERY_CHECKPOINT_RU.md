# HAPYCH YouTube Factory — контрольная точка восстановления

> **ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ ПЕРЕД ЛЮБЫМ ИЗМЕНЕНИЕМ ЗАВОДА.**
> Актуальный основной тикет: [GitHub issue #80](https://github.com/GUSTAVA009/moto-shorts-cloud/issues/80).
> Точка продолжения: **2026-11-01 14:30 UTC**; PR #81 объединён с `main` (`1d5906916d2e16bfef4ab40466785068f45e5927`); выполняется исправление поставки кадров в PR #82. Все очередные итоги и новый стартовый шаг фиксировать **и здесь, и в issue #80**.

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

1. **Actions OIDC ✅ реальный canary восстановлен**: прежний [run 41315937719](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315937719) возвращал `TTS_REJECTED_cloud_403`; после перезапуска приватного TTS с безопасной диагностикой и PR #81 [run 41316443252](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41316443252) вернул **SUCCESS**, 8.56 с настоящего русского WAV, SHA-256 `b16f21d56041a5650379e7d4d733bf58d4c9e5cdb4c5d60e3ca0b018f6240198`; все boolean OIDC-проверки (`issuer`, `aud`, `nbf`, `repository_id`, `ref`, `workflow_ref`) истинны. Это доказательство только автономного TTS канала, **не** рабочей генерации роликов.
2. **Поставка кадров сломана**: [Run 41315947994](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315947994) `NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS`; ключ Pexels отсутствует, Commons 1 запрос/цикл, пары разных действий двух авторов нет. Нужны новые реальные клипы с проверенной лицензией и соответствием сценарию. Не подменять скрипты новыми MP4.
3. **Renderer QUEUE_EMPTY**: [Run 41315937698](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315937698); не готов новый кандидат, существующие 19 historical «ready» записей не являются новыми задачами.
4. **Buffer и резерв пустые**: [Run 41315966563](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41315966563): `buffer_scheduled_posts=0`, `unqueued_reviewed_mp4_reserve=0`, `voice_ready_unrendered_episodes=0`, `configured_owner_voice_routes=['cloud']`, `voice_live_verified=false`, подготовлено 10 скриптов, старые 26 Buffer receipts, **нет подтверждённых новых публичных Shorts**.
5. Windows и Chatterbox fallback-сервисы пока не подключены; допуск только к тому же проверенному Deep-тембру, без замены голоса.

## Порядок продолжения (отмечать галочки ТОЛЬКО по фактическому результату)

- [x] Подтвердить подписанный OIDC и реальный приватный WAV: успешно [run 41316443252](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41316443252), 8,56 с, SHA `b16f21d56041a5650379e7d4d733bf58d4c9e5cdb4c5d60e3ca0b018f6240198`, токен не логировался. Следующий необязательный контроль — повторить запрос из рендера при первом живом задании.
- [x] **Первый раз доказано:** [autofill run 41316905424](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41316905424) автоматически взял Pexels 7170232 и 31881759 от двух разных авторов, создал неопубликованный `moto-vintage-c81aecc34671`, source_ID в history закреплены. Проблема регулярного снабжения 400/мес всё ещё открыта.
- [ ] **Незакрыто: MP4 + ASR + визуальный QA.** Автоматический autofill уже создал правдивую независимую пару кадров и сценарий ([run 41316905424](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41316905424)). Первый автоматический render ([run 41316919801](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41316919801)) скачал исходники и **сгенерировал WAV 18,4с**, но **БЛОКИРОВАН** `VISUAL_DURATION_SHORTAGE` (лимиты сцены ремонт ~6с + грязь ~8с). PR #83 укоротил речь с 270 до 158 символов и добавил единственный безопасный retry по точному failed run/fingerprint. После merge проверить повторный MP4+source/mixed ASR+visual QA и похожесть на Deep, не выпускать без контроля качества.
- [ ] После QA, не раньше: Buffer queue >0, действительный Buffer Post ID и sent; затем независимо подтверждённый публичный YouTube Shorts ID.
- [ ] Проверить надёжное автоматическое пополнение реальных MP4 и очереди, 3 маршрута при возможности, без скрытых остановок. Проверить долгосрочную мощность 400/месяц по фактической статистике.
- [ ] Обновлять issue #80 и этот документ с новым run id, SHA, действиями и единственной следующей операцией; делать PR + тесты; никакого «всё работает» без опубликованного Shorts.


## Изменения текущего этапа — 2026-11-01 14:30 UTC

- [PR #81](https://github.com/GUSTAVA009/moto-shorts-cloud/pull/81) включён в main: защищённая диагностика только классов ошибок на VPS и boolean-свойств токена в Actions, плюс этот файл и указатель в AGENTS. CI зелёный.
- [OIDC canary run 41316443252](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41316443252) — **успешен**. Следующий этап **только** независимая поставка видеоматериалов / autofill / рендер / QA, не повторять установку Qwen.
- PR #82: в банке 38 проверенных Pexels клипов, 34 уже использованы, три ещё оставшиеся содержат разные действия `repair/mud/snow` и разных авторов. Старый поиск пытался найти два внутри одной рубрики, пропуская межтематический правдивый сюжет. Новый подбор не отменяет source_id, лицензию, двух создателей, QA и запрет auto_publish. Публичных новых Shorts пока нет.


## Изменения этапа — 2026-11-01 14:37 UTC

- После PR #82 (`552b5a2fffc367991732aefb95b9edbd64c5c251`), pipeline запускается **сам**: GitHub autofill 41316905424 успешно создал новый episode `moto-vintage-c81aecc34671`, затем автоматически dispatch renderer 41316919801.
- Рендер 41316919801 реально скачал Pexels 7170232 и 31881759 (обрезанные MOVING excerpts 12,2с каждый), вызвал приватный Qwen через OIDC, создал **оригинальный WAV продолжительностью 18,4с**. Техническая ошибка `VISUAL_DURATION_SHORTAGE` при реальных editorial scene caps (6с механик + 8с offroad), **готового MP4 нет**, артефакт содержит только диагностику, QA не пройдены. Buffer остался 0.
- Приватная квитанция `render-ledger:render-receipts/moto-vintage-c81aecc34671.json` имеет `state=reserved`, `run_id=41316919801`, `attempt_count=1`, `preview_fingerprint=7a61955e435972a44cad2e1ef3f12dbf64315ecbff7c7f1ef75ee9aa8c50f445`. Никогда не переиспользовать эту пару для **нового другого эпизода**.
- [PR #83](https://github.com/GUSTAVA009/moto-shorts-cloud/pull/83): правдивая сокращённая озвучка (158 символов), тот же неизменный Pexels source ID, `auto_publish=false`; одна исправительная попытка только если подтверждено завершение предыдущего Action с ошибкой и прошлой SHA fingerprint; тесты защищают от имитации авторизации и публикации.
- **СЛЕДУЮЩИЙ ШАГ:** дождаться CI PR #83, merge в main → автоматически запускается `daily-preview.yml` (в пути `episodes.json`, `preview_queue.py`) → проверить наличие *настоящего* MP4, источниковая и mixed ASR, visual_qa. Если QA блокирует — фиксировать точный run id / причину и корректировать только соответствующий модуль. НЕ утверждать, что Buffer и YouTube уже работают.

## Быстрая процедура диагностики после нового чата

1. GitHub: открыть [issue #80](https://github.com/GUSTAVA009/moto-shorts-cloud/issues/80), `AGENTS.md`, `factory_contract.json`, `docs/SEVEN_PILLARS_GROWTH_RU.md`.
2. Проверить последние GitHub Actions: `voice-live-smoke.yml`, `autofill-motorcycle.yml`, `daily-preview.yml`, `rolling-ten.yml`, Buffer delivery и YouTube confirmation.
3. SentinelX `host_1716a611b8e82469`: `systemctl is-active hapych-factory-tts.service`, `systemctl is-active hapych-factory-voice-tunnel.service`, `curl -fsS https://voice.hapychrust.ru/health`; `journalctl -u hapych-factory-tts.service --since today` читать **только без токенов**. Чужие VPS/VPN сервисы не перезапускать.
4. Последняя незакрытая галочка выше — точка продолжения. Каждый PR обновляет issue и фиксирует следующую точку.

_Примечание: авторский Deep голос ещё не прошёл независимого прослушивания нового клона, задача по качеству озвучки открыта. Цель 400 роликов/месяц не достигнута._

## Контрольная точка 2026-11-01 14:47 UTC — первый реальный MP4 автономного завода

- ✅ PR #83 объединён в main (commit `ae134ee0ac0a3be8ddf596ad1c9a65e4edb673cc`).
- ✅ **Сам запустился и прошёл** [GitHub Actions renderer 41317559714](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41317559714): получен настоящий **12,5-секундный 720×1280, 30fps, H.264/AAC MP4 2 862 020 bytes** `moto-vintage-c81aecc34671.mp4`, SHA-256 `0d6e1dfeebfd9f56f269b870127aaefe5a0c253867c30830fc5ec13b3dd85b41`, GitHub artifact **ID 13087824309**, ZIP `daily-preview-moto-vintage-c81aecc34671-41317559714` (3.01 MB). 2 разных Pexels источника и один приватный Qwen Deep клон; **WAV 11,36 с**.
- ✅ Проверки `voice_qa.json` **100%** и `mixed_audio_qa.json` **100%** с отдельным faster-whisper small CPU. Первая/вторая автоматические попытки имели mixed coverage .917, третья с pace .98 и music_gain .10 — 1.0. `visual_qa.json` технич. `passed:true`, сцены `clip_0` (6.0с) и `clip_1` (6.61с), без повторения; отчет `repair_history.json` сохранён. Run SUCCESS, `preview_queue.finish` отметил `preview_ready` в `render-ledger:render-receipts/moto-vintage-c81aecc34671.json`, `run_id=41317559714`, `attempt_count=2`, `preview_fingerprint=b5138c8c73f9331c2316264ea280b7f1a643e047fc6e4ea033afd496483f5bea`, обе ASR проверки пройдены.
- ⚠️ **При реальном просмотре 10 кадров MP4 выявлены две существенные смысловые ошибки, автоматический `visual_qa` их пропустил**: (1) `caption_middle='ГРЯЗЕВАЯ ТРАССА'` появляется с 3.9 секунды на КАДРАХ РЕМОНТА, хотя реальная смена сцены в 5.9с; (2) во второй сцене люди **вручную помогают вытолкнуть мотоцикл из грязи**, а синтезированный текст неверно говорит «райдер проезжает грязный участок». Повторная визуально-смысловая доработка **обязательна** до публикации. Эти наблюдения из фактических кадры 0.2, 1.5, 3, 4.5, 5.8, 6.6, 8, 9.5, 11, 12.2 сек; SHA MP4 подтверждён внутри artifact.
- 🔧 PR #84 (`fix/visual-frame-audit-mud-rescue-caption-sync-20261101`) исправляет **только тот же неопубликованный эпизод**: новый честный текст о людях, помогающих байку выбраться из грязи; `spoken_second_scene_at_seconds=4.85`, `align_middle_caption_to_second_scene=true`, `visual_revision_requested=true`, `visual_revision_reason=spoken_scene_caption_mismatch`, отдельное `visual_revision_evidence` с прежними live run и реальным MP4 SHA. Даже при идеальном ASR это не разрешение на публикацию: `auto_publish=false` и тембровое сходство с оригинальным Deep ещё не проверено независимо.
- ❌ Buffer по [run 41317559639](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41317559639): `0/7 scheduled`, не нашёл **редакционно одобренный** MP4; это правильный отказ, а не ошибка ключа. `buffer-backlog` запускается автоматически после QA, но публикация также ждёт явного `auto_publish=true`, который не стоит обходить без корректного тембра и визуального согласования.
- ❌ Поставка следующей пары кадров всё ещё ограничена; [autofill 41317559612](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41317559612) снова `NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS` после расходования пары. Цель 400/мес **не достигнута**.

**Единственный следующий шаг при восстановлении:** открыть свежий статус PR #84, дождаться зелёного CI и merge; его push должен автоматически запустить третий PRIVATE `daily-preview` на том же эпизоде, после чего визуально проверить, что кадр грязи начинается раньше подписи и речь действительно описывает помощь застрявшему байку. Если снова смысловая ошибка — блокировать релиз, фиксировать кадры/времена. После реального QA проверить/подтвердить собственный тембр Deep отдельной независимой проверкой. Только затем Buffer + публичный YouTube URL. Всю новую фактическую информацию фиксировать в [issue #80](https://github.com/GUSTAVA009/moto-shorts-cloud/issues/80) и этом файле. Не заявлять о опубликованном ролике раньше события.
