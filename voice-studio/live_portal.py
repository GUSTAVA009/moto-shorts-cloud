#!/usr/bin/env python3
"""Isolated owner-only portal for the LIVE Qwen clone API.

The legacy factory API stays on 127.0.0.1:8077. This portal binds 8078,
does not edit the reference/Factory contract, and never reveals API keys.
"""
from __future__ import annotations

import hashlib
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import wave
import io

HOST = "127.0.0.1"
PORT = 8078
ORIGIN = "https://voice.hapychrust.ru"
PRIVATE = Path(os.environ.get("VOICE_PORTAL_PRIVATE", "/opt/hapych-factory-voice/private/portal"))
PASSWORD_FILE = PRIVATE / "password.json"
PREFS_FILE = PRIVATE / "preferences.json"
AUDIO_DIR = PRIVATE / "previews"
TTS_HOST = "http://127.0.0.1:8077"
VOICE_ID = "gustava-original-v1"
REF_SHA = "ed27b23b9f86345c45263ab28957e96fd2d399379b3ea90ed9fbc75be183a3cc"
KDF_ITERATIONS = 460000
SESSIONS = {}
ATTEMPTS = {}
JOBS = {}
LOCK = threading.RLock()
SYNTH_LOCK = threading.Lock()
MAX_JSON = 4200
EQ_FREQS = ("80", "250", "1000", "3000", "8000")
EQ_FLAT = {frequency: 0 for frequency in EQ_FREQS}
EQ_MIN_DB = -6
EQ_MAX_DB = 6


