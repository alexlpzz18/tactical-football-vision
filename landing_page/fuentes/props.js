/* ═══════════════════════════════════════════════════════════════════════
   OBJETOS DEL ENTORNO — arbolado, torres de luz, caserío y valla.

   Son lo que convierte un plano en un sitio. Van instanciados: una sola
   llamada de dibujado para todos los árboles del mundo.

   Cada hueco de la escena (un árbol, una casa) tiene una apariencia por
   mundo, y en cada frame se sube la mezcla de las dos apariencias activas.
   Así los árboles se TRANSFORMAN de roble a acacia en vez de aparecer de
   golpe, que es justo lo que pide "el mundo cambia, el juego no".
   ═══════════════════════════════════════════════════════════════════════ */

/* ---------- carteles (árboles, arbustos, matorral) ---------- */
const CART_VS = `#version 300 es
in vec2 esq;              /* esquina del cartel, -0.5..0.5 */
in vec3 iPos;             /* posición en el mundo */
in vec4 iForma;           /* ancho, alto, tipoA, semilla */
in vec2 iForma2;          /* tipoB, mezcla */
in vec3 iCol;
out vec2 vUv;
out vec3 vCol;
out float vTipoA, vTipoB, vMez, vSemilla, vDist;

uniform mat4 uViewProj;
uniform vec3 uCamPos;

void main(){
  vec3 haciaCam = uCamPos - iPos;
  vec3 der = normalize(vec3(-haciaCam.z, 0.0, haciaCam.x));   /* siempre de frente */
  vec3 p = iPos + der*esq.x*iForma.x + vec3(0.0, (esq.y+0.5)*iForma.y, 0.0);
  vUv = esq + 0.5;
  vCol = iCol; vTipoA = iForma.z; vTipoB = iForma2.x; vMez = iForma2.y;
  vSemilla = iForma.w;
  vDist = length(haciaCam);
  gl_Position = uViewProj*vec4(p,1.0);
}`;

