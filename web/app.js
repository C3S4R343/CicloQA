'use strict';

const HISTORIA_EJEMPLO = `HU-482 · Inicio de sesión en el portal

Como usuario registrado quiero iniciar sesión con mi usuario y contraseña
para acceder al catálogo de productos.

CA-1  Con credenciales válidas el usuario llega al listado de productos.
CA-2  Con credenciales inválidas se muestra un mensaje de error y no se
      permite el acceso.
CA-3  Si algún campo queda vacío se indica cuál falta.`;

const ETAPAS = [
  { id: 'analisis', nom: 'Análisis' },
  { id: 'casos', nom: 'Casos de prueba' },
  { id: 'automatizacion', nom: 'Automatización' }
];

const ESTADO_ETAPA = {
  Analizando:        { analisis: 'curso' },
  EsperaAnalisis:    { analisis: 'espera' },
  GenerandoCasos:    { analisis: 'listo', casos: 'curso' },
  EsperaCasos:       { analisis: 'listo', casos: 'espera' },
  GenerandoScripts:  { analisis: 'listo', casos: 'listo', automatizacion: 'curso' },
  EsperaScripts:     { analisis: 'listo', casos: 'listo', automatizacion: 'espera' },
  Terminado:         { analisis: 'listo', casos: 'listo', automatizacion: 'listo' },
  Cancelado:         {},
  Fallido:           {}
};
const ROTULO = { pendiente:'Pendiente', curso:'Trabajando…', espera:'Espera tu aprobación', listo:'Aprobado', alto:'Detenido' };

let ej = null;          // ejecución vigente
let trabajando = false;
let excluidos = new Set();
let salud = null;

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const hora = f => (f || '').replace('T', ' ').slice(11, 16);

async function api(ruta, opc) {
  const r = await fetch(ruta, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opc));
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(cuerpo.detail || `Error ${r.status}`);
  return cuerpo;
}

// --------------------------------------------------------------- estado

async function comprobarSalud() {
  try {
    salud = await api('/api/salud');
    const c = $('estado-api');
    if (!salud.llave_configurada) {
      c.innerHTML = '<span class="pt off"></span>sin llave de API';
    } else {
      c.innerHTML = `<span class="pt"></span>${esc(salud.modelo)} · ${esc(salud.entorno.nombre)}`;
    }
    $('pie').textContent = `Corre en tu máquina. Gasto del mes: $${salud.gasto_mes_usd.toFixed(4)} de $${salud.tope_usd.toFixed(2)} USD.`;
  } catch (e) {
    $('estado-api').innerHTML = '<span class="pt off"></span>servidor no disponible';
  }
}

function estadoDe(id) {
  if (!ej) return 'pendiente';
  if (ej.estado === 'Cancelado' || ej.estado === 'Fallido') {
    const previas = ETAPAS.map(e => e.id);
    const idx = previas.indexOf(ej.etapa_corte || id);
    return id === (ej.etapa_corte || '') ? 'alto' : 'pendiente';
  }
  return (ESTADO_ETAPA[ej.estado] || {})[id] || 'pendiente';
}

function pintarTuberia() {
  $('tuberia').innerHTML = ETAPAS.map((e, i) => {
    const s = trabajando && !ej ? 'pendiente' : estadoDe(e.id);
    const v = ej && ej.versiones ? ej.versiones[e.id] : null;
    return `<div class="etapa" data-e="${s}">
      <div class="e-top"><span class="e-n">${String(i + 1).padStart(2, '0')}</span>
      ${v > 1 ? `<span class="pill p-n">v${v}</span>` : ''}</div>
      <div class="e-nom">${e.nom}</div><div class="e-est">${ROTULO[s]}</div></div>`;
  }).join('');
}

function pintarBitacora() {
  const l = $('bit-l'), b = (ej && ej.bitacora) || [];
  $('bit-n').textContent = b.length ? `${b.length} registros` : 'Sin movimientos';
  l.innerHTML = b.length ? b.map(e => `
    <div class="ent" data-k="${esc(e.clase)}"><div class="ent-b"></div><div class="ent-c">
      <div class="ent-h"><span class="ent-t">${hora(e.fecha)}</span><span class="ent-a">${esc(e.accion)}</span></div>
      <div class="ent-n">${esc(ROTULO_ETAPA[e.etapa] || e.etapa)}${e.nota ? ' · “' + esc(e.nota) + '”' : ''}</div>
    </div></div>`).join('')
    : '<p style="color:var(--fg-3);font-size:12.5px">Cada decisión queda registrada aquí con su hora y su nota.</p>';
  l.scrollTop = l.scrollHeight;
}
const ROTULO_ETAPA = { analisis:'Análisis', casos:'Casos de prueba', automatizacion:'Automatización' };

