/* ═══════════════════════════════════════════════════════════════════════
   JUGADORES — figuras de baja poligonización, instanciadas.

   Una sola malla humana (piernas, torso, brazos, cabeza) dibujada 22 veces
   en una llamada. La zancada se resuelve en el vertex shader rotando las
   extremidades según la fase y la velocidad, así que no hay esqueletos ni
   animaciones que cargar.

   El tono de piel y la equipación son parámetros del mundo: en cada sitio
   juegan equipos distintos, que es justo lo que la página quiere decir.
   ═══════════════════════════════════════════════════════════════════════ */

const JUG_VS = `#version 300 es
in vec3 pos;
in vec3 nor;
in float region;        /* 0 torso · 1 cabeza · 2 pierna izq · 3 pierna der
                           4 brazo izq · 5 brazo der */
in vec3  iPos;
in vec4  iDir;          /* cos, sin del rumbo · fase · velocidad */
in vec3  iKit;
in vec3  iPiel;
in float iMarca;        /* 0..1 resalte del jugador seguido */

out vec3 vNor, vCol, vMundo;
out float vDist, vMarca, vArriba;

uniform mat4 uViewProj;
uniform vec3 uCamPos;

void main(){
  vec3 p = pos;
  vec3 n = nor;

  /* zancada: piernas y brazos oscilan en oposición, con amplitud
     proporcional a la velocidad real del jugador */
  float amp = clamp(iDir.w/7.0, 0.0, 1.0);
  float sw  = sin(iDir.z)*amp;
  float ang = 0.0;
  if(region > 1.5 && region < 3.5) ang = (region < 2.5 ?  sw : -sw)*0.85;
  if(region > 3.5)                 ang = (region < 4.5 ? -sw :  sw)*0.55;

  if(ang != 0.0){
    float piv = (region < 3.5) ? 0.86 : 1.40;     /* cadera u hombro */
    float c = cos(ang), s = sin(ang);
    float y = p.y - piv, z = p.z;
    p.y = piv + y*c - z*s;
    p.z =        y*s + z*c;
    float ny = n.y, nz = n.z;
    n.y = ny*c - nz*s; n.z = ny*s + nz*c;
  }
  /* rebote del cuerpo al correr */
  p.y += abs(sin(iDir.z))*amp*0.055;

  /* rumbo */
  float c = iDir.x, s = iDir.y;
  vec3 q = vec3(p.x*c - p.z*s, p.y, p.x*s + p.z*c);
  vec3 qn = vec3(n.x*c - n.z*s, n.y, n.x*s + n.z*c);

  vec3 w = iPos + q;
  vMundo = w;
  vNor = qn;
  vCol = (region > 0.5 && region < 1.5) ? iPiel
       : (region > 3.5 ? iPiel : iKit);           /* brazos y cara al aire */
  vArriba = p.y;
  vMarca = iMarca;
  vDist = length(uCamPos - w);
  gl_Position = uViewProj*vec4(w, 1.0);
}`;

const JUG_FS = `#version 300 es
precision highp float;
in vec3 vNor, vCol, vMundo;
in float vDist, vMarca, vArriba;
out vec4 frag;
uniform vec3 uHaze, uSunDir, uSunCol, uSkyTop, uMarcaCol;
uniform float uNiebla, uExposure, uNoche;
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
` + SOMBRA_GLSL + `
vec3 ambiente(vec3 cielo){
  float g = dot(cielo, vec3(0.2126,0.7152,0.0722));
  return mix(cielo, vec3(g), 0.60);
}
void main(){
  vec3 n = normalize(vNor), sd = normalize(uSunDir);
  float dif = max(dot(n, sd), 0.0);
  float cielo = 0.45 + 0.55*n.y;
  float sm = enSombra(vMundo, 1.0-dif);
  float sombraVis = mix(1.0, 0.44, (1.0 - sm)*(1.0 - uNoche*0.85));
  vec3 luz = (ambiente(uSkyTop)*cielo*0.75 + uSunCol*dif*1.6*(1.0-uNoche*0.75)
           + vec3(0.06)*(1.0-uNoche*0.4)) * sombraVis;
  vec3 col = vCol*luz;

  /* resalte del jugador que sigue el sistema: un borde frío, no un tinte */
  float borde = 1.0 - abs(dot(n, normalize(vec3(0.0,0.0,1.0))));
  col = mix(col, uMarcaCol, vMarca*0.30);

  float niebla = 1.0 - exp(-vDist*uNiebla);
  col = mix(col, uHaze, niebla);
  col = aces(col*uExposure);
  col = pow(max(col,0.0), vec3(1.0/2.2));
  frag = vec4(col, 1.0);
}`;

