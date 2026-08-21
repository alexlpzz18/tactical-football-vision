/* ═══════════════════════════════════════════════════════════════════════
   ENTORNO — cielo, sol, terreno lejano, agua y niebla.

   Todo es procedural: no hay ni un solo asset externo. El horizonte se
   resuelve como una silueta angular (una altura por cada azimut), que es
   barato y da cordilleras creíbles; el agua se limita a un sector del
   horizonte para poder tener mar abierto o un lago concreto.

   Un "mundo" es solo un juego de parámetros. Cambiar de mundo es
   interpolar ese juego, así que la transición sale gratis.
   ═══════════════════════════════════════════════════════════════════════ */

const ENV_VS = `#version 300 es
in vec2 pos;
out vec2 vUv;
void main(){ vUv = pos; gl_Position = vec4(pos, 0.0, 1.0); }`;

const ENV_FS = `#version 300 es
precision highp float;

in vec2 vUv;
out vec4 frag;

uniform mat4 uInvViewProj;
uniform vec3 uCamPos;
uniform float uTime;

uniform vec3  uSkyTop, uSkyHorizon, uSunDir, uSunCol, uHaze;
uniform float uSunSize, uSunPower, uStars, uExposure;
uniform float uCloud, uCloudHeight;
uniform vec3  uCloudCol;
uniform vec3  uRidgeCol[3];
uniform float uRidgeBase[3], uRidgeAmp[3], uRidgeFreq[3], uRidgeHaze[3], uRidgeSeed[3];
uniform float uWater, uWaterAz, uWaterWide;
uniform vec3  uWaterCol;

/* ---------- ruido ---------- */
float hash11(float p){ p = fract(p*0.1031); p *= p+33.33; p *= p+p; return fract(p); }
float hash21(vec2 p){
  vec3 p3 = fract(vec3(p.xyx)*0.1031);
  p3 += dot(p3, p3.yzx+33.33);
  return fract((p3.x+p3.y)*p3.z);
}
float vnoise(float x){
  float i = floor(x), f = fract(x);
  f = f*f*(3.0-2.0*f);
  return mix(hash11(i), hash11(i+1.0), f);
}
float vnoise2(vec2 p){
  vec2 i = floor(p), f = fract(p);
  f = f*f*(3.0-2.0*f);
  return mix(mix(hash21(i), hash21(i+vec2(1,0)), f.x),
             mix(hash21(i+vec2(0,1)), hash21(i+vec2(1,1)), f.x), f.y);
}
float fbm1(float x, int oct){
  float s = 0.0, a = 0.5, f = 1.0;
  for(int i=0;i<6;i++){ if(i>=oct) break; s += a*vnoise(x*f); f *= 2.03; a *= 0.5; }
  return s;
}
float fbm2(vec2 p, int oct){
  float s = 0.0, a = 0.5;
  for(int i=0;i<7;i++){ if(i>=oct) break; s += a*vnoise2(p); p *= 2.02; a *= 0.5; }
  return s;
}

/* Silueta del horizonte: una altura angular por cada azimut. */
float ridge(float az, int i){
  float base, amp, fq, sd;
  if(i==0){ base=uRidgeBase[0]; amp=uRidgeAmp[0]; fq=uRidgeFreq[0]; sd=uRidgeSeed[0]; }
  else if(i==1){ base=uRidgeBase[1]; amp=uRidgeAmp[1]; fq=uRidgeFreq[1]; sd=uRidgeSeed[1]; }
  else { base=uRidgeBase[2]; amp=uRidgeAmp[2]; fq=uRidgeFreq[2]; sd=uRidgeSeed[2]; }
  float n = fbm1(az*fq + sd, 5);
  float m = fbm1(az*fq*0.31 + sd*1.7, 3);
  /* el segundo octavo bajo agrupa las cimas en macizos en vez de dientes */
  return base + amp * (n*0.62 + m*0.55 - 0.42);
}
vec3 ridgeCol(int i){ return i==0 ? uRidgeCol[0] : (i==1 ? uRidgeCol[1] : uRidgeCol[2]); }
float ridgeHaze(int i){ return i==0 ? uRidgeHaze[0] : (i==1 ? uRidgeHaze[1] : uRidgeHaze[2]); }

vec3 skyColor(vec3 d){
  float h = clamp(d.y*0.5+0.5, 0.0, 1.0);
  float t = pow(clamp(d.y,0.0,1.0), 0.42);
  vec3 col = mix(uSkyHorizon, uSkyTop, t);

  /* halo del sol: un lóbulo ancho más un núcleo estrecho */
  float mu = max(dot(d, normalize(uSunDir)), 0.0);
  col += uSunCol * pow(mu, 6.0) * 0.32 * uSunPower;
  col += uSunCol * pow(mu, 220.0) * 1.5 * uSunPower;
  float disc = smoothstep(1.0 - uSunSize, 1.0 - uSunSize*0.35, mu);
  col += uSunCol * disc * 5.0 * uSunPower;

  /* estrellas: sólo arriba, y se apagan cerca del horizonte */
  if(uStars > 0.001 && d.y > 0.0){
    vec2 sp = d.xz / max(d.y, 0.08);
    float s = vnoise2(sp*62.0);
    float tw = 0.7 + 0.3*sin(uTime*1.6 + hash21(floor(sp*62.0))*40.0);
    float star = smoothstep(0.975, 0.999, s) * tw;
    col += vec3(0.85,0.9,1.0) * star * uStars * smoothstep(0.02, 0.35, d.y);
  }

  /* nubes: fbm sobre el plano proyectado a altura de nube */
  if(uCloud > 0.001 && d.y > 0.012){
    vec2 cp = d.xz / d.y * uCloudHeight;
    float n = fbm2(cp*0.0016 + vec2(uTime*0.0035, uTime*0.0012), 6);
    float cover = smoothstep(0.52 - uCloud*0.30, 0.80, n);
    float edge  = smoothstep(0.46 - uCloud*0.30, 0.92, n);
    /* iluminación: los bordes hacia el sol brillan más */
    float lit = pow(max(dot(d, normalize(uSunDir)),0.0), 3.0);
    vec3 cc = mix(uCloudCol, uCloudCol*1.5 + uSunCol*0.4, lit*0.8);
    float fade = smoothstep(0.012, 0.16, d.y);      /* sin nubes pegadas al horizonte */
    col = mix(col, cc, clamp(cover*0.80 + edge*0.18, 0.0, 1.0) * fade * uCloud);
  }
  return col;
}

void main(){
  /* rayo de cámara reconstruido desde la matriz inversa */
  vec4 p0 = uInvViewProj * vec4(vUv, -1.0, 1.0);
  vec4 p1 = uInvViewProj * vec4(vUv,  1.0, 1.0);
  vec3 d = normalize(p1.xyz/p1.w - p0.xyz/p0.w);

  float az = atan(d.z, d.x);
  float el = d.y;
  vec3 col = skyColor(d);

  /* agua: sólo dentro de un sector del horizonte, para poder tener
     mar abierto (sector ancho) o un lago (sector estrecho) */
  if(uWater > 0.001 && el < 0.0){
    float da = abs(atan(sin(az-uWaterAz), cos(az-uWaterAz)));
    float inSector = 1.0 - smoothstep(uWaterWide*0.72, uWaterWide, da);
    if(inSector > 0.001){
      vec3 r = normalize(vec3(d.x, -d.y, d.z));
      vec3 refl = skyColor(r);
      float fres = pow(1.0 - min(-el,1.0), 4.0);
      /* brillo especular hacia el sol, roto en escamas por el oleaje */
      float sun = pow(max(dot(r, normalize(uSunDir)), 0.0), 90.0);
      vec2 wp = d.xz/max(-el,0.02);
      float ripple = fbm2(wp*0.06 + vec2(uTime*0.05, uTime*0.03), 4);
      float glit = smoothstep(0.62, 0.95, ripple) * sun * 3.2;
      vec3 wc = mix(uWaterCol, refl, 0.30 + 0.55*fres) + uSunCol*glit;
      float band = smoothstep(-0.005, -0.10, el);   /* se funde en el horizonte */
      col = mix(col, wc, inSector * band);
    }
  }

  /* cordilleras, de la más lejana a la más cercana */
  for(int i=0;i<3;i++){
    float h = ridge(az, i);
    float aa = fwidth(el) * 1.2 + 0.0006;
    float m = smoothstep(h + aa, h - aa, el);
    if(m > 0.001){
      vec3 rc = ridgeCol(i);
      /* un poco de forma interior para que no sea un recorte plano */
      float shade = fbm1(az*uRidgeFreq[0]*3.1 + float(i)*11.0, 3);
      rc *= 0.88 + 0.24*shade;
      /* luz de borde en el lado del sol */
      float sunAz = atan(uSunDir.z, uSunDir.x);
      float rim = 1.0 - smoothstep(0.0, 1.4, abs(atan(sin(az-sunAz), cos(az-sunAz))));
      rc += uSunCol * rim * 0.10 * uSunPower;
      rc = mix(rc, uHaze, ridgeHaze(i));
      col = mix(col, rc, m);
    }
  }

  /* bruma acumulada justo sobre la línea del horizonte */
  col = mix(col, uHaze, smoothstep(0.10, -0.02, el) * 0.34);

  /* exposición + tono filmico suave (Reinhard extendido) */
  col *= uExposure;
  col = col / (1.0 + col*0.72);
  col = pow(col, vec3(1.0/2.2));

  frag = vec4(col, 1.0);
}`;

