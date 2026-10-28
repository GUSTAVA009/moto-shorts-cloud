# GUSTAVA — 60-дневный кросс-тематический видеопроект

> **Актуальное направление с 28 октября 2026:** не только мотоциклы. Исследуем
> необычные проверенные факты, науку, животных, технику, историю, космос и
> настоящие приключения. Мотоистории остаются одной из оригинальных рубрик.
> Оформление канала GUSTAVA Enduro без отдельного решения владельца не изменяется.

## Быстрый рост: что реально запущено

- [План 14-дневного эксперимента и 24 новые темы](cloud-shorts/rapid_growth_backlog.json).
- **20 уникальных сценариев в производственном каталоге**; новые пилоты:
  [авиация, осьминог, промышленная гибка](cloud-shorts/episodes.json),
  со своими новыми лицензированными видео и научными ссылками.
- [Дважды в сутки — новая многотемная RSS-подборка](.github/workflows/continuous-stories.yml).
  Заголовки исследований — только кандидаты. Не копируем статьи, кадры
  или опубликованные видео и не делаем публикаций без отдельного полного QA.
- [До трёх попыток облачной сборки Shorts в сутки](.github/workflows/daily-preview.yml).
  Начальные новые сюжеты исследуем быстрее, но не повторяем использованные источники.
  [Проверка русского голоса и звука MP4](cloud-shorts/voice_qa.py) перед релизом.
- **Публикация через Publora API** включена с защищённым GitHub Secret,
  но фактический выпуск зависит от отчёта QA, внешнего API и квоты
  текущего плана Starter (15 публикаций в месяц). **Никакого бесплатного
  неограниченного выпуска сейчас нет**. Прямая GitHub→YouTube API загрузка
  отдельно выключена до Google OAuth/необходимого аудита.
- Цели на 60 дней — +479 реальных подписчиков (проверка vidIQ 28.10.2026: 521),
  квалифицированные Shorts-просмотры и альтернативный путь через
  4 000 учитываемых часов длинных авторских видео. Количество просмотров,
  доход, монетизация и сам 60-дневный дедлайн не гарантируются.
- Пересмотр форматов в течение 14 дней по фактическим engagedViews, удержанию,
  комментариям, репостам, подпискам и просмотрам длинных выпусков.
  Не устраиваем хаотичную публикацию на любые темы, если это разрушает
  возвращаемость аудитории, и не делаем однотипный AI/сток-контент.

---

# Moto Shorts Cloud

Бесплатный облачный конвейер коротких видео: оригинальная русская озвучка, собственная фоновая музыка, монтаж FFmpeg и прямая загрузка через официальный YouTube Data API.

**Статус:** тестовая инфраструктура. Публичная автоматическая загрузка выключена, пока Google OAuth и правила YouTube не настроены.

- Видео на домашнем ПК не используются.
- Публичные описания без ссылок на источники.
- Информация о происхождении исходных кадров хранится внутри проекта, отдельно от описания YouTube.
- Никакие платные API не используются.
- Ролики требуют оригинального сценария и реальной ценности; просмотры и монетизация не гарантированы.

Облачный запуск: GitHub Actions. Использование API и Google OAuth — только с разрешения владельца канала.

See `SETUP_RU.md` after installation.

## Продолжить настройку

- [Инструкция на русском: Google OAuth и GitHub Actions](SETUP_RU.md)
- [Новые оригинальные Shorts: разовые сборки](.github/workflows/render-new-short.yml)
- [Безопасная прямая загрузка YouTube](.github/workflows/youtube-direct-upload.yml)
- [Рост реальных подписчиков и план $5 000/мес](GROWTH_AND_REVENUE_RU.md)
- [Тесты CTA и достоверная аналитика](.github/workflows/validate-pipeline.yml)

После подтверждения владельца Google-аккаунта нужно установить секреты в GitHub Actions. Без этого прямые загрузки намеренно не выполняются. Первый ранее опубликованный ролик не следует загружать заново.

## Текущее состояние — 27 октября 2026