const CART_FS = `#version 300 es
precision highp float;
in vec2 vUv;
in vec3 vCol;
in float vTipoA, vTipoB, vMez, vSemilla, vDist;
out vec4 frag;

uniform vec3  uHaze, uSunDir, uSunCol, uSkyTop;
uniform float uNiebla, uExposure, uNoche;

float hash21(vec2 p){
  vec3 q=fract(vec3(p.xyx)*0.1031); q+=dot(q,q.yzx+33.33);
  return fract((q.x+q.y)*q.z);
}
float vnoise2(vec2 p){
  vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
  return mix(mix(hash21(i),hash21(i+vec2(1,0)),f.x),
             mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)),f.x),f.y);
}
float fbm(vec2 p){
  float s=0.0,a=0.5;
  for(int i=0;i<4;i++){ s+=a*vnoise2(p); p*=2.05; a*=0.5; }
  return s;
}
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
vec3 ambiente(vec3 cielo){
  float g = dot(cielo, vec3(0.2126,0.7152,0.0722));
  return mix(cielo, vec3(g), 0.60);
}

/* Silueta por tipo. Devuelve (masa, tronco) para poder mezclar dos tipos
   y que el arbolado se TRANSFORME al cambiar de mundo. */
vec2 silueta(vec2 uv, float tipo, float sem, float ruido){
  float x = uv.x-0.5, y = uv.y;
  float dens = 0.0, tronco = 0.0;

  if(tipo < 0.5){
    /* copa redonda (roble, chopo) */
    vec2 q = vec2(x/0.42, (y-0.63)/0.36);
    dens = 1.0 - smoothstep(0.72, 1.02, length(q) - ruido*0.30);
    tronco = (1.0-smoothstep(0.030,0.055,abs(x)))*(1.0-smoothstep(0.30,0.42,y));
  } else if(tipo < 1.5){
    /* acacia: copa ancha y plana, tronco largo */
    float copa  = 1.0 - smoothstep(0.06,0.20, abs(y-0.78));
    float ancho = 1.0 - smoothstep(0.26,0.50, abs(x));
    dens = 1.0 - smoothstep(0.30,0.62, 1.0-copa*ancho + ruido*0.26);
    tronco = (1.0-smoothstep(0.020,0.040,abs(x+(y-0.4)*0.09)))
           * (1.0-smoothstep(0.62,0.80,y));
  } else if(tipo < 2.5){
    /* árbol desnudo de invierno */
    float ramas = 0.0;
    for(int i=0;i<5;i++){
      float f=float(i);
      float ang=(hash21(vec2(sem,f))-0.5)*1.5;
      float alt=0.42+f*0.115;
      float dx=abs(x-(y-0.36)*ang);
      ramas=max(ramas,(1.0-smoothstep(0.008,0.026,dx))*(1.0-smoothstep(alt,alt+0.22,y)));
    }
    dens = ramas*0.85;
    tronco = (1.0-smoothstep(0.022,0.042,abs(x)))*(1.0-smoothstep(0.55,0.78,y));
  } else {
    /* matorral bajo */
    vec2 q = vec2(x/0.5,(y-0.24)/0.26);
    dens = 1.0 - smoothstep(0.70,1.05, length(q) - ruido*0.36);
  }
  return vec2(dens, tronco);
}

void main(){
  vec2 uv = vUv;
  float x = uv.x-0.5, y = uv.y;
  float sem = vSemilla*37.0;
  float ruido = fbm(uv*7.0 + sem) - 0.5;

  vec2 sa = silueta(uv, vTipoA, sem, ruido);
  vec2 sb = silueta(uv, vTipoB, sem, ruido);
  vec2 sil = mix(sa, sb, vMez);
  float dens = sil.x, tronco = sil.y;

  float a = max(dens, tronco);
  if(a < 0.02) discard;

  /* Volumen barato y MULTIPLICATIVO: si la luz se suma, el follaje oscuro
     se convierte en un borrón del color del sol y pierde el verde. */
  float sunX = normalize(uSunDir).x;
  float lado = 0.40 + 0.60*smoothstep(-0.6,0.6, x*sign(sunX)+0.10);
  float base = 0.42 + 0.58*smoothstep(0.0,0.60,y);
  vec3 luz = ambiente(uSkyTop)*0.55 + uSunCol*lado*1.10*(1.0-uNoche*0.85);

  vec3 propio = mix(vCol, vec3(0.055,0.038,0.026), tronco*0.9);  /* corteza */
  vec3 col = propio*luz*base;

  float niebla = 1.0 - exp(-vDist*uNiebla);
  col = mix(col, uHaze, niebla);

  col = aces(col*uExposure);
  col = pow(max(col,0.0), vec3(1.0/2.2));
  frag = vec4(col, a);
}`;

/* ---------- cajas (casas, torres, vallas, porterías) ---------- */
const CAJA_VS = `#version 300 es
in vec3 pos;
in vec3 nor;
in vec3 iPos;
in vec3 iEsc;
in vec4 iCol;      /* rgb + tipo(a): 0 muro, 1 tejado, 2 metal */
out vec3 vNor, vCol, vMundo, vLocal, vEsc;
out float vTipo, vDist, vAlt;
uniform mat4 uViewProj;
uniform vec3 uCamPos;
void main(){
  vec3 p = iPos + pos*iEsc;
  vMundo = p;
  vLocal = pos; vEsc = iEsc;
  vNor = nor; vCol = iCol.rgb; vTipo = iCol.a;
  vAlt = p.y;
  vDist = length(uCamPos - p);
  gl_Position = uViewProj*vec4(p,1.0);
}`;

