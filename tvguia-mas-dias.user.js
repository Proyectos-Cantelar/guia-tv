// ==UserScript==
// @name          TVguia.es · más días
// @namespace     guia-tv
// @version       1.1.0
// @description   Añade botones para navegar varios días atrás (y algunos adelante) en la parrilla de tvguia.es, que de serie solo ofrece 2 días atrás y 1 adelante.
// @match         https://www.tvguia.es/*
// @run-at        document-idle
// @grant         none
// ==/UserScript==

/*
 * Cómo funciona (por si algún día cambia el HTML):
 *  - La parrilla se pinta con window.tvmachine (template/month/day/hour/...) y la
 *    función global showTVProgram(template), que hace GET a
 *    /program/ajax/<template>/<sets>/<month>/<day>/<hour>/<minute>/<colores...>
 *  - Ese endpoint NO limita la fecha: sirve ~10 días atrás y algo más adelante.
 *    El límite de 2 días atrás es solo de la interfaz.
 *  - Sustituimos la fila de días nativa por una única fila ordenada: así el
 *    resaltado y el corte de línea son nuestros y no se mezclan con los suyos.
 */
(function () {
  'use strict';

  const DAYS_BACK = 10;      // días hacia atrás
  const DAYS_FORWARD = 3;    // días hacia adelante
  const WD = ['Do', 'Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sá'];
  const ANCHO = 54;          // px por botón: los 14 caben en los 816 del contenedor

  if (window.__tvmExtraDaysLoaded) return;
  window.__tvmExtraDaysLoaded = true;

  const botones = [];

  const hoy = () => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  };

  function fechaEn(offset) {
    const d = hoy();
    d.setDate(d.getDate() + offset);
    return d;
  }

  function urlAjax(date) {
    const t = window.tvmachine;
    return `${t.base_url}/program/ajax/${t.template}/${t.sets}/${date.getMonth() + 1}/${date.getDate()}` +
      `/${t.hour}/${t.minute}/${t.color1}/${t.color2}/${t.color3}/${t.color4}`;
  }

  // ¿Hay parrilla ese día a la hora que está seleccionada ahora mismo?
  async function hayDatos(date) {
    try {
      const res = await fetch(urlAjax(date), { credentials: 'same-origin' });
      const html = await res.text();
      return /\ba-details\b|tv-program-listing-block/.test(html);
    } catch (e) {
      return true; // ante la duda, dejamos el botón usable
    }
  }

  function marcarActivo(activo) {
    for (const b of botones) {
      b.style.backgroundColor = '';
      b.style.color = '';
    }
    if (activo) {
      activo.style.backgroundColor = '#a3d7ff';
      activo.style.color = '#000';
    }
  }

  function crearBoton(date, offset) {
    const btn = document.createElement('a');
    btn.href = 'javascript:void(0);';
    btn.className = 'tv-button';
    btn.style.width = `${ANCHO}px`;
    btn.style.marginRight = '4px';
    btn.style.textIndent = '4px';
    btn.textContent = offset === 0 ? 'Hoy' : `${WD[date.getDay()]} ${date.getDate()}`;
    btn.title = date.toLocaleDateString('es-ES', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });

    const alPulsar = (ev) => {
      if (ev && ev.__tvmHandled) return;   // evita doble disparo (listener + onclick)
      if (ev) { ev.__tvmHandled = true; ev.preventDefault(); }
      // Equivalente a callback(template, month, day, btn) sin tocar las clases del sitio.
      window.tvmachine.month = String(date.getMonth() + 1);
      window.tvmachine.day = String(date.getDate());
      marcarActivo(btn);
      showTVProgram(window.tvmachine.template);
    };
    // En tvguia.es hay scripts (anti-adblock) que parchean addEventListener, así que
    // además del listener usamos el handler DOM0 como red de seguridad.
    btn.addEventListener('click', alPulsar);
    btn.onclick = alPulsar;

    return btn;
  }

  function construirFila() {
    const nativo = document.getElementById('button-today');
    if (!nativo) return false;                        // esta página no tiene parrilla
    const fila = nativo.parentElement;
    if (fila.dataset.tvmDias === '1') return true;     // ya construida

    // Fuera los botones de día originales: solo llegan a ±2 días y su resaltado
    // se rompe al convivir con los nuestros.
    fila.querySelectorAll('a, br').forEach((el) => el.remove());
    fila.dataset.tvmDias = '1';

    botones.length = 0;
    for (let o = -DAYS_BACK; o <= DAYS_FORWARD; o++) {
      const btn = crearBoton(fechaEn(o), o);
      fila.appendChild(btn);
      botones.push(btn);
    }

    // La fila de horas viene justo después: cortamos los floats para que caiga abajo.
    const salto = document.createElement('br');
    salto.style.clear = 'both';
    fila.appendChild(salto);

    botones[DAYS_BACK].style.backgroundColor = '#a3d7ff';   // "Hoy" seleccionado
    botones[DAYS_BACK].style.color = '#000';

    // Atenuamos los días de los que no hay datos a esta hora.
    for (let o = -DAYS_BACK; o <= DAYS_FORWARD; o++) {
      const btn = botones[o + DAYS_BACK];
      hayDatos(fechaEn(o)).then((ok) => {
        if (ok) return;
        btn.style.opacity = '0.45';
        btn.title += ' (sin datos a esta hora)';
      });
    }

    return true;
  }

  // La parrilla puede cargarse más tarde; reintentamos un poco.
  let intentos = 0;
  const timer = setInterval(() => {
    if (construirFila() || ++intentos > 40) clearInterval(timer);
  }, 250);
})();
