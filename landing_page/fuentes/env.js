/* ═══════════════════════════════════════════════════════════════════════
   ENTORNO — cielo, sol, terreno, agua, suelo y campo.

   Todo procedural, sin un solo asset externo.

   Dos decisiones que sostienen la calidad de imagen:

   1. El horizonte es una silueta angular (una altura por azimut). Barato,
      y da cordilleras creíbles con parallaje correcta al girar la cámara.

   2. El suelo y las líneas del campo se resuelven ANALÍTICAMENTE por rayo,
      no con geometría. Una línea de cal es una fórmula, así que se ve
      perfecta desde 400 m y desde 6 m, sin teselado ni aliasing.

   Un "mundo" es solo un juego de parámetros: cambiar de mundo es
   interpolarlos, así que la transición sale gratis.
   ═══════════════════════════════════════════════════════════════════════ */

const ENV_VS = `#version 300 es
in vec2 pos;
void main(){ gl_Position = vec4(pos, 0.0, 1.0); }`;

const ENV_FS = `#version 300 es
precision highp float;
out vec4 frag;

uniform vec2  uRes;
uniform mat4  uInvViewProj;
uniform vec3  uCamPos;
uniform float uTime;

uniform vec3  uSkyTop, uSkyHorizon, uSunDir, uSunCol, uHaze;
uniform float uSunSize, uSunPower, uStars, uExposure;
uniform float uCloud, uCloudHeight;
uniform vec3  uCloudCol;
uniform vec3  uRidgeCol[3];
uniform float uRidgeBase[3], uRidgeAmp[3], uRidgeFreq[3], uRidgeHaze[3], uRidgeSeed[3];
uniform float uWater, uWaterAz, uWaterWide;
uniform vec3  uWaterCol;
uniform vec3  uSueloCol;
uniform float uTierra, uNieve;      /* 0..1 mezcla de tipo de suelo */
uniform float uCampo;               /* visibilidad de las líneas del campo */
uniform float uNiebla;              /* densidad de niebla de distancia */

const float CX = 105.0, CY = 68.0;  /* campo reglamentario, en metros */

/* ---------- ruido ---------- */
float hash11(float p){ p=fract(p*0.1031); p*=p+33.33; p*=p+p; return fract(p); }
float hash21(vec2 p){
  vec3 q = fract(vec3(p.xyx)*0.1031);
  q += dot(q, q.yzx+33.33);
  return fract((q.x+q.y)*q.z);
}
float vnoise(float x){
  float i=floor(x), f=fract(x); f=f*f*(3.0-2.0*f);
  return mix(hash11(i), hash11(i+1.0), f);
}
float vnoise2(vec2 p){
  vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
  return mix(mix(hash21(i),          hash21(i+vec2(1,0)), f.x),
             mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)), f.x), f.y);
}
float fbm1(float x, int oct){
  float s=0.0,a=0.5,f=1.0;
  for(int i=0;i<6;i++){ if(i>=oct) break; s+=a*vnoise(x*f); f*=2.03; a*=0.5; }
  return s;
}
float fbm2(vec2 p, int oct){
  float s=0.0,a=0.5;
  for(int i=0;i<7;i++){ if(i>=oct) break; s+=a*vnoise2(p); p*=2.02; a*=0.5; }
  return s;
}

/* ---------- horizonte ---------- */
float ridge(float az, int i){
  float base,amp,fq,sd;
  if(i==0){ base=uRidgeBase[0]; amp=uRidgeAmp[0]; fq=uRidgeFreq[0]; sd=uRidgeSeed[0]; }
  else if(i==1){ base=uRidgeBase[1]; amp=uRidgeAmp[1]; fq=uRidgeFreq[1]; sd=uRidgeSeed[1]; }
  else { base=uRidgeBase[2]; amp=uRidgeAmp[2]; fq=uRidgeFreq[2]; sd=uRidgeSeed[2]; }
  /* ridged noise: 1-|2n-1| convierte el ruido suave en cimas afiladas */
  float r = 1.0 - abs(fbm1(az*fq + sd, 3)*2.0 - 1.0);
  float m = fbm1(az*fq*0.34 + sd*1.7, 3);   /* agrupa las cimas en macizos */
  return base + amp*(r*0.95 + m*0.70 - 0.80);
}
vec3  ridgeCol(int i){ return i==0?uRidgeCol[0]:(i==1?uRidgeCol[1]:uRidgeCol[2]); }
float ridgeHaze(int i){ return i==0?uRidgeHaze[0]:(i==1?uRidgeHaze[1]:uRidgeHaze[2]); }

/* Aproximación de la curva ACES: comprime altas luces y da contraste. */
vec3 aces(vec3 x){
  return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14), 0.0, 1.0);
}

/* ---------- cielo ---------- */
vec3 skyColor(vec3 d){
  vec3 sd = normalize(uSunDir);
  float t = pow(clamp(d.y,0.0,1.0), 0.40);
  vec3 col = mix(uSkyHorizon, uSkyTop, t);

  float mu = max(dot(d, sd), 0.0);
  col += uSunCol * pow(mu, 5.0)   * 0.42 * uSunPower;
  col += uSunCol * pow(mu, 190.0) * 1.80 * uSunPower;
  col += uSunCol * smoothstep(1.0-uSunSize, 1.0-uSunSize*0.30, mu) * 9.0 * uSunPower;

  if(uStars > 0.001 && d.y > 0.0){
    vec2 sp = d.xz/max(d.y,0.08);
    float s  = vnoise2(sp*70.0);
    float tw = 0.65 + 0.35*sin(uTime*1.7 + hash21(floor(sp*70.0))*40.0);
    col += vec3(0.8,0.86,1.0) * smoothstep(0.972,0.999,s) * tw * uStars
           * smoothstep(0.02,0.30,d.y);
  }

  if(uCloud > 0.001 && d.y > 0.010){
    vec2 cp = d.xz/d.y * uCloudHeight;
    float n = fbm2(cp*0.00085 + vec2(uTime*0.0030, uTime*0.0011), 4);
    float cover = smoothstep(0.56-uCloud*0.16, 0.74, n);
    float lit   = pow(max(dot(d,sd),0.0), 3.0);
    /* base en sombra y borde encendido hacia el sol: da volumen */
    vec3  cc    = mix(uCloudCol*0.55, uCloudCol*1.9 + uSunCol*0.7, lit*0.9);
    col = mix(col, cc, cover*0.92 * smoothstep(0.010,0.12,d.y));
  }
  return col;
}

void main(){
  vec2 uv = (gl_FragCoord.xy/uRes)*2.0 - 1.0;
  vec4 p0 = uInvViewProj*vec4(uv,-1.0,1.0);
  vec4 p1 = uInvViewProj*vec4(uv, 1.0,1.0);
  vec3 d  = normalize(p1.xyz/p1.w - p0.xyz/p0.w);

  float az = atan(d.z,d.x);
  float el = d.y;
  vec3  col = skyColor(d);

  /* cordilleras, de la más lejana a la más cercana. Van sobre el cielo y
     por encima del horizonte; el suelo se dibuja después, bajo el horizonte. */
  for(int i=0;i<3;i++){
    float h = ridge(az, i);
    float aa = fwidth(el)*1.1 + 0.0004;
    float m = smoothstep(h+aa, h-aa, el);
    if(m > 0.001){
      vec3 rc = ridgeCol(i);
      rc *= 0.86 + 0.28*fbm1(az*uRidgeFreq[0]*3.3 + float(i)*11.0, 2);
      float sunAz = atan(uSunDir.z, uSunDir.x);
      float rim = 1.0 - smoothstep(0.0, 1.3, abs(atan(sin(az-sunAz), cos(az-sunAz))));
      rc += uSunCol*rim*0.14*uSunPower;
      rc = mix(rc, uHaze, ridgeHaze(i));
      col = mix(col, rc, m);
    }
  }

  col = mix(col, uHaze, smoothstep(0.035,-0.01,el)*0.16);

  col *= uExposure;
  col = aces(col);                           /* curva filmica con contraste */
  col = pow(max(col,0.0), vec3(1.0/2.2));    /* vuelta a espacio de pantalla */

  /* viñeteado suave: enfoca la mirada sin que se note */
  vec2 vg = gl_FragCoord.xy/uRes - 0.5;
  col *= 1.0 - dot(vg,vg)*0.42;

  frag = vec4(col,1.0);
}`;


