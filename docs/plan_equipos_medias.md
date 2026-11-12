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

---

## Resultado (12-nov)

Arnés de los intentos anteriores; el alevín B con el mini-GT a ojo (`medir_gt_equipos_alevinb.py`).
Control = producción (benjamín 1,245 % sobre 723; Villaviciosa, su ventana v2, 22,2 % · 4,69 m).

| brazo | benjamín: eq. mal · ambos ok | Villaviciosa: eq. mal · centroide | alevín B: mini-GT · equilibrio |
|---|---|---|---|
| control | 1,2 % · 52 % | 22,2 % · 4,69 m | 65,8 % · 0,25 |
| medias + v2 + k 2 | 3,0 % · 43 % | 26,2 % · 3,84 m | 64,6 % · 0,38 |
| medias + v2 + k 8 | rota (361 casadas) | 21,9 % · 5,29 m | **55,7 % · 0,73** ⚠️ |
| medias + HS + k 2 | 2,4 % · 45 % | 23,2 % · 3,43 m | 65,8 % · 0,25 |
| voto por ventana (sin medias) | = control | — | 73,4 % |
| **dentro del campo + voto por ventana** | **1,2 % · 52 % (idéntico)** | **17,5 % · 4,01 m** | 73,4 % · 0,39 |
| dentro + voto + medias + v2 + k 2 | 3,0 % · 43 % | 20,9 % · 4,25 m | **79,7 %** · 0,64 |
| dentro + voto + medias + v 0,25 + k 2 | 1,9 % · 47 % | 22,3 % · 4,58 m | 69,6 % · 0,36 |
| dentro + voto + medias + v 0,5 + k 2 | 2,1 % · 47 % | 22,1 % · 4,47 m | 73,4 % · 0,40 |
| dentro + voto + medias + v 0,5 + k 8 | 2,1 % · 47 % | 17,1 % · 3,95 m | 68,4 % · 0,25 |

### Lo que se aprende

- ⚠️ **El equilibrio ENGAÑA**: «medias + v2 + k 8» dejó 8 contra 9 por fotograma (0,73, «pasa») con un
  55,7 % en el mini-GT: equipos equilibrados y repartidos al azar. Es el principio de CLAUDE.md (una
  guarda que cuenta no ve un fallo de identidad). Sin el mini-GT se habría dado por bueno.
- **Causa encontrada y general: el ajuste aprendía «gente de fuera contra jugadores».** «Cercano» es
  profundidad, y por delante de la banda cercana también es cercano: en el alevín B el 23 % de todas
  las detecciones con color son banquillos, entrenadores y público (4 % benjamín, 5 % Villaviciosa).
  `entrenamiento.solo_dentro_del_campo` (nuevo, apagado) lo corrige.
- **Votar por identidad entera mezcla equipos** cuando la identidad es una quimera (F11): el voto por
  ventana (`agregacion.por_observacion`, ya existente, encendido solo en el benjamín) recupera.
- **«Dentro del campo + voto por ventana» mejora dos patas sin tocar la tercera** (benjamín idéntico,
  Villaviciosa −4,7 puntos y −0,68 m, alevín B +7,6 puntos). No lo mejora TODO: en Villaviciosa el
  recuento correcto de B baja (26 → 12 %), así que adoptarlo es decisión de Alex.
- **El alevín B necesita el brillo** para pasar del ~73 % al ~80 % (86 % sobre los que reciben equipo),
  y el brillo empeora el benjamín a cualquier peso: **no hay meseta común** ⇒ por el criterio 5 la
  parte de medias + v2 no se adopta.