STYLE = """
:root{color-scheme:dark;font-family:Inter,system-ui,Segoe UI,Arial,sans-serif;background:#090e18;color:#f3f5fa}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 25% -25%,#16375a 0,transparent 42%),#090e18}
a{color:#85c9ff}p{line-height:1.55}.muted{color:#8a9eb5}.brand{font-weight:900;letter-spacing:.13em;font-size:1.15rem}.brand span{color:#35b5ff}
.auth{max-width:470px;margin:12vh auto;padding:38px;background:#111b2a;border:1px solid #29405e;border-radius:24px;box-shadow:0 35px 120px #0008}
.auth h1{font-size:2rem}.auth .brand{margin-bottom:42px}
input,textarea,select{display:block;width:100%;border:1px solid #35506c;border-radius:12px;background:#0a1423;padding:14px;color:white;font:inherit;outline:none}
textarea{resize:vertical;min-height:160px}input:focus,textarea:focus{border-color:#4fc2ff}
label{display:block;font-weight:650;font-size:.85rem;margin:15px 0 8px}
button{cursor:pointer;background:#2db7ff;color:#041222;border:0;border-radius:12px;padding:13px 18px;font:inherit;font-weight:800}
button:disabled{opacity:.6;cursor:wait}.secondary{background:#1b3147;color:#e8f6ff;border:1px solid #365570}
.auth button{width:100%;margin-top:20px}.error{color:#ff8c9a}.ok{color:#6de0ad}
.shell{max-width:1330px;margin:0 auto;padding:26px 26px 60px;display:grid;grid-template-columns:230px 1fr;gap:30px}
aside{padding:25px 15px;border-right:1px solid #20334b;min-height:90vh}
aside a{display:block;text-decoration:none;color:#a4b7c9;margin-top:24px;font-weight:600}
aside a:hover{color:#fff}.tag{display:inline-block;color:#9bddff;background:#143750;padding:5px 10px;border-radius:24px;font-size:.72rem}
header{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:22px}
h1{font-size:2.25rem;line-height:1.15;margin:5px 0 15px}h2{font-size:1.2rem;margin-top:0}
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(290px,1fr);gap:20px}
.panel{background:#111b2a;border:1px solid #243c58;border-radius:18px;padding:24px;margin-bottom:18px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.kpi{padding:18px;background:#0d1725;border-radius:12px}
.kpi b{font-size:1.12rem;display:block;margin:8px 0}.kpi span{color:#9aabc0;font-size:.78rem}
select{appearance:auto}.two{display:flex;gap:12px;align-items:end}.two>*{flex:1}.inline-action{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.eq-row{display:grid;grid-template-columns:55px minmax(0,1fr) 55px;gap:11px;align-items:center;margin:9px 0}
.eq-row label{margin:0;font-size:.83rem;color:#a4dfff}
.eq-row output{text-align:right;font-size:.83rem;color:#f0f5fc;font-variant-numeric:tabular-nums}
.eq-row input[type=range]{padding:0;background:transparent;accent-color:#33b9ff;border:0;height:20px}
.eq-box{padding:12px 14px;border:1px solid #2a4965;background:#0c1929;border-radius:12px}
.eq-help{font-size:.83rem;color:#96aec8}
.pw-hint{font-size:.8rem;color:#9eb5c9}
audio{width:100%;margin:14px 0}small{color:#a0afc2}.feedback{min-height:22px}.line{height:1px;background:#2a3d50;margin:22px 0}
@media(max-width:870px){.shell{display:block;padding:18px}aside{min-height:auto;border-right:0;padding:12px 5px 22px}aside a{display:inline-block;margin:12px 16px 0 0}.grid{grid-template-columns:1fr}.kpis{grid-template-columns:1fr}.auth{margin:8vh 14px}}
"""
LOGIN_JS = """
const form=document.getElementById('login-form');
form.addEventListener('submit',async e=>{
e.preventDefault();const button=document.getElementById('login-button'),el=document.getElementById('msg');
button.disabled=true;el.textContent='';
try{const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({password:document.getElementById('password').value})});
if(!r.ok)throw Error(r.status===429?'Слишком много попыток. Повтори позже.':'Неверный ключ доступа.');
document.getElementById('password').value='';location.replace('/studio');
}catch(x){el.textContent=x.message;button.disabled=false}
});
"""
APP_JS = """
let csrf='',job=null;
const $=id=>document.getElementById(id);
const msg=(id,s)=>{$(id).textContent=s;};
const EQ_FREQS=['80','250','1000','3000','8000'];
const EQ_PRESETS={
flat:[0,0,0,0,0],
deep:[3,1,-1,1,0],
warm:[2,1,0,-1,-2],
clear:[-2,-1,0,2,2]
};
function readEq(){const v={};for(const f of EQ_FREQS)v[f]=Number($('eq-'+f).value);return v}
function drawEq(eq){
for(const f of EQ_FREQS){
const v=Number(eq?.[f]??0);
$('eq-'+f).value=Number.isInteger(v)&&v>=-6&&v<=6?v:0;
$('eq-value-'+f).textContent=(Number($('eq-'+f).value)>0?'+':'')+$('eq-'+f).value+' дБ';
}
syncEqPreset()
}
function syncEqPreset(){
const v=EQ_FREQS.map(f=>Number($('eq-'+f).value));
const match=Object.keys(EQ_PRESETS).find(p=>v.every((x,i)=>x===EQ_PRESETS[p][i]));
$('eq-preset').value=match||'custom';
}
async function api(path,method='GET',body=null){
const headers={};if(method!=='GET')headers['X-CSRF-Token']=csrf;
if(body!==null)headers['Content-Type']='application/json';
const r=await fetch(path,{method,credentials:'same-origin',cache:'no-store',headers,body:body===null?undefined:JSON.stringify(body)});
if(r.status===401){location.replace('/login');throw Error('Сессия завершена')}
if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.error||('HTTP '+r.status))}
return r.json()
}
async function boot(){
try{
const s=await api('/auth/session');csrf=s.csrf;
const p=await api('/api/portal/preferences');
$('channel-name').value=p.channel_name;$('speed').value=p.speed;$('text').value=p.text;drawEq(p.eq);
const h=await api('/api/portal/status');
$('tts').textContent=h.tts_ready?'Работает':'Недоступен';
$('tts').className=h.tts_ready?'ok':'error';
$('voice').textContent=h.voice_id;$('ref').textContent=h.reference_sha_prefix+'…';
$('factory-note').textContent='Публичная публикация YouTube и заполнение Buffer требуют отдельного подтверждения.';
$('server-status').textContent=h.tts_ready?'Qwen3 CPU доступен':'Проверка TTS не пройдена';
}catch(e){msg('feedback',e.message)}
}
$('save').onclick=async()=>{
try{
await api('/api/portal/preferences','POST',{channel_name:$('channel-name').value,speed:Number($('speed').value),text:$('text').value,eq:readEq()});
msg('feedback','Настройки сохранены. Темп и эквалайзер применяются к новым WAV-предпросмотрам.');
}catch(e){msg('feedback',e.message)}
};
$('generate').onclick=async()=>{
const button=$('generate');button.disabled=true;msg('preview-status','Генерация на сервере запущена…');
try{
const r=await api('/api/portal/preview','POST',{text:$('text').value,speed:Number($('speed').value),eq:readEq()});
job=r.job_id;poll();
}catch(e){msg('preview-status',e.message);button.disabled=false}
};
async function poll(){
if(!job)return;
let pending=false;
try{
const s=await api('/api/portal/preview/'+job);
if(s.state==='pending'||s.state==='running'){pending=true;msg('preview-status','Озвучка '+(s.state==='running'?'создаётся':'ожидает')+'…');setTimeout(poll,2500);return}
if(s.state!=='done')throw Error(s.error||'Генерация отклонена');
$('player').src='/api/portal/audio/'+job;
$('download').href='/api/portal/audio/'+job;
$('result-audio').hidden=false;
msg('preview-status','Реальный WAV готов, '+s.duration_seconds+' с. Не является одобрением тембра Deep для автопубликации.');
}catch(e){msg('preview-status',e.message)}
finally{if(!pending)$('generate').disabled=false}
}
$('change').onclick=async()=>{
const current=$('old-password').value, next=$('new-password').value, confirm=$('confirm-password').value;
if(!current)return msg('security-msg','Введите действующий пароль, с которым вошли в кабинет.');
if(next.length<14)return msg('security-msg','Новый пароль слишком короткий: нужно минимум 14 символов. Сейчас: '+next.length+'.');
if(next.length>128)return msg('security-msg','Новый пароль должен быть не длиннее 128 символов.');
if(next!==confirm)return msg('security-msg','Новый пароль и подтверждение не совпадают.');
if(current===next)return msg('security-msg','Новый пароль должен отличаться от текущего.');
const button=$('change');button.disabled=true;
try{
const changed=await api('/auth/change-password','POST',{current,next});
csrf=changed.csrf;
$('old-password').value='';$('new-password').value='';$('confirm-password').value='';
msg('password-length','Минимум 14 символов.');
msg('security-msg','Пароль успешно изменён. Текущий вход сохранён, остальные сеансы завершены.');
}catch(e){
const messages={
CURRENT_PASSWORD_INCORRECT:'Неверный текущий пароль. Вводи только значение пароля, без INITIAL_OWNER_PASSWORD=.',
NEW_PASSWORD_MIN_14_CHARACTERS:'Новый пароль должен содержать минимум 14 символов.',
NEW_PASSWORD_TOO_LONG:'Максимальная длина нового пароля — 128 символов.',
NEW_PASSWORD_MUST_DIFFER:'Новый пароль должен отличаться от текущего.',
PASSWORD_REQUIRED:'Заполни оба поля.',
NEW_PASSWORD_MUST_NOT_MATCH_CURRENT:'Новый пароль должен отличаться от текущего.'
};
msg('security-msg',messages[e.message]||e.message);
}finally{button.disabled=false}
};
$('new-password').addEventListener('input',()=>{
const n=$('new-password').value.length;
msg('password-length',n>=14?'Длина: '+n+' — подходит.':'Длина: '+n+' из минимум 14 символов.');
});
$('eq-preset').addEventListener('change',()=>{
const preset=EQ_PRESETS[$('eq-preset').value];
if(preset)drawEq(Object.fromEntries(EQ_FREQS.map((f,i)=>[f,preset[i]])));
});
for(const f of EQ_FREQS)$('eq-'+f).addEventListener('input',()=>drawEq(readEq()));
$('eq-reset').onclick=()=>drawEq(Object.fromEntries(EQ_FREQS.map(f=>[f,0])));

$('logout').onclick=async()=>{await api('/auth/logout','POST');location.replace('/login')};
boot();
"""
LOGIN_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HAPYCH Voice — вход</title><link rel="stylesheet" href="/portal-assets/site.css"><script defer src="/portal-assets/login.js"></script></head><body>
<main class="auth"><div class="brand">◈ HAPYCH <span>VOICE</span></div><span class="tag">ЗАКРЫТЫЙ КАБИНЕТ</span>
<h1>Вход в студию</h1><p class="muted">Только владелец. Управление персональными предпросмотрами озвучки на своём сервере Qwen3.</p>
<form id="login-form"><label for="password">Личный пароль</label><input id="password" type="password" autocomplete="current-password" minlength="14" required placeholder="Пароль владельца">
<button id="login-button" type="submit">Войти в кабинет →</button></form><p id="msg" class="error" role="alert"></p>
<small>HTTPS · Защищённая сессия · Без платных голосовых API</small></main></body></html>"""
APP_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HAPYCH Voice — мой кабинет</title><link rel="stylesheet" href="/portal-assets/site.css"><script defer src="/portal-assets/app.js"></script></head><body><div class="shell">
<aside><div class="brand">◈ HAPYCH <span>VOICE</span></div><p class="muted">Личная студия владельца</p>
<a href="#status">● Состояние</a><a href="#studio">◈ Озвучка</a><a href="#settings">⚙ Настройки</a><a href="#security">⌘ Безопасность</a>
<p style="margin-top:36px"><button id="logout" class="secondary">Выйти</button></p></aside>
<main><header><div><span class="tag">OWNER CONTROL CENTER</span><h1>Мой кабинет</h1><p class="muted">Живая студия озвучки для GUSTAVA, не демонстрационная страница.</p></div><span class="tag" id="server-status">Проверяем</span></header>
<section id="status" class="panel"><h2>Состояние голосового сервера</h2><div class="kpis"><div class="kpi"><span>Qwen3-TTS · облако</span><b id="tts">Проверяем</b></div>
<div class="kpi"><span>Закреплённый профиль</span><b id="voice">…</b></div><div class="kpi"><span>SHA эталона</span><b id="ref">…</b></div></div>
<p id="factory-note" class="muted"></p></section>
<div class="grid"><section id="studio" class="panel"><h2>◈ Создать предпросмотр</h2>
<p class="muted">Настоящий русский WAV на приватном Qwen3. Автовыпуск остаётся закрытым до проверки тембра, текста и видеокадров.</p>
<label for="text">Текст диктора (до 400 символов)</label><textarea id="text" maxlength="400" placeholder="Напиши текст для теста русского голоса…"></textarea>
<div class="two"><div><label for="speed">Темп речи</label><select id="speed"><option value="0.85">0.85× мягче</option><option value="0.90">0.90×</option><option value="0.95">0.95×</option><option value="1.00">1.00× оригинал</option><option value="1.05">1.05×</option><option value="1.10">1.10×</option><option value="1.15">1.15× быстрее</option></select></div><div><label>Синтез</label><button id="generate">▶ Сгенерировать WAV</button></div></div>
<p id="preview-status" class="feedback" role="status"></p>
<div id="result-audio" hidden><audio id="player" controls></audio><a id="download" download="gustava-private-preview.wav">Скачать WAV</a></div></section>
<div><section id="settings" class="panel"><h2>⚙ Настройки кабинета</h2><label for="channel-name">Название канала в кабинете</label><input id="channel-name" maxlength="72">
<p class="muted">Сохраняются название, черновик и темп предпросмотра. Основной голос Factory и правила публикации остаются защищены.</p>
<button id="save" class="secondary">Сохранить настройки</button><p id="feedback" class="feedback"></p></section>
<section id="eq" class="panel"><h2>🎚 Эквалайзер голоса</h2>
<p class="eq-help">5 полос, от −6 до +6 дБ. Настройка реально применяется к WAV-предпросмотру, а не к исходному голосу завода.</p>
<label for="eq-preset">Звучание</label>
<select id="eq-preset"><option value="flat">Нейтральное</option><option value="deep">Глубже и объёмнее</option><option value="warm">Тёплый баритон</option><option value="clear">Чёткая дикция</option><option value="custom" disabled>Ручная настройка</option></select>
<div class="eq-box">
<div class="eq-row"><label for="eq-80">80 Гц</label><input id="eq-80" type="range" min="-6" max="6" step="1" value="0"><output id="eq-value-80">0 дБ</output></div>
<div class="eq-row"><label for="eq-250">250 Гц</label><input id="eq-250" type="range" min="-6" max="6" step="1" value="0"><output id="eq-value-250">0 дБ</output></div>
<div class="eq-row"><label for="eq-1000">1 кГц</label><input id="eq-1000" type="range" min="-6" max="6" step="1" value="0"><output id="eq-value-1000">0 дБ</output></div>
<div class="eq-row"><label for="eq-3000">3 кГц</label><input id="eq-3000" type="range" min="-6" max="6" step="1" value="0"><output id="eq-value-3000">0 дБ</output></div>
<div class="eq-row"><label for="eq-8000">8 кГц</label><input id="eq-8000" type="range" min="-6" max="6" step="1" value="0"><output id="eq-value-8000">0 дБ</output></div>
</div><button type="button" class="secondary" id="eq-reset">Сбросить эквалайзер</button>
<p class="eq-help">Для сохранения нажми «Сохранить настройки» выше. Для сравнения с оригиналом выбери «Нейтральное».</p></section>
<section id="security" class="panel"><h2>⌘ Сменить пароль</h2>
<label for="old-password">Текущий пароль</label><input id="old-password" type="password" autocomplete="current-password">
<p class="pw-hint">Если копируешь из начального файла, бери только значение после знака =.</p>
<label for="new-password">Новый пароль</label><input id="new-password" type="password" autocomplete="new-password" minlength="14" maxlength="128">
<p id="password-length" class="pw-hint">Минимум 14 символов.</p>
<label for="confirm-password">Повтори новый пароль</label><input id="confirm-password" type="password" autocomplete="new-password" minlength="14" maxlength="128">
<button id="change" type="button" class="secondary">Сменить пароль</button><p id="security-msg" class="feedback" role="status" aria-live="polite"></p></section></div></div>
<p class="muted"><small>Рабочее API YouTube Factory остаётся независимо доступным по /v1/audio/speech · Без подмены голоса и обхода QA.</small></p></main></div></body></html>"""