/* ═══════════ SUELO ═══════════
   Geometría real (un disco grande) para que la profundidad la escriba el
   rasterizador. Las marcas del campo siguen siendo analíticas: una línea
   de cal es una fórmula, y así se ve perfecta desde 400 m y desde 6 m. */

const SUELO_VS = `#version 300 es
in vec2 pos;                 /* coordenadas en metros sobre el plano */
out vec2 vP;
out float vDist, vRasante, vAlt;
out vec3 vNor;
uniform mat4 uViewProj;
uniform vec3 uCamPos;
uniform float uWater, uWaterAz, uWaterWide, uWaterDist;

float hash21b(vec2 p){
  vec3 q=fract(vec3(p.xyx)*0.1031); q+=dot(q,q.yzx+33.33);
  return fract((q.x+q.y)*q.z);
}
float vnoise2b(vec2 p){
  vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
  return mix(mix(hash21b(i),hash21b(i+vec2(1,0)),f.x),
             mix(hash21b(i+vec2(0,1)),hash21b(i+vec2(1,1)),f.x),f.y);
}
float fbm2b(vec2 p, int oct){
  float s=0.0,a=0.5;
  for(int i=0;i<5;i++){ if(i>=oct) break; s+=a*vnoise2b(p); p*=2.02; a*=0.5; }
  return s;
}

/* Altura del terreno en metros. El campo se asienta sobre una explanada
   plana: fuera de ella el terreno recupera su relieve. */
float alturaTerreno(vec2 p){
  /* centrado en cero: el campo queda a media ladera, no en un hoyo */
  float h = 78.0*(fbm2b(p*0.00052 + vec2(31.7, 12.3), 4) - 0.46)
          + 21.0*(fbm2b(p*0.0024  + vec2( 7.1, 55.9), 3) - 0.46);
  float d = length(max(abs(p) - vec2(88.0, 60.0), vec2(0.0)));
  float explanada = 1.0 - smoothstep(0.0, 130.0, d);
  return mix(h, 0.0, explanada);
}

/* Dentro del agua el terreno se hunde y queda plano: es el fondo del mar. */
float alturaConAgua(vec2 p){
  float h = alturaTerreno(p);
  if(uWater > 0.004){
    float az = atan(p.y, p.x);
    float da = abs(atan(sin(az-uWaterAz), cos(az-uWaterAz)));
    float sector = 1.0 - smoothstep(uWaterWide*0.62, uWaterWide, da);
    float dOrilla = uWaterDist*(0.80 + 0.42*vnoise2b(vec2(az*2.1, 3.7))
                                    + 0.16*vnoise2b(vec2(az*6.3, 1.1)));
    float lejos = smoothstep(dOrilla*0.97, dOrilla*1.16, length(p*vec2(0.80,1.0)));
    h = mix(h, -2.0, uWater*sector*lejos);
  }
  return h;
}

void main(){
  vP = pos;
  float y = alturaConAgua(pos);
  vAlt = y;
  /* normal por diferencias finitas: sin ella el relieve no se ilumina */
  float e = 6.0;
  vNor = normalize(vec3(alturaConAgua(pos-vec2(e,0.0)) - alturaConAgua(pos+vec2(e,0.0)),
                        2.0*e,
                        alturaConAgua(pos-vec2(0.0,e)) - alturaConAgua(pos+vec2(0.0,e))));
  vec3 w = vec3(pos.x, y, pos.y);
  vec3 hacia = w - uCamPos;
  vDist = length(hacia);
  vRasante = 1.0 - abs(normalize(hacia).y);
  gl_Position = uViewProj*vec4(w, 1.0);
}`;

