/* ═══════════════════════════════════════════════════════════════════════
   EL GUION — recorrido de cámara y encendido de capas, por scroll.

   La altura de la cámara ES la narrativa: baja hasta el fútbol y vuelve a
   subir hasta el dato. Cada hito define dónde está la cámara y qué capas
   del sistema están encendidas; entre hitos se interpola.

   El cambio de MUNDO no vive aquí: va por tiempo, independiente del
   scroll, para que el entorno se transforme a tu alrededor mientras el
   partido y el análisis siguen. Esa es la idea de la marca.
   ═══════════════════════════════════════════════════════════════════════ */

/* dist: distancia al centro del campo · alt: altura · az: azimut de cámara
   mira: [x,y,z] objetivo, o 'balon' para seguir la jugada
   fov: campo de visión en grados */
const HITOS = [
  { s:0.00, dist:1250, alt:300, az:2.30, fov:42, mira:[0,150,0],
    capas:{} },
  { s:0.11, dist:700,  alt:190, az:2.05, fov:43, mira:[0,86,0],
    capas:{} },
  { s:0.22, dist:300,  alt:88,  az:1.80, fov:45, mira:[0,26,0],
    capas:{} },
  { s:0.32, dist:118,  alt:24,  az:1.62, fov:49, mira:[0,6,0],
    capas:{} },
  { s:0.41, dist:52,   alt:7.5, az:1.50, fov:52, mira:'balon',
    capas:{} },
  { s:0.50, dist:34,   alt:5.5, az:1.34, fov:54, mira:'balon',
    capas:{jugador:1, deteccion:0.35} },
  { s:0.59, dist:48,   alt:15,  az:1.16, fov:50, mira:'balon',
    capas:{jugador:0.5, deteccion:1, balon:1} },
  { s:0.68, dist:78,   alt:36,  az:1.02, fov:46, mira:[0,0,0],
    capas:{deteccion:0.7, estela:1, balon:0.8} },
  { s:0.77, dist:104,  alt:72,  az:0.90, fov:42, mira:[0,0,0],
    capas:{deteccion:0.3, estela:0.9, movimiento:1, balon:0.6} },
  { s:0.87, dist:96,   alt:132, az:0.80, fov:38, mira:[0,0,0],
    capas:{estela:0.35, tactica:1, zonas:0.8, balon:0.4, deteccion:0.55} },
  { s:0.96, dist:34,   alt:172, az:0.74, fov:36, mira:[0,0,0],
    capas:{tactica:1, zonas:1, deteccion:0.6} },
  { s:1.00, dist:26,   alt:186, az:0.72, fov:34, mira:[0,0,0],
    capas:{tactica:0.8, zonas:0.8, deteccion:0.5} },
];

const CAPAS = ['deteccion','estela','movimiento','tactica','zonas','balon','jugador'];

function estadoGuion(s, partido){
  s = lim(s, 0, 1);
  let i = 0;
  while(i < HITOS.length-2 && HITOS[i+1].s < s) i++;
  const a = HITOS[i], b = HITOS[i+1];
  const t = easeIO(lim((s - a.s)/(b.s - a.s || 1), 0, 1));

  const dist = mez(a.dist, b.dist, t);
  const alt  = mez(a.alt,  b.alt,  t);
  const az   = mez(a.az,   b.az,   t);
  const fov  = mez(a.fov,  b.fov,  t);

  /* objetivo: el centro del campo o la jugada, con transición suave */
  const oa = a.mira === 'balon' ? [partido.balon.x, 1.2, partido.balon.y] : a.mira;
  const ob = b.mira === 'balon' ? [partido.balon.x, 1.2, partido.balon.y] : b.mira;
  const mira = [mez(oa[0],ob[0],t), mez(oa[1],ob[1],t), mez(oa[2],ob[2],t)];

  const capas = {};
  for(const k of CAPAS) capas[k] = mez(a.capas[k]||0, b.capas[k]||0, t);

  const camPos = [mira[0] + Math.cos(az)*dist, alt, mira[2] + Math.sin(az)*dist];
  return {camPos, mira, fov, capas, hito:i};
}