/* ---------- malla humana ---------- */
function mallaJugador(){
  const pos=[], nor=[], reg=[];
  function caja(x0,y0,z0, x1,y1,z1, region){
    const v=[[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
             [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]];
    const caras=[
      {i:[4,5,6,7], n:[0,0,1]}, {i:[1,0,3,2], n:[0,0,-1]},
      {i:[5,1,2,6], n:[1,0,0]}, {i:[0,4,7,3], n:[-1,0,0]},
      {i:[3,2,6,7], n:[0,1,0]}, {i:[0,1,5,4], n:[0,-1,0]},
    ];
    for(const f of caras){
      const [a,b,c,d]=f.i;
      for(const k of [a,b,c, a,c,d]){
        pos.push(...v[k]); nor.push(...f.n); reg.push(region);
      }
    }
  }
  /* proporciones en metros, altura total ~1,78 */
  caja(-0.19,0.00,-0.08, -0.03,0.86,0.08, 2);   /* pierna izquierda */
  caja( 0.03,0.00,-0.08,  0.19,0.86,0.08, 3);   /* pierna derecha  */
  caja(-0.21,0.84,-0.11,  0.21,1.46,0.11, 0);   /* torso */
  caja(-0.32,0.92,-0.07, -0.22,1.42,0.07, 4);   /* brazo izquierdo */
  caja( 0.22,0.92,-0.07,  0.32,1.42,0.07, 5);   /* brazo derecho */
  caja(-0.10,1.46,-0.10,  0.10,1.72,0.10, 1);   /* cabeza */
  return {pos:new Float32Array(pos), nor:new Float32Array(nor),
          reg:new Float32Array(reg), cuenta:pos.length/3};
}

/* ---------- equipaciones y tonos de piel por mundo ---------- */
const EQUIPO_MUNDO = {
  pueblo:   {A:[0.72,0.10,0.12], B:[0.94,0.94,0.92],
             piel:[[0.76,0.58,0.44],[0.52,0.36,0.26]]},
  costa:    {A:[0.94,0.78,0.16], B:[0.10,0.16,0.38],
             piel:[[0.78,0.60,0.46],[0.48,0.33,0.24]]},
  /* En la sabana juegan equipos locales: pieles oscuras, con la misma
     variación entre jugadores que en cualquier otro sitio. */
  sabana:   {A:[0.12,0.44,0.24], B:[0.92,0.44,0.10],
             piel:[[0.40,0.25,0.16],[0.20,0.12,0.08]]},
  invierno: {A:[0.95,0.95,0.96], B:[0.13,0.13,0.16],
             piel:[[0.80,0.63,0.50],[0.50,0.35,0.26]]},
};

function crearJugadores(gl){
  const prog = programa(gl, JUG_VS, JUG_FS, 'jugador');
  const malla = mallaJugador();

  const bufPos = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufPos);
  gl.bufferData(gl.ARRAY_BUFFER, malla.pos, gl.STATIC_DRAW);
  const bufNor = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufNor);
  gl.bufferData(gl.ARRAY_BUFFER, malla.nor, gl.STATIC_DRAW);
  const bufReg = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, bufReg);
  gl.bufferData(gl.ARRAY_BUFFER, malla.reg, gl.STATIC_DRAW);

  const MAX = 24;
  const datos = new Float32Array(MAX*14);
  const bufInst = gl.createBuffer();
  let n = 0;

  function construir(partido, mA, mB, t, seguido){
    const eA = EQUIPO_MUNDO[mA.id], eB = EQUIPO_MUNDO[mB.id];
    const L = (x,y)=> x+(y-x)*t;
    n = 0;
    for(const j of partido.jugadores){
      const kitA = j.eq==='A' ? eA.A : eA.B;
      const kitB = j.eq==='A' ? eB.A : eB.B;
      /* el portero va de otro color, como en cualquier campo */
      const kit = j.portero ? [0.85,0.80,0.20] : [0,1,2].map(k=> L(kitA[k], kitB[k]));
      const pielA = eA.piel[0].map((v,k)=> mez(v, eA.piel[1][k], j.tono));
      const pielB = eB.piel[0].map((v,k)=> mez(v, eB.piel[1][k], j.tono));
      const piel = [0,1,2].map(k=> L(pielA[k], pielB[k]));

      const rumbo = Math.atan2(j.vy, j.vx) || 0;
      const o = n*14;
      datos[o  ]=j.x; datos[o+1]=0; datos[o+2]=j.y;
      datos[o+3]=Math.cos(rumbo); datos[o+4]=Math.sin(rumbo);
      datos[o+5]=partido.t*7.0 + j.fase; datos[o+6]=j.v;
      for(let k=0;k<3;k++) datos[o+7+k]  = Math.pow(kit[k], 2.2);
      for(let k=0;k<3;k++) datos[o+10+k] = Math.pow(piel[k], 2.2);
      datos[o+13] = (seguido!=null && j.id===seguido) ? 1 : 0;
      n++;
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, bufInst);
    gl.bufferData(gl.ARRAY_BUFFER, datos, gl.DYNAMIC_DRAW);
  }

  function dibujar(est, attr, comunes){
    const {viewProj, camPos, m} = est;
    gl.useProgram(prog);
    attr(prog, 'pos', bufPos, 3, 0, 0, 0);
    attr(prog, 'nor', bufNor, 3, 0, 0, 0);
    attr(prog, 'region', bufReg, 1, 0, 0, 0);
    attr(prog, 'iPos',  bufInst, 3, 56, 0,  1);
    attr(prog, 'iDir',  bufInst, 4, 56, 12, 1);
    attr(prog, 'iKit',  bufInst, 3, 56, 28, 1);
    attr(prog, 'iPiel', bufInst, 3, 56, 40, 1);
    attr(prog, 'iMarca',bufInst, 1, 56, 52, 1);
    comunes(prog, m, camPos, viewProj);
    gl.uniform3fv(prog.u.uMarcaCol, aLineal([0.62,0.91,1.0]));
    gl.drawArraysInstanced(gl.TRIANGLES, 0, malla.cuenta, n);
  }

  /* El pase de sombra reutiliza los mismos búferes: la sombra tiene que
     salir de la MISMA geometría deformada, o no cuadra con el cuerpo. */
  function dibujarSombra(prog, attr){
    gl.useProgram(prog);
    attr(prog, 'pos', bufPos, 3, 0, 0, 0);
    attr(prog, 'region', bufReg, 1, 0, 0, 0);
    attr(prog, 'iPos', bufInst, 3, 56, 0,  1);
    attr(prog, 'iDir', bufInst, 4, 56, 12, 1);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, malla.cuenta, n);
  }

  return {construir, dibujar, dibujarSombra};
}
