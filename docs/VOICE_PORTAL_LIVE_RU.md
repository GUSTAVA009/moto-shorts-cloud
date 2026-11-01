# HAPYCH Voice — живой закрытый личный кабинет (01.11.2026)

## Проверенная производственная установка

- URL владельца: **https://voice.hapychrust.ru/login**. Главная `/` переводит на `/studio`, затем без сессии на `/login`.
- На VPS `hapych-eu-de-01` (SentinelX `host_1716a611b8e82469`) запущена **отдельная** `hapych-factory-portal.service` (loopback `127.0.0.1:8078`). Исходник: `voice-studio/live_portal.py`; template сервиса: `voice-studio/hapych-factory-portal.service`.
- Текущий TTS **НЕ заменён**: `hapych-factory-tts.service` на `127.0.0.1:8077`, `hapych-factory-voice-tunnel.service` в существующем Cloudflare Tunnel. Путь `/health` возвращает HTTP 200 и `tts_ready_for_private_request:true`; `/v1/audio/speech` остаётся на 8077 для GitHub OIDC.
- В выделенном `voice-tunnel.yml` добавлен только path route `/ | /login | /studio | /portal-assets/* | /auth/* | /api/portal/*` на 8078, общая старая трасса остальных путей на 8077 сохранена. Backup: `/opt/hapych-factory-voice/voice-tunnel.pre-portal-20261101.yml`; пример: `voice-studio/portal-ingress.example.yml`.
- Проверка после активации: `/ = 303`, `/login = 200`, `/studio без сессии = 303`, `/health = 200`; три службы active. Проверено c VPS через PUBLIC HTTPS.
- Единичные интеграционные тесты: `python3 -m unittest discover -s /opt/hapych-factory-voice/tests -p test_live_portal.py -v` **4 passed** (с подставным голосом: тесты не считаются proof тембра/Factory). Ни одна существующая VPN-служба не менялась.
- Случайно сгенерированный первоначальный пароль хранится приватно в `private/portal/owner-first-login.txt` (0600), передаётся владельцу только по защищённой одноразовой ссылке, в GitHub не коммитится и удаляется при успешном первом входе; в `password.json` хранится соль+PBKDF2-хеш (0600). При восстановлении пароль **НЕ** перегенерировать, если `password.json` уже существует.
- Процесс ограничен по памяти/CPU, перезапускается systemd, все секреты, WAV и настройки остаются в `/opt/hapych-factory-voice/private/portal` (0700). Сервис не выводит в журналы пароли, токены и тексты запросов.

## Действительно работающие возможности интерфейса

Вход владельца по HTTPS, signed random cookie с HttpOnly/Secure/SameSite=Strict, сессия 8 часов, CSRF, защита от перебора, выход, смена пароля и сброс остальных сессий. Просмотр готовности облачного Qwen3 и закреплённого SHA референса, персональное название канала, сохранённый черновик текста, скорость 0.85–1.15, генерация **приватного** WAV из существующего API с контролем SHA/voice/ref, плеер и загрузка. Никакой автоматической смены Deep/эталона при настройке скорости; скорость — постобработка предпросмотра (ffmpeg atempo), не новая обученная модель.

**Явно не реализовано:** полноценное управление несколькими каналами и API-ключами Factory с сайта, управление расписанием Buffer, полноценная YouTube Studio Analytics, регистрация пользователей/почта, смена основной производственной модели через UI. В репозитории есть `voice-studio/app.py` (другая незапущенная ARM-бэкенд-архитектура), **его нельзя просто подменить на 8077 без адаптации к текущему Base Qwen**. Переключатели, не влияющие на реальную фабрику, не выдавать за рабочие. Текущий live-портал является персональным интерфейсом владельца, а не доказательством полностью восстановленного YouTube Factory.

## Проверки и восстановление

1. `systemctl is-active hapych-factory-portal.service hapych-factory-tts.service hapych-factory-voice-tunnel.service`; `curl -I https://voice.hapychrust.ru/login` (использовать GET для HTML) и `curl -fsS https://voice.hapychrust.ru/health`.
2. Если портал недоступен, проверить собственный systemd unit, порт `127.0.0.1:8078` и path rule Cloudflare, **не перезапускать существующий VPN и не удалять сервис 8077**.
3. Если смена маршрутизации ломает API, вернуть сохранённый `voice-tunnel.pre-portal-20261101.yml` и перезапустить **только выделенный** `hapych-factory-voice-tunnel.service`.
4. Деплой изменений: обновлять `live_portal.py` из проверенного Git commit; запускать `test_live_portal.py`; менять портал через `systemctl restart hapych-factory-portal.service` (TTS не трогать).
5. Держать обязательную точку восстановления Factory в `docs/FACTORY_RECOVERY_CHECKPOINT_RU.md` и issue #80, указывать run ID, SHA, состояния.

## Не перепутать с выпуском Shorts

После PR #84 успешно закончился **автоматический третий приватный** [daily-preview run 41318314496](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41318314496), artifact `13088023430`. Это лишь факт генерации и автоматической QA-цепочки. **Визуально-смысловая проверка исправленного MP4 и независимое сравнение тембра Deep ещё не подтверждены**, `auto_publish=false` не менять. Нет новых подтверждённых публичных Shorts / заполненного Buffer. В последнем [autofill run 41325408427](https://github.com/GUSTAVA009/moto-shorts-cloud/actions/runs/41325408427) по-прежнему failure; запас законных кадров недостаточен.
