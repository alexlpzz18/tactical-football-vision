# Plan de reentrenamiento del detector de balón: el balón pegado al pie (3-oct-2026)

**Por escrito y SIN lanzar.** Nada se entrena sin el OK de Alex.

## Por qué

Lo que el sistema pierde del balón es, sobre todo, el balón en el suelo pegado al pie
de un jugador, tapado a medias o en conducción, a resolución completa
(`docs/balon_en_vuelo.md`, GT leído a mano: 15 de 25 visibles). No es la fusión del
postproceso (el modelo del balón es aparte y no deja caja encima) y no se arregla
bajando el umbral: a 0,15 se recuperan 3 de 9 pero los cambios de objeto se duplican
(`docs/colab_balon_umbral_bajo.md`). Queda enseñárselo al modelo.

## Los datos: `outputs/pool_balon_pegado/` (no se versiona)

`scripts/preparar_pool_balon_pegado.py`, semilla fija. **153 imágenes**:

| | imágenes | de dónde |
|---|---|---|
| train | 102 | 30 del etiquetado dirigido (6 casos del GT × 5 frames) + 72 nuevas |
| val | 15 | minutos 13 y 19 enteros (para la parada temprana, ver abajo) |
| test | 36 | minutos 0, 9, 10 y 17 enteros |

- Candidatos: frames SIN balón elegido dentro de un hueco ≤ 1,5 s de la pista de
  producción, con el balón a ≤ 2,5 m de un jugador antes y después y casi quieto
  (≤ 3 m) entre medias: 1.039 frames en 343 huecos. **Un frame por hueco** (los de un
  mismo hueco son casi la misma imagen), ≥ 1,5 s entre dos elegidos, por rondas entre
  minutos y equilibrando los tres tercios del campo (el cercano tiene pocos: allí el
  balón es grande y casi siempre se detecta).
- **Test por MINUTOS enteros**, uno de cada bloque de 5: frames vecinos son casi
  idénticos y mezclarlos inflaría el resultado. **El test no se mira hasta medir**
  (en la revisión de las cajas solo se miró `hoja_train.jpg`).
- **Ningún frame nuevo de entrenamiento a ±3 s del banco de medida** (38 del GT de
  desempates, 25 del GT de vuelo) ni en los dos tramos etiquetados (365-378 y
  990-1005 s). Excepción pedida por Alex: los 30 dirigidos entran a entrenar aunque
  sean del GT de vuelo, porque son justo los ejemplos que el modelo no sabe; **esos 6
  casos (V05, V06, V15, V16, V18, V24) ya no valen para medir el beneficio.**
- Cada imagen trae una caja PRE-PUESTA (YOLO y COCO) donde el sistema cree que está el
  balón (en los nuevos, interpolada entre la última y la siguiente posición medida;
  en los dirigidos, el círculo que nombró Alex), del tamaño de un balón ahí según la
  homografía. Revisada a ojo en train: casi todas caen sobre el balón o junto a él.

## Cuánto lleva etiquetarlo

Herramienta: **CVAT**, como el GT de tracking. Dos tareas, `train` y `test`, para no
mezclar el split; en cada una se importan `images/` y `preanotaciones_coco.json`, se
ajusta la caja al balón visible (aunque esté medio tapado: cubre lo que se VE), se borra
si el balón no se ve (la imagen queda como ejemplo sin balón, que también enseña) y se
exporta en **YOLO 1.1**.

Estimación: con la caja ya cerca, ~10-15 s por imagen ajustándola, ~5 s borrándola y
~30 s en las difíciles → **35-50 min** las 153, más ~10 min de crear las tareas y
exportar. Por lo visto en el GT de vuelo, esperamos que ~60 % tengan el balón visible.

⚠️ Antes de entrenar se cuentan los negativos que deja el etiquetado: si pasan de la
mitad del pool, se avisa a Alex (el reentreno aprendería sobre todo "aquí no hay balón";
v1 tenía un 37 % de negativos).

## Cómo entrenar

1. **Partir de `best_balon_v1.pt`, no desde cero.** Con 117 imágenes nuevas no se
   reaprende el balón entero; se ajusta lo que ya sabe. Desde cero habría que juntar
   todo y arriesgar lo que ya funciona.
2. **Junto con el dataset original** (el de v1, en Drive: `balon_benja_frames.zip` y
   sus etiquetas), para que no olvide el balón normal (olvido catastrófico): el pool
   repetido ×3 para que pese, el resto tal cual.
3. Mismos hiperparámetros de base que v1 (`configs/entrenamiento_balon.yaml`, bloque
   `reentreno`; corregido el 3-oct: la base es yolov8s, no la 'n' que decía:
   yolov8s, imgsz 1280, batch 8, la misma augmentation) salvo: **lr0 = 0,001** (diez
   veces menor: es un ajuste fino), **40 épocas**, paciencia 15, semilla fija.
