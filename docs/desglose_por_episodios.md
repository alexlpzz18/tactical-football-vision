# El desglose en los minutos malos, el trapecio visible y el suavizado (21-sep-2026)

Rama `experimento/asociacion-global`. `scripts/desglose_por_episodios.py`,
`scripts/suavizado_y_filas_sin_deteccion.py`. Continúa `docs/desglose_del_error.md`.

Alex: *«extiende el desglose a más de una ventana, aunque sea con proxies: quiero
saber si el 83 % de "quién está presente" se sostiene en los minutos malos o si ahí
aparece algo distinto»* y *«mide la pista de las filas es_real=1 a más de 1 m de toda
detección»*.

## Respuesta corta

1. **En los minutos malos el 83 % se sostiene y crece; no aparece nada peor aguas
   abajo.** Todo el déficit sale de las detecciones. Pero hay un **segundo tipo de
   episodio** (visto una vez, en el GT) que los proxies de recuento NO ven.
2. **El campo visible es un trapecio**: a x = 8 m la cámara solo ve 16 m de los 40 de
   ancho. Con el juego junto a la cámara, gente queda fuera de plano *por geometría*.
   Es coherente con tu hipótesis del encuadre; **no la prueba** (haría falta el GT).
3. **La pista de las filas sin detección es el suavizado de 0,5 s, y cuesta poco**:
   +0,066 m de centroide contra el GT (IC 95 % [+0,033, +0,103]). **No causa** las
   filas desplazadas 2–5 m (siguen ahí sin suavizar). No se cambia nada.

## 1. El encuadre es geométrico

Proyectando la cuadrícula del campo a la imagen con la homografía inversa (el pie del
jugador tiene que caer dentro de los 1920×1080):

| x (m) | 4 | 8 | 12 | 16 | 20 | 24 | ≥ 28 |
|---|---|---|---|---|---|---|---|
| y visible (m) | nada | 13-29,5 | 8-32 | 5,5-34,5 | 3,5-37 | 1,5-39,5 | 0-40 |

Solo se ve el 80 % del campo. Junto a la cámara (x < 16) los jugadores de banda quedan
fuera. ⚠️ «Pie fuera» no es «invisible»: un jugador cortado por el borde inferior sigue
saliendo en parte (el portero de A, `docs/portero_cortado.md`); el criterio es
conservador para el borde inferior.

## 2. Los malos son EPISODIOS, y en ellos no empeora nada aguas abajo

Bins de 15 s por detecciones crudas EN CAMPO por frame: **bueno ≥ 13,5 (55 bins) ·
medio (13) · malo < 12 (13 bins = 16 % del tiempo)**. Malos: 3:00, 3:15, 3:30, 4:30,
4:45, 8:00, 9:00, 13:30, 14:00, 14:15, 16:45, 18:30, 20:00 (el último es un fragmento).
Las detecciones en campo correlacionan **−0,63** con las que caen a x < 20 m, y en varios de esos
bins el balón deja de detectarse (3:15, 4:30, 4:45, 8:00, 13:30).

| por frame (ambos equipos) | bueno | medio | **malo** |
|---|---|---|---|
| detecciones crudas en campo | 14,3 | 13,0 | **10,3** |
| filas reales | 15,5 | 14,0 | 10,9 |
| filas A/B | 13,5 | 11,9 | **9,0** |
| detecciones a x < 20 m | 1,5 | 2,6 | **4,4** |
| árbitro contado en un equipo (EXT) | 0,40 | 0,34 | 0,14 |
| filas a > 1 m de toda detección (DES/LOC) | 1,13 | 1,03 | 0,41 |
| filas `otro/staff` sin firma de árbitro (LAB) | 1,48 | 1,58 | 1,09 |
| cambios de etiqueta A↔B (LAB) | 0,06 | 0,07 | 0,03 |

**Las filas A/B bajan 4,6 y las detecciones 4,0**: el tracking casi no pierde nada
(filas 10,9 contra 10,3 detecciones) y ningún proxy de sobrantes, desplazadas o
etiqueta **sube**. O sea, el déficit está **entero aguas arriba** y el trozo MIS (faltan)
crece; los demás se quedan igual o bajan. La confianza del detector no cambia (0,86).

**Error esperado** (⚠️ EXTRAPOLACIÓN: mapa «recuento del equipo → error de centroide»
calibrado con el GT: recuento 7 → 1,00 m · 6 → 2,26 · ≤ 5 → 2,26 con solo **10 pares** ·
≥ 8 → 1,50):

| clase | tiempo | recuento medio | ≤ 5 personas | error esperado |
|---|---|---|---|---|
| bueno | 69 % | 6,77 | 10 % | ≥ 1,55 m |
| medio | 16 % | 5,94 | 38 % | ≥ 1,85 m |
| **malo** | 15 % | **4,56** | **69 %** | **≥ 2,12 m** |

Es un **suelo**: con 4,5 jugadores de media el GT casi no tiene ejemplos, y el tercio 3
del GT ya dio 2,46 m con 6,9. El partido entero saldría a **≥ 1,68 m** (contra los 1,45
del minuto 5).