- 3 **разных** новых видео собраны в GitHub Actions с новой русской озвучкой и оригинальной фоновой музыкой; исходники загружаются из интернета, а не с домашнего ПК.
- Первый preview: [прыжок](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/40559540195), 9.0 секунд.
- Второй preview: [поездка через лес](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/40560248377), 8.8 секунд.
- Третий preview: [крутой подъём](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/40560875103), 9.0 секунд. Он собран **автоматической очередью** и помечен `preview_ready` в отдельной ветке `render-ledger`.
- Каждый новый ролик использует отдельные разрешённые источники Pexels. В публичных описаниях нет ссылок, внутри проекта хранится учёт лицензий.
- [Ежедневная очередь новых черновиков](.github/workflows/daily-preview.yml) запускается в 07:17 UTC; после исчерпания разрешённых новых сюжетов ничего не дублирует.
- [Проверки сценариев, исходников и ограничений](.github/workflows/validate-pipeline.yml) выполняются отдельно и не запускают платную видеогенерацию.
- [Прямая загрузка через YouTube API](.github/workflows/youtube-direct-upload.yml) всё ещё **выключена**, пока владелец Google-аккаунта не завершит OAuth и настройку секретов; для публичных загрузок из нового API-проекта необходим аудит Google.
- Ни один из трёх новых preview не опубликован на YouTube. Первый ранее опубликованный ролик и исправленное описание не изменялись.

**Масштабирование:** каталог расширен до семи разных сценариев, включая четыре новых совершенно разных направления. Для 30–60 оригинальных Shorts в месяц потребуется непрерывная проверка и добавление новых лицензированных исходников, людей, мотоциклов и сюжетов. Повторы старого материала запрещены.

См. [SETUP_RU.md](SETUP_RU.md) для завершения авторизации YouTube.

## 28 октября 2026 — новый контент и запланированная очередь

Обновление к историческому блоку о первых трёх тестовых видео:

- **4 новых, не похожих друг на друга направления** из новой подборки: [ночной город и стрит-байки](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/40581450572), [три мотомастерские](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/40582234041), [гоночный старт и грунтовый поворот](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/40583263654), [райдер на песчаных дюнах](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/40582880121). Все MP4 собраны в GitHub Actions из новых Pexels-источников, с русской озвучкой и синтезированной оригинальной музыкой. Для города слабый первый кадр признан нуждающимся в доработке — его ещё не публикуем.
- **28.10 в 16:45 UTC** — гараж и механики, Publora: `scheduled`, media: `ready`
- **29.10 в 16:45 UTC** — грунтовая гоночная трасса, Publora: `scheduled`, media: `ready`
- **30.10 в 16:45 UTC** — пустыня и дюны, Publora: `scheduled`, media: `ready`
- Публичные описания: без ссылок на источники. Лицензии и авторы сохраняются во внутренних `license_sources.json` каждого выпуска.
- Создано правило `cloud-shorts/editorial_guard.py`: обязательны новые источники, история, место, категории мотоциклов и участников. Тесты запрещают повтор ранее опубликованных видео.
- В ветке `render-ledger` ведётся постоянный файл `history/used_footage.json`: **20 идентификаторов источников** (включая опубликованные кадры и отклонённый бракованный вариант) зарезервированы и больше не должны использоваться в новом контенте. Новый облачный конвейер отказывает в скачивании, если реестр отсутствует/испорчен.
- Используются разные оригинальные программно синтезированные музыкальные стили: городской электронный, гаражный грув, гоночный брейкбит, пустынный кинематографический. Никакие коммерческие сэмплы/чужие готовые записи не использованы.
- Устаревший `render-preview.yml`, повторно генерировавший старый уже опубликованный ролик, удалён. Для ручных запусков — `render-new-short.yml`, для разовых автоматических черновиков — `daily-preview.yml`.
- Дополнительно создана ежедневная задача ChatGPT пополнять каталог, проверять разнообразие, качество и доступные публикационные слоты; это не заменяет финальной проверки готового видео.
- **Предел публикаций остаётся:** Publora Starter — до 15 публикаций в месяц, максимум 3 активных отложенных; для независимой публичной загрузки нужен завершённый Google OAuth и соответствующий аудит YouTube API. Нельзя обещать 30–60 публичных роликов уже сейчас или гарантировать монетизацию.

## Просмотры опубликованного Shorts (28.10.2026)