def ensure_dirs():
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(PRIVATE, 0o700)
    os.chmod(AUDIO_DIR, 0o700)

def password_record(value):
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, KDF_ITERATIONS)
    return {"salt": salt.hex(), "digest": digest.hex(), "iterations": KDF_ITERATIONS}

def verify_password(value):
    try:
        saved = json.loads(PASSWORD_FILE.read_text())
        salt = bytes.fromhex(saved["salt"])
        expected = bytes.fromhex(saved["digest"])
        iterations = int(saved["iterations"])
        if not 200000 <= iterations <= 1000000:
            return False
        result = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, iterations)
        return hmac.compare_digest(result, expected)
    except (OSError, ValueError, KeyError, TypeError):
        return False

def atomic_json(path, data):
    tmp = path.with_name(path.name + "." + secrets.token_hex(5) + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)

def validate_eq(value):
    if not isinstance(value, dict) or set(value) != set(EQ_FREQS):
        raise ValueError("INVALID_EQ_BANDS")
    if any(type(value[f]) is not int or not EQ_MIN_DB <= value[f] <= EQ_MAX_DB
           for f in EQ_FREQS):
        raise ValueError("INVALID_EQ_DB")
    return {f: value[f] for f in EQ_FREQS}

def voice_filters(speed, eq):
    """Safe ffmpeg allowlisted equalizer: no user-supplied filter strings."""
    result = [] if speed == 1.0 else [f"atempo={speed:.2f}"]
    for f in EQ_FREQS:
        if eq[f]:
            result.append(f"equalizer=f={f}:t=q:w=1.0:g={eq[f]}")
    if any(eq.values()):
        result.append("alimiter=limit=0.95:level=false")
    return result

