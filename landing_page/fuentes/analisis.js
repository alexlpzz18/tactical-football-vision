/* ═══════════════════════════════════════════════════════════════════════
   CAPA DE ANÁLISIS — lo que ve el sistema, dibujado sobre el partido.

   Dos piezas:

   1. Geometría PLANA sobre el césped (estelas, anillos de detección,
      líneas y zonas tácticas). Va en un único búfer dinámico y un solo
      dibujado. Al estar pegada al suelo se lee como una proyección sobre
      el campo, que es exactamente lo que es.

   2. Etiquetas en un lienzo 2D por encima (dorsales, coordenadas, cifras).
      El texto nítido en WebGL es un incordio; proyectando a pantalla y
      pintando en 2D sale perfecto a cualquier resolución.

   Regla de color: el mundo es cálido y la máquina es fría. Todo lo que
   dibuja el sistema usa el mismo cian pálido, y nunca se confunde con
   la escena.
   ═══════════════════════════════════════════════════════════════════════ */

const FRIO      = [0.62, 0.91, 1.00];   /* la capa máquina */
const FRIO_2    = [0.35, 0.78, 0.96];
const CALIENTE  = [1.00, 0.74, 0.35];   /* resaltes puntuales */

const CAPA_VS = `#version 300 es
in vec3 pos;              /* x, y (altura sobre el césped), z */
in vec4 col;
out vec4 vCol;
out float vDist;
uniform mat4 uViewProj;
uniform vec3 uCamPos;
void main(){
  vCol = col;
  vDist = length(uCamPos - pos);
  gl_Position = uViewProj*vec4(pos, 1.0);
}`;

const CAPA_FS = `#version 300 es
precision highp float;
in vec4 vCol;
in float vDist;
out vec4 frag;
uniform float uNiebla;
void main(){
  /* la capa se desvanece con la distancia como todo lo demás, si no
     flotaría por delante de la niebla y delataría que es un dibujo */
  float niebla = 1.0 - exp(-vDist*uNiebla*0.6);
  frag = vec4(vCol.rgb, vCol.a*(1.0-niebla*0.85));
}`;