const SUELO_FS = `#version 300 es
precision highp float;
in vec2 vP;
in float vDist, vRasante, vAlt;
in vec3 vNor;
out vec4 frag;

uniform vec3  uHaze, uSueloCol, uSunCol, uSkyTop, uSunDir, uWaterCol, uSkyHorizon;
uniform float uTierra, uNieve, uCampo, uNiebla, uExposure, uNoche;
uniform float uWater, uWaterAz, uWaterWide, uWaterDist, uTime;

const float CX = 105.0, CY = 68.0;

float hash21(vec2 p){
  vec3 q=fract(vec3(p.xyx)*0.1031); q+=dot(q,q.yzx+33.33);
  return fract((q.x+q.y)*q.z);
}
float vnoise2(vec2 p){
  vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
  return mix(mix(hash21(i),hash21(i+vec2(1,0)),f.x),
             mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)),f.x),f.y);
}
float fbm2(vec2 p, int oct){
  float s=0.0,a=0.5;
  for(int i=0;i<6;i++){ if(i>=oct) break; s+=a*vnoise2(p); p*=2.02; a*=0.5; }
  return s;
}
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
` + SOMBRA_GLSL + `

/* ---------- distancias 2D para las marcas del campo ---------- */
float dSeg(vec2 p, vec2 a, vec2 b){
  vec2 pa=p-a, ba=b-a;
  return length(pa - ba*clamp(dot(pa,ba)/dot(ba,ba),0.0,1.0));
}
float dRect(vec2 p, vec2 c, vec2 h){        /* contorno, no relleno */
  vec2 q = abs(p-c)-h;
  return abs(min(max(q.x,q.y),0.0) + length(max(q,0.0)));
}
float dArco(vec2 p, vec2 c, float r){ return abs(length(p-c)-r); }

/* Marcas del campo como campo de distancia. Devuelve 0..1 de "hay cal". */
float marcas(vec2 p, float aa){
  float d = 1e9;
  d = min(d, dRect(p, vec2(0.0), vec2(CX*0.5, CY*0.5)));          /* banda */
  d = min(d, dSeg(p, vec2(0.0,-CY*0.5), vec2(0.0,CY*0.5)));       /* medio */
  d = min(d, dArco(p, vec2(0.0), 9.15));                          /* círculo */
  for(float s=-1.0; s<=1.0; s+=2.0){
    float x = s*CX*0.5;
    d = min(d, dRect(p, vec2(x - s*8.25, 0.0), vec2(8.25, 20.16)));  /* área */
    d = min(d, dRect(p, vec2(x - s*2.75, 0.0), vec2(2.75,  9.16)));  /* pequeña */
    /* arco frontal del área, sólo la parte que sobresale */
    vec2 pen = vec2(x - s*11.0, 0.0);
    if(abs(p.x - (x - s*16.5)) < 20.0 && s*(p.x-(x-s*16.5)) < 0.0)
      d = min(d, dArco(p, pen, 9.15));
    d = min(d, length(p-pen) - 0.12);                               /* punto */
  }
  float w = 0.06;                       /* media anchura de la cal, en metros */
  return 1.0 - smoothstep(w-aa, w+aa, d);
}

/* ---------- suelo ---------- */
vec3 suelo(vec3 hit, float dist, float aa){
  vec2 p = hit.xz;
  vec3 col = uSueloCol;

  /* huella del píxel en metros: por debajo de ella, cualquier patrón es
     ruido. Se usa para apagar el detalle fino con la distancia. */
  float huella  = max(fwidth(p.x), fwidth(p.y));
  float detalle = 1.0 - smoothstep(0.35, 3.0, huella);    /* césped, surcos */
  float medio   = 1.0 - smoothstep(3.0, 26.0, huella);    /* linderos, caminos */

  /* Sólo se evalúa el material que pesa: en un mundo de hierba no se
     paga el ruido de la tierra ni el de la nieve. */
  float wH = (1.0-uTierra)*(1.0-uNieve);
  col = vec3(0.0);
  if(wH > 0.004){
    float franja = smoothstep(0.42,0.58, sin(p.x*0.3927)*0.5+0.5);   /* corte, ~8 m */
    float mod = mix(1.0, mix(0.92,1.09,franja)*(0.90+0.20*fbm2(p*0.09,2)), detalle);
    vec3 hierba = uSueloCol * mod;

    /* Desgaste: las bocas de portería, el círculo central y los puntos de
       penalti son las zonas que más se pisan y en un campo de verdad están
       peladas. Sin esto el césped se ve como una moqueta uniforme. */
    float gast = 0.0;
    for(float sg=-1.0; sg<=1.0; sg+=2.0){
      vec2 boca = vec2(sg*(CX*0.5-2.2), 0.0);
      gast = max(gast, 1.0 - smoothstep(2.5, 10.0, length((p-boca)*vec2(0.55,1.0))));
      vec2 pen = vec2(sg*(CX*0.5-11.0), 0.0);
      gast = max(gast, (1.0 - smoothstep(0.6, 2.4, length(p-pen)))*0.85);
    }
    gast = max(gast, (1.0 - smoothstep(1.5, 11.0, length(p)))*0.55);
    gast *= 0.55 + 0.45*fbm2(p*0.35, 2)*detalle + 0.45*(1.0-detalle);
    vec3 pelado = mix(uSueloCol*0.85, vec3(0.34,0.26,0.15), 0.62);
    col += wH * mix(hierba, pelado, clamp(gast,0.0,1.0)*0.80);
  }
  if(uTierra > 0.004){
    vec3 t = uSueloCol*(0.80 + 0.42*fbm2(p*0.14,3)*detalle + 0.21*(1.0-detalle));
    float uso = 1.0 - smoothstep(0.0,46.0, length(p*vec2(0.62,1.0)));
    col += uTierra*(1.0-uNieve) * mix(t, t*1.20+vec3(0.05,0.035,0.02), uso*0.55);
  }
  if(uNieve > 0.004)
    col += uNieve * uSueloCol * (0.94 + 0.12*fbm2(p*0.5,3)*detalle + 0.06*(1.0-detalle));

  /* fuera del campo el terreno pierde el cuidado y se ensucia */
  vec2 q = abs(p) - vec2(CX*0.5+6.0, CY*0.5+5.0);
  float fuera = smoothstep(0.0, 16.0, max(q.x,q.y));

  if(fuera > 0.01){
    /* Parcelas: celdas grandes de distinto cultivo. Sin esto, desde el aire
       el mundo es una llanura de un solo color y se pierde toda la escala. */
    vec2 celda = floor(p/150.0 + vec2(0.0, 0.37));
    float tipo = hash21(celda*1.7);
    float sub  = hash21(celda*3.1 + 11.0);
    vec3 cultivo = mix(vec3(0.30,0.26,0.11),      /* rastrojo */
                       vec3(0.16,0.24,0.09), tipo);   /* verde */
    cultivo = mix(cultivo, vec3(0.34,0.22,0.12), step(0.78, sub)); /* barbecho */
    cultivo *= 1.0 + (0.40*fbm2(p*0.020, 3) - 0.20)*medio;
    /* surcos dentro de cada parcela, girados por celda */
    float giro = tipo*3.1416;
    vec2 pr = vec2(p.x*cos(giro)-p.y*sin(giro), p.x*sin(giro)+p.y*cos(giro));
    cultivo *= 1.0 + 0.14*(smoothstep(0.45,0.55, fract(pr.x*0.09)) - 0.5)*detalle;
    /* linderos entre parcelas: se ensanchan con la distancia en vez de
       centellear, que es como se comporta una línea real vista de lejos */
    vec2 borde = abs(fract(p/150.0 + vec2(0.0,0.37)) - 0.5);
    float anchoLinde = 0.026 + huella/150.0;
    float linde = 1.0 - smoothstep(0.5-anchoLinde*2.0, 0.5-anchoLinde*0.2,
                                   max(borde.x, borde.y));
    cultivo = mix(vec3(0.24,0.22,0.14), cultivo, mix(1.0, linde, medio));
    /* un camino de tierra que pasa cerca del campo */
    float cam = 1.0 - smoothstep(3.0+huella, 7.0+huella*2.0,
                                 abs(p.y - 96.0 - 26.0*fbm2(vec2(p.x*0.004,0.0),2)));
    cultivo = mix(cultivo, vec3(0.42,0.34,0.22), cam*0.85*medio);

    vec3 lejano = mix(cultivo, uHaze*0.55, 0.18);
    col = mix(col, lejano, fuera*0.92);
  }

  /* cal. Sólo se evalúa cerca del campo: fuera es la mayoría de la pantalla
     y calcular allí una decena de distancias por píxel no aporta nada. */
  float cal = 0.0;
  if(uCampo > 0.004 && abs(p.x) < CX*0.5+3.0 && abs(p.y) < CY*0.5+3.0)
    cal = marcas(p, aa) * uCampo * (1.0 - fuera);
  vec3 colCal = mix(vec3(0.92,0.93,0.88), vec3(0.88,0.86,0.80), uTierra);
  col = mix(col, colCal, cal*0.92);

  return col;
}


void main(){
  /* el antialias de la cal crece con la distancia: nunca centellea */
  float aa = max(vDist*0.0016, 0.010);
  vec3 col = suelo(vec3(vP.x,0.0,vP.y), vDist, aa);

  /* Agua: un sector del plano más allá de cierta distancia. Así el mar de
     la costa y el lago de la sabana son el mismo mecanismo, sólo cambia
     lo ancho que es el sector y a qué distancia empieza. */
  if(uWater > 0.004){
    float az = atan(vP.y, vP.x);
    float da = abs(atan(sin(az-uWaterAz), cos(az-uWaterAz)));
    float sector = 1.0 - smoothstep(uWaterWide*0.62, uWaterWide, da);
    float radio  = length(vP*vec2(0.80,1.0));
    /* la orilla no es un círculo perfecto: se ondula con el azimut */
    float dOrilla = uWaterDist*(0.80 + 0.42*vnoise2(vec2(az*2.1, 3.7))
                                     + 0.16*vnoise2(vec2(az*6.3, 1.1)));
    float lejos  = smoothstep(dOrilla*0.97, dOrilla*1.16, radio);
    float agua   = uWater*sector*lejos;
    if(agua > 0.004){
      /* Fresnel de verdad: el agua es oscura vista a plomo y espejo al ras.
         Sin esto el reflejo domina y el mar parece más bruma. */
      float fres = pow(clamp(vRasante,0.0,1.0), 5.0);
      vec3 refl = mix(uSkyHorizon, uSkyTop, 0.25);
      float onda = fbm2(vP*0.030 + vec2(uTime*0.06, uTime*0.04), 3);
      float brillo = smoothstep(0.58,0.94,onda)
                   * pow(max(normalize(uSunDir).y,0.0), 0.5);
      vec3 wc = mix(uWaterCol, refl, 0.04 + 0.46*fres)
              + uSunCol*brillo*0.5*(0.3+0.7*fres);
      /* la orilla: una línea de espuma que hace que el agua se LEA como agua */
      float orilla = smoothstep(dOrilla*0.95, dOrilla*1.03, radio)
                   * (1.0 - smoothstep(dOrilla*1.03, dOrilla*1.15, radio));
      wc = mix(wc, vec3(0.85,0.88,0.90), orilla*0.55*sector);
      col = mix(col, wc, agua);
    }
  }

  /* El color del terreno ya está autorizado tal y como debe verse, así que
     aquí sólo se tiñe con la luz del mundo en vez de multiplicar por ella. */
  /* Iluminación con la normal del relieve: las laderas que miran al sol se
     encienden y las contrarias se apagan. Es lo que da volumen al paisaje. */
  vec3 n = normalize(vNor), sd = normalize(uSunDir);
  float dif = max(dot(n, sd), 0.0);
  float amb = 0.55 + 0.45*n.y;
  float sm = enSombra(vec3(vP.x, vAlt, vP.y), 1.0 - dif);
  /* la sombra oscurece por sí misma: multiplicarla por el difuso la
     hacía desaparecer con el sol rasante, que es justo cuando más se ve */
  float sombraVis = mix(1.0, 0.42, (1.0 - sm)*(1.0 - uNoche*0.85));
  vec3 tinte = mix(vec3(1.0), uSunCol*1.35, 0.30);
  col *= tinte * (1.0 - uNoche*0.60) * (0.62 + 0.62*dif*(1.0-uNoche*0.7)) * amb * sombraVis;
  float g = dot(uSkyTop, vec3(0.2126,0.7152,0.0722));
  col += mix(uSkyTop, vec3(g), 0.6)*0.05*(1.0-uNoche*0.5);   /* rebote del cielo */

  float niebla = 1.0 - exp(-vDist*uNiebla);
  col = mix(col, uHaze, niebla);
  col = aces(col*uExposure);
  col = pow(max(col,0.0), vec3(1.0/2.2));
  frag = vec4(col,1.0);
}`;

