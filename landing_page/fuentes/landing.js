/* ═══════════════════════════════════════════════════════════════════════
   MOTOR DE LA PÁGINA

   Une las piezas: simulación → cámara por scroll → escena → capa de
   análisis → lecturas en el texto.

   Dos relojes independientes, y esa es la idea de la marca:
   · el SCROLL mueve la cámara y enciende las capas del sistema,
   · el TIEMPO cambia el mundo alrededor cada 30 segundos.
   El partido y el análisis nunca se interrumpen.
   ═══════════════════════════════════════════════════════════════════════ */
(function(){
'use strict';

const MENOS_MOV = matchMedia('(prefers-reduced-motion: reduce)').matches;
const cv    = document.getElementById('escena');
const cvEt  = document.getElementById('etiq');
const gl    = cv.getContext('webgl2', {antialias:true, alpha:false, powerPreference:'high-performance'});

if(!gl){
  document.getElementById('cargando').innerHTML =
    '<span>Este navegador no admite WebGL2</span>';
  return;
}

const esc = crearEscena(gl, cvEt);
const par = crearPartido(20260821);

/* ─────────── resolución adaptativa ───────────
   El coste es de fragmento, así que la palanca correcta es la resolución.
   Se sube o se baja sola buscando 55 fps, sin preguntar al usuario. */
let escala = 1.0, W=0, H=0, DPR=1;
/* Sin techo artificial: en una pantalla Retina esto llega a 4K de verdad.
   Si la GPU no da, la escala adaptativa baja sola; si da, se aprovecha. */
const DPR_MAX = Math.min(devicePixelRatio||1, 2);
const PIX_MAX = 9.0e6;      /* tope de píxeles por frame, ~4K */

function medir(){
  DPR = DPR_MAX * escala;
  W = Math.max(2, Math.round(innerWidth*DPR));
  H = Math.max(2, Math.round(innerHeight*DPR));
  if(W*H > PIX_MAX){                     /* nunca por encima del tope */
    const k = Math.sqrt(PIX_MAX/(W*H));
    DPR *= k; W = Math.round(W*k); H = Math.round(H*k);
  }
  cv.width=W; cv.height=H;
  cvEt.width=W; cvEt.height=H;
  cvEt.style.width=innerWidth+'px'; cvEt.style.height=innerHeight+'px';
}
medir();
addEventListener('resize', ()=>{ medir(); grano(); });

let acumFps=0, nFps=0, ultimoAjuste=0;
function ajustarEscala(dt, ahora){
  acumFps += 1/Math.max(dt,0.001); nFps++;
  if(ahora - ultimoAjuste < 1400) return;
  const fps = acumFps/nFps; acumFps=0; nFps=0; ultimoAjuste=ahora;
  const antes = escala;
  if(fps < 44 && escala > 0.45) escala = Math.max(0.45, escala-0.12);
  else if(fps > 57 && escala < 1.0) escala = Math.min(1.0, escala+0.06);
  if(escala !== antes) medir();
}

/* ─────────── grano de película ───────────
   Fijo y con pointer-events desactivados: nunca sobre un contenedor que
   haga scroll, o el repintado continuo se come el móvil. */
const cvG = document.getElementById('grano');
function grano(){
  const g = cvG.getContext('2d');
  const w = 220, h = 220;
  cvG.width=w; cvG.height=h;
  cvG.style.width=innerWidth+'px'; cvG.style.height=innerHeight+'px';
  const d = g.createImageData(w,h);
  let s = 12345;
  for(let i=0;i<d.data.length;i+=4){
    s = (s*1664525 + 1013904223) >>> 0;
    const v = 110 + (s % 40);
    d.data[i]=d.data[i+1]=d.data[i+2]=v; d.data[i+3]=30;
  }
  g.putImageData(d,0,0);
}
grano();

/* ─────────── ciclo de mundos, por tiempo ─────────── */
const DUR_MUNDO = 30000, DUR_TRANS = 5200;
let relojMundo = 0;
const elMundoN = document.getElementById('mundo-n');
const elMundoB = document.getElementById('mundo-b');

/* ─────────── hitos del guion en el raíl lateral ─────────── */
const elFases = document.getElementById('fases');
for(let i=0;i<HITOS.length-1;i++) elFases.appendChild(document.createElement('i'));
const marcasFase = [...elFases.children];

/* ─────────── lecturas del texto ─────────── */
const lect = id => document.getElementById(id);
const mN=lect('m-n'), mPunta=lect('m-punta'), mRitmo=lect('m-ritmo');
const mAmp=lect('m-amp'), mProf=lect('m-prof'), mEnt=lect('m-ent');
const iAmp=lect('i-amp'), iProf=lect('i-prof'), iLinea=lect('i-linea'), iEnt=lect('i-ent');
let punta=0, ritmo=0, tick=0;
/* medias del tramo, que es lo que iría en un informe de verdad */
let acAmp=0, acProf=0, acLinea=0, acEnt=0, nAc=0;

function lecturas(){
  const M = par.metricas('A');
  const vmax = Math.max(...par.jugadores.map(j=>j.v));
  punta = Math.max(punta*0.997, vmax);
  const media = par.jugadores.reduce((a,j)=>a+j.v,0)/par.jugadores.length;
  ritmo = ritmo ? mez(ritmo, media*60, 0.02) : media*60;

  acAmp+=M.amplitud; acProf+=M.profundidad;
  acLinea+=M.alturaLinea; acEnt+=M.entreLineas; nAc++;

  if((tick++ % 8) !== 0) return;
  if(mN) mN.textContent = par.jugadores.length;
  if(mPunta) mPunta.innerHTML = punta.toFixed(1)+'<u>m/s</u>';
  if(mRitmo) mRitmo.innerHTML = Math.round(ritmo)+'<u>m/min</u>';
  if(mAmp)  mAmp.innerHTML  = M.amplitud.toFixed(1)+'<u>m</u>';
  if(mProf) mProf.innerHTML = M.profundidad.toFixed(1)+'<u>m</u>';
  if(mEnt)  mEnt.innerHTML  = M.entreLineas.toFixed(1)+'<u>m</u>';
  if(iAmp)  iAmp.innerHTML  = (acAmp/nAc).toFixed(1)+'<u>m</u>';
  if(iProf) iProf.innerHTML = (acProf/nAc).toFixed(1)+'<u>m</u>';
  if(iLinea)iLinea.innerHTML= (acLinea/nAc).toFixed(0)+'<u>m</u>';
  if(iEnt)  iEnt.innerHTML  = (acEnt/nAc).toFixed(1)+'<u>m</u>';
}

/* ─────────── progreso de scroll ───────────
   Se lee dentro del bucle que ya está corriendo, no con un escuchador de
   scroll: así no hay trabajo sin agrupar en cada evento. */
function progreso(){
  const alto = document.documentElement.scrollHeight - innerHeight;
  const inf = document.getElementById('informe');
  /* el recorrido 3D ocupa hasta donde empieza el informe */
  const finEscena = inf.getBoundingClientRect().top + scrollY - innerHeight*0.5;
  return lim(scrollY / Math.max(finEscena, 1), 0, 1);
}

/* actos, cacheados: consultarlos cada frame con querySelectorAll es tirar trabajo */
const ACTOS = [...document.querySelectorAll('.acto')].map(el=>({
  el, caja: el.querySelector('.caja'), der: el.classList.contains('derecha')
}));

/* ─────────── bucle ─────────── */
let ultimo = 0, arrancado = false;
const seguido = 9;                     /* el jugador que sigue la cámara */

function frame(ahora){
  requestAnimationFrame(frame);
  const dt = ultimo ? Math.min((ahora-ultimo)/1000, 0.05) : 0.016;
  ultimo = ahora;

  par.paso(MENOS_MOV ? 0.016 : dt);
  relojMundo += (MENOS_MOV ? 0 : dt*1000);

  /* mundo activo y transición */
  const ciclo = Math.floor(relojMundo/DUR_MUNDO) % MUNDOS.length;
  const sig   = (ciclo+1) % MUNDOS.length;
  const dentro = relojMundo % DUR_MUNDO;
  const tt = dentro > DUR_MUNDO-DUR_TRANS
           ? easeIO((dentro-(DUR_MUNDO-DUR_TRANS))/DUR_TRANS) : 0;
  const mA = MUNDOS[ciclo], mB = MUNDOS[sig];
  const m = mezclarMundos(mA, mB, tt);

  elMundoN.innerHTML = tt > 0.5 ? `<b>${mB.nombre}</b>` : `<b>${mA.nombre}</b>`;
  elMundoB.style.width = (dentro/DUR_MUNDO*100)+'%';

  /* cámara y capas según el scroll */
  const s = progreso();
  const g = estadoGuion(s, par);
  marcasFase.forEach((el,i)=> i===g.hito ? el.setAttribute('data-on','')
                                         : el.removeAttribute('data-on'));

  const view = M4.mirar(g.camPos, g.mira, [0,1,0]);
  const proj = M4.perspectiva(g.fov*Math.PI/180, W/H, 0.4, 30000);
  const vp = M4.mul(proj, view);

  esc.construir(mA, mB, tt, g.camPos, par, seguido, g.capas, vp, W, H);
  esc.dibujar({W,H, viewProj:vp, invViewProj:M4.invertir(vp),
               camPos:g.camPos, m, tiempo:ahora*0.001, campo:1});
  esc.analisis.pintarEtiquetas(vp, W, H, DPR);

  /* Sólo se lee el acto que está centrado: los demás se apagan. Sin esto
     se solapan dos textos a la vez y con la cabecera fija. */
  let derecha = false, mejor = 1e9;
  for(const a of ACTOS){
    const r = a.el.getBoundingClientRect();
    const centro = r.top + r.height*0.5 - innerHeight*0.5;
    const d = Math.abs(centro)/(innerHeight*0.5);
    const vis = lim(1 - Math.max(0, d-0.16)/0.42, 0, 1);
    a.caja.style.opacity = vis.toFixed(3);
    a.caja.style.transform = `translateY(${(centro*0.055).toFixed(1)}px)`;
    a.caja.style.pointerEvents = vis > 0.6 ? 'auto' : 'none';
    if(d < mejor){ mejor = d; derecha = a.der; }
  }
  document.body.classList.toggle('der', derecha);

  lecturas();
  ajustarEscala(dt, ahora);

  if(!arrancado){
    arrancado = true;
    document.getElementById('cargando').classList.add('fuera');
  }
}
requestAnimationFrame(frame);

})();
