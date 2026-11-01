"use strict";
const $=(id)=>document.getElementById(id);
let csrf="";
let lastAudioURL=null;
let referenceURL=null;
let waitingRequest=null;
let activeChannel="gustava";
let activeVoice="gustava-original-v1";
let allChannels=[];

function channelQuery(){
 return "?channel_slug="+encodeURIComponent(activeChannel);
}
async function refreshChannels(selected){
 const data=await ownerFetch("/api/admin/channels");
 allChannels=data.channels;
 const select=$("channel-select");
 select.replaceChildren();
 for(const ch of allChannels){
  const option=document.createElement("option");
  option.value=ch.slug;option.textContent=ch.name+" · "+ch.slug;
  select.append(option);
 }
 if(!allChannels.length)throw Error("Ни одного YouTube-канала не найдено.");
 activeChannel=allChannels.some(x=>x.slug===selected)?selected:allChannels[0].slug;
 select.value=activeChannel;
 activeVoice=allChannels.find(x=>x.slug===activeChannel).voice_id;
 $("speaker-name").textContent=allChannels.find(x=>x.slug===activeChannel).name+" · Original";
 $("speaker-channel").textContent=activeChannel+" / "+activeVoice;
}
async function selectChannel(slug){
 await refreshChannels(slug);
 waitingRequest=null;
 $("client-token").value="";
 $("new-key").hidden=true;
 $("issued-secret").textContent="";
 $("player-wrap").hidden=true;
 await Promise.all([refreshStatus(),refreshKeys()]);
}
async function createChannel(){
 const button=$("create-channel");button.disabled=true;
 const payload={
  slug:$("channel-slug").value.trim(),
  name:$("channel-name").value.trim(),
  youtube_channel_id:$("youtube-channel-id").value.trim()||null,
 };
 try{
  const item=await ownerFetch("/api/admin/channels","POST",payload);
  $("channel-slug").value="";$("channel-name").value="";
  $("youtube-channel-id").value="";
  await selectChannel(item.slug);
  $("channel-result").textContent="Канал добавлен, настроен отдельный голос и пространство ключей.";
  feedback("owner-result","Оригинальный эталон для этого канала ещё не создан.");
 }catch(e){$("channel-result").textContent=e.message;}
 finally{button.disabled=false;}
}