/* ═══════════ Los cuatro mundos ═══════════
   Sitios concretos, no paletas abstractas. Los colores se escriben tal y
   como se quieren ver; el motor los pasa a lineal antes de subirlos. */
const MUNDOS = [
  {
    id:'pueblo', nombre:'Castilla', pie:'Campo municipal · interior · tarde',
    skyTop:[0.16,0.33,0.66], skyHorizon:[0.98,0.68,0.38],
    sunDir:[-0.62,0.115,-0.42], sunCol:[1.00,0.66,0.30], sunSize:0.00042, sunPower:1.25,
    haze:[0.90,0.68,0.46], stars:0, exposure:1.05,
    cloud:0.55, cloudHeight:900, cloudCol:[1.00,0.80,0.66],
    ridge:[
      {base:0.090, amp:0.085, freq:3.4, haze:0.62, seed:12.3, col:[0.36,0.40,0.56]},
      {base:0.048, amp:0.055, freq:6.2, haze:0.48, seed:41.7, col:[0.30,0.35,0.38]},
      {base:0.017, amp:0.026, freq:11.0, haze:0.22, seed:77.1, col:[0.24,0.30,0.20]},
    ],
    water:0, waterAz:0, waterWide:0, waterDist:0, waterCol:[0,0,0], noche:0,
    suelo:'hierba', sueloCol:[0.26,0.40,0.17], niebla:0.00013,
  },
  {
    id:'costa', nombre:'Cantábrico', pie:'Campo junto al mar · amanecer',
    skyTop:[0.10,0.26,0.55], skyHorizon:[0.86,0.86,0.88],
    sunDir:[0.70,0.085,0.30], sunCol:[1.00,0.80,0.60], sunSize:0.00040, sunPower:1.05,
    haze:[0.72,0.79,0.86], stars:0, exposure:1.04,
    cloud:0.70, cloudHeight:1100, cloudCol:[0.94,0.95,0.98],
    ridge:[
      {base:0.072, amp:0.070, freq:2.8, haze:0.70, seed:5.5,  col:[0.34,0.42,0.54]},
      {base:0.034, amp:0.036, freq:5.4, haze:0.56, seed:33.2, col:[0.24,0.34,0.36]},
      {base:0.012, amp:0.018, freq:9.5, haze:0.30, seed:61.8, col:[0.20,0.30,0.24]},
    ],
    water:1, waterAz:0.55, waterWide:1.55, waterDist:150, waterCol:[0.020,0.075,0.135], noche:0,
    suelo:'hierba', sueloCol:[0.22,0.38,0.19], niebla:0.00012,
  },
  {
    id:'sabana', nombre:'Sabana', pie:'Campo de tierra · lago · media tarde',
    skyTop:[0.20,0.42,0.72], skyHorizon:[0.96,0.84,0.58],
    sunDir:[0.34,0.26,-0.72], sunCol:[1.00,0.84,0.48], sunSize:0.00038, sunPower:1.40,
    haze:[0.88,0.76,0.54], stars:0, exposure:1.12,
    cloud:0.30, cloudHeight:1500, cloudCol:[1.00,0.98,0.94],
    ridge:[
      {base:0.048, amp:0.030, freq:2.2, haze:0.74, seed:19.1, col:[0.44,0.42,0.46]},
      {base:0.022, amp:0.017, freq:4.4, haze:0.60, seed:52.4, col:[0.44,0.38,0.24]},
      {base:0.008, amp:0.011, freq:8.0, haze:0.34, seed:88.9, col:[0.40,0.33,0.17]},
    ],
    water:1, waterAz:-2.30, waterWide:0.62, waterDist:380, waterCol:[0.030,0.095,0.115], noche:0,
    suelo:'tierra', sueloCol:[0.50,0.31,0.17], niebla:0.00016,
  },
  {
    id:'invierno', nombre:'Invierno', pie:'Campo helado · focos encendidos · noche',
    skyTop:[0.012,0.022,0.055], skyHorizon:[0.07,0.11,0.20],
    sunDir:[0.40,0.50,0.60], sunCol:[0.55,0.65,0.90], sunSize:0.00075, sunPower:0.35,
    haze:[0.09,0.13,0.22], stars:1, exposure:1.45,
    cloud:0.18, cloudHeight:1000, cloudCol:[0.12,0.16,0.26],
    ridge:[
      {base:0.100, amp:0.090, freq:3.0, haze:0.62, seed:8.8,  col:[0.26,0.33,0.50]},
      {base:0.050, amp:0.050, freq:5.8, haze:0.42, seed:27.6, col:[0.17,0.22,0.34]},
      {base:0.018, amp:0.024, freq:10.5, haze:0.22, seed:70.2, col:[0.11,0.15,0.24]},
    ],
    water:0, waterAz:0, waterWide:0, waterDist:0, waterCol:[0,0,0], noche:1,
    suelo:'nieve', sueloCol:[0.55,0.62,0.76], niebla:0.00015,
  },
];