- Публичная ссылка: https://www.youtube.com/shorts/26FQE80Io-Y
- Подтверждённый начальный снимок YouTube Studio: **663 просмотра** (2026-10-27 19:38 UTC), канал **520 подписчиков**, 719 просмотров канала за последние 48 ч.
- Снимки хранятся в отдельной ветке `views-ledger` без доступа к видеофайлам или редактору YouTube.
- Сценарий `.github/workflows/views-watch.yml` рассчитан на чтение публичных счётчиков каждые 6 часов через официальный YouTube Data API v3. 
- **Автоматический сбор новых значений пока не активен:** отсутствует GitHub Actions secret `YOUTUBE_DATA_API_KEY`. Первые офлайн-тесты проверки прошли. Без ключа автоматизация честно пропускает запрос, не выдумывает просмотры.
- API key должен быть создан отдельно в Google Cloud и ограничен только YouTube Data API v3, затем добавлен в Repository secrets. Это ключ для чтения публичной статистики, не OAuth для загрузки видео.
- Ссылки на исходники отсутствуют в публичном YouTube-описании; внутренние лицензии сохранены.
- Никаких автоматических лайков, ботов, закупки просмотров или повторной заливки опубликованного файла.

## Новая механика роста аудитории

В каждом оригинальном Shorts — один короткий уместный призыв: подписка, комментарий, лайк или репост. Небольшой титр появляется только в конце. Контент не превращается в спам. Система сохраняет отдельную тему, людей, технику, обстановку и исходники для каждого видео. Подтверждённая базовая статистика на 28.10.2026: **520 подписчиков**, 60 309 просмотров канала, первый опубликованный Short 909 просмотров и 6 лайков. До отметки 1 000 подписчиков остаётся 480. Доход сейчас не подтверждён; $5 000/месяц — целевой бизнес-ориентир, не обещание.

Видео трёх ближайших публикаций остаются по расписанию; в описания добавлены разные тематические CTA. Полный финансовый план, YPP и региональные требования: [GROWTH_AND_REVENUE_RU.md](GROWTH_AND_REVENUE_RU.md).

## Срочный 90-дневный спринт YouTube Partner Program — 28.10.2026

- [Калькулятор реального порога YouTube Earn](cloud-shorts/sprint90.py), [краткая фактическая база](cloud-shorts/growth_baseline.json), [проработка сценариев для разных мотоциклов и локаций](cloud-shorts/rapid_growth_backlog.json).
- Прямая проверка **YouTube Studio → Монетизация** показала (данные на **22 октября 2026**, фактический просмотр 28 октября): **520/1000 подписчиков**, **780/10 млн квалифицированных просмотров Shorts за 90 дней**, **27/4000 учитываемых часов длинных видео за 365 дней**. **Двухэтапная аутентификация успешно включена 28 октября 2026 года; YouTube Studio убрал предупреждение.**
- Последний публичный видеосчётчик vidIQ: 990 просмотров, 6 лайков. Это другой срок измерения и не 990 квалифицированных просмотров YPP.
- **Математическая планка:** при условных 90 днях нужно около 111 103 подходящих Shorts-просмотров ежедневно. При 45 новых Shorts за 90 дней (примерная текущая квота Publora 15/мес.) около 222 205 просмотров на выпуск, если всё должно быть получено от них. **Это не прогноз/гарантия.**
- Развиваем альтернативный путь: остаётся 3973 учитываемых часов длинных видео; готовим одну новую полноценную **оригинальную** 5–10-минутную работу в неделю, не слайдшоу и не поверхностную нарезку чужих кадров.
- Новый тестовый ролик `wet-road-checklist-08`: оригинальные рекомендации перед поездкой в дождь по чек-листу MSF, **пять ранее неиспользованных видеоисточников**, озвучка, авторские пояснения, фоновая музыка и содержательный вопрос в финале. Источники MSF и лицензии Pexels остаются во внутреннем отчёте. Публичное описание без ссылок.
- Три ранее запланированных ролика остаются в Publora без изменений. **Ни одна новая загрузка в YouTube автоматически не разрешается без проверки качества и доступа.** И никаких ботов/накрутки/повторных исходников.
- Юридический фактор: у YouTube-канала публично указан регион RU, но AdSense-страна **не установлена**. До обещаний выплат надо проверить реальную доступность YPP и платёжного аккаунта; нельзя обходить региональные ограничения фиктивными данными.

Официальные правила: https://support.google.com/youtube/answer/72851 и https://support.google.com/youtube/answer/1311392.

