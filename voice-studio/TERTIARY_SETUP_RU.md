# Третья ступень TTS — Chatterbox Multilingual V3 (GUSTAVA)

Статус: **код интеграции и тесты**; НЕ доказательство запущенного сервера.
Нужен третий **физически независимый** хост: не тот облачный Qwen и
не тот Windows-PC, который используется второй ступенью. Если такого
хоста нет, нельзя утверждать, что третий резерв «доступен».
Бесплатность весов MIT не равна бесплатной круглосуточной машине.

## API третьего источника

`voice-studio/tertiary_chatterbox.py` — закрытый FastAPI:
`POST /v1/audio/speech`; русский `language_id=ru`; Chatterbox Multilingual V3;
`Authorization: Bearer gvk_...`; `X-Idempotency-Key: episode-id`.
Обязательны `voice=gustava-original-v1`, `channel_slug=gustava`,
`response_format=wav`. Только проверенный референс WAV из **частного
каталога машины**, никогда из публичного GitHub. Простой HTTP в интернете
запрещён — нужен HTTPS c проверенным сертификатом.

У сервера отдельный ключ, SHA-256 исходного эталона и idempotency cache;
ключ не должен совпадать с ключами облака и Windows. Никакого открытого
веб-интерфейса для всех пользователей. Дополнительно ограничьте доступ
в фаерволе и установите безопасный reverse proxy. Запускать на
отдельной машине, не открывать порт приложения наружу.

## Развёртывание при наличии третьей машины

1. Установить Python 3.11, ffmpeg, Git, совместимые PyTorch/CUDA-драйверы
   (если есть NVIDIA). Создать private working directory и venv.
2. Скопировать только исходный код `voice-studio` и выполнить
   `pip install -r voice-studio/requirements-chatterbox.txt`.
   Модель Chatterbox v3 загрузится при первом реальном запросе.
3. Поместить туда **заранее одобренный самим владельцем голосовой эталон**
   (например, `/opt/hapych/private/owner-reference.wav`), доступный только
   сервисному пользователю; он не должен быть чужим голосом или личным видео.
4. Создать секреты **вне Git**:
   - `GUSTAVA_TERTIARY_TTS_ENABLED=1`
   - `GUSTAVA_TERTIARY_VOICE_API_KEY=gvk_<48+ random chars>`
   - `GUSTAVA_TERTIARY_REFERENCE_WAV=/private/path/owner-reference.wav`
   - `GUSTAVA_VOICE_REFERENCE_SHA256=<SHA-256 именно этого WAV>`
   - `GUSTAVA_TERTIARY_CACHE_DIR=/private/tts-cache`
   - `GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED=0` (сначала закрыто)
5. Протестировать API **локально** с тестовым русским текстом, при
   закрытом CANARY перейти в контролируемый staging и временно разрешить
   CANARY только для одного владельческого теста. Проверить русский ASR,
   полноту слов, характер голоса и контрольные хеши. Нельзя утверждать,
   что Chatterbox точно воспроизводит тембр Qwen без прослушивания.
6. Запустить с единственным worker под ограниченным системным пользователем:
   `uvicorn tertiary_chatterbox:app --host 127.0.0.1 --port 8077 --workers 1`
   из папки `voice-studio`, только за собственным HTTPS reverse proxy.
7. В GitHub Repository Settings > Actions > Variables установить:
   `GUSTAVA_TERTIARY_TTS_ENABLED=1`,
   `GUSTAVA_TERTIARY_VOICE_API_URL=https://backup-voice.example.org/v1/audio/speech`,
   `GUSTAVA_TERTIARY_VOICE_APPROVED_HOST=backup-voice.example.org`,
   `GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED=1` — **только после успешного
   контрольного теста**. В Actions Secrets установить
   `GUSTAVA_TERTIARY_VOICE_API_KEY`, не писать его в репозиторий.
   У всех трёх маршрутов одинаковый закреплённый
   `GUSTAVA_VOICE_REFERENCE_SHA256`; иной эталон нельзя подменять.
8. Для локального Windows-пути (маршрут №2) аналогично задать:
   `GUSTAVA_LOCAL_TTS_ENABLED`,
   `GUSTAVA_LOCAL_VOICE_API_URL`,
   `GUSTAVA_LOCAL_VOICE_APPROVED_HOST`,
   Secret `GUSTAVA_LOCAL_VOICE_API_KEY`.
   Этот маршрут требует работающий HTTPS-туннель к уже запущенному
   владельческому API Qwen3, а не только подключение Windows к Wi-Fi.

## Failover и завод

`cloud-shorts/voice_failover.py` пробует облачный Qwen, затем Windows,
затем Chatterbox v3. Переключение **только** для недоступности транспорта
и временных кодов 408/429/500/502/503/504. Ошибки 401/403, иной voice
id, иной channel slug, неверные WAV/SHA или неподходящий TTS backend
останавливают генерацию. Готовый MP4 будет считаться готовым только
после независимых исходного и смешанного ASR, проверки кадра, одобрения
и отдельных квитанций отправки Buffer и реальной YouTube-публикации.

Переключение не отключает нынешний триггер «очередь Buffer 0–1» и не
меняет 400/месяц на фиктивные голосовые запросы. Старые DEEP WAV/MP3
и сведения о публикациях остаются неизменными. Ни Silero, ни V6, ни
Kokoro не включаются.