/* Interpolación lineal entre dos mundos: es toda la transición. */
function mezclarMundos(a,b,t){
  const L =(x,y)=> x+(y-x)*t;
  const LV=(x,y)=> x.map((v,i)=> v+(y[i]-v)*t);
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
    waterDist:L(a.waterDist||300,b.waterDist||300),
    sueloCol:LV(a.sueloCol,b.sueloCol), niebla:L(a.niebla,b.niebla),
    noche:L(a.noche,b.noche),
    tierra:L(a.suelo==='tierra'?1:0, b.suelo==='tierra'?1:0),
    nieve: L(a.suelo==='nieve' ?1:0, b.suelo==='nieve' ?1:0),
  };
}

/* sRGB -> lineal. La paleta se escribe como se quiere ver; el shader
   trabaja en lineal y devuelve a pantalla al final. */
const aLineal = c => c.map(v => Math.pow(v, 2.2));

function subirMundo(gl, prog, m){
  gl.uniform3fv(prog.u.uSkyTop,     aLineal(m.skyTop));
  gl.uniform3fv(prog.u.uSkyHorizon, aLineal(m.skyHorizon));
  gl.uniform3fv(prog.u.uSunCol,     aLineal(m.sunCol));
  gl.uniform3fv(prog.u.uHaze,       aLineal(m.haze));
  gl.uniform3fv(prog.u.uCloudCol,   aLineal(m.cloudCol));
  gl.uniform3fv(prog.u.uWaterCol,   aLineal(m.waterCol));
  gl.uniform3fv(prog.u.uSueloCol,   aLineal(m.sueloCol));
  gl.uniform3fv(prog.u.uSunDir, m.sunDir);
  gl.uniform1f(prog.u.uSunSize, m.sunSize);
  gl.uniform1f(prog.u.uSunPower, m.sunPower);
  gl.uniform1f(prog.u.uStars, m.stars);
  gl.uniform1f(prog.u.uExposure, m.exposure);
  gl.uniform1f(prog.u.uCloud, m.cloud);
  gl.uniform1f(prog.u.uCloudHeight, m.cloudHeight);
  gl.uniform1f(prog.u.uWater, m.water);
  gl.uniform1f(prog.u.uWaterAz, m.waterAz);
  gl.uniform1f(prog.u.uWaterWide, m.waterWide);
  gl.uniform1f(prog.u.uTierra, m.tierra);
  gl.uniform1f(prog.u.uNieve, m.nieve);
  gl.uniform1f(prog.u.uNiebla, m.niebla);
  const rc=[],rb=[],ra=[],rf=[],rh=[],rs=[];
  m.ridge.forEach(r=>{ rc.push(...aLineal(r.col)); rb.push(r.base); ra.push(r.amp);
                       rf.push(r.freq); rh.push(r.haze); rs.push(r.seed); });
  gl.uniform3fv(prog.u.uRidgeCol, rc);
  gl.uniform1fv(prog.u.uRidgeBase, rb); gl.uniform1fv(prog.u.uRidgeAmp, ra);
  gl.uniform1fv(prog.u.uRidgeFreq, rf); gl.uniform1fv(prog.u.uRidgeHaze, rh);
  gl.uniform1fv(prog.u.uRidgeSeed, rs);
}