def get_preferences():
    default = {"channel_name": "GUSTAVA Enduro", "speed": 1.0, "text": "", "eq": dict(EQ_FLAT)}
    try:
        value = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        prefs = {k: value.get(k, v) for k, v in default.items()}
        try:
            prefs["eq"] = validate_eq(prefs["eq"])
        except ValueError:
            prefs["eq"] = dict(EQ_FLAT)
        return prefs
    except (OSError, ValueError, TypeError):
        return default

def new_session():
    token = secrets.token_urlsafe(36)
    csrf = secrets.token_urlsafe(32)
    with LOCK:
        SESSIONS[token] = (time.time() + 8 * 3600, csrf)
    return token

def owner_cookie(token):
    return "hapych_portal=" + token + "; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=28800"

def check_session(headers):
    jar = SimpleCookie()
    try:
        jar.load(headers.get("Cookie", ""))
    except Exception:
        return None
    item = jar.get("hapych_portal")
    if not item:
        return None
    with LOCK:
        session = SESSIONS.get(item.value)
        if session and session[0] > time.time():
            return item.value, session[1]
    return None

def runtime_health():
    req = Request(TTS_HOST + "/health", headers={"User-Agent": "HAPYCH-owner-portal"})
    try:
        with urlopen(req, timeout=4) as resp:
            data = json.load(resp)
            return bool(data.get("tts_ready_for_private_request") is True)
    except (OSError, HTTPError, URLError, ValueError):
        return False