// --------------------------------------------------------------- vistas

function cab(tit, sub, extra) {
  return `<div class="t-cab"><div><div class="t-tit">${tit}</div><div class="t-sub">${sub}</div></div>${extra || ''}</div>`;
}

function vistaInicio(error) {
  const sinLlave = salud && !salud.llave_configurada;
  return cab('Nueva solicitud', 'Escribe o pega la historia de usuario. Los casos los genera el sistema.') +
  `<div class="t-cuerpo">
    ${error ? `<div class="aviso err">${esc(error)}</div>` : ''}
    ${sinLlave ? `<div class="aviso err">No hay llave de API. Define ANTHROPIC_API_KEY y reinicia el servidor.</div>` : ''}
    <div style="margin-top:${error || sinLlave ? '14px' : '0'}">
      <label for="historia">Historia de usuario y criterios de aceptación</label>
      <textarea id="historia" rows="11">${esc(HISTORIA_EJEMPLO)}</textarea>
      <p class="ayuda">No captures casos de prueba aquí. El agente de análisis los deriva de los criterios que escribas.</p>
    </div>
    <div class="acc">
      <button class="btn btn-p" id="btn-ini" ${sinLlave ? 'disabled' : ''}>Iniciar proceso</button>
      <span class="ayuda" style="margin:0">Tres llamadas a ${esc(salud ? salud.modelo : 'Claude')}, una por etapa.</span>
    </div>
  </div>`;
}

function vistaCargando(txt) {
  return cab('Trabajando', 'El agente está generando su entrega.') +
    `<div class="t-cuerpo"><div class="cargando"><span class="giro"></span>${txt}</div>
     <p class="ayuda">Una llamada real a la API puede tardar entre 10 y 40 segundos.</p></div>`;
}

function compuertas() {
  return `<div class="acc">
    <button class="btn btn-ok" data-dec="aprobado">Aprobar y continuar</button>
    <button class="btn" id="btn-cambios">Pedir cambios</button>
    <button class="btn" data-dec="rechazado">Rechazar</button>
  </div><div id="caja-nota"></div>`;
}

function vistaAnalisis() {
  const a = ej.analisis || {}, v = (ej.versiones || {}).analisis || 1;
  return cab('Análisis del requisito', `Entregado por el agente · versión ${v}`, '<span class="pill p-w">Espera tu aprobación</span>') +
  `<div class="t-cuerpo">
    ${ej.nota_vigente ? `<div class="nota-caja" style="margin:0 0 16px"><b>Regenerado según tu nota:</b> “${esc(ej.nota_vigente)}”</div>` : ''}
    <p style="color:var(--fg-2);margin-bottom:16px">${esc(a.resumen)}</p>
    <h3 style="font-size:13px;margin-bottom:9px">Criterios identificados</h3>
    <ul class="lista">${(a.criterios || []).map(c => `
      <li class="it"><div class="it-t"><span class="cod">${esc(c.id)}</span><span class="it-n">${esc(c.texto)}</span></div>
      <div class="it-d">${c.verificable ? 'Verificable con una prueba objetiva' : 'No verificable como está redactado'}</div></li>`).join('')}</ul>
    ${(a.ambiguedades || []).length ? `<h3 style="font-size:13px;margin:18px 0 9px">Ambigüedades detectadas</h3>
      <ul class="lista">${a.ambiguedades.map(x => `<li class="it">${esc(x.descripcion)}<div class="it-d">${esc(x.impacto)}</div></li>`).join('')}</ul>` : ''}
    ${(a.riesgos || []).length ? `<h3 style="font-size:13px;margin:18px 0 9px">Riesgos</h3>
      <ul class="lista">${a.riesgos.map(r => `<li class="it">${esc(r)}</li>`).join('')}</ul>` : ''}
    ${compuertas()}
  </div>`;
}