**Проверено 28 октября:** YouTube Studio распознал 2FA, предупреждение снято. Для публикации в обход Publora создан [бесплатный диагностический GitHub Action](.github/workflows/youtube-api-readiness.yml). Он подтвердил, что все три `YOUTUBE_*` OAuth secrets отсутствуют, `YOUTUBE_EXPECTED_CHANNEL_ID` не установлен/не совпадает и официальный аудит публичных API-загрузок не заявлен. Никаких новых публикаций через API не было; старые три Publora-записи сохранены.


## Ускоренное производство — 28 октября 2026

- GitHub Actions `daily-preview.yml`: **три попытки сборки нового уникального Shorts в сутки**, в **07:17, 12:17 и 18:17 UTC** (10:17, 15:17, 21:17 МСК). Это *производство предпросмотров*, а не автоматическая публикация. При пустой очереди задача ничего не дублирует.
- Вручную доступны отдельные сборки для выпусков 09–12 из `render-new-short.yml`; перед публичной публикацией обязательны проверка готового MP4 и оригинальности.
- Запланированные через Publora три публичные публикации 28–30 октября, 16:45 UTC, оставлены без изменений. План Publora Starter допускает максимум 15 публикаций в месяц и три отложенных одновременно, поэтому график три Shorts ежедневно нельзя считать реализованным по YouTube, пока не подключён подходящий способ загрузки.
- Загрузчик YouTube через GitHub API остаётся **выключен без OAuth secrets, правильного channel ID и подтверждения применимых требований Google к публичным загрузкам**. Запрещено автоматически выставлять публичность, обходить ограничения или повторять видео.
- Целевой редакционный график после устранения ограничения публикации: 2–3 непохожих видео ежедневно с контролем первых секунд, удержания, реакции аудитории и отдельным реестром уникальности. Внутренние видеоисточники и права фиксируются отдельно; URL запрещены в публичных описаниях.


## Видеопроизводство длинного формата — 28 октября 2026

- Создан самостоятельный оригинальный 16:9 документальный выпуск №01: [сценарий и правообладатели](longform/01-rain-production.json) (30 разных сцен, 16 новых источников съёмки, 6 авторских информационных карточек), [движок FFmpeg/Piper](longform/render_documentary.py), [тесты](longform/test_render_documentary.py).
- [Облачная сборка](.github/workflows/longform-documentary-preview.yml) создаёт только MP4-предпросмотр с отдельной картинкой и источниками лицензий; **ничего не отправляется в YouTube без просмотра и редакторской оценки.** Это не гарантия 4 000 часов или соответствия YPP.
- Выпуски №13 (грязный грунт) и №14 (мойка против осмотра) добавлены в каталог с шестью новыми лицензированными видеосценами; их авторы указаны в [отдельном реестре](FOOTAGE_CREDITS.md) и не вставляются в публичные описания.
- Для владельца канала опубликован отдельный Shorts №10 через Publora, до конца октября действуют три прежних запланированных выпуска. YouTube дал каналу 58 публичных видео на последней проверке, подписчиков 520.
- Настроена повторяющаяся ChatGPT-автоматизация исследований и пополнения видео дважды в день; **она не является прямой публичной публикацией**. В GitHub производство отдельных новых предпросмотров пытается выполняться трижды в сутки.
- **Важное изменение YPP с 1 февраля 2027 года:** новые рекламные заявители должны достичь 1 000 подписчиков + 8 000 квалифицированных часов за 12 месяцев ИЛИ 20 млн квалифицированных Shorts-просмотров за 90 дней. До указанной даты остаются нынешние пороги. Официальный источник: https://support.google.com/youtube/answer/12843009 . Нельзя обещать выплат без проверки страны AdSense и фактического статуса YPP.


## 28.10.2026 — Auto-publishing, intact Russian voice, ongoing research and real-event series

