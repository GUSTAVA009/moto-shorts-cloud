"use strict";
const form=document.getElementById("login-form");
const button=document.getElementById("login-button");
const error=document.getElementById("error");
form.addEventListener("submit",async(event)=>{
 event.preventDefault();error.textContent="";button.disabled=true;
 try {
  const response=await fetch("/auth/login",{
   method:"POST",credentials:"same-origin",cache:"no-store",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({password:document.getElementById("password").value})
  });
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(response.status===429?"Временно заблокировано: слишком много попыток входа.":"Доступ не подтверждён.");
  document.getElementById("password").value="";
  window.location.replace("/");
 }catch(err){error.textContent=err.message||"Ошибка входа";button.disabled=false;}
});