function vistaCasos() {
  const c = ej.casos || {}, lista = c.casos || [], v = (ej.versiones || {}).casos || 1;
  const sr = lista.filter(x => x.sin_respaldo).length;
  return cab('Casos de prueba', `${lista.length} casos · ${sr} sin respaldo en los criterios · versión ${v}`, '<span class="pill p-w">Espera tu aprobación</span>') +
  `<div class="t-cuerpo">
    ${ej.nota_vigente ? `<div class="nota-caja" style="margin:0 0 16px"><b>Regenerado según tu nota:</b> “${esc(ej.nota_vigente)}”</div>` : ''}
    <ul class="lista">${lista.map(x => `
      <li class="it ${x.sin_respaldo ? 'marca-sr' : ''}">
        <div class="it-t"><span class="cod">${esc(x.id_caso)}</span><span class="it-n">${esc(x.titulo)}</span>
        ${x.sin_respaldo ? '<span class="pill p-w">sin respaldo</span>' : `<span class="pill p-n">${esc(x.criterio_origen || '')}</span>`}</div>
        ${x.sin_respaldo && x.razon_sin_respaldo ? `<div class="it-d"><b>Por qué se propone:</b> ${esc(x.razon_sin_respaldo)}</div>` : ''}
        <ol class="pasos">${(x.pasos || []).map(p => `<li>${esc(p)}</li>`).join('')}</ol>
        ${Object.keys(x.datos || {}).length ? `<div class="datos">${Object.entries(x.datos).map(([k, vv]) => esc(k) + ': ' + esc(vv)).join(' · ')}</div>` : ''}
        <div class="it-d"><b>Esperado:</b> ${esc(x.resultado_esperado)}</div>
        <label class="ck"><input type="checkbox" data-caso="${esc(x.id_caso)}" ${excluidos.has(x.id_caso) ? '' : 'checked'}> Incluir en la automatización</label>
      </li>`).join('')}</ul>
    ${c.cobertura ? `<div class="aviso"><b>Cobertura:</b>&nbsp;${esc(c.cobertura)}</div>` : ''}
    ${compuertas()}
  </div>`;
}

function vistaScripts() {
  const s = ej.automatizacion || {}, v = (ej.versiones || {}).automatizacion || 1;
  const arch = s.archivos || [];
  return cab('Automatización generada', `${arch.length} archivos · versión ${v}`, '<span class="pill p-w">Espera tu aprobación</span>') +
  `<div class="t-cuerpo">
    ${ej.nota_vigente ? `<div class="nota-caja" style="margin:0 0 16px"><b>Regenerado según tu nota:</b> “${esc(ej.nota_vigente)}”</div>` : ''}
    ${arch.map(a => `<div class="cod-caja">
      <div class="cod-cab"><span class="cod-ruta">${esc(a.ruta_relativa)}</span>
      <span class="pill p-n">${a.tipo === 'page_object' ? 'Page Object' : 'Escenario'}</span></div>
      <pre>${esc(a.contenido)}</pre></div>`).join('')}
    ${(s.clases_reutilizadas || []).length ? `<div class="aviso"><b>Clases reutilizadas:</b>&nbsp;${esc(s.clases_reutilizadas.join(', '))}</div>` : ''}
    ${(s.notas || []).length ? s.notas.map(n => `<div class="aviso err">${esc(n)}</div>`).join('') : ''}
    <div class="aviso">Ningún selector aparece en los archivos de escenario: un validador los busca con expresiones regulares y, si los encuentra, el agente regenera.</div>
    ${compuertas()}
  </div>`;
}

function vistaFin(cancelado) {
  const lista = (ej.casos || {}).casos || [];
  const arch = (ej.automatizacion || {}).archivos || [];
  const c = ej.consumo || {};
  return cab(cancelado ? 'Proceso cancelado' : 'Proceso terminado',
    cancelado ? 'Lo generado hasta aquí queda en la bitácora.' : 'El reporte incluye los casos, las decisiones y la bitácora completa.',
    `<span class="pill ${cancelado ? 'p-b' : 'p-g'}">${cancelado ? 'Detenido' : 'Terminado'}</span>`) +
  `<div class="t-cuerpo">
    <div class="res">
      <div><b>${lista.length}</b><span>casos diseñados</span></div>
      <div><b>${lista.filter(x => x.sin_respaldo).length}</b><span>sin respaldo</span></div>
      <div><b>${arch.length}</b><span>archivos generados</span></div>
      <div><b>$${(c.costo_usd || 0).toFixed(4)}</b><span>costo real USD</span></div>
    </div>
    <p style="color:var(--fg-2)">${c.tokens_entrada || 0} tokens de entrada · ${c.tokens_salida || 0} de salida.</p>
    <div class="acc">
      <a class="btn btn-p" href="/api/ejecuciones/${esc(ej.id)}/reporte.pdf">Descargar reporte PDF</a>
      <button class="btn" id="btn-nueva">Nueva solicitud</button>
    </div>
  </div>`;
}

