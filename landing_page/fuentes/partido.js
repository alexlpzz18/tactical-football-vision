/* ═══════════════════════════════════════════════════════════════════════
   EL PARTIDO — simulación sintética de once contra once.

   Todo es artificial: ni un dato ni una imagen del material del proyecto.
   El modelo es deliberadamente simple (posición de referencia + atracción
   al balón + separación entre compañeros), pero produce movimiento
   colectivo creíble: el bloque bascula, se estira y se comprime solo.

   Eso importa porque la capa táctica que se dibuja encima MIDE esta
   simulación. Las cifras que aparecen en pantalla no están escritas a
   mano: salen de las posiciones que el usuario está viendo.
   ═══════════════════════════════════════════════════════════════════════ */

const CAMPO_X = 105, CAMPO_Y = 68;

/* Formaciones en fracción de campo: x hacia la portería rival, y a lo ancho. */
const F_433 = [
  [-0.42, 0.00],                                            /* portero */
  [-0.24,-0.26],[-0.26,-0.09],[-0.26, 0.09],[-0.24, 0.26],  /* defensa */
  [-0.10,-0.15],[-0.12, 0.00],[-0.10, 0.15],                /* medio */
  [ 0.04,-0.27],[ 0.07, 0.00],[ 0.04, 0.27],                /* ataque */
];
const F_442 = [
  [-0.42, 0.00],
  [-0.25,-0.24],[-0.27,-0.08],[-0.27, 0.08],[-0.25, 0.24],
  [-0.11,-0.24],[-0.13,-0.07],[-0.13, 0.07],[-0.11, 0.24],
  [ 0.04,-0.10],[ 0.04, 0.10],
];