### Lo que estos proxies NO ven: un segundo tipo de episodio

El **tercio 3 del GT** (el de 2,46 m) cae en el bin 5:45, que es «bueno»: 14,6
detecciones en campo, casi todas las 13,9 personas. Aun así el **21 %** de las personas
no tiene fila (contra el 4 % del tercio 1) y **35 de las 46 filas desplazadas** son de
esos 10 s. Con detecciones normales, ahí falla lo de después. No es un desplazamiento
global (la mediana de las casadas por frame es ≈ 0), no es el árbitro (0 de 46 parejas
usan la fila de la id 292) y no es el retardo del suavizado. Está **sin nombre y visto
una vez**: los proxies de recuento no lo detectan, así que solo un GT dice con qué
frecuencia ocurre.

## 3. La pista: `es_real=1` a más de 1 m de toda detección

Se vuelve a correr el procesador desde el caché con el config de producción, con y sin
el suavizado de 0,5 s. **Control**: la pasada con suavizado reproduce el CSV de
producción (v3) idéntica.

| | filas reales | mediana a detección | > 1 m | > 2 m | > 1 m en x < 20 · 20-40 · > 40 |
|---|---|---|---|---|---|
| **con** suavizado | 174.618 | 0,202 m | **6,9 %** | 2,0 % | 2,4 · 5,1 · **11,5 %** |
| **sin** suavizado | 174.596 | 0,004 m | 0,0 % | 0,0 % | 0 · 0 · 0 |

Sin suavizado, **el 100 % de las filas reales coincide con una detección**: la pista
era el suavizado (la ventana se alarga con la resolución, así que en el fondo mueve la
fila hasta 2,6 m: p99). Es el análogo de las «alas» del balón.

**¿Y perjudica?** Contra el GT (radio 2 m):

| | centroide | casadas | equipo mal | LOC | LAB | EXT | MIS | DES |
|---|---|---|---|---|---|---|---|---|
| con | 1,45 | 723 | 9 | 0,16 | 0,08 | 0,36 | 0,60 | 0,24 |
| sin | 1,39 | 736 | 15 | 0,13 | 0,15 | 0,39 | 0,50 | 0,22 |

Diferencia pareada por (frame, equipo), remuestreo de bloques de 5 s: **con − sin =
+0,066 m** de centroide (IC 95 % [+0,033, +0,103]), +0,068 de anchura ([−0,003, +0,126])
y +0,035 de profundidad ([−0,093, +0,187]). El suavizado empeora el centroide un 4,5 %:
**real pero pequeño**. Y sin suavizado hay más equipo equivocado (15 contra 9 de ~730;
no se ha investigado, son cifras pequeñas).

**Lo que NO explica el suavizado**: las filas desplazadas. Sin suavizado siguen siendo
37 parejas (contra 46 con él), a 2,5 m de mediana en profundidad y el 95 % hacia la
cámara. Ya estaban en la detección. El suavizado como mucho añade 9. De esas 37, el 35 %
tiene una caja solapada con otra (IoU > 0,1) contra el 13 % de las casadas, y sus cajas
son un 11 % más bajas (0,89 de la altura esperada). Es una pista, no una explicación.

**Qué se sigue de aquí** (nada se ha tocado):
- El suavizado se adoptó por credibilidad visual (99,9 % de los pasos < 8,5 m/s) y
  cuesta 0,07 m. Si algún día importa, la salida limpia es la de las «alas» del balón:
  **métricas de equipo sobre la posición medida y replay sobre la suavizada**. Ojo:
  no se ha medido qué pasa con distancia recorrida y velocidades sin suavizar (ahí el
  suavizado sí ayuda), así que no es una decisión gratis.
- La causa de las filas desplazadas (2,5 m hacia la cámara, en la detección) queda
  **sin nombre**.

## 4. GT de recuento: ventanas y coste

Ventanas de 30 s con menos detecciones en campo (sin solape), por el script:

| ventana | frame de inicio | dets en campo | dets a x<20 | por qué |
|---|---|---|---|---|
| **3:10-3:40** | 5.694 | 8,6 | 4,6 | el peor; juego junto a la cámara |
| **4:30-5:00** | 8.092 | 9,3 | 5,9 | segundo peor; pegado al GT actual (5:25) |
| **14:00-14:30** | 25.175 | 11,3 | 6,1 | otro, en la segunda mitad |
| 13:25-13:55 | 24.126 | 11,6 | **3,2** | **control**: pocas detecciones SIN juego cerca de la cámara |

La cuarta es la que discrimina: si el déficit fuera solo encuadre por cercanía, esta
ventana no debería tener déficit; si lo tiene, hay otra causa (detector, oclusión).

Formato recomendado y estimación de tiempo en la respuesta a Alex. El sistema no
sabe cuánto tarda Alex: las cifras son **supuestos** (segundos por imagen) y conviene
calibrar con 5 imágenes cronometradas antes de comprometerse.