function pintar(error) {
  const p = $('panel');
  if (trabajando) {
    const txt = { analisis: 'Leyendo la historia y los criterios…', casos: 'Diseñando los casos de prueba…', automatizacion: 'Escribiendo las clases de página y los escenarios…' };
    p.innerHTML = vistaCargando(txt[trabajando] || 'Trabajando…');
  } else if (!ej) {
    p.innerHTML = vistaInicio(error);
  } else {
    const v = { EsperaAnalisis: vistaAnalisis, EsperaCasos: vistaCasos, EsperaScripts: vistaScripts };
    if (v[ej.estado]) p.innerHTML = v[ej.estado]();
    else if (ej.estado === 'Terminado') p.innerHTML = vistaFin(false);
    else if (ej.estado === 'Cancelado') p.innerHTML = vistaFin(true);
    else p.innerHTML = vistaInicio('El proceso quedó en estado ' + ej.estado + '.');
  }
  pintarTuberia(); pintarBitacora(); enlazar();
}

// --------------------------------------------------------------- acciones

function enlazar() {
  const ini = $('btn-ini');
  if (ini) ini.onclick = iniciar;
  const nueva = $('btn-nueva');
  if (nueva) nueva.onclick = () => { ej = null; excluidos = new Set(); pintar(); comprobarSalud(); };
  const camb = $('btn-cambios');
  if (camb) camb.onclick = pedirCambios;
  document.querySelectorAll('[data-dec]').forEach(b => b.onclick = () => decidir(b.dataset.dec, null));
  document.querySelectorAll('[data-caso]').forEach(ch => ch.onchange = () => {
    ch.checked ? excluidos.delete(ch.dataset.caso) : excluidos.add(ch.dataset.caso);
  });
}

async function iniciar() {
  const historia = $('historia').value.trim();
  if (historia.length < 20) { $('historia').focus(); return; }
  trabajando = 'analisis'; pintar();
  try {
    ej = await api('/api/ejecuciones', { method: 'POST', body: JSON.stringify({ historia, entorno: 'qa' }) });
    trabajando = false; pintar();
  } catch (e) {
    trabajando = false; ej = null; pintar(e.message);
  }
  comprobarSalud();
}

function pedirCambios() {
  const c = $('caja-nota');
  if (c.querySelector('textarea')) { c.querySelector('textarea').focus(); return; }
  c.innerHTML = `<div class="nota-caja">
    <label for="nt">Qué debe corregir el agente</label>
    <textarea id="nt" rows="2" placeholder="Ejemplo: falta cubrir el caso de usuario bloqueado"></textarea>
    <p class="ayuda">La nota entra al contexto del agente y queda en la bitácora.</p>
    <div class="acc"><button class="btn btn-p" id="btn-enviar">Enviar y regenerar</button>
    <button class="btn" id="btn-cancel">Cancelar</button></div></div>`;
  $('nt').focus();
  $('btn-cancel').onclick = () => { c.innerHTML = ''; };
  $('btn-enviar').onclick = () => {
    const nota = $('nt').value.trim();
    if (!nota) { $('nt').focus(); $('nt').style.borderColor = 'var(--bad)'; return; }
    decidir('cambios', nota);
  };
}

async function decidir(decision, nota) {
  const etapa = ej.etapa;
  trabajando = decision === 'rechazado' ? false : (decision === 'cambios' ? etapa : siguiente(etapa));
  if (trabajando) pintar();
  try {
    ej = await api(`/api/ejecuciones/${ej.id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, nota, casos_excluidos: Array.from(excluidos) })
    });
    trabajando = false; pintar();
  } catch (e) {
    trabajando = false; pintar(e.message);
  }
  comprobarSalud();
}

function siguiente(etapa) {
  const i = ETAPAS.findIndex(e => e.id === etapa);
  return i >= 0 && i < ETAPAS.length - 1 ? ETAPAS[i + 1].id : false;
}

comprobarSalud().then(pintar);
