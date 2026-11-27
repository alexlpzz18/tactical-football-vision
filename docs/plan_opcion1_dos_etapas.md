# Opción 1 del embudo lejano: detecciones débiles que solo alargan pistas (plan, 27-nov-2026)

Rama `alevinb-preparacion`. Aprobada por Alex para prueba en los 60 s del alevín A. Escrito y
commiteado ANTES de gastar GPU. Solo prueba: no toca los configs de producción.

## Por qué

Embudo del tercio lejano (`docs/segunda_opinion_27nov.md`): con el radio por profundidad faltan el
35 % de las personas del fondo, y «faltan» sigue siendo el 60 % del error de anchura. Del detector,
el 21 % de los que faltan solo aparece con confianza 0,1-0,3; bajar el umbral a secas mete más
basura que personas (0,3 → 0,1: +10,9 puntos de recall y +2,4 falsos positivos por frame en el
fondo). La basura de umbral bajo casi nunca cae sobre una pista viva.

## Qué se prueba

1. **Detección** (Colab, `scripts/colab_villa_dos_etapas.py`, trabajo `villa_dos_etapas` de
   `gpu_colab.py`): el modo full de producción sobre 5:00-6:00 con SAHI a 0,10 sin fusionar; las de
   conf ≥ 0,30 se fusionan EXACTAMENTE como en producción, y las de 0,10-0,30 que no solapan con
   ninguna fuerte se añaden con su confianza.
2. **Tracking**: `bytetrack.umbral_activacion` = **0,2**, no 0,3. En supervision una pista nueva
   exige `umbral_activacion + 0,1`: con 0,3, las detecciones de producción de 0,3-0,4 dejarían de
   poder crear pistas y cambiaría también la base. Con 0,2: todo lo ≥ 0,3 crea pistas como hoy, lo de
   0,2-0,3 solo se empareja con pistas existentes (primera ronda) y lo de 0,1-0,2, en la segunda
   ronda de ByteTrack. Nada por debajo de 0,3 puede iniciar una pista.
3. **Filtro de quietos** (cámara a 0,22 px): una detección débil se quita si en ≥ 50 % de los
   fotogramas muestreados de ± 2 s hay otra caja con el centro a ≤ 2 px. Parámetros fijados aquí.

Variantes (todas con los configs de `main`, exportados con `git show`):
- **V0** producción (el caché de hoy): 35,0 % de faltan lejanos, anchura 5,71 m;
- **V1** caché nuevo solo con las fuertes (control);
- **V2** caché nuevo completo + activación 0,2, sin filtro de quietos;
- **V3** = V2 + filtro de quietos (la propuesta).

## Controles

- Las fuertes del caché nuevo reproducen las cajas del de producción (IoU ≥ 0,9): se espera ≥ 95 %
  en GPU (en la CPU del Mac sale 85-90 %, ya conocido).
- V1 tiene que quedar cerca de V0 (no idéntico: otra máquina, otra versión de las librerías).
- El oráculo con el radio por profundidad usa K = 3,48 px, el medido sobre producción
  (`docs/segunda_opinion_27nov.md`, sección 5), en todas las variantes.

## Criterio de éxito (Alex, 27-nov), sobre V3 contra V0

1. faltan en el tercio lejano (radio por profundidad): 35 % → **≤ 25 %**;
2. error de anchura: 5,71 m → **≤ 4,85 m** (−15 %);
3. peso de «sobran» (EXT) en la anchura: **≤ 5 %** (hoy 2 %).

Se informa también (no decide): el centroide, la profundidad, «sobran» en filas por frame, las
identidades por persona y el equipo equivocado contra el GT.

## Qué podría estar inventando

Una caja débil pegada a la pista de un VECINO (asociación): saldría como fila desplazada o como
sobrante. Por eso el criterio 3 y el recuento de filas desplazadas 2-5 m.

## Antes de lanzar: controles ya hechos en el Mac (27-nov)

- **El evaluador**: pasándole el caché de PRODUCCIÓN como si fuera el nuevo, V1 sale idéntica byte a
  byte a V0, y el oráculo da las cifras de referencia (35,0 % · 5,71 m · sobran 2 %).