function feedback(id,text,kind=""){
 const el=$(id);el.textContent=text;el.className="feedback"+(kind?" "+kind:"");
}
async function ownerFetch(path,method="GET",body=null,raw=false){
 const headers={};
 if(method!=="GET"){headers["X-CSRF-Token"]=csrf;}
 if(body!==null)headers["Content-Type"]="application/json";
 const response=await fetch(path,{method,credentials:"same-origin",cache:"no-store",
  headers,body:body===null?undefined:JSON.stringify(body)});
 if(response.status===401){location.replace("/login");throw Error("Сессия завершена");}
 if(!response.ok){const d=await response.json().catch(()=>({}));
  throw Error(String(d.detail||"HTTP "+response.status));}
 return raw?response:response.json();
}
async function boot(){
 try{
  const sess=await fetch("/auth/session",{credentials:"same-origin",cache:"no-store"});
  if(!sess.ok){location.replace("/login");return;}
  csrf=(await sess.json()).csrf;
  await refreshChannels(activeChannel);
  await Promise.all([refreshStatus(),refreshKeys()]);
 }catch(e){feedback("owner-result",e.message,"error");}
}
async function refreshStatus(){
 try{
  const [health,voice]=await Promise.all([
   ownerFetch("/health"),
   ownerFetch("/api/admin/voice"+channelQuery())
  ]);
  const created=voice.created===true;
  activeVoice=voice.voice_id;
  $("speaker-channel").textContent=activeChannel+" / "+activeVoice;
  $("service-status").textContent=created?"Эталон закреплён":"Эталон не создан";
  $("original-status").textContent=created?"Зафиксирован":"Не создан";
  $("service-status").parentElement.classList.toggle("offline",!created);
  $("timbre").disabled=created;$("delivery").disabled=created;
  $("design-voice").disabled=created;$("original-consent").disabled=created;
  if(created){
   $("timbre").value=voice.design?.timbre||"deep";
   $("delivery").value=voice.design?.delivery||"documentary";
   feedback("owner-result","Оригинальный эталон закреплён • SHA "+voice.reference_sha256.slice(0,16)+"…","success");
  }
 }catch(e){feedback("owner-result",e.message,"error");}
}
async function refreshKeys(){
 try{const list=await ownerFetch("/api/admin/keys"+channelQuery());
  const root=$("key-list");root.replaceChildren();
  if(!list.keys.length){const p=document.createElement("p");p.className="description";p.textContent="Ключи ещё не выдавались.";root.append(p);return;}
  for(const key of list.keys){
   const item=document.createElement("div");item.className="key-line";
   const wrap=document.createElement("div"),title=document.createElement("strong"),detail=document.createElement("small");
   title.textContent=key.label;
   detail.textContent=(key.revoked?"Отозван":"Активен")+" · "+(key.max_chars_month||"без квоты")+" симв./мес · "+key.max_rpm+" запр./мин";
   wrap.append(title,detail);item.append(wrap);
   if(!key.revoked){
    const revoke=document.createElement("button");revoke.type="button";revoke.textContent="Отозвать";
    revoke.addEventListener("click",async()=>{
     if(!confirm("Отозвать этот API-ключ? Завод может потерять доступ."))return;
     try{await ownerFetch("/api/admin/keys/"+key.id,"DELETE");await refreshKeys();}
     catch(err){feedback("owner-result",err.message,"error");}
    });item.append(revoke);
   }
   root.append(item);
  }
 }catch(e){feedback("owner-result",e.message,"error");}
}
function setAudio(blob,target){
 const obj=URL.createObjectURL(blob);
 if(target==="sample"){
  if(lastAudioURL)URL.revokeObjectURL(lastAudioURL);
  lastAudioURL=obj;$("player-wrap").hidden=false;
  $("player").src=obj;$("download-audio").href=obj;
 }else{
  if(referenceURL)URL.revokeObjectURL(referenceURL);
  referenceURL=obj;$("reference-player").hidden=false;
  $("reference-audio").src=obj;
 }
}
async function audioBlob(response){
 if(!response.ok){
  const error=await response.json().catch(()=>({}));
  throw Error(String(error.detail||"Сервис озвучки недоступен"));
 }
 const file=await response.blob();
 if(file.size<1500||!file.type.includes("audio/"))throw Error("Сервер вернул неверный WAV");
 return file;
}
async function generateAudio(){
 const text=$("transcript").value.trim(),key=$("client-token").value.trim();
 const speed=Number($("speed").value);
 if(!key){$("api-options").open=true;return feedback("generate-result","Нужен выданный владельцем API-ключ.","error");}
 if(!text||text.length>600)return feedback("generate-result","Текст должен содержать от 1 до 600 символов.","error");
 const fingerprint=JSON.stringify({text,speed,voice:activeVoice,channel_slug:activeChannel});
 if(waitingRequest&&waitingRequest.fingerprint!==fingerprint)waitingRequest=null;
 if(!waitingRequest)waitingRequest={fingerprint,key:"hapych-"+crypto.randomUUID()};
 const button=$("generate");button.disabled=true;
 feedback("generate-result","Генерация на собственном GPU…");
 try{
  const response=await fetch("/v1/audio/speech",{
   method:"POST",credentials:"omit",cache:"no-store",headers:{
    "Authorization":"Bearer "+key,"X-Idempotency-Key":waitingRequest.key,
    "Content-Type":"application/json"},
   body:JSON.stringify({text,voice:activeVoice,channel_slug:activeChannel,
    speed,response_format:"wav"})
  });
  const file=await audioBlob(response);setAudio(file,"sample");
  feedback("generate-result","WAV создан • SHA "+(response.headers.get("X-Audio-SHA256")||"")?.slice(0,16)+"…","success");
  waitingRequest=null;
 }catch(error){
  feedback("generate-result",error.message+" • При неясном результате не меняй ID запроса для слепой повторной генерации.","error");
 }finally{button.disabled=false;}
}
async function designVoice(){
 if(!$("original-consent").checked)return feedback("owner-result","Подтверди создание собственного оригинального голоса.","error");
 const button=$("design-voice");button.disabled=true;
 feedback("owner-result","Создаётся единственный оригинальный эталон. Он будет закреплён за заводом.");
 try{
  const response=await ownerFetch("/api/admin/voice/design","POST",{
   confirm_original:true,timbre:$("timbre").value,
   delivery:$("delivery").value,channel_slug:activeChannel
  });
  feedback("owner-result","Эталон создан • SHA "+response.reference_sha256.slice(0,16)+"…","success");
  await refreshStatus();
 }catch(e){feedback("owner-result",e.message,"error");}
 finally{if(!$("timbre").disabled)button.disabled=false;}
}
async function listen(){
 try{
  const response=await ownerFetch("/api/admin/voice/reference"+channelQuery(),
    "GET",null,true);
  const audio=await audioBlob(response);setAudio(audio,"reference");
 }catch(e){feedback("owner-result",e.message,"error");}
}
async function issueKey(){
 const button=$("issue-key");button.disabled=true;
 try{
  const result=await ownerFetch("/api/admin/keys","POST",{
   label:$("key-label").value.trim(),
   max_chars_month:Number($("key-limit").value),
   max_rpm:Number($("key-rpm").value),channel_slug:activeChannel
  });
  $("issued-secret").textContent=result.api_key;
  $("new-key").hidden=false;
  $("client-token").value=result.api_key; // only in memory, never localStorage
  feedback("owner-result","API-ключ выпущен. Сохрани его сейчас — повторно значение не показывается.","success");
  await refreshKeys();
 }catch(e){feedback("owner-result",e.message,"error");}
 finally{button.disabled=false;}
}
async function logout(){
 try{await ownerFetch("/auth/logout","POST");}finally{location.replace("/login");}
}
$("generate").addEventListener("click",generateAudio);
$("channel-select").addEventListener("change",e=>selectChannel(e.target.value));
$("create-channel").addEventListener("click",createChannel);
$("design-voice").addEventListener("click",designVoice);
$("listen-reference").addEventListener("click",listen);
$("issue-key").addEventListener("click",issueKey);
$("logout").addEventListener("click",logout);
$("copy-key").addEventListener("click",async()=>{
 try{await navigator.clipboard.writeText($("issued-secret").textContent);
  $("copy-key").textContent="Ключ скопирован";
 }catch{$("copy-key").textContent="Выдели ключ вручную";}
});
$("transcript").addEventListener("input",()=>{
 $("text-count").textContent=$("transcript").value.length+" / 600";
});
$("speed").addEventListener("input",()=>{
 $("speed-value").textContent=Number($("speed").value).toFixed(2)+"×";
});
$("text-count").textContent=$("transcript").value.length+" / 600";
boot();