const CAJA_FS = `#version 300 es
precision highp float;
in vec3 vNor, vCol, vMundo, vLocal, vEsc;
in float vTipo, vDist, vAlt;
out vec4 frag;
uniform vec3 uHaze, uSunDir, uSunCol, uSkyTop;
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
  float cielo = 0.5 + 0.5*n.y;
  float sm = enSombra(vMundo, 1.0-dif);                    /* luz ambiente del cielo */
  float sombraVis = mix(1.0, 0.46, (1.0 - sm)*(1.0 - uNoche*0.85));
  vec3 col = vCol*(ambiente(uSkyTop)*cielo*0.70
                 + uSunCol*dif*1.25*(1.0-uNoche*0.8))*sombraVis;

  /* Ventanas de verdad, en rejilla y medidas en metros sobre la fachada.
     Un muro liso es lo que hacía que el caserío pareciera cajas. */
  if(vTipo < 0.5 && abs(n.y) < 0.5){
    float ancho = abs(n.x) > 0.5 ? vEsc.z : vEsc.x;
    float u = (abs(n.x) > 0.5 ? vLocal.z : vLocal.x) * ancho;
    float v = vLocal.y * vEsc.y;
    /* una ventana cada 2,6 m de ancho y cada 3,1 m de alto */
    vec2 c = vec2(u/2.6, (v-1.1)/3.1);
    vec2 f = abs(fract(c) - 0.5);
    float hueco = (1.0 - smoothstep(0.20,0.30,f.x)) * (1.0 - smoothstep(0.16,0.26,f.y));
    /* ni bajo el alero ni pegadas al suelo */
    hueco *= step(1.0, v) * (1.0 - step(vEsc.y - 0.9, v));
    /* de lejos la rejilla haría moiré: se apaga con la distancia */
    hueco *= 1.0 - smoothstep(160.0, 420.0, vDist);
    if(hueco > 0.01){
      vec3 cristal = mix(vec3(0.10,0.13,0.17), uSkyTop*1.4, 0.45);
      col = mix(col, cristal, hueco*0.85);
      /* de noche, algunas encendidas */
      float enc = step(0.45, fract(sin(floor(c.x)*12.9 + floor(c.y)*78.2 + vEsc.x)*43758.5));
      col += vec3(1.0,0.76,0.40)*hueco*enc*uNoche*1.4;
    }
  }
  if(vTipo > 1.5 && vTipo < 2.5) col *= 0.8;      /* metal, más mate */

  float niebla = 1.0 - exp(-vDist*uNiebla);
  col = mix(col, uHaze, niebla);
  col = aces(col*uExposure);
  col = pow(max(col,0.0), vec3(1.0/2.2));
  frag = vec4(col, 1.0);
}`;

/* ═══════════ Distribución de la escena ═══════════
   Un solo reparto de huecos que sirve para los cuatro mundos. Las
   coordenadas están en metros, con el campo (105 x 68) centrado en 0. */

/* Relieve del terreno, réplica exacta del shader. Todo lo que se planta
   en el mundo tiene que apoyarse en él o quedará flotando. */
/* Réplica EXACTA del hash y el ruido del shader. Si difieren aunque sea un
   poco, los árboles y las casas quedan flotando o enterrados. */
const fract = v => v - Math.floor(v);

function hash21j(px, py){
  /* GLSL: q = fract(vec3(p.xyx)*0.1031)  →  qz es igual que qx */
  let qx = fract(px*0.1031), qy = fract(py*0.1031), qz = fract(px*0.1031);
  const d = qx*(qy+33.33) + qy*(qz+33.33) + qz*(qx+33.33);
  qx += d; qy += d; qz += d;
  return fract((qx+qy)*qz);
}
function vnoise2j(x, y){
  const ix = Math.floor(x), iy = Math.floor(y);
  let fx = fract(x), fy = fract(y);
  fx = fx*fx*(3-2*fx); fy = fy*fy*(3-2*fy);
  const a = hash21j(ix,iy),   b = hash21j(ix+1,iy);
  const c = hash21j(ix,iy+1), d = hash21j(ix+1,iy+1);
  const ab = a + (b-a)*fx, cd = c + (d-c)*fx;
  return ab + (cd-ab)*fy;
}
function fbm2j(x, y, oct){
  let s = 0, a = 0.5;
  for(let i=0;i<oct;i++){ s += a*vnoise2j(x,y); x*=2.02; y*=2.02; a*=0.5; }
  return s;
}
function alturaTerreno(x, z){
  const h = 78.0*(fbm2j(x*0.00052 + 31.7, z*0.00052 + 12.3, 4) - 0.46)
          + 21.0*(fbm2j(x*0.0024  +  7.1, z*0.0024  + 55.9, 3) - 0.46);
  const dx = Math.max(Math.abs(x) - 88.0, 0);
  const dz = Math.max(Math.abs(z) - 60.0, 0);
  const t = Math.min(Math.hypot(dx, dz)/130.0, 1);
  const explanada = 1 - t*t*(3-2*t);
  return h*(1 - explanada);
}

