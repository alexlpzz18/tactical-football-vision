# Reentreno del detector de balón con el pool del balón pegado al pie: CERRADO (8-oct-2026)

Plan y criterio, fijados antes de entrenar: `docs/plan_reentreno_balon.md`. Criterio escrito
como código antes de medir: `scripts/medir_reentreno_balon.py::CRITERIO` (commit 92516e1).
Declarado antes de ver números: el candidato era `best.pt` y `last.pt` solo entraba si
best.pt fallaba. **Fallaron los dos, por el criterio 2. Son los dos intentos: la vía se cierra.**
Nada ha cambiado en producción, que sigue con `best_balon_v1.pt`.

## La receta (`configs/entrenamiento_balon.yaml`, bloque `reentreno`)

- Ajuste fino desde `best_balon_v1.pt` (yolov8s, imgsz 1280).
- Datos: el dataset original de v1 (799 imágenes, el split de v1, semilla 42) + el train del
  pool (102 imágenes) repetido ×3. Validación: la de v1 + la del pool (15 imágenes, minutos
  13 y 19 enteros). El test del pool (36 imágenes, minutos 0, 9, 10 y 17) no entró en ningún paso.
- AdamW con lr0 0,0002 (diez veces menos que lo que v1 usó de verdad), 40 épocas, paciencia 15,
  batch automático, semilla 20261003.
- Augmentation: `scale 0,2 · translate 0,05` (no la de v1, 0,5 / 0,1: la de v1 conservaba el
  balón en el 91,6 % del pool, por debajo del 95 %), color como v1 (`hsv` 0,15 / 0,7 / 0,5),
  mosaico 1,0, volteo horizontal 0,5.
- Paró por paciencia: `best.pt` en la época 13 (mAP50 de validación 0,862) y `last.pt` en la 28.

## Los números (medida A: test del pool, 36 imágenes, 23 con balón)

Esquema mixto de producción, confianza 0,35. Acierto = centro de la detección a ≤ max(8 px,
diagonal de la caja etiquetada) del centro de la caja de Alex; el resto, falsos positivos.

| | aciertos | balones más que v1 (≥ 6) | FP por imagen (≤ 1,21) | FP en las 23 con balón | FP en las 13 sin balón |
|---|---|---|---|---|---|
| v1 (producción) | 0 | — | 1,11 | 26 | 14 |
| `best.pt` (ép. 13) | 5 | **+5 ✗** | **2,47 ✗** | 51 | 38 |
| `last.pt` (ép. 28) | 9 | **+9 ✓** | **2,25 ✗** | 51 | 30 |

Sin los 3 frames de test a ≤ 2 frames del original (informativo, mismo umbral de 6): +5 y +9,
los mismos, porque ninguno de los dos modelos acierta en esos frames. FP por imagen 2,52 y
2,27, contra un límite de 1,22.

La medida B (partido entero, criterios 3-8) y la C (a ojo, criterio 9) **no se lanzaron**:
con el criterio 2 suspendido en los dos candidatos, no podían cambiar el veredicto.

## Lo que dice el fallo

- **El reentreno sí aprendió lo que se buscaba**: `last.pt` encuentra 9 de los 23 balones
  pegados al pie del test, que v1 no encuentra ninguno. Es la mejora que pedía el criterio 1.
- **Pero lo paga en falsos positivos**: los duplica (40 → 81-89) y suben también en las
  imágenes SIN balón (14 → 30-38). Ha aprendido "algo redondo junto a un pie" y lo dispara
  donde no hay balón. Con una confianza de 0,35, ese ruido entraría en el selector.

## La lección, antes de cualquier tercer intento

**El pool tenía pocos negativos: un 24 % (36 de 153), frente al 37 % del dataset de v1
(297 de 799).** Un pool que enseña "balón pegado al pie" casi siempre con balón empuja al
modelo a ver balón en cada pie. Antes de un tercer intento hay que **subir los negativos**:
pies, botas y cruces sin balón, sobre todo en los minutos y zonas donde ahora salen los
falsos positivos. Ese tercer intento sería un **experimento nuevo**, con su plan y su
criterio fijados antes, no una tercera vuelta de este.