def generate_job(job_id, text, speed, eq):
    with LOCK:
        JOBS[job_id]["state"] = "running"
    try:
        if not SYNTH_LOCK.acquire(timeout=1):
            raise RuntimeError("Голосовой сервер занят другим предпросмотром.")
        try:
            key = os.environ.get("OWNER_TTS_API_KEY", "")
            if not re.fullmatch(r"gvk_[A-Za-z0-9_-]{40,64}", key):
                raise RuntimeError("Не подключён закрытый ключ голосового API.")
            payload = json.dumps({
                "text": text, "voice": VOICE_ID, "channel_slug": "gustava",
                "response_format": "wav"
            }, ensure_ascii=False).encode("utf-8")
            request = Request(TTS_HOST + "/v1/audio/speech", data=payload, method="POST",
                              headers={"Authorization": "Bearer " + key,
                                       "Content-Type": "application/json",
                                       "X-Idempotency-Key": "ownerportal-" + job_id})
            with urlopen(request, timeout=350) as response:
                if response.status != 200 or response.headers.get("Content-Type") != "audio/wav":
                    raise RuntimeError("Голосовой API не вернул WAV.")
                data = response.read(12_000_001)
                sha = response.headers.get("X-Audio-SHA256", "")
                ref = response.headers.get("X-Reference-SHA256", "")
                vid = response.headers.get("X-Voice-ID", "")
            if len(data) > 12_000_000 or hashlib.sha256(data).hexdigest() != sha or ref != REF_SHA or vid != VOICE_ID:
                raise RuntimeError("Контроль качества WAV: неверная SHA или идентичность голоса.")
            filters = voice_filters(speed, eq)
            if filters:
                source = AUDIO_DIR / (job_id + ".source.wav")
                target = AUDIO_DIR / (job_id + ".processed.wav")
                source.write_bytes(data)
                os.chmod(source, 0o600)
                try:
                    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
                                    "-i",str(source),"-filter:a",",".join(filters),
                                    "-ar","24000","-ac","1","-c:a","pcm_s16le",str(target)],
                                   check=True, timeout=65, capture_output=True)
                    data = target.read_bytes()
                finally:
                    source.unlink(missing_ok=True)
                    target.unlink(missing_ok=True)
            with wave.open(io.BytesIO(data), "rb") as wav:
                if wav.getnchannels() != 1 or wav.getframerate() != 24000 or wav.getsampwidth() != 2:
                    raise RuntimeError("Неверный аудиоформат.")
                duration = round(wav.getnframes() / 24000, 2)
                if not 2 <= duration <= 45:
                    raise RuntimeError("Неверная длительность WAV.")
            if not data or len(data) > 12_000_000:
                raise RuntimeError("AUDIO_INVALID_OUTPUT_SIZE")
            final = AUDIO_DIR / (job_id + ".wav")
            final.write_bytes(data)
            os.chmod(final, 0o600)
            with LOCK:
                JOBS[job_id].update(state="done", duration_seconds=duration)
        finally:
            SYNTH_LOCK.release()
    except Exception:
        with LOCK:
            JOBS[job_id].update(state="failed", error="Генерация не выполнена. Проверь статус сервера или попробуй другой короткий текст.")