function crearAnalisis(gl, lienzo2d){
  const prog = programa(gl, CAPA_VS, CAPA_FS, 'capa');
  const MAXV = 90000;
  const datos = new Float32Array(MAXV*7);
  const buf = gl.createBuffer();
  let nv = 0;
  const ctx = lienzo2d.getContext('2d');
  let etiquetas = [];

  /* ---------- primitivas planas ---------- */
  function vert(x,y,z, c, a){
    if(nv >= MAXV) return;
    const o = nv*7;
    datos[o]=x; datos[o+1]=y; datos[o+2]=z;
    datos[o+3]=c[0]; datos[o+4]=c[1]; datos[o+5]=c[2]; datos[o+6]=a;
    nv++;
  }
  const ALTURA = 0.045;          /* justo por encima del césped */

  /* Segmento de anchura constante, tumbado en el plano del campo. */
  function segmento(x0,z0, x1,z1, w, c, a0, a1){
    const dx=x1-x0, dz=z1-z0, L=Math.hypot(dx,dz);
    if(L < 1e-5) return;
    const nx=-dz/L*w*0.5, nz=dx/L*w*0.5;
    vert(x0-nx,ALTURA,z0-nz,c,a0); vert(x0+nx,ALTURA,z0+nz,c,a0);
    vert(x1+nx,ALTURA,z1+nz,c,a1);
    vert(x0-nx,ALTURA,z0-nz,c,a0); vert(x1+nx,ALTURA,z1+nz,c,a1);
    vert(x1-nx,ALTURA,z1-nz,c,a1);
  }

  function anillo(cx,cz, r, w, c, a, seg){
    seg = seg||28;
    for(let i=0;i<seg;i++){
      const u0=i/seg*6.2832, u1=(i+1)/seg*6.2832;
      segmento(cx+Math.cos(u0)*r, cz+Math.sin(u0)*r,
               cx+Math.cos(u1)*r, cz+Math.sin(u1)*r, w, c, a, a);
    }
  }

  function rectangulo(x0,z0,x1,z1, w, c, a){
    segmento(x0,z0, x1,z0, w, c, a, a);
    segmento(x1,z0, x1,z1, w, c, a, a);
    segmento(x1,z1, x0,z1, w, c, a, a);
    segmento(x0,z1, x0,z0, w, c, a, a);
  }

  function relleno(x0,z0,x1,z1, c, a){
    vert(x0,ALTURA,z0,c,a); vert(x1,ALTURA,z0,c,a); vert(x1,ALTURA,z1,c,a);
    vert(x0,ALTURA,z0,c,a); vert(x1,ALTURA,z1,c,a); vert(x0,ALTURA,z1,c,a);
  }

  /* Polígono convexo relleno (abanico desde el primer vértice). */
  function poligono(pts, c, a){
    for(let i=1;i<pts.length-1;i++){
      vert(pts[0][0],ALTURA,pts[0][1],c,a);
      vert(pts[i][0],ALTURA,pts[i][1],c,a);
      vert(pts[i+1][0],ALTURA,pts[i+1][1],c,a);
    }
  }

  /* ---------- historial de posiciones para las estelas ---------- */
  const historia = new Map();
  const LARGO = 90;
  function registrar(partido){
    for(const j of partido.jugadores){
      let h = historia.get(j.id);
      if(!h){ h = []; historia.set(j.id, h); }
      h.push(j.x, j.y);
      if(h.length > LARGO*2) h.splice(0, h.length - LARGO*2);
    }
  }

  /* ---------- construcción de la capa ---------- */
  /* `peso` marca cuánto pesa cada capa: así el scroll enciende y apaga
     sin que haya que reescribir nada. */
  function construir(partido, peso, camPos, viewProj, W, H, seguido){
    nv = 0; etiquetas = [];
    const P = k => peso[k] || 0;

    /* — anillos de detección bajo los pies —
       El radio crece con la distancia de cámara: desde 130 m un anillo de
       0,85 m es un píxel y el cenital se queda sin marcar a nadie. */
    if(P('deteccion') > 0.004){
      const a = P('deteccion');
      const dCam = Math.hypot(camPos[0], camPos[1], camPos[2]);
      const r = Math.max(0.85, dCam*0.0075);
      for(const j of partido.jugadores){
        anillo(j.x, j.y, r, r*0.16, FRIO, a*0.95, 20);
        anillo(j.x, j.y, r*0.34, r*0.34, FRIO, a*0.55, 12);
      }
    }

    /* — estelas: el camino que ha recorrido cada jugador — */
    if(P('estela') > 0.004){
      const a = P('estela');
      for(const j of partido.jugadores){
        const h = historia.get(j.id);
        if(!h || h.length < 6) continue;
        const n = h.length/2;
        const esA = j.eq === 'A';
        const c = esA ? FRIO : FRIO_2;
        for(let i=1;i<n;i++){
          const f0=(i-1)/(n-1), f1=i/(n-1);
          segmento(h[(i-1)*2], h[(i-1)*2+1], h[i*2], h[i*2+1],
                   0.16+0.42*f1, c, a*f0*f0*0.85, a*f1*f1*0.85);
        }
      }
    }

    /* — vectores de velocidad — */
    if(P('movimiento') > 0.004){
      const a = P('movimiento');
      for(const j of partido.jugadores){
        if(j.v < 0.5) continue;
        const L = lim(j.v*0.75, 0.8, 6.0);
        const ux = j.vx/j.v, uy = j.vy/j.v;
        segmento(j.x, j.y, j.x+ux*L, j.y+uy*L, 0.26, FRIO, a*0.9, a*0.15);
      }
    }

    /* — geometría táctica del equipo A — */
    if(P('tactica') > 0.004){
      const a = P('tactica');
      const M = partido.metricas('A');
      const campoA = partido.jugadores.filter(j=> j.eq==='A' && !j.portero);
      const ys = campoA.map(j=>j.y), xs = campoA.map(j=>j.x);
      const y0=Math.min(...ys), y1=Math.max(...ys);
      const x0=Math.min(...xs), x1=Math.max(...xs);

      relleno(x0,y0,x1,y1, FRIO, a*0.055);
      rectangulo(x0,y0,x1,y1, 0.22, FRIO, a*0.55);

      /* la línea defensiva, trazada entre los cuatro más retrasados */
      const linea = [...M.linea].sort((p,q)=> p.y-q.y);
      for(let i=1;i<linea.length;i++)
        segmento(linea[i-1].x, linea[i-1].y, linea[i].x, linea[i].y,
                 0.30, CALIENTE, a*0.95, a*0.95);
      for(const j of linea) anillo(j.x, j.y, 1.15, 0.18, CALIENTE, a*0.9, 18);

      etiquetas.push({t:`AMPLITUD ${M.amplitud.toFixed(1)} m`, x:(x0+x1)/2, z:y0-3.5, c:'frio'});
      etiquetas.push({t:`PROFUNDIDAD ${M.profundidad.toFixed(1)} m`, x:x1+4.5, z:(y0+y1)/2, c:'frio'});
      etiquetas.push({t:`LÍNEA A ${M.alturaLinea.toFixed(0)} m`,
                      x:linea[0].x, z:linea[0].y-3.0, c:'calido'});
      etiquetas.push({t:`ENTRE LÍNEAS ${M.entreLineas.toFixed(1)} m`,
                      x:(x0+x1)/2, z:y1+3.5, c:'frio'});
    }

    /* — tercios y pasillos: la ocupación del campo — */
    if(P('zonas') > 0.004){
      const a = P('zonas');
      for(let i=-1;i<=1;i++){
        const x = i*CAMPO_X/6;
        segmento(x, -CAMPO_Y/2, x, CAMPO_Y/2, 0.14, FRIO, a*0.35, a*0.35);
      }
      for(let i=-1;i<=1;i++){
        const y = i*CAMPO_Y/6;
        segmento(-CAMPO_X/2, y, CAMPO_X/2, y, 0.14, FRIO, a*0.35, a*0.35);
      }
      /* tinte por presencia real de jugadores en cada casilla */
      for(let cx=-1;cx<=1;cx++) for(let cz=-1;cz<=1;cz++){
        const x0=cx*CAMPO_X/3-CAMPO_X/6, x1=x0+CAMPO_X/3;
        const z0=cz*CAMPO_Y/3-CAMPO_Y/6, z1=z0+CAMPO_Y/3;
        let n=0;
        for(const j of partido.jugadores)
          if(j.x>=x0&&j.x<x1&&j.y>=z0&&j.y<z1) n++;
        if(n) relleno(x0+0.4,z0+0.4,x1-0.4,z1-0.4, FRIO, a*Math.min(n/6,1)*0.14);
      }
    }

    /* — el balón — */
    if(P('balon') > 0.004){
      const a = P('balon'), b = partido.balon;
      anillo(b.x, b.y, 1.5, 0.16, CALIENTE, a*0.85, 20);
      anillo(b.x, b.y, 2.6, 0.10, CALIENTE, a*0.35, 24);
      etiquetas.push({t:'BALÓN', x:b.x, z:b.y-3.4, c:'calido'});
    }

    /* — jugador seguido: su ficha — */
    if(P('jugador') > 0.004 && seguido != null){
      const j = partido.jugadores.find(p=> p.id===seguido);
      if(j){
        const a = P('jugador');
        anillo(j.x, j.y, 1.6, 0.20, FRIO, a*0.95, 26);
        etiquetas.push({t:`#${j.dorsal}`, x:j.x, z:j.y-3.2, c:'frio', grande:true});
        etiquetas.push({t:`${j.x.toFixed(1)} , ${j.y.toFixed(1)} m`,
                        x:j.x, z:j.y+3.0, c:'frio'});
        etiquetas.push({t:`${j.v.toFixed(1)} m/s`, x:j.x+3.6, z:j.y, c:'frio'});
      }
    }

    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, datos.subarray(0, nv*7), gl.DYNAMIC_DRAW);
  }

  /* ---------- etiquetas en 2D, proyectadas desde el mundo ---------- */
  function proyectar(x, y, z, viewProj, W, H){
    const cx = viewProj[0]*x + viewProj[4]*y + viewProj[8]*z + viewProj[12];
    const cy = viewProj[1]*x + viewProj[5]*y + viewProj[9]*z + viewProj[13];
    const cw = viewProj[3]*x + viewProj[7]*y + viewProj[11]*z + viewProj[15];
    if(cw <= 0.001) return null;
    return [(cx/cw*0.5+0.5)*W, (1-(cy/cw*0.5+0.5))*H];
  }

  function pintarEtiquetas(viewProj, W, H, dpr){
    ctx.setTransform(1,0,0,1,0,0);
    ctx.clearRect(0,0,lienzo2d.width, lienzo2d.height);
    if(!etiquetas.length) return;
    ctx.scale(dpr, dpr);

    /* Separación vertical: en cenital varias etiquetas caen casi en el mismo
       punto y se pisan. Se proyectan, se ordenan y se empujan lo justo. */
    const puestas = [];
    for(const e of etiquetas){
      const q = proyectar(e.x, 0.1, e.z, viewProj, W/dpr, H/dpr);
      if(q) puestas.push({e, x:q[0], y:q[1]});
    }
    puestas.sort((a,b)=> a.y-b.y);
    const ALTO = 19;
    for(let i=1;i<puestas.length;i++){
      const a = puestas[i-1], b = puestas[i];
      if(Math.abs(b.x-a.x) < 130 && b.y-a.y < ALTO) b.y = a.y + ALTO;
    }

    for(const {e, x, y} of puestas){
      const p = [x, y];
      const col = e.c==='calido' ? 'rgba(255,196,107,0.96)' : 'rgba(180,236,255,0.96)';
      ctx.font = `600 ${e.grande?15:11}px ui-monospace, SFMono-Regular, Menlo, monospace`;
      ctx.textAlign='center'; ctx.textBaseline='middle';
      const w = ctx.measureText(e.t).width;
      ctx.fillStyle='rgba(6,12,20,0.55)';
      ctx.fillRect(p[0]-w/2-5, p[1]-8, w+10, 16);
      ctx.fillStyle=col;
      ctx.fillText(e.t, p[0], p[1]);
    }
  }

  function dibujar(est, attr){
    if(!nv) return;
    const {viewProj, camPos, m} = est;
    gl.useProgram(prog);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    attr(prog, 'pos', buf, 3, 28, 0, 0);
    attr(prog, 'col', buf, 4, 28, 12, 0);
    gl.uniformMatrix4fv(prog.u.uViewProj, false, viewProj);
    gl.uniform3fv(prog.u.uCamPos, camPos);
    gl.uniform1f(prog.u.uNiebla, m.niebla);
    gl.drawArrays(gl.TRIANGLES, 0, nv);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
  }

  return {registrar, construir, dibujar, pintarEtiquetas};
}