function crearPartido(semilla){
  const r = rnd(semilla || 987654);

  const jugadores = [];
  const nuevo = (eq, i, form, sentido) => {
    const f = form[i];
    const x = f[0]*CAMPO_X*sentido, y = f[1]*CAMPO_Y;
    jugadores.push({
      eq, dorsal: i+1, portero: i===0, sentido,
      hx: x, hy: y,                 /* posición de referencia */
      x, y, vx:0, vy:0,
      fase: r()*6.28,               /* desfase del ciclo de zancada */
      tono: r(),                    /* variación de tono de piel */
      id: (eq==='A'?0:11) + i,
    });
  };
  for(let i=0;i<11;i++) nuevo('A', i, F_433,  1);
  for(let i=0;i<11;i++) nuevo('B', i, F_442, -1);

  /* Balón: recorre una secuencia de destinos, como una posesión larga. */
  const balon = {x:0, y:0, z:0, vx:0, vy:0, destino:0, t:0};
  const jugada = [];
  for(let i=0;i<26;i++){
    /* una posesión que progresa hacia la portería de B y luego se pierde */
    const av = i/26;
    jugada.push({
      x: mez(-28, 42, av) + (r()-0.5)*22,
      y: (r()-0.5)*CAMPO_Y*0.72,
      dur: 1.1 + r()*1.5,
    });
  }

  let t = 0;

  function paso(dt){
    dt = Math.min(dt, 0.05);
    t += dt;

    /* ── balón ── */
    balon.t += dt;
    const d = jugada[balon.destino % jugada.length];
    const k = lim(balon.t / d.dur, 0, 1);
    const sig = jugada[(balon.destino+1) % jugada.length];
    balon.x = mez(d.x, sig.x, easeIO(k));
    balon.y = mez(d.y, sig.y, easeIO(k));
    /* parábola del pase: sube y baja entre destino y destino */
    balon.z = Math.sin(k*Math.PI) * Math.min(2.6, Math.hypot(sig.x-d.x, sig.y-d.y)*0.07);
    if(k >= 1){ balon.destino++; balon.t = 0; }

    /* ── jugadores ── */
    for(const j of jugadores){
      let ox = j.hx, oy = j.hy;

      if(j.portero){
        /* el portero se mueve poco, sigue la línea del balón */
        ox = j.hx + lim(balon.x*0.05*j.sentido, -3, 3);
        oy = lim(balon.y*0.42, -6, 6);
      } else {
        /* el bloque bascula hacia el balón y se desplaza a lo largo */
        const haciaBalonY = (balon.y - j.hy)*0.24;
        const bloqueX = balon.x*0.22;
        ox = j.hx + bloqueX;
        oy = j.hy + haciaBalonY;

        /* los tres más cercanos al balón lo presionan de verdad */
        const dist = Math.hypot(balon.x-j.x, balon.y-j.y);
        if(dist < 14){
          const w = (1 - dist/14)*0.55;
          const tx = mez(ox, balon.x, w), ty = mez(oy, balon.y, w);
          /* nadie abandona su zona más de 9 m: si no, el bloque se rompe */
          const dx = lim(tx-ox, -9, 9), dy = lim(ty-oy, -9, 9);
          ox += dx; oy += dy;
        }
        /* respiración: nadie está quieto */
        ox += Math.sin(t*0.7 + j.fase)*1.5;
        oy += Math.cos(t*0.5 + j.fase*1.7)*1.5;
      }

      /* separación: evita que se amontonen */
      let sx=0, sy=0;
      for(const o of jugadores){
        if(o===j || o.eq!==j.eq) continue;
        const dx=j.x-o.x, dy=j.y-o.y, d2=dx*dx+dy*dy;
        if(d2 < 64 && d2 > 0.01){
          const f = (8 - Math.sqrt(d2))/8;
          sx += dx*f*0.5; sy += dy*f*0.5;
        }
      }

      /* aceleración hacia el objetivo, con tope de velocidad humano */
      const ax = (ox - j.x)*1.6 + sx*2.2;
      const ay = (oy - j.y)*1.6 + sy*2.2;
      j.vx += ax*dt; j.vy += ay*dt;
      const v = Math.hypot(j.vx, j.vy), VMAX = j.portero ? 3.2 : 7.4;
      if(v > VMAX){ j.vx = j.vx/v*VMAX; j.vy = j.vy/v*VMAX; }
      j.vx *= 0.90; j.vy *= 0.90;
      j.x += j.vx*dt; j.y += j.vy*dt;
      j.x = lim(j.x, -CAMPO_X*0.5-2, CAMPO_X*0.5+2);
      j.y = lim(j.y, -CAMPO_Y*0.5-2, CAMPO_Y*0.5+2);
      j.v = Math.hypot(j.vx, j.vy);
    }
  }

  /* ── métricas colectivas, medidas sobre lo que se está viendo ── */
  function metricas(eq){
    const campo = jugadores.filter(j=> j.eq===eq && !j.portero);
    const xs = campo.map(j=>j.x), ys = campo.map(j=>j.y);
    const cx = xs.reduce((a,b)=>a+b,0)/xs.length;
    const cy = ys.reduce((a,b)=>a+b,0)/ys.length;
    const amplitud = Math.max(...ys) - Math.min(...ys);
    const profundidad = Math.max(...xs) - Math.min(...xs);
    const compacidad = campo.reduce((a,j)=>a+Math.hypot(j.x-cx, j.y-cy),0)/campo.length;

    /* línea defensiva: los cuatro más retrasados respecto a su portería */
    const sentido = campo[0].sentido;
    const orden = [...campo].sort((a,b)=> (a.x-b.x)*sentido);
    const linea = orden.slice(0,4);
    const xLinea = linea.reduce((a,j)=>a+j.x,0)/4;
    const alturaLinea = (xLinea + sentido*CAMPO_X*0.5)*sentido;
    const ataque = orden.slice(-3);
    const xAtaque = ataque.reduce((a,j)=>a+j.x,0)/3;
    const entreLineas = Math.abs(xAtaque - xLinea);
    const vmax = Math.max(...campo.map(j=>j.v));

    return {cx, cy, amplitud, profundidad, compacidad,
            alturaLinea, entreLineas, vmax, linea};
  }

  return {jugadores, balon, paso, metricas, get t(){return t;}};
}