class PortalHandler(BaseHTTPRequestHandler):
    server_version = "HAPYCH-Private-Portal/1"
    sys_version = ""
    def log_message(self, format, *args):
        # Never log cookies, passwords, prompts or request URL tokens.
        return
    def send(self, status, data, kind="application/json; charset=utf-8", extra=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store, private")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; media-src 'self'; connect-src 'self'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        if extra:
            for k,v in extra.items():
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def json(self, status, obj, extra=None):
        return self.send(status, json.dumps(obj, ensure_ascii=False), extra=extra)
    def error(self, status, message):
        return self.json(status, {"error": message})
    def redirect(self, where):
        return self.send(303, b"", extra={"Location": where})
    def authorized(self, csrf=False):
        session = check_session(self.headers)
        if not session:
            self.error(401, "OWNER_SESSION_REQUIRED")
            return None
        if csrf and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session[1]):
            self.error(403, "CSRF_CHECK_FAILED")
            return None
        return session
    def body(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("EXPECTED_JSON")
        length = int(self.headers.get("Content-Length", "0"))
        if not 2 <= length <= MAX_JSON:
            raise ValueError("INVALID_BODY_SIZE")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("INVALID_REQUEST")
        return value
    def request_path(self):
        return self.path.split("?",1)[0]
    def do_GET(self):
        path = self.request_path()
        if path == "/":
            return self.redirect("/studio")
        if path == "/login":
            if check_session(self.headers):
                return self.redirect("/studio")
            return self.send(200, LOGIN_HTML, "text/html; charset=utf-8")
        if path == "/portal-assets/site.css":
            return self.send(200, STYLE, "text/css; charset=utf-8")
        if path == "/portal-assets/login.js":
            return self.send(200, LOGIN_JS, "application/javascript; charset=utf-8")
        if path == "/portal-assets/app.js":
            if not self.authorized():return
            return self.send(200, APP_JS, "application/javascript; charset=utf-8")
        if path == "/studio":
            if not check_session(self.headers):
                return self.redirect("/login")
            return self.send(200, APP_HTML, "text/html; charset=utf-8")
        if path == "/auth/session":
            session = self.authorized()
            if session:
                return self.json(200, {"csrf": session[1]})
            return
        if path == "/api/portal/status":
            if not self.authorized():return
            return self.json(200, {"tts_ready": runtime_health(), "voice_id": VOICE_ID,
                                   "reference_sha_prefix": REF_SHA[:16],
                                   "youtube_publication_confirmed": False})
        if path == "/api/portal/preferences":
            if not self.authorized():return
            return self.json(200, get_preferences())
        if path.startswith("/api/portal/preview/"):
            if not self.authorized():return
            job = path.rsplit("/",1)[-1]
            session = check_session(self.headers)
            with LOCK:
                value = JOBS.get(job)
                if not value or value["owner"] != session[0]:
                    return self.error(404, "PREVIEW_NOT_FOUND")
                snapshot = {k:v for k,v in value.items() if k in ("state","duration_seconds","error")}
            return self.json(200, snapshot)
        if path.startswith("/api/portal/audio/"):
            if not self.authorized():return
            job = path.rsplit("/",1)[-1]
            session = check_session(self.headers)
            with LOCK:
                value = JOBS.get(job)
                if not value or value["owner"] != session[0] or value["state"]!="done":
                    return self.error(404, "AUDIO_NOT_FOUND")
            file = AUDIO_DIR / (job + ".wav")
            if not re.fullmatch("[a-f0-9]{32}",job) or not file.is_file():
                return self.error(404, "AUDIO_NOT_FOUND")
            return self.send(200, file.read_bytes(), "audio/wav",
                             {"Content-Disposition": 'attachment; filename="gustava-preview.wav"'})
        return self.error(404, "NOT_FOUND")
    def do_POST(self):
        path = self.request_path()
        if self.headers.get("Origin") != ORIGIN:
            return self.error(403,"ORIGIN_REJECTED")
        try:
            body = self.body()
        except (ValueError,TypeError,json.JSONDecodeError):
            return self.error(422,"INVALID_JSON")
        if path == "/auth/login":
            ip = self.headers.get("CF-Connecting-IP","")[:64] or self.client_address[0]
            now = time.time()
            with LOCK:
                history = [x for x in ATTEMPTS.get(ip, []) if x > now - 600]
                if len(history) >= 7:return self.error(429,"LOGIN_RATE_LIMIT")
                ATTEMPTS[ip] = history + [now]
            password=body.get("password")
            if not isinstance(password,str) or len(password)>256 or not verify_password(password):
                return self.error(401,"OWNER_AUTH_REQUIRED")
            with LOCK:
                ATTEMPTS[ip] = []
            try:
                (PRIVATE / 'owner-first-login.txt').unlink(missing_ok=True)
            except OSError:
                pass
            token = new_session()
            return self.json(200, {"ok":True}, {"Set-Cookie": owner_cookie(token)})
        session = self.authorized(csrf=True)
        if not session:return
        if path == "/auth/logout":
            with LOCK:
                SESSIONS.pop(session[0],None)
            return self.json(200, {"ok":True}, {"Set-Cookie":"hapych_portal=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0"})
        if path == "/auth/change-password":
            if set(body) != {"current", "next"}:
                return self.error(422, "PASSWORD_REQUIRED")
            old,new = body.get("current"),body.get("next")
            if not isinstance(old,str) or not isinstance(new,str) or not old or not new:
                return self.error(422, "PASSWORD_REQUIRED")
            if not verify_password(old):
                return self.error(403, "CURRENT_PASSWORD_INCORRECT")
            if len(new) < 14:
                return self.error(422, "NEW_PASSWORD_MIN_14_CHARACTERS")
            if len(new) > 128:
                return self.error(422, "NEW_PASSWORD_TOO_LONG")
            if old == new:
                return self.error(422, "NEW_PASSWORD_MUST_DIFFER")
            atomic_json(PASSWORD_FILE,password_record(new))
            with LOCK:
                SESSIONS.clear()
                token=new_session()
                new_csrf=SESSIONS[token][1]
            return self.json(200,{"ok":True,"csrf":new_csrf},{"Set-Cookie":owner_cookie(token)})
        if path == "/api/portal/preferences":
            if set(body) != {"channel_name","speed","text","eq"}:
                return self.error(422,"INVALID_SETTINGS")
            name, speed, script = body.get("channel_name"),body.get("speed"),body.get("text")
            try:
                eq=validate_eq(body.get("eq"))
            except ValueError:
                return self.error(422,"INVALID_EQ")
            if not isinstance(name,str) or not 2<=len(name.strip())<=72 or not isinstance(script,str) or len(script)>600 or isinstance(speed,bool) or not isinstance(speed,(float,int)) or not .85<=speed<=1.15:
                return self.error(422,"INVALID_SETTINGS")
            allowed = [0.85,0.9,0.95,1.0,1.05,1.1,1.15]
            if not any(abs(speed-x)<0.001 for x in allowed):
                return self.error(422,"UNSUPPORTED_TEMPO")
            prefs={"channel_name":name.strip(),"speed":speed,"text":script,"eq":eq}
            atomic_json(PREFS_FILE,prefs)
            return self.json(200,{"saved":True})
        if path == "/api/portal/preview":
            if set(body) != {"text","speed","eq"}:
                return self.error(422,"INVALID_PREVIEW_REQUEST")
            text,speed=body.get("text"),body.get("speed")
            if not isinstance(text,str) or not 15<=len(text.strip())<=400 or isinstance(speed,bool) or not isinstance(speed,(int,float)) or not any(abs(speed-x)<0.001 for x in [.85,.90,.95,1,1.05,1.1,1.15]):
                return self.error(422,"INVALID_PREVIEW_TEXT_OR_SPEED")
            try:
                eq=validate_eq(body.get("eq"))
            except ValueError:
                return self.error(422, "INVALID_EQ")
            with LOCK:
                active=[j for j in JOBS.values() if j["state"] in ("pending","running")]
                if active:return self.error(429,"PREVIEW_ALREADY_RUNNING")
                job=secrets.token_hex(16)
                JOBS[job]={"state":"pending","owner":session[0],"started_at":time.time()}
            threading.Thread(target=generate_job,args=(job,text.strip(),float(speed),eq),daemon=True).start()
            return self.json(202,{"job_id":job})
        return self.error(404,"NOT_FOUND")

def main():
    ensure_dirs()
    if len(sys.argv)>1 and sys.argv[1]=="--init-owner":
        if PASSWORD_FILE.exists():
            raise SystemExit("OWNER_ALREADY_INITIALIZED")
        password = secrets.token_urlsafe(30)
        atomic_json(PASSWORD_FILE,password_record(password))
        print("INITIAL_OWNER_PASSWORD="+password)
        return
    if not PASSWORD_FILE.is_file():
        raise SystemExit("OWNER_PASSWORD_NOT_INITIALIZED")
    server = ThreadingHTTPServer((HOST,PORT),PortalHandler)
    print("HAPYCH_OWNER_PORTAL_LISTENING_LOOPBACK_8078",flush=True)
    server.serve_forever(poll_interval=.25)

if __name__=="__main__":
    main()
