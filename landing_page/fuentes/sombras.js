/* ═══════════════════════════════════════════════════════════════════════
   SOMBRAS — mapa de profundidad desde el sol.

   Es lo que más realismo aporta por vatio: sin sombra de contacto, los
   jugadores y las porterías parecen pegatinas flotando sobre el césped.

   Sólo se cubre el entorno del campo (±190 m). Más allá no hace falta:
   el relieve ya se sombrea solo con su normal, y así cada texel del mapa
   vale menos de 20 cm, que es lo que hace que la sombra tenga borde.
   ═══════════════════════════════════════════════════════════════════════ */

const SOMBRA_RADIO = 190, SOMBRA_LADO = 1024;

/* Sólo posición: el pase de sombra no necesita color ni normales. */
const SOMBRA_CAJA_VS = `#version 300 es
in vec3 pos;
in vec3 iPos;
in vec3 iEsc;
uniform mat4 uLuzVP;
void main(){ gl_Position = uLuzVP*vec4(iPos + pos*iEsc, 1.0); }`;

const SOMBRA_JUG_VS = `#version 300 es
in vec3 pos;
in float region;
in vec3 iPos;
in vec4 iDir;
uniform mat4 uLuzVP;
void main(){
  vec3 p = pos;
  /* misma zancada que en el pase de color, o la sombra no cuadra */
  float amp = clamp(iDir.w/7.0, 0.0, 1.0);
  float sw  = sin(iDir.z)*amp;
  float ang = 0.0;
  if(region > 1.5 && region < 3.5) ang = (region < 2.5 ?  sw : -sw)*0.85;
  if(region > 3.5)                 ang = (region < 4.5 ? -sw :  sw)*0.55;
  if(ang != 0.0){
    float piv = (region < 3.5) ? 0.86 : 1.40;
    float c = cos(ang), s = sin(ang);
    float y = p.y - piv, z = p.z;
    p.y = piv + y*c - z*s;
    p.z =        y*s + z*c;
  }
  p.y += abs(sin(iDir.z))*amp*0.055;
  float c = iDir.x, s = iDir.y;
  vec3 q = vec3(p.x*c - p.z*s, p.y, p.x*s + p.z*c);
  gl_Position = uLuzVP*vec4(iPos + q, 1.0);
}`;

/* El arbolado proyecta como una elipse: recalcular la silueta completa en
   el pase de sombra no cambia nada visible y cuesta el doble. */
const SOMBRA_CART_VS = `#version 300 es
in vec2 esq;
in vec3 iPos;
in vec4 iForma;
out vec2 vUv;
uniform mat4 uLuzVP;
uniform vec3 uLuzDir;
void main(){
  vec3 der = normalize(vec3(-uLuzDir.z, 0.0, uLuzDir.x));
  vec3 p = iPos + der*esq.x*iForma.x + vec3(0.0, (esq.y+0.5)*iForma.y, 0.0);
  vUv = esq + 0.5;
  gl_Position = uLuzVP*vec4(p, 1.0);
}`;

const SOMBRA_FS = `#version 300 es
precision highp float;
void main(){}`;

const SOMBRA_CART_FS = `#version 300 es
precision highp float;
in vec2 vUv;
void main(){
  vec2 q = vec2((vUv.x-0.5)/0.44, (vUv.y-0.60)/0.40);
  if(dot(q,q) > 1.0) discard;
}`;

/* Fragmento GLSL que se inyecta en los shaders que RECIBEN sombra. */
const SOMBRA_GLSL = `
uniform sampler2D uMapaSombra;
uniform mat4 uLuzVP;
uniform float uSombraFuerza;

float enSombra(vec3 w, float pendiente){
  vec4 lp = uLuzVP*vec4(w, 1.0);
  vec3 q = lp.xyz/lp.w*0.5 + 0.5;
  if(q.x < 0.002 || q.x > 0.998 || q.y < 0.002 || q.y > 0.998 || q.z > 1.0)
    return 1.0;
  /* sesgo dependiente de la pendiente: sin él aparecen bandas de acné */
  float bias = 0.0006 + 0.0035*pendiente;
  float suma = 0.0;
  vec2 tex = vec2(1.0/${SOMBRA_LADO}.0);
  for(int y=-1;y<=1;y++)
    for(int x=-1;x<=1;x++){
      float d = texture(uMapaSombra, q.xy + vec2(x,y)*tex).r;
      suma += (q.z - bias > d) ? 0.0 : 1.0;
    }
  float s = suma/9.0;
  /* la sombra se disuelve en el borde del mapa para que no haya costura */
  vec2 b = abs(q.xy - 0.5)*2.0;
  float borde = 1.0 - smoothstep(0.86, 0.99, max(b.x, b.y));
  return mix(1.0, s, borde*uSombraFuerza);
}
`;

function crearSombras(gl){
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.DEPTH_COMPONENT24, SOMBRA_LADO, SOMBRA_LADO,
                0, gl.DEPTH_COMPONENT, gl.UNSIGNED_INT, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

  const fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, tex, 0);
  gl.drawBuffers([gl.NONE]);
  gl.readBuffer(gl.NONE);
  const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  if(!ok) console.warn('[sombras] framebuffer incompleto; se desactivan');

  const progCaja = programa(gl, SOMBRA_CAJA_VS, SOMBRA_FS, 'sombra:caja');
  const progJug  = programa(gl, SOMBRA_JUG_VS,  SOMBRA_FS, 'sombra:jugador');
  const progCart = programa(gl, SOMBRA_CART_VS, SOMBRA_CART_FS, 'sombra:arbol');

  let luzVP = M4.ident();

  /* Matriz de la luz: ortográfica centrada en el campo y mirando desde el sol. */
  function calcularLuzVP(sunDir){
    const d = Math.hypot(sunDir[0], sunDir[1], sunDir[2]) || 1;
    let dx = sunDir[0]/d, dy = sunDir[1]/d, dz = sunDir[2]/d;
    /* con el sol muy rasante la sombra se alarga hasta el infinito y el mapa
       deja de tener resolución útil: se levanta a un mínimo practicable */
    if(dy < 0.34){
      const k = Math.hypot(dx, dz) || 1;
      const h = Math.sqrt(Math.max(1 - 0.34*0.34, 0));
      dx = dx/k*h; dz = dz/k*h; dy = 0.34;
    }
    const D = 340;
    const ojo = [dx*D, dy*D, dz*D];
    const arriba = Math.abs(dy) > 0.98 ? [1,0,0] : [0,1,0];
    const view = M4.mirar(ojo, [0,0,0], arriba);
    const proj = M4.orto(-SOMBRA_RADIO, SOMBRA_RADIO, -SOMBRA_RADIO, SOMBRA_RADIO, 1, 900);
    luzVP = M4.mul(proj, view);
    return luzVP;
  }

  return {tex, fbo, ok, progCaja, progJug, progCart, calcularLuzVP,
          get luzVP(){ return luzVP; }};
}