4. Validación para la parada temprana: la del dataset original **más la del pool**
   (minutos 13 y 19 enteros, 15 imágenes, sin dirigidos). Ajuste de Alex: con solo la
   del dataset original, `best.pt` saldría de las primeras épocas —esa validación no ve
   lo nuevo— y el reentreno no aprendería el balón pegado al pie. **El test del pool no
   entra en ningún paso del entrenamiento.**
5. Antes de entrenar, dos comprobaciones (en Colab):
   - volcar 50 imágenes aumentadas y contar cuántas conservan el balón (≥ 95 %,
     regla de `plan_deteccion_balon.md`);
   - listar de qué frames/minutos sale el dataset original. Si incluye frames de los
     minutos de test o del banco, se anota (los dos modelos los habrían visto igual),
     y si coincide algún frame exacto con el test del pool, se saca del test.

Coste estimado en T4, a confirmar: entrenamiento ~45-60 min; la pasada de inferencia
del partido entero con el modelo nuevo, ~30-40 min.

## Cómo medir: el criterio, fijado ANTES de entrenar

Tres medidas, cada una contra el modelo de producción (v1) en las MISMAS condiciones
(confianza 0,35, esquema mixto):

**A. Test del pool** (36 imágenes, minutos nunca vistos): un acierto es una detección
cuyo centro cae a ≤ max(8 px, diagonal de la caja etiquetada) del centro de la caja de
Alex; cualquier otra detección es falso positivo (en una imagen sin balón, todas).

**B. Partido entero por la cadena de producción**: caché nuevo con el modelo nuevo
(`detectar_balon.py`, esquema mixto, 0,35) y el banco de `medir_umbral_balon.py`.

**C. Lo ganado, a ojo**: 30 frames al azar donde el modelo nuevo elige balón y el viejo no.

Se adopta solo si se cumple TODO:

| | criterio |
|---|---|
| 1 | A: recall del nuevo − recall del viejo ≥ **+0,25**, que se REESCRIBE en balones absolutos al contar los positivos reales del test (`contar_etiquetado_pool.py`: ⌈0,25 × positivos⌉ balones más que v1). Con menos de 12 positivos, el test se amplía con más frames de los MISMOS minutos de test antes de entrenar |
| 2 | A: falsos positivos por imagen del nuevo ≤ los del viejo + **0,10** |
| 3 | B: GT de desempates **≥ 35/38** (lo que da producción con la misma vara) |
| 4 | B: cambios de objeto **≤ 3/min** (producción: 2,85) |
| 5 | B: fracción en las 5 marcas de verdad **= 0** |
| 6 | B: duración anclada ≤ 19,4 s; si la supera, se mira y solo vale si es una parada |
| 7 | B: en los dos tramos etiquetados, lo que no es balón **no sube** |
| 8 | B: de los 8 casos visibles del GT de vuelo NO usados para entrenar (V03, V07, V08, V09, V12, V14, V17, V19), **≥ 2 recuperados** (producción: 0) |
| 9 | C: **≥ 2/3 balón real y ≤ 1/6 basura clara** |

Si falla, **un segundo intento** como mucho (otra proporción del pool o otro lr). Si
falla otra vez, se cierra y se documenta el negativo (regla del proyecto: dos intentos).

## Lo que esta medida NO dice

- Todo es del MISMO partido (mismo día, misma cámara). Un detector que mejora aquí
  puede no mejorar en otro partido.
- Villaviciosa no tiene caché de balón: la segunda pata no se puede medir, igual que
  en el selector.


## Correcciones de la receta antes de entrenar (5-oct-2026)

- **La config no era la receta de v1.** `notebooks/entrenamiento_balon_v1.ipynb` usó `hsv_h 0,15`,
  `hsv_s 0,7`, `hsv_v 0,5` (la config decía 0,015 / 0,5 / 0,4), `batch -1`, 100 épocas y
  `optimizer` automático. El reentreno usa lo de v1 (bloque `reentreno.augmentation`).
- **`lr0` no tenía efecto.** Con `optimizer` automático, ultralytics ignora `lr0` (v1 acabó
  en AdamW con lr 0,002). El reentreno fija AdamW con lr0 0,0002: diez veces menor que lo
  que v1 usó de verdad.
- **Augmentation, PENDIENTE.** La comprobación con 50 imágenes dio 92 % sin mosaico
  (regla ≥ 95 %). Se repite con las 502 y 3 semillas, atribuyendo la pérdida a escala o
  traslación. ⚠️ **Si la de v1 no llega al 95 %, el `scale`/`translate` que se adopte YA NO
  SERÁ EL DE v1**: se anotará aquí con el % de cada valor del barrido. La celda de
  entrenamiento no corre mientras `reentreno.augmentation_medida` sea `false`.
- **Cruce test/original, PENDIENTE.** El original cubre los 20 minutos (40 imágenes por
  minuto), incluidos los minutos de test y validación del pool. Falta saber si hay frames
  repetidos o a ≤ 2 frames (`scripts/cruzar_original_pool.py`).