/* ═══════════ Los cuatro mundos ═══════════
   Cada uno es un sitio concreto, no una paleta abstracta. */
const MUNDOS = [
  {
    id: 'pueblo',
    nombre: 'Castilla',
    pie: 'Campo municipal · interior · tarde',
    skyTop:[0.19,0.34,0.62], skyHorizon:[0.95,0.72,0.45],
    sunDir:[-0.62,0.13,-0.42], sunCol:[1.00,0.72,0.38], sunSize:0.0055, sunPower:1.15,
    haze:[0.86,0.70,0.53], stars:0.0, exposure:1.16,
    cloud:0.58, cloudHeight:900, cloudCol:[0.98,0.84,0.72],
    ridge:[
      {base:0.040, amp:0.052, freq:0.85, haze:0.80, seed:12.3, col:[0.42,0.45,0.56]},
      {base:0.018, amp:0.034, freq:1.60, haze:0.55, seed:41.7, col:[0.34,0.38,0.40]},
      {base:0.004, amp:0.020, freq:3.10, haze:0.26, seed:77.1, col:[0.26,0.30,0.24]},
    ],
    water:0.0, waterAz:0, waterWide:0, waterCol:[0,0,0],
    suelo:'hierba', sueloCol:[0.30,0.42,0.22], polvo:[0.86,0.70,0.53],
  },
  {
    id:'costa',
    nombre:'Cantábrico',
    pie:'Campo junto al mar · amanecer',
    skyTop:[0.13,0.28,0.52], skyHorizon:[0.78,0.80,0.84],
    sunDir:[0.70,0.10,0.30], sunCol:[1.00,0.83,0.66], sunSize:0.0050, sunPower:0.95,
    haze:[0.78,0.82,0.86], stars:0.0, exposure:1.10,
    cloud:0.72, cloudHeight:1100, cloudCol:[0.90,0.91,0.94],
    ridge:[
      {base:0.030, amp:0.040, freq:0.70, haze:0.86, seed:5.5,  col:[0.40,0.46,0.54]},
      {base:0.010, amp:0.022, freq:1.90, haze:0.62, seed:33.2, col:[0.28,0.36,0.36]},
      {base:0.002, amp:0.012, freq:4.20, haze:0.34, seed:61.8, col:[0.22,0.30,0.26]},
    ],
    water:1.0, waterAz:0.55, waterWide:1.55, waterCol:[0.08,0.19,0.26],
    suelo:'hierba', sueloCol:[0.26,0.40,0.24], polvo:[0.78,0.82,0.86],
  },
  {
    id:'sabana',
    nombre:'Sabana',
    pie:'Campo de tierra · lago · media tarde',
    skyTop:[0.24,0.42,0.68], skyHorizon:[0.92,0.83,0.63],
    sunDir:[0.34,0.30,-0.72], sunCol:[1.00,0.86,0.56], sunSize:0.0048, sunPower:1.30,
    haze:[0.88,0.79,0.60], stars:0.0, exposure:1.20,
    cloud:0.34, cloudHeight:1400, cloudCol:[1.00,0.97,0.90],
    ridge:[
      {base:0.022, amp:0.020, freq:0.55, haze:0.88, seed:19.1, col:[0.46,0.44,0.44]},
      {base:0.006, amp:0.011, freq:1.30, haze:0.66, seed:52.4, col:[0.42,0.38,0.28]},
      {base:0.001, amp:0.007, freq:3.60, haze:0.40, seed:88.9, col:[0.38,0.34,0.20]},
    ],
    water:1.0, waterAz:-2.30, waterWide:0.62, waterCol:[0.10,0.22,0.24],
    suelo:'tierra', sueloCol:[0.52,0.34,0.20], polvo:[0.88,0.79,0.60],
  },
  {
    id:'invierno',
    nombre:'Invierno',
    pie:'Campo helado · focos encendidos · noche',
    skyTop:[0.020,0.035,0.075], skyHorizon:[0.10,0.14,0.22],
    sunDir:[0.40,0.52,0.60], sunCol:[0.62,0.70,0.88], sunSize:0.0075, sunPower:0.30,
    haze:[0.13,0.17,0.26], stars:1.0, exposure:1.30,
    cloud:0.20, cloudHeight:1000, cloudCol:[0.16,0.20,0.30],
    ridge:[
      {base:0.046, amp:0.058, freq:0.80, haze:0.72, seed:8.8,  col:[0.30,0.36,0.50]},
      {base:0.016, amp:0.030, freq:1.70, haze:0.50, seed:27.6, col:[0.20,0.25,0.36]},
      {base:0.003, amp:0.016, freq:3.40, haze:0.28, seed:70.2, col:[0.14,0.18,0.26]},
    ],
    water:0.0, waterAz:0, waterWide:0, waterCol:[0,0,0],
    suelo:'nieve', sueloCol:[0.62,0.68,0.80], polvo:[0.13,0.17,0.26],
  },
];

