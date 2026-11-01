"use strict";
const $ = (id) => document.getElementById(id);
let currentAudioURL = null;
let referenceAudioURL = null;
let pendingRequest = null;

function message(id, value, ok = false) {
  const node = $(id);
  node.textContent = value;
  node.classList.toggle("error", !ok && !/готов|создаётся|данных|нужны|проверь/i.test(value));
  node.classList.toggle("success", ok);
}
function adminToken() { return $("admin-token").value.trim(); }
function clientToken() { return $("client-token").value.trim(); }
function reportError(error) { return error.message || "Сервер не ответил"; }

async function jsonCall(path, method="GET", body=null, isAdmin=false) {
  const headers = {"Accept":"application/json"};
  if (body !== null) headers["Content-Type"] = "application/json";
  if (isAdmin) headers["X-Admin-Token"] = adminToken();
  const response = await fetch(path, {
    method, headers,
    body: body === null ? undefined : JSON.stringify(body),
    cache: "no-store", credentials: "omit"
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(String(data.detail || "HTTP " + response.status));
  return data;
}
async function audioCall(path, options) {
  const response = await fetch(path, {...options, credentials:"omit", cache:"no-store"});
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(String(detail.detail || "HTTP " + response.status));
  }
  const content = await response.blob();
  if (content.size < 1500 || content.type.indexOf("audio/") === -1)
    throw new Error("Пустой или неподходящий WAV от сервера");
  return {blob:content, sha:response.headers.get("X-Audio-SHA256")};
}
function updateCounter() {
  const count = $("transcript").value.length;
  $("text-count").textContent = count + " / 600";
}
async function updateStatus() {
  try {
    const r = await jsonCall("/health");
    const ready = r.reference_available === true;
    $("service-status").textContent = ready
      ? "Сервис доступен · голос создан"
      : "Сервис доступен · нужен оригинальный голос";
    $("service-status").classList.toggle("bad", !ready);
    $("original-status").textContent = ready
      ? "Эталон закреплён · готов к синтезу" : "Оригинальный голос ещё не создан";
  } catch {
    $("service-status").textContent = "Сервис недоступен";
    $("service-status").classList.add("bad");
  }
}
function showAudio(blob, type="preview") {
  const obj = URL.createObjectURL(blob);
  if (type === "reference") {
    if (referenceAudioURL) URL.revokeObjectURL(referenceAudioURL);
    referenceAudioURL = obj;
    $("reference-player").hidden = false;
    $("reference-audio").src = obj;
    return;
  }
  if (currentAudioURL) URL.revokeObjectURL(currentAudioURL);
  currentAudioURL = obj;
  $("player-wrap").hidden = false;
  $("player").src = obj;
  $("download-audio").href = obj;
}
async function generate() {
  const text = $("transcript").value.trim();
  const token = clientToken();
  if (!token) return message("generate-result","Нужен собственный API-ключ формата gvk_…");
  if (!text || text.length > 600)
    return message("generate-result","Текст должен содержать от 1 до 600 символов");
  const fp = text + "|" + $("voice-selector").value;
  if (pendingRequest && pendingRequest.fingerprint !== fp) pendingRequest = null;
  if (!pendingRequest) pendingRequest = {
    id: "studio-" + crypto.randomUUID(), fingerprint: fp
  };
  $("generate").disabled = true;
  message("generate-result", "Генерация на собственном GPU. Повторный вызов с тем же ID не будет дублировать озвучку.");
  try {
    const result = await audioCall("/v1/audio/speech", {
      method:"POST",
      headers: {
        "Authorization":"Bearer " + token,
        "X-Idempotency-Key":pendingRequest.id,
        "Content-Type":"application/json"
      },
      body:JSON.stringify({text,voice:$("voice-selector").value,response_format:"wav"})
    });
    showAudio(result.blob);
    message("generate-result", "WAV готов. SHA-256: " + (result.sha || "проверяется"), true);
    pendingRequest = null;
  } catch (error) {
    message("generate-result", reportError(error) +
      ". При неизвестном результате не перезапускай тот же запрос с другим ID.");
  } finally { $("generate").disabled = false; }
}

function displayKeys(keys) {
  const host = $("key-list");
  host.textContent = "";
  if (!keys.length) { const p=document.createElement("p");p.className="muted";p.textContent="Ключей пока нет.";host.append(p); return; }
  for (const key of keys) {
    const line=document.createElement("div");line.className="key-line";
    const meta=document.createElement("div");
    const name=document.createElement("strong");name.textContent=key.label;
    const sub=document.createElement("small");
    sub.textContent="ID " + key.id + " · " +
      (key.revoked ? "Отозван" : "Активен") + " · " +
      (key.max_chars_month || "Без лимита") + " симв./мес · " +
      key.max_rpm + " запр./мин";
    meta.append(name,sub);line.append(meta);
    if (!key.revoked) {
      const revoke=document.createElement("button");
      revoke.type="button";revoke.textContent="Отозвать";
      revoke.addEventListener("click",async()=>{
        if (!confirm("Отозвать ключ \"" + key.label + "\"? Это отключит доступ завода, если он его использует.")) return;
        try { await jsonCall("/api/admin/keys/"+key.id,"DELETE",null,true);await refreshAdmin(); }
        catch(e) {message("owner-result",reportError(e));}
      });
      line.append(revoke);
    }
    host.append(line);
  }
}
async function refreshAdmin() {
  if (!adminToken()) return message("owner-result", "Введи секрет владельца сервера.");
  try {
    const [voice,keys] = await Promise.all([
      jsonCall("/api/admin/voice","GET",null,true),
      jsonCall("/api/admin/keys","GET",null,true)
    ]);
    $("original-status").textContent = voice.created
      ? "Закреплён · SHA " + voice.reference_sha256.slice(0,12) + "…"
      : "Не создан: один раз нажми «Создать и закрепить голос»";
    displayKeys(keys.keys);
    message("owner-result","Панель владельца доступна.",true);
  } catch(error) {message("owner-result",reportError(error));}
}
async function issueKey() {
  if (!adminToken()) return message("owner-result","Введи секрет владельца.");
  $("issue-key").disabled = true;
  try {
    const body={
      label:$("key-label").value.trim(),
      max_chars_month:Number($("key-limit").value),
      max_rpm:Number($("key-rpm").value)
    };
    const data=await jsonCall("/api/admin/keys","POST",body,true);
    $("new-key").hidden=false;
    $("issued-secret").textContent=data.api_key;
    message("owner-result","API-ключ создан. Сохрани его сейчас — потом увидеть его значение нельзя.",true);
    await refreshAdmin();
  } catch(error) {message("owner-result",reportError(error));}
  finally{$("issue-key").disabled=false;}
}
async function designVoice() {
  if (!$("original-consent").checked)
    return message("owner-result","Подтверди создание самостоятельного оригинального голоса.");
  if (!adminToken())
    return message("owner-result","Введи секрет владельца.");
  $("design-voice").disabled=true;
  message("owner-result","Qwen VoiceDesign создаёт оригинальный русский баритон. Эталон закрепится без возможности случайной перезаписи.");
  try {
    const data=await jsonCall("/api/admin/voice/design","POST",
                              {confirm_original:true},true);
    message("owner-result","Оригинальный голос создан: " +
            data.reference_sha256.slice(0,16) + "…",true);
    await refreshAdmin();
    await updateStatus();
  } catch(error){message("owner-result",reportError(error));}
  finally{$("design-voice").disabled=false;}
}
async function listenReference() {
  if (!adminToken()) return message("owner-result","Нужен секрет владельца.");
  try {
    const result=await audioCall("/api/admin/voice/reference",{
      headers:{"X-Admin-Token":adminToken()}
    });
    showAudio(result.blob,"reference");
    message("owner-result","Воспроизводится наш оригинальный закреплённый эталон.",true);
  } catch(error){message("owner-result",reportError(error));}
}
$("transcript").addEventListener("input",updateCounter);
$("generate").addEventListener("click",generate);
$("refresh-admin").addEventListener("click",refreshAdmin);
$("issue-key").addEventListener("click",issueKey);
$("design-voice").addEventListener("click",designVoice);
$("listen-reference").addEventListener("click",listenReference);
$("copy-key").addEventListener("click",async()=>{
  const token=$("issued-secret").textContent;
  try {await navigator.clipboard.writeText(token);$("copy-key").textContent="Скопировано";}
  catch{$("copy-key").textContent="Выдели ключ и скопируй вручную";}
});
updateCounter();
updateStatus();