function rnd(semilla){                      /* aleatorio reproducible */
  let s = semilla >>> 0;
  return () => {
    s = (s*1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/* Apariencia del arbolado en cada mundo: tipo, tamaño y color. */
/* sector de agua por mundo, para no plantar árboles en el mar */
const AGUA_MUNDO = {
  pueblo:{w:0,az:0,ancho:0,dist:1e9}, costa:{w:1,az:0.55,ancho:1.55,dist:150},
  sabana:{w:1,az:-2.30,ancho:0.62,dist:380}, invierno:{w:0,az:0,ancho:0,dist:1e9},
};

const ARBOL_MUNDO = {
  pueblo:   {tipo:0, alto:[7,13],  ancho:[5,9],  col:[0.19,0.31,0.12], densidad:1.0},
  costa:    {tipo:0, alto:[5,9],   ancho:[4,7],  col:[0.16,0.30,0.18], densidad:0.7},
  sabana:   {tipo:1, alto:[6,10],  ancho:[9,15], col:[0.34,0.36,0.17], densidad:0.85},
  invierno: {tipo:2, alto:[7,12],  ancho:[5,8],  col:[0.30,0.26,0.24], densidad:0.9},
};

/* Caserío: en la sabana desaparece (escala 0) y deja sitio a unas casas bajas. */
const CASA_MUNDO = {
  pueblo:   {n:1.0, alto:[6,13], muro:[0.78,0.70,0.58], tejado:[0.52,0.26,0.17]},
  costa:    {n:0.7, alto:[6,11], muro:[0.86,0.86,0.84], tejado:[0.38,0.36,0.40]},
  sabana:   {n:0.35,alto:[3, 5], muro:[0.72,0.58,0.40], tejado:[0.46,0.36,0.22]},
  invierno: {n:0.9, alto:[6,12], muro:[0.62,0.60,0.60], tejado:[0.82,0.84,0.88]},
};

function generarEscena(){
  const r = rnd(20260821);
  const arboles = [], casas = [], estructuras = [];

  /* ── arbolado: anillo alrededor del campo, más denso en el lado lejano ── */
  for(let i=0;i<260;i++){
    const ang = r()*Math.PI*2;
    const rad = 78 + Math.pow(r(),0.55)*420;
    const x = Math.cos(ang)*rad*1.35, z = Math.sin(ang)*rad;
    /* despeja el rectángulo del campo y sus bandas */
    if(Math.abs(x) < 74 && Math.abs(z) < 50) continue;
    arboles.push({x, z, s:r(), esc:0.6+r()*0.8, tipoLado: Math.sin(ang)});
  }

  /* ── caserío: un pueblo agrupado en un lado ── */
  for(let i=0;i<54;i++){
    const ang = -0.9 + (r()-0.5)*1.5;
    const rad = 160 + Math.pow(r(),0.7)*300;
    casas.push({x:Math.cos(ang)*rad*1.2, z:Math.sin(ang)*rad, s:r(),
                w:7+r()*9, d:7+r()*9, giro:r()*Math.PI});
  }

  /* ── torres de luz: cuatro, en las esquinas del recinto ── */
  for(const sx of [-1,1]) for(const sz of [-1,1])
    estructuras.push({tipo:'torre', x:sx*61, z:sz*42});

  /* ── porterías ── */
  for(const s of [-1,1]) estructuras.push({tipo:'porteria', x:s*52.5, z:0, lado:s});

  /* ── valla perimetral ── */
  estructuras.push({tipo:'valla'});

  return {arboles, casas, estructuras};
}

/* Malla de una caja unitaria centrada en XZ y apoyada en y=0. */
function mallaCaja(){
  const p=[], n=[];
  const caras = [
    {nor:[0,0,1],  v:[[-.5,0,.5],[.5,0,.5],[.5,1,.5],[-.5,1,.5]]},
    {nor:[0,0,-1], v:[[.5,0,-.5],[-.5,0,-.5],[-.5,1,-.5],[.5,1,-.5]]},
    {nor:[1,0,0],  v:[[.5,0,.5],[.5,0,-.5],[.5,1,-.5],[.5,1,.5]]},
    {nor:[-1,0,0], v:[[-.5,0,-.5],[-.5,0,.5],[-.5,1,.5],[-.5,1,-.5]]},
    {nor:[0,1,0],  v:[[-.5,1,.5],[.5,1,.5],[.5,1,-.5],[-.5,1,-.5]]},
  ];
  for(const c of caras){
    const [a,b,cc,d] = c.v;
    for(const v of [a,b,cc, a,cc,d]){ p.push(...v); n.push(...c.nor); }
  }
  return {pos:new Float32Array(p), nor:new Float32Array(n), cuenta:p.length/3};
}

/* Disco de suelo por anillos concéntricos: mucha resolución cerca del campo
   y triángulos grandes lejos, donde nadie los mira. */
function mallaSuelo(){
  const radios = [0,4,9,18,30,46,66,92,124,164,214,276,352,448,568,
                720,910,1150,1450,1830,2300,2900,3700,4700,6000,
                8000,11000,15000,20000];
  const SEG = 120, p = [];
  for(let r=0; r<radios.length-1; r++){
    const r0 = radios[r], r1 = radios[r+1];
    for(let i=0;i<SEG;i++){
      const a0 = i/SEG*Math.PI*2, a1 = (i+1)/SEG*Math.PI*2;
      const c0=Math.cos(a0), s0=Math.sin(a0), c1=Math.cos(a1), s1=Math.sin(a1);
      /* estirado en X para que el disco cubra bien el campo, que es alargado */
      const K = 1.35;
      p.push(r0*c0*K, r0*s0,  r1*c0*K, r1*s0,  r1*c1*K, r1*s1);
      p.push(r0*c0*K, r0*s0,  r1*c1*K, r1*s1,  r0*c1*K, r0*s1);
    }
  }
  return {pos:new Float32Array(p), cuenta:p.length/2};
}

/* Prisma triangular: el tejado a dos aguas. Una caja plana como cubierta
   es lo que delataba que las casas eran cajas apiladas. */
function mallaTejado(){
  const pos=[], nor=[];
  const V=(x,y,z,n)=>{ pos.push(x,y,z); nor.push(...n); };
  const s2 = Math.SQRT1_2;
  /* faldón +z y faldón -z */
  V(-.5,0,.5,[0,s2,s2]); V(.5,0,.5,[0,s2,s2]); V(.5,1,0,[0,s2,s2]);
  V(-.5,0,.5,[0,s2,s2]); V(.5,1,0,[0,s2,s2]); V(-.5,1,0,[0,s2,s2]);
  V(.5,0,-.5,[0,s2,-s2]); V(-.5,0,-.5,[0,s2,-s2]); V(-.5,1,0,[0,s2,-s2]);
  V(.5,0,-.5,[0,s2,-s2]); V(-.5,1,0,[0,s2,-s2]); V(.5,1,0,[0,s2,-s2]);
  /* hastiales */
  V(.5,0,.5,[1,0,0]); V(.5,0,-.5,[1,0,0]); V(.5,1,0,[1,0,0]);
  V(-.5,0,-.5,[-1,0,0]); V(-.5,0,.5,[-1,0,0]); V(-.5,1,0,[-1,0,0]);
  return {pos:new Float32Array(pos), nor:new Float32Array(nor), cuenta:pos.length/3};
}