/* Interpolación lineal entre dos mundos: es toda la transición. */
function mezclarMundos(a, b, t){
  const L = (x,y)=> x + (y-x)*t;
  const LV = (x,y)=> x.map((v,i)=> v + (y[i]-v)*t);
  return {
    skyTop:LV(a.skyTop,b.skyTop), skyHorizon:LV(a.skyHorizon,b.skyHorizon),
    sunDir:LV(a.sunDir,b.sunDir), sunCol:LV(a.sunCol,b.sunCol),
    sunSize:L(a.sunSize,b.sunSize), sunPower:L(a.sunPower,b.sunPower),
    haze:LV(a.haze,b.haze), stars:L(a.stars,b.stars), exposure:L(a.exposure,b.exposure),
    cloud:L(a.cloud,b.cloud), cloudHeight:L(a.cloudHeight,b.cloudHeight),
    cloudCol:LV(a.cloudCol,b.cloudCol),
    ridge:a.ridge.map((r,i)=>({
      base:L(r.base,b.ridge[i].base), amp:L(r.amp,b.ridge[i].amp),
      freq:L(r.freq,b.ridge[i].freq), haze:L(r.haze,b.ridge[i].haze),
      seed:L(r.seed,b.ridge[i].seed), col:LV(r.col,b.ridge[i].col),
    })),
    water:L(a.water,b.water), waterAz:L(a.waterAz,b.waterAz),
    waterWide:L(a.waterWide,b.waterWide), waterCol:LV(a.waterCol,b.waterCol),
    sueloCol:LV(a.sueloCol,b.sueloCol), polvo:LV(a.polvo,b.polvo),
    tierra:L(a.suelo==='tierra'?1:0, b.suelo==='tierra'?1:0),
    nieve:L(a.suelo==='nieve'?1:0, b.suelo==='nieve'?1:0),
  };
}