- **Activación 0,2 es neutra**: sobre el caché de producción (sin débiles), V2 sale idéntica byte a
  byte a V0. Con 0,3, la base cambia (equipo equivocado contra el GT 25,2 %): por eso 0,2.
- **La celda**, en la CPU del Mac con 3 fotogramas: las fuertes salen en el mismo número que en
  producción (27, 25, 29), el 85-90 % con IoU ≥ 0,9 (la diferencia CPU/GPU ya conocida), y añade 4-7
  débiles por fotograma.

## SigLIP en el alevín A (pregunta de Alex, informativo)

- En 60 s el selector NO decide: 92 parejas, menos de las 100 fijadas. Forzado (mínimo 0), elige
  SigLIP (kappa 0,912 frente a 0,804).
- SigLIP solo actúa dentro del voto por ventana (`agregacion.por_observacion`), que está en la rama y
  no en `main`. Con los configs de `main`, forzarlo deja la salida idéntica byte a byte.
- Con los configs de la rama (oráculo con radio por profundidad):

| | rama, HS | rama, SigLIP forzado | `main`, HS |
|---|---|---|---|
| centroide | 5,07 m | **4,04 m** | 4,82 m |
| equipo equivocado | 19,3 % | **12,2 %** | 24,8 % |
| anchura | 5,01 m | 4,59 m | 5,71 m |
| peso de «faltan» en la anchura | 70 % | 74 % | 60 % |

  Con SigLIP la etiqueta pesa menos en el centroide (43 → 33 %) y «faltan» pasa a mandar todavía
  más. La opción 1 se mide con los configs de `main`, como dice el plan, para que la base sea la del
  oráculo (5,71 m); la combinación con SigLIP es un paso posterior.

---

## Resultado (27-nov)

Colab: L4, 0,20 h encendida (0,47 CU), 7,5 min de detección; el vídeo se subió desde el Mac (no está
en Drive). Caché: 500 frames (7500-8997), 13.713 detecciones, de ellas **2.311 débiles** (0,10-0,30);
el filtro de quietos quita 545.

**Control**: las fuertes del caché nuevo reproducen el **99,9 %** de las cajas de producción (IoU ≥ 0,9).
V1 (solo fuertes) da los mismos faltan y la misma anchura que V0; el centroide (4,67 frente a 4,82 m) y
«sobran» (3,39 frente a 2,57 filas por frame) se mueven porque la feature de color se recalculó en
Colab y el fit cambia un poco.

| | V0 producción | V1 solo fuertes | V2 débiles, activación 0,2 | **V3 = V2 + quietos** |
|---|---|---|---|---|
| faltan en el tercio lejano (radio por profundidad) | 35,0 % | 35,0 % | 30,0 % | **30,5 %** |
| error de anchura | 5,71 m | 5,71 m | 4,73 m | **4,50 m** (−21 %) |
| peso de «sobran» en la anchura | 2 % | 2 % | 1 % | **1 %** |
| centroide | 4,82 m | 4,67 m | 4,77 m | 4,81 m |
| profundidad | 6,63 m | 6,63 m | 7,00 m | 7,00 m |
| sobran, filas por frame | 2,57 | 3,39 | 2,53 | 2,56 |
| identidades | 115 | 115 | 109 | 110 |

**Criterio**: 1. faltan lejanos ≤ 25 % → **NO** (30,5 %) · 2. anchura ≤ 4,85 m → **sí** (4,50) ·
3. «sobran» en la anchura ≤ 5 % → **sí** (1 %).

**Cumple 2 de 3: no se adopta por la letra del criterio.** La anchura baja más de lo pedido (−21 %
frente a −15 %) sin meter sobrantes, pero la presencia lejana solo recupera 4,5 puntos de los 10 que
se pedían. Coherente con el embudo: la parte de 0,10-0,30 era el 21 % de los que faltan y aquí se
recupera ~13 % de ellos; el resto de la presencia perdida es fusión (13 %), detecciones por debajo de
0,10 o nunca vistas (15 %) y tracking (10 %). La profundidad empeora un 6 % (6,63 → 7,00 m), a vigilar.
El filtro de quietos apenas cambia la presencia (30,0 → 30,5 %) y mejora la anchura (4,73 → 4,50 m).
Decide Alex. Regla de dos intentos: este es el intento 1.
