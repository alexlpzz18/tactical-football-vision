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

## Las tres comprobaciones de Alex antes de decidir (27-nov, tarde)

**1. Comparación limpia** (V1 = solo fuertes del caché de Colab, V3 = fuertes + débiles + quietos;
MISMO fichero de colores, configs de `main`):

| | V1 | V3 | delta |
|---|---|---|---|
| anchura | 5,71 m | 4,50 m | **−21 %** |
| centroide | 4,67 m | 4,81 m | +0,14 m |
| profundidad | 6,63 m | 7,00 m | **+0,37 m** |
| «sobran» en la anchura | 2 % | 1 % | −1 punto |
| sobran, filas por frame | 3,39 | 2,56 | −24 % |

El +0,37 m de profundidad viene de las DÉBILES, no del recálculo del color (V1 y V3 comparten
colores y V1 tiene la misma profundidad que producción).

**2. Con los configs de la rama y SigLIP forzado** (etiquetas de SigLIP reasignadas por caja, IoU ≥
0,9, a cada caché: si no, sus índices apuntarían a otras cajas; 4 detecciones de V1 sin etiqueta y las
1.770 débiles de V3, que votan por HS):

| | V1 rama HS | V3 rama HS | V1 rama SigLIP | V3 rama SigLIP |
|---|---|---|---|---|
| anchura | 4,99 m | 4,41 m (−12 %) | 4,59 m | **3,82 m (−17 %)** |
| centroide | 5,09 m | 4,53 m | 4,04 m | **3,57 m** |
| profundidad | 2,47 m | 2,24 m | 1,92 m | **1,77 m** (mejora) |
| «sobran» en la anchura | 5 % | 7 % | 4 % | 4 % |
| sobran, filas por frame | 2,58 | 2,84 | 2,58 | 2,84 |
| faltan lejanos | 35,0 % | 30,5 % | 35,0 % | 30,5 % |

Con el voto por ventana de la rama, la profundidad la manda la etiqueta y las débiles la MEJORAN.

**3. Coste**. Máquina encendida 12 min (0,47 CU a 2,33 CU/h): arranque y Drive ~2 min, modelo 0,5
min, subida del vídeo 2 min, **detección 4,4 min** (11:41:17 → 11:45:41, incluye cargar el modelo y
llegar al frame 7500 decodificando desde el principio), descarga de los colores ~3 min. Cota de
inferencia: ≤ 0,53 s por frame procesado. La pasada de producción del alevín B (conf 0,30) fue de
0,22 s por frame (56,8 min para 15.184 frames). El alevín B entero son 30.418 frames procesados:
**entre 1,9 y 4,5 h de L4, unas 4-10 CU**, más ~10 min fijos por lanzamiento (los vídeos del alevín B
sí están en Drive). El tope de `gpu_colab.yaml` (40 CU) y la proyección tras el primer checkpoint
paran la pasada si se dispara.

---

## Adopción en `alevinb-preparacion` (Alex, 27-nov)

Se adopta con la lectura «con SigLIP» (lo que se usará en F11): anchura 3,82 m, centroide 3,57 m y
profundidad 1,77 m, sin subir «sobran» (4 %).

**En la rama** (los dos F11 usan `configs/tracking.yaml`; el benjamín no se toca):
- `bytetrack.umbral_activacion: 0.20`;
- `filtro_quietas` como etapa del pipeline (`src/tracking/filtro_quietas.py`), encendido. Solo toca
  detecciones con conf < 0,30.
- Control: la etapa del pipeline reproduce byte a byte la variante V3 medida. Con los cachés de
  producción de hoy (sin débiles), la salida de las dos patas F11 tiene que ser idéntica byte a byte
  (comprobación en `outputs/f11_neutralidad/`).

**Checklist antes de lanzar el alevín B en Colab**:
1. **Imagen original sin rectificar**: sí. `colab_alevinb.py --imagen original` detecta sobre el
   fotograma sin corregir (`distorsion` 0) y guarda las cajas en PÍXELES; los metros se ponen después
   en el Mac con la lente (`a_metros_con_lente`, fase `seguimiento`). Recalibrar con Iberpix = repetir
   esa fase en local, sin GPU.
2. **SigLIP**: no se recalcula solo. Para la parte 1 se reasigna en local por caja
   (`scripts/siglip_reasignar.py`, IoU ≥ 0,9: es justo lo que se midió en el alevín A; control: el
   100 % de las fuertes del alevín A recupera etiqueta). Las débiles se quedan sin etiqueta y el voto
   por ventana las decide con el color. La parte 2 no tiene SigLIP: necesitaría su pasada de
   embeddings en Colab (~1,5 CU).
3. **Trabajo** `alevinb_dos_etapas` de `gpu_colab.py`: las dos partes, con nombres NUEVOS
   (`alevinb_p1_conf010`, `_p2_conf010`) para no pisar los cachés de producción. `--max-cu` baja el
   tope de ese lanzamiento (nunca lo sube por encima del YAML).

**Después de Colab** (en el Mac):
1. `gpu_colab.py seguimiento alevinb_dos_etapas` (metros con la lente);
2. `siglip_reasignar.py` de `cache_alevinb_p1.pkl` a `cache_alevinb_p1_conf010.pkl`;
3. apuntar `data/tracking_alevinb/config_alevinb_p1.yaml` (`rutas.cache`, `rutas.cache_colores`) y
   `siglip.etiquetas` del YAML de equipos del alevín B a los ficheros nuevos, banco y mini-GT.
