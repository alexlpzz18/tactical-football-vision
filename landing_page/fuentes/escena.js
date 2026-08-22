/* ═══════════════════════════════════════════════════════════════════════
   ESCENA — orquesta los pases de dibujado.

   Orden: entorno (cielo, terreno, suelo y campo, escribiendo profundidad)
   → cajas opacas (caserío, torres, porterías, valla) → arbolado con
   transparencia, ordenado de lejos a cerca.
   ═══════════════════════════════════════════════════════════════════════ */

/* El cielo es de baja frecuencia (degradados, nubes, bruma) pero cuesta lo
   mismo que cualquier otro pase a pantalla completa. Se dibuja a media
   resolución y se estira: la diferencia no se ve y libera la mitad del
   presupuesto de fragmento, que es lo que permite subir a 4K. */
const BLIT_VS = `#version 300 es
in vec2 pos;
out vec2 vUv;
void main(){ vUv = pos*0.5 + 0.5; gl_Position = vec4(pos, 0.0, 1.0); }`;

const BLIT_FS = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 frag;
uniform sampler2D uTex;
void main(){ frag = texture(uTex, vUv); }`;

function crearEscena(gl, lienzo2d){
  const progEnv   = programa(gl, ENV_VS,  ENV_FS,  'env');
  const progCart  = programa(gl, CART_VS, CART_FS, 'cartel');
  const progCaja  = programa(gl, CAJA_VS, CAJA_FS, 'caja');
  const progSuelo = programa(gl, SUELO_VS, SUELO_FS, 'suelo');
  const jugadores = crearJugadores(gl);
  const analisis = crearAnalisis(gl, lienzo2d);
  const som = crearSombras(gl);
  const progBlit = programa(gl, BLIT_VS, BLIT_FS, 'blit');

  /* destino de media resolución para el cielo */
  const cieloTex = gl.createTexture();
  const cieloFbo = gl.createFramebuffer();
  let cieloW = 0, cieloH = 0;
  function ajustarCielo(W, H){
    const w = Math.max(2, W>>1), h = Math.max(2, H>>1);
    if(w === cieloW && h === cieloH) return;
    cieloW = w; cieloH = h;
    gl.bindTexture(gl.TEXTURE_2D, cieloTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.bindFramebuffer(gl.FRAMEBUFFER, cieloFbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, cieloTex, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.bindTexture(gl.TEXTURE_2D, null);
  }

  const quad  = bufferQuad(gl);
  const caja  = mallaCaja();
  const disp  = generarEscena();
  const suelo = mallaSuelo();
  const bufSuelo = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufSuelo);
  gl.bufferData(gl.ARRAY_BUFFER, suelo.pos, gl.STATIC_DRAW);

  /* ---------- geometría estática ---------- */
  const bufCajaPos = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufCajaPos);
  gl.bufferData(gl.ARRAY_BUFFER, caja.pos, gl.STATIC_DRAW);
  const bufCajaNor = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufCajaNor);
  gl.bufferData(gl.ARRAY_BUFFER, caja.nor, gl.STATIC_DRAW);

  const tejado = mallaTejado();
  const bufTejPos = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufTejPos);
  gl.bufferData(gl.ARRAY_BUFFER, tejado.pos, gl.STATIC_DRAW);
  const bufTejNor = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufTejNor);
  gl.bufferData(gl.ARRAY_BUFFER, tejado.nor, gl.STATIC_DRAW);
  const datosTej = new Float32Array(80*10);
  const bufTej = gl.createBuffer();
  let nTej = 0;

  const bufEsq = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufEsq);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
    -.5,-.5,  .5,-.5,  .5,.5,   -.5,-.5,  .5,.5,  -.5,.5]), gl.STATIC_DRAW);

  /* ---------- búferes de instancia ---------- */
  const N_ARB = disp.arboles.length;
  const datosArb = new Float32Array(N_ARB*12);
  const bufArb = gl.createBuffer();

  const N_CAJA = disp.casas.length*2 + 4*2 + 2*3 + 44;
  const datosCaja = new Float32Array(N_CAJA*10);
  const bufCaja = gl.createBuffer();
  let nCajas = 0;

  const orden = disp.arboles.map((_,i)=>i);   /* índices para ordenar por z */

  /* ---------- construcción por frame ---------- */
  function construir(mA, mB, t, camPos, partido, seguido, peso, vp, W, H){
    if(partido){
      jugadores.construir(partido, mA, mB, t, seguido);
      analisis.registrar(partido);
      if(peso) analisis.construir(partido, peso, camPos, vp, W, H, seguido);
    }
    const aA = ARBOL_MUNDO[mA.id], aB = ARBOL_MUNDO[mB.id];
    const gA = AGUA_MUNDO[mA.id], gB = AGUA_MUNDO[mB.id];
    /* 1 si el hueco cae dentro del agua de ese mundo */
    const enAgua = (a, g) => {
      if(!g.w) return 0;
      const az = Math.atan2(a.z, a.x);
      const da = Math.abs(Math.atan2(Math.sin(az-g.az), Math.cos(az-g.az)));
      const radio = Math.hypot(a.x*0.80, a.z);
      return (da < g.ancho && radio > g.dist*0.86) ? 1 : 0;
    };
    const cA = CASA_MUNDO[mA.id],  cB = CASA_MUNDO[mB.id];
    const L = (x,y)=> x+(y-x)*t;

    /* arbolado, ordenado de lejos a cerca para que la transparencia case */
    for(const i of orden){
      const a = disp.arboles[i];
      const dx = a.x-camPos[0], dz = a.z-camPos[2];
      a._d = dx*dx + dz*dz;
    }
    orden.sort((p,q)=> disp.arboles[q]._d - disp.arboles[p]._d);

    for(let k=0;k<N_ARB;k++){
      const a = disp.arboles[orden[k]];
      const alto  = L(mez(aA.alto[0], aA.alto[1], a.s),  mez(aB.alto[0], aB.alto[1], a.s))*a.esc;
      const ancho = L(mez(aA.ancho[0],aA.ancho[1],a.s),  mez(aB.ancho[0],aB.ancho[1],a.s))*a.esc;
      const dens  = L(aA.densidad, aB.densidad);
      const moja  = L(enAgua(a,gA), enAgua(a,gB));
      const vis   = (a.s < dens ? 1 : 0) * (1 - moja);
      const o = k*12;
      datosArb[o  ] = a.x; datosArb[o+1] = alturaTerreno(a.x, a.z); datosArb[o+2] = a.z;
      datosArb[o+3] = ancho*vis; datosArb[o+4] = alto*vis;
      datosArb[o+5] = aA.tipo;   datosArb[o+6] = a.s;
      datosArb[o+7] = aB.tipo;   datosArb[o+8] = t;
      for(let c=0;c<3;c++)
        datosArb[o+9+c] = Math.pow(L(aA.col[c], aB.col[c]), 2.2);
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, bufArb);
    gl.bufferData(gl.ARRAY_BUFFER, datosArb, gl.DYNAMIC_DRAW);

    /* cajas */
    nCajas = 0; nTej = 0;
    const push = (x,y,z, sx,sy,sz, r,g,b, tipo)=>{
      const o = nCajas*10;
      datosCaja[o]=x; datosCaja[o+1]=y; datosCaja[o+2]=z;
      datosCaja[o+3]=sx; datosCaja[o+4]=sy; datosCaja[o+5]=sz;
      datosCaja[o+6]=Math.pow(r,2.2); datosCaja[o+7]=Math.pow(g,2.2);
      datosCaja[o+8]=Math.pow(b,2.2); datosCaja[o+9]=tipo;
      nCajas++;
    };

    /* caserío: cuerpo + tejado. En la sabana encoge a casa baja. */
    const nCasas = L(cA.n, cB.n);
    for(let i=0;i<disp.casas.length;i++){
      const c = disp.casas[i];
      if(c.s > nCasas) continue;
      /* tampoco hay caserío dentro del agua */
      if(L(enAgua(c,gA), enAgua(c,gB)) > 0.5) continue;
      const h = L(mez(cA.alto[0],cA.alto[1],c.s), mez(cB.alto[0],cB.alto[1],c.s));
      const muro = [0,1,2].map(k=> L(cA.muro[k], cB.muro[k]));
      const tej  = [0,1,2].map(k=> L(cA.tejado[k], cB.tejado[k]));
      const y0 = alturaTerreno(c.x, c.z);
      push(c.x, y0, c.z, c.w, h, c.d, muro[0],muro[1],muro[2], 0);
      if(nTej < 80){
        const o = nTej*10;
        datosTej[o]=c.x; datosTej[o+1]=y0+h; datosTej[o+2]=c.z;
        /* el faldón vuela un poco sobre la fachada, como un alero */
        datosTej[o+3]=c.w*1.12; datosTej[o+4]=Math.min(c.w,c.d)*0.42; datosTej[o+5]=c.d*1.12;
        datosTej[o+6]=Math.pow(tej[0],2.2); datosTej[o+7]=Math.pow(tej[1],2.2);
        datosTej[o+8]=Math.pow(tej[2],2.2); datosTej[o+9]=1;
        nTej++;
      }
    }

    /* torres de luz */
    for(const e of disp.estructuras){
      if(e.tipo === 'torre'){
        const yt = alturaTerreno(e.x, e.z);
        push(e.x, yt, e.z, 0.9, 17, 0.9, 0.30,0.31,0.33, 2);
        push(e.x, yt+17, e.z, 5.2, 1.5, 1.0, 0.36,0.37,0.39, 2);
      }
      if(e.tipo === 'porteria'){
        const L_ = e.lado;
        push(e.x, 0,  3.66, 0.14, 2.44, 0.14, 0.92,0.93,0.94, 2);
        push(e.x, 0, -3.66, 0.14, 2.44, 0.14, 0.92,0.93,0.94, 2);
        push(e.x, 2.44, 0, 0.14, 0.14, 7.32, 0.92,0.93,0.94, 2);
      }
      if(e.tipo === 'valla'){
        /* postes del cierre perimetral */
        for(let i=0;i<22;i++){
          const u = i/22*Math.PI*2;
          const vx=Math.cos(u)*62, vz=Math.sin(u)*44;
          push(vx, alturaTerreno(vx,vz), vz, 0.16, 2.1, 0.16, 0.30,0.32,0.30, 2);
        }
      }
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, bufCaja);
    gl.bufferData(gl.ARRAY_BUFFER, datosCaja, gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, bufTej);
    gl.bufferData(gl.ARRAY_BUFFER, datosTej, gl.DYNAMIC_DRAW);
  }

  /* ---------- ayudantes de atributos ----------
     Se usa el VAO por defecto, así que los arrays activos y sus divisores
     son estado GLOBAL y se filtran de un programa al siguiente. Con varios
     programas de distinta disposición eso acaba en INVALID_OPERATION, así
     que antes de configurar cada uno se limpia lo que dejó el anterior. */
  const MAX_ATTR = Math.min(gl.getParameter(gl.MAX_VERTEX_ATTRIBS), 16);
  function limpiarAttrs(){
    for(let i=0;i<MAX_ATTR;i++){
      gl.disableVertexAttribArray(i);
      gl.vertexAttribDivisor(i, 0);
    }
  }
  function attr(prog, nombre, buf, tam, stride, offset, divisor){
    const loc = gl.getAttribLocation(prog, nombre);
    if(loc < 0) return;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, tam, gl.FLOAT, false, stride, offset);
    gl.vertexAttribDivisor(loc, divisor||0);
  }

  function comunes(prog, m, camPos, viewProj){
    /* mapa de sombras: unidad 0 para todos los receptores */
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, som.tex);
    gl.uniform1i(prog.u.uMapaSombra, 0);
    gl.uniformMatrix4fv(prog.u.uLuzVP, false, som.luzVP);
    gl.uniform1f(prog.u.uSombraFuerza, som.ok ? (1.0 - m.noche*0.78) : 0.0);
    gl.uniformMatrix4fv(prog.u.uViewProj, false, viewProj);
    gl.uniform3fv(prog.u.uCamPos, camPos);
    gl.uniform3fv(prog.u.uHaze, aLineal(m.haze));
    gl.uniform3fv(prog.u.uSunDir, m.sunDir);
    gl.uniform3fv(prog.u.uSunCol, aLineal(m.sunCol));
    gl.uniform3fv(prog.u.uSkyTop, aLineal(m.skyTop));
    gl.uniform1f(prog.u.uNiebla, m.niebla);
    gl.uniform1f(prog.u.uExposure, m.exposure);
    gl.uniform1f(prog.u.uNoche, m.noche);
  }

  /* ---------- dibujado ---------- */
  function dibujar(est){
    const {W,H, viewProj, invViewProj, camPos, m, tiempo, campo} = est;
    const pases = est.pases || 'todo';
    const hacer = n => pases==='todo' || pases.indexOf(n)>=0;

    /* ── 0 · mapa de sombras, desde el sol ── */
    if(som.ok && hacer('sombra')){
      som.calcularLuzVP(m.sunDir);
      /* La textura de sombra sigue enlazada a la unidad 0 desde el frame
         anterior. Si se deja así al enlazar SU propio framebuffer se forma
         un bucle de realimentación y el driver descarta el dibujado. */
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, null);
      gl.bindFramebuffer(gl.FRAMEBUFFER, som.fbo);
      gl.viewport(0, 0, SOMBRA_LADO, SOMBRA_LADO);
      gl.enable(gl.DEPTH_TEST); gl.depthMask(true);
      gl.disable(gl.BLEND);
      gl.clear(gl.DEPTH_BUFFER_BIT);

      limpiarAttrs(); gl.useProgram(som.progCaja);
      gl.uniformMatrix4fv(som.progCaja.u.uLuzVP, false, som.luzVP);
      attr(som.progCaja, 'pos', bufCajaPos, 3, 0, 0, 0);
      attr(som.progCaja, 'iPos', bufCaja, 3, 40, 0,  1);
      attr(som.progCaja, 'iEsc', bufCaja, 3, 40, 12, 1);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, caja.cuenta, nCajas);

      limpiarAttrs();
      attr(som.progCaja, 'pos', bufTejPos, 3, 0, 0, 0);
      attr(som.progCaja, 'iPos', bufTej, 3, 40, 0,  1);
      attr(som.progCaja, 'iEsc', bufTej, 3, 40, 12, 1);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, tejado.cuenta, nTej);

      limpiarAttrs();
      gl.useProgram(som.progJug);
      gl.uniformMatrix4fv(som.progJug.u.uLuzVP, false, som.luzVP);
      jugadores.dibujarSombra(som.progJug, attr);

      limpiarAttrs(); gl.useProgram(som.progCart);
      gl.uniformMatrix4fv(som.progCart.u.uLuzVP, false, som.luzVP);
      gl.uniform3fv(som.progCart.u.uLuzDir, m.sunDir);
      attr(som.progCart, 'esq', bufEsq, 2, 0, 0, 0);
      attr(som.progCart, 'iPos',   bufArb, 3, 48, 0,  1);
      attr(som.progCart, 'iForma', bufArb, 4, 48, 12, 1);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, N_ARB);

      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    }

    gl.viewport(0,0,W,H);
    gl.disable(gl.BLEND);
    gl.clear(gl.DEPTH_BUFFER_BIT);

    /* 1 · cielo, a media resolución y estirado después */
    if(hacer('cielo')){
    ajustarCielo(W, H);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, null);        /* nunca leer lo que se escribe */
    gl.bindFramebuffer(gl.FRAMEBUFFER, cieloFbo);
    gl.viewport(0, 0, cieloW, cieloH);
    gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false);
    limpiarAttrs(); gl.useProgram(progEnv);
    attr(progEnv, 'pos', quad, 2, 0, 0, 0);
    gl.uniform2f(progEnv.u.uRes, cieloW, cieloH);
    gl.uniformMatrix4fv(progEnv.u.uInvViewProj, false, invViewProj);
    gl.uniform3fv(progEnv.u.uCamPos, camPos);
    gl.uniform1f(progEnv.u.uTime, tiempo);
    subirMundo(gl, progEnv, m);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, W, H);
    limpiarAttrs(); gl.useProgram(progBlit);
    attr(progBlit, 'pos', quad, 2, 0, 0, 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, cieloTex);
    gl.uniform1i(progBlit.u.uTex, 1);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    /* 2 · suelo y campo, ya con profundidad de rasterizador */
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.depthMask(true);
    if(hacer('suelo')){
    limpiarAttrs(); gl.useProgram(progSuelo);
    attr(progSuelo, 'pos', bufSuelo, 2, 0, 0, 0);
    gl.uniform3fv(progSuelo.u.uSueloCol, aLineal(m.sueloCol));
    gl.uniform1f(progSuelo.u.uTierra, m.tierra);
    gl.uniform1f(progSuelo.u.uNieve, m.nieve);
    gl.uniform1f(progSuelo.u.uCampo, campo);
    gl.uniform1f(progSuelo.u.uWater, m.water);
    gl.uniform1f(progSuelo.u.uWaterAz, m.waterAz);
    gl.uniform1f(progSuelo.u.uWaterWide, m.waterWide);
    gl.uniform1f(progSuelo.u.uWaterDist, m.waterDist);
    gl.uniform1f(progSuelo.u.uTime, tiempo);
    gl.uniform3fv(progSuelo.u.uWaterCol, aLineal(m.waterCol));
    gl.uniform3fv(progSuelo.u.uSkyHorizon, aLineal(m.skyHorizon));
    comunes(progSuelo, m, camPos, viewProj);
    gl.drawArrays(gl.TRIANGLES, 0, suelo.cuenta);
    }

    /* 3 · cajas opacas */
    if(hacer('cajas')){
    limpiarAttrs(); gl.useProgram(progCaja);
    attr(progCaja, 'pos', bufCajaPos, 3, 0, 0, 0);
    attr(progCaja, 'nor', bufCajaNor, 3, 0, 0, 0);
    attr(progCaja, 'iPos', bufCaja, 3, 40, 0,  1);
    attr(progCaja, 'iEsc', bufCaja, 3, 40, 12, 1);
    attr(progCaja, 'iCol', bufCaja, 4, 40, 24, 1);
    comunes(progCaja, m, camPos, viewProj);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, caja.cuenta, nCajas);

    limpiarAttrs();
    attr(progCaja, 'pos', bufTejPos, 3, 0, 0, 0);
    attr(progCaja, 'nor', bufTejNor, 3, 0, 0, 0);
    attr(progCaja, 'iPos', bufTej, 3, 40, 0,  1);
    attr(progCaja, 'iEsc', bufTej, 3, 40, 12, 1);
    attr(progCaja, 'iCol', bufTej, 4, 40, 24, 1);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, tejado.cuenta, nTej);
    }

    /* 4 · jugadores */
    if(hacer('jug')){ limpiarAttrs(); jugadores.dibujar(est, attr, comunes); }

    /* 5 · arbolado, transparente y ya ordenado de lejos a cerca */
    if(hacer('arb')){
    limpiarAttrs(); gl.useProgram(progCart);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    attr(progCart, 'esq', bufEsq, 2, 0, 0, 0);
    attr(progCart, 'iPos',    bufArb, 3, 48, 0,  1);
    attr(progCart, 'iForma',  bufArb, 4, 48, 12, 1);
    attr(progCart, 'iForma2', bufArb, 2, 48, 28, 1);
    attr(progCart, 'iCol',    bufArb, 3, 48, 36, 1);
    comunes(progCart, m, camPos, viewProj);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, N_ARB);
    }
    gl.depthMask(true);
    gl.disable(gl.BLEND);

    /* 6 · capa de análisis, siempre por encima de la escena */
    if(hacer('capa')){ limpiarAttrs(); analisis.dibujar(est, attr); }
  }

  return {construir, dibujar, disp, analisis};
}