- Publishing code: `cloud-shorts/publora_autopublish.py`; two GitHub pipelines: `.github/workflows/daily-preview.yml` (three daily MP4 render attempts) and `.github/workflows/publora-backlog.yml` (check for safely released MP4 every three hours). Public YouTube release is **NOT ACTIVE UNTIL** a personal Publora API key is stored in GitHub Secret `PUBLORA_API_KEY` and repository Variable `PUBLORA_AUTO_PUBLISH_ENABLED=true`. Only `auto_publish:true` and QA-approved new episodes may be publicly released, and each gets a durable publication receipt before the API request. Previously posted videos are never reuploaded. Publora account's quota still governs whether a release can happen. 
- **Human one-time setup:** in Publora → API → Generate, create a scoped key; put it directly in GitHub → Settings → Secrets and variables → Actions → New repository secret `PUBLORA_API_KEY`. Never send it in chat or commit it. Then set Actions repository variable `PUBLORA_AUTO_PUBLISH_ENABLED` to `true`. `Starter` is 15 posts/month; to post 2–3 every day requires a properly billed Pro account or another authorized, permitted publish pathway. Connect the intended YouTube channel, do not change its ID. Official instructions: https://docs.publora.com/getting-started and https://docs.publora.com/endpoints/upload-media.
- The regenerated Piper Russian voice now uses longer phonemes and sentence pauses; additional video tail prevents clipping. `cloud-shorts/voice_qa.py` runs independent offline Whisper ASR, and stores `voice_qa.json`. If the beginning, ending or enough words are missing, or the recognizer fails, the release is blocked rather than publishing defective speech. `faster-whisper==1.2.1` requires `av==18.1.0` compatibility pin in GitHub Actions as of October 2026.
- Continuous research: `.github/workflows/continuous-stories.yml` scans motorcycle public research feeds twice daily, deduplicates leads in `render-ledger` and archives ideas. Headlines are not scripts; only independently checked facts, original narrative and footage with proven commercial rights can be promoted to `episodes.json`. When feeds are down or no cleared material exists, no new video is invented.
- New series `series/elspeth-beard-1982/season1.json`: 6 factual chronological Shorts chapters about Elspeth Beard's solo world trip, 1982–1984. First actual video preview `elspeth-beard-s1-e01` added to `cloud-shorts/episodes.json` using 5 new Pexels sources. All visuals are modern **ILLUSTRATIONS**, not footage of Elspeth; overlays and YouTube description label the difference. No unlicensed historic photos or fictional dialogue. Sequential parts 2–6 remain scripted but require clearance and original footage before rendering. 
- This is a **guarded autonomous pipeline, not a promise that every MP4 is already on YouTube**: account authentication, quota, recognized words, actual sources, copyright, server errors and human content audits may halt a release. Inspect `render-ledger`, `publication-receipts` and Publora/YouTube before reporting `published`.

## 28 October 2026 — Reality-checked motorcycle history production

- The first documentary chapter `elspeth-beard-s1-e01` is authorized for automated public release **only when a current matching MP4 passes** voice QA, mixed-audio QA, provenance, and duplicate guards. It uses a commercially permitted MIT Silero narrator. A 23s verified preview recorded 97.8% original narration coverage and 95.6% MP4-with-music coverage. It has a factually labelled map/classic-bike illustrative montage, not historical archive footage. Newer cloud previews must be checked by revision and published status; do not report this chapter as public until Publora confirms.
- Chapter two `elspeth-beard-s1-e02` is rewritten to remove ASR failures on names/abbreviations. It uses a genuine USA road map and real motorcycle footage (replacing erroneous Germany map/scooter). Remains `auto_publish:false` until new exact audio is validated and chapter one is published.
- Chapter three `elspeth-beard-s1-e03` was added to the catalog with a verified historical story about running out of funds in Sydney and making aluminium travel panniers. Five new Pexels footage sources, source citations and a distinct Russian script were prepared. It is an **editorial script in the automatic render queue, not a published video**.
- The episode catalog currently has **17 uniquely sourced story outlines**. Audio checks now analyze the actual mixed soundtrack in MP4, not just the isolated WAV. Publishing requires both ASR reports and matching SHA256 of the final video. `preview_queue.py` can rerender revised unpublished documentary material for visual corrections with a bounded retry cap and checks the durable publish ledger. Public repeats are prohibited.
- `.github/workflows/voice-comparison.yml`, `silero-mit-audition.yml`, and `series-preview.yml` are manual-on-demand now: repeatedly running independent voice A/B and a three-episode preview on every unrelated catalog change wastes cloud minutes. The **three-slot daily factory** and **twice-daily sourced story research watcher** remain autonomous.
- **Still blocked for fully self-hosted public MP4 delivery:** GitHub Actions secret `PUBLORA_API_KEY` and repository variable `PUBLORA_AUTO_PUBLISH_ENABLED=true`, followed by sufficient account-wide Publora monthly quota. Refer to [AUTOPILOT_SETUP_RU.md](AUTOPILOT_SETUP_RU.md). Publora Starter has 15 posts/month; current official Pro offers unlimited posting subject to fair-use rather than a 100/month cap.
