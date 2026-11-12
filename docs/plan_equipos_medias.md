# Plan: ajustar los equipos sobre MEDIAS por ventana de identidad (tercera vía, automática)

Escrito el 12-nov-2026, ANTES de medir en las patas. Alex: «la gracia es que detecte el color; en el
benjamín funciona perfecto y en este no». Nada manual.

## Por qué (premisa comprobada en el mini-GT del alevín B, sin etiquetas)

Los dos intentos cerrados (`plan_equipos_v2.md`, `plan_equipos_embeddings.md`) cambiaban la
FEATURE. Con etiquetas, las features ya separan (87-90 %): lo que falla es el AJUSTE sin etiquetas,
que agrupa RECORTES SUELTOS, y en este vídeo un recorte suelto es ruido (neblina, 21-29 px,
contraluz). KMeans de 2 sobre el mini-GT (75 jugadores):

| features | recortes sueltos | medias de 1,5 s por identidad | tamaños |
|---|---|---|---|
| HS (hoy) | 75 % | 80 % | 8.081 / 11.919 |
| v2 (HS + brillo + pantalón) | 76 % | **89 %** | 9.585 / 10.415 |
| DINOv2 + v2 | 80 % | 91 % | 9.720 / 10.280 |

Promediar una docena de recortes del mismo jugador quita lo que cambia entre recortes y deja la
equipación. Es la lección del árbitro (su verde solo aparece al promediar) aplicada al ajuste. Y el
ajuste de producción pierde por el camino (66 % con el HS de hoy, contra 75 % de un KMeans de 2):
KMeans de 8 + fusión + los dos grupos más grandes.

## El cambio (detrás de interruptores; por defecto, hoy)

- `entrenamiento.medias_por_ventana_s` (por defecto `null` = hoy): si vale `w`, el ajuste se hace
  DESPUÉS del tracking, sobre la media de cada observación con las de SU identidad a ±`w`/2 (mínimo
  3), y la parte de equipos (voto, catálogo, porteros) ve esas medias. El tracking no usa el
  clasificador en `bytetrack` (producción); con otro perfil se para con un error.
- Ya existen y se combinan: `version_color: 2` (feature v2), `clasificador_color.peso_v_pecho`,
  `peso_pantalon` y `k_clusters`.

## Brazos y medida

Arnés de los intentos anteriores (`banco_equipos_v2.py`, con nombres A/B corregidos) más el mini-GT
del alevín B (`medir_gt_equipos_alevinb.py`):

| brazo | medias | feature | k |
|---|---|---|---|
| control | no | HS | 8 |
| M-v2-k2 | 1,5 s | v2 (pesos 1, 1) | 2 |
| M-v2-k8 | 1,5 s | v2 (pesos 1, 1) | 8 |
| M-hs-k2 | 1,5 s | HS | 2 |

Benjamín: caché v2 = cajas de producción. Villaviciosa: caché v2 de su ventana (otra pasada del
detector, coherente consigo misma; su control es el de esa pasada).

## Criterios (fijados antes de mirar)

1. Interruptor real: con `medias_por_ventana_s: null` el CSV es idéntico al de hoy (test).
2. Benjamín: equipo equivocado ≤ control + 0,5 puntos y «ambos ok» sin bajar más de 2 puntos.
3. Villaviciosa: equipo equivocado ≤ control + 0,5 puntos y centroide no peor que el control.
4. Alevín B: mini-GT ≥ 85 % en jugadores y equilibrio del tramo ≥ 0,7.
5. Un solo brazo para las tres patas; si ninguno pasa, no se adopta nada.
6. ¿Qué podría estar inventando? Una media de una identidad QUIMERA (dos personas) es un color que
   no es de nadie (CLAUDE.md). La ventana corta (1,5 s) limita el daño, y el control es el mini-GT
   por franjas (las quimeras se concentran en los cruces y en el fondo).
