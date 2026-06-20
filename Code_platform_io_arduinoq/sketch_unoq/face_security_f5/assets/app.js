// ============================================================================
//  app.js  -  EMBEBIDOS_1 / Fase 4  -  Logica del portal WiFi
//  Ing 2 (firmware embedded)
// ----------------------------------------------------------------------------
//  Habla con la API REST del brick web_ui (python/main.py):
//    GET  /api/status   estado actual
//    POST /api/save     guarda 2 redes
//    POST /api/reset    reset de fabrica
//
//  El prefijo de rutas del brick puede ser "" o "/api" segun version; por eso
//  apiFetch() prueba "/api/<x>" y, si da 404, cae a "/<x>".
// ============================================================================
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var form = $("form"), msg = $("msg"), saveBtn = $("saveBtn"), resetBtn = $("resetBtn");
  var dot = $("dot"), statusText = $("statusText");

  // Llama a la API probando con prefijo /api y sin el.
  function apiFetch(path, opts) {
    return fetch("/api/" + path, opts).then(function (r) {
      if (r.status === 404) return fetch("/" + path, opts);
      return r;
    });
  }

  function setMsg(text, kind) {
    msg.textContent = text || "";
    msg.className = "msg" + (kind ? " " + kind : "");
  }

  function renderStatus(s) {
    var state = (s && s.state) || "unknown";
    dot.className = "dot";
    if (state === "ap") {
      dot.classList.add("ap");
      statusText.textContent = "Modo AP — esperando configuracion";
    } else if (state === "client") {
      dot.classList.add("client");
      statusText.textContent = "Conectado" + (s.ssid ? " a " + s.ssid : "") + (s.ip ? " · " + s.ip : "");
    } else if (state === "saving") {
      dot.classList.add("ap");
      statusText.textContent = "Guardando y conectando...";
    } else if (state === "error") {
      dot.classList.add("err");
      statusText.textContent = "No se pudo conectar — revisa las credenciales";
    } else {
      statusText.textContent = "Estado: " + state;
    }
  }

  function refreshStatus() {
    apiFetch("status")
      .then(function (r) { return r.json(); })
      .then(renderStatus)
      .catch(function () { statusText.textContent = "Sin conexion con el portal"; });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var body = {
      ssid1: $("ssid1").value.trim(),
      pass1: $("pass1").value,
      ssid2: $("ssid2").value.trim(),
      pass2: $("pass2").value
    };
    if (!body.ssid1) { setMsg("La red primaria (SSID) es obligatoria.", "err"); return; }

    saveBtn.disabled = true;
    setMsg("Enviando configuracion...", "info");
    apiFetch("save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res && res.ok) {
          setMsg("Configuracion guardada. El dispositivo se esta conectando a tu red. "
               + "Al conmutar a cliente, el AP FaceSecurity_Setup desaparecera; "
               + "reconectate a tu WiFi normal para seguir viendolo.", "ok");
        } else {
          setMsg((res && res.error) || "Error al guardar.", "err");
          saveBtn.disabled = false;
        }
      })
      .catch(function () { setMsg("Error de red al guardar.", "err"); saveBtn.disabled = false; });
  });

  resetBtn.addEventListener("click", function () {
    if (!confirm("Restablecer borrara las redes guardadas y volvera a modo AP. Continuar?")) return;
    resetBtn.disabled = true;
    setMsg("Solicitando reset...", "info");
    apiFetch("reset", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () { setMsg("Reset solicitado. Volviendo a modo AP...", "info"); })
      .catch(function () { setMsg("Error al solicitar reset.", "err"); resetBtn.disabled = false; });
  });

  refreshStatus();
  setInterval(refreshStatus, 3000);
})();
