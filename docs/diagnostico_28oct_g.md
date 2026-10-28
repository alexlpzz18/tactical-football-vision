# Diagnóstico 28-oct (g): puerta de calidad de caja y color estable ≥ 1 s en el dibujo

Rama `mejoras-28oct-g`, sale de `main`. Máximo **dos intentos** por mejora. Criterios escritos y
commiteados ANTES de medir. Producción solo detrás de un flag, apagado por defecto. Commit solo con
pytest en 0.

Relojes: archivo; reproductor = archivo + 1:33. Clip 1 = 14:00 del archivo + el segundo del clip.

## 1. Puerta de calidad de caja

### Lo que ya se probó con la «altura relativa de caja» (22-oct, bloque 3)

- **Qué se probó**: f(u, v) = altura esperada de la caja según la posición de su pie (cuadrática,
  pérdida de Huber), y h / f por IDENTIDAD, como señal del ÁRBITRO (un adulto entre niños).
- **Resultado**: en el benjamín separó limpio (1,22 contra ≤ 1,03). En Villaviciosa no pasó el
  umbral (1,14 < 1,15), aunque el árbitro seguía siendo la caja más alta en proporción.
- **Por qué no se validó**:
  - eran 2 identidades de árbitro en 60 s; un AUC de 1,0 con 2 casos dice «es la más alta», no una
    tasa;
  - el control de un jugador al azar llegaba a 0,95-0,97 de p95;
  - se dejó «repetir en la parte entera antes de creérselo», y **no se repitió nunca**.
- **Lo de ahora es otra cosa**: no se pregunta QUIÉN es (árbitro), sino si un RECORTE suelto es de
  fiar para el color. Por recorte, no por identidad.

### La puerta

**La caja esperada**:
- f_h(u, v) y f_w(u, v) son el alto y el ancho esperados de una caja según la posición de su pie
  (u = centro de la base, v = borde inferior, en píxeles). Se ajustan igual que en el 22-oct:
  cuadrática con Huber, sobre TODAS las detecciones del caché de la parte entera.
- Por qué no solo la homografía: la homografía es del PLANO DEL SUELO. Da la escala horizontal en
  el pie (`escala_px_por_m`), pero no la vertical: la altura de una persona no está en el plano.
  El ajuste por posición es «el rango que da la geometría» de esta cámara.

**Anormal** (fijado ahora, intento 1):
- **h / f_h > 1,4** (una caja que coge a dos personas en vertical, como el árbitro con el naranja de
  debajo del caso 11 del 28-oct f);
- o **w / f_w > 1,6** (dos personas una al lado de otra);
- o **h / f_h < 0,6** (un fragmento: cabeza o torso).

**Qué hace**:
- con el flag `agregacion.por_observacion.excluir_cajas_anormales.activo` (apagado por defecto),
  esos recortes NO VOTAN en la media de la ventana de 1,5 s;
- la observación recibe la etiqueta de los demás recortes de su ventana;
- si todos los de la ventana son anormales, votan todos, como hoy.
- Es el mismo camino que ya tiene `excluir_ocluidas` (el conjunto que no vota); cambia solo QUÉ
  recortes entran en el conjunto.
- Villaviciosa no tiene `por_observacion` encendido, así que la puerta ni corre allí. Se dice, no se
  mide.

**Medida**: `desde_cache` de la parte entera del benjamín, con el flag apagado y encendido.
- **Los 9 errores del GT de 30 s**: el casado 1-a-1 a 2 m de `comparar_escalas.casar`, sobre 723
  casadas. Se identifica cada error por (frame, persona del GT).
- **Los 2 errores de la hoja de 120**: la marca contra la etiqueta del DUEÑO de la caja que vio Alex
  (28-oct f / auditoría).
- **Total: 11 errores** antes de la puerta.

**Criterio (el de Alex)**, las tres cosas a la vez:
- **corrige ≥ 6 de los 11**;
- **excluye ≤ 3 %** de las observaciones (detecciones A/B que no votan);
- **0 errores nuevos**, ni en las 723 casadas ni en las 120 filas.

**Control con el flag apagado**: el CSV tiene que salir **idéntico byte a byte** al de `main`.

⚠️ **Poder estadístico, antes de medir**: con 11 errores el criterio decide sobre muy poco. «6 de
11» tiene un IC de Wilson de 28-79 %. Un cambio de 2 o 3 casos puede ser ruido de qué recortes caen
en la ventana. Y «0 nuevos» sobre 843 filas solo descarta un daño grande: con 0/843, el IC llega al
0,45 %. Si pasa, es «no se ve daño y corrige estos casos», no una tasa.

¿Qué podría estar inventando? La puerta excluye recortes de porteros cortados por el borde inferior
(una caja cortada es «baja»). No cambia su etiqueta (la decide la posición), pero cuenta en el 3 %.
Se informa cuántos excluidos son de porteros.

**Intento 2**, solo si el 1 falla y muestra por qué. Criterio nuevo, escrito antes.

## 2. Color estable ≥ 1 s en el dibujo (pizarra y clips)

**Qué**: lo que se DIBUJA no cambia de color hasta que el cambio dura ≥ 1 s.
- Sobre la secuencia de etiquetas de cada identidad, una racha de una etiqueta nueva que dura
  **< 1 s** (del primer frame de la racha al primero de la siguiente) se pinta con el color
  anterior.
- Una racha de ≥ 1 s se pinta desde su PRIMER frame: el render es offline y ve el futuro, así que no
  hay retraso.
- La primera racha de una identidad se pinta tal cual.

**Dónde**:
- `src/report/replay_tactico.py`, con el parámetro `histeresis_visual_s`;
- `scripts/render_clips_26oct.py`, con la misma función.
- Los dos rótulos dicen «color estable ≥ 1 s: SOLO VISUAL, los datos no cambian». En el vídeo va en
  la cabecera de cada frame.

**Comprobaciones**:
- **CSV idéntico byte a byte**: `desde_cache` de la parte entera en la rama (flags por defecto)
  contra el de `main`. El dibujo no escribe el CSV; esto comprueba que la rama tampoco lo cambia por
  otro lado.
- **La guarda `test_renderizadores_no_colapsan.py` tiene que seguir pasando.** Una identidad que
  pasa de A a B y se queda en B (racha ≥ 1 s) tiene que verse con los dos colores. La histéresis no
  es la moda.

**Los 10 eventos** de las notas de Alex del clip 1 (`diagnostico_28oct_balon_inventado.md`):

| # | clip | qué vio Alex | identidades |
|---|---|---|---|
| 1 | 0:04 | B689 y A683 se ponen naranjas un instante | 689, 683 |
| 2 | 0:15 | los dos de la derecha se cambian el id (los colores bien); el blanco pierde la caja | las que cambian de etiqueta en la ventana |
| 3 | 0:21 | el blanco pierde la caja un instante | ídem |
| 4 | 0:40-0:41 | A683 detrás de B708: una caja B708, luego A683 | 683, 708 |
| 5 | 0:44 | el naranja detrás del blanco: la caja se vuelve naranja un instante | 683, 708 |
| 6 | 1:00-1:01 | A683 pasa a B683 un segundo; luego intercambio de ids | 683, 708 |
| 7 | 1:06-1:07 | A708 y B525 en una caja B525; al separarse, A525 y B742 | 708, 525, 742 |
| 8 | 0:00-0:33 | el portero de A: B695 → otro → B → desaparece → A718 | 695, 718 |
| 9 | 1:11 | el árbitro desaparece un instante | la pista del árbitro |
| 10 | 1:30 | el árbitro pasa a A un instante | la pista del árbitro |

**Medida por evento**, en su ventana (el instante ± 1 s; el 8, de 0:00 a 0:34):
- **parpadeo** = una racha de color < 1 s en lo dibujado de alguna de sus identidades;
- un evento **deja de verse como parpadeo** si tenía ≥ 1 en lo crudo y 0 con la histéresis;
- si en lo crudo no tenía ninguno, lo que Alex vio no era un cambio de color (una caja que se pierde,
  un id que cambia sin cambiar de color), la histéresis no lo toca, y **cuenta como NO resuelto**.
- Además se comprueba a ojo en el clip renderizado.

**Criterio (el de Alex)**: **≥ 8 de 10** dejan de verse como parpadeo.

⚠️ **Predicción, antes de medir**: el 2 (cambio de id con los colores bien), el 3 y el 9 (cajas que
se pierden) no son cambios de color. El 8 tiene rachas largas (otro durante ~2 s). **El techo
probable es 6-7 de 10, por debajo del 8.** Si sale así, el criterio no se cumple por construcción:
la histéresis de color no puede arreglar lo que no es color. Y se dice cuáles serían de asociación.

¿Qué podría estar inventando? CLAUDE.md cerró «suavizar el parpadeo» porque taparlo esconde el fallo
de asociación. Esto solo toca el DIBUJO, con el rótulo en el vídeo, y el dato sigue mostrando el
parpadeo para el diagnóstico. Pero quien mire la pizarra dejará de ver cruces que fallan: **es una
decisión de producto, no una mejora del sistema.**

**Intento 2**, solo si el 1 falla por algo de la regla (no por eventos que no son color). Criterio
nuevo, escrito antes.

## Fusión

Solo lo que pase su criterio, con pytest en 0. Lo que no pase se queda en la rama, documentado.

---

# Resultados

## 1. Puerta de calidad de caja: NO CUMPLE, y la premisa no se sostiene. Cerrada en el intento 1

`python scripts/diag28g.py pasadas` y `python scripts/diag28g.py medir` → `outputs/diagnostico_28oct_g/`.

- **Control**: con el flag apagado, el CSV de la parte entera sale **idéntico byte a byte** al de
  `main`. Encendido, cambia (228 filas con otra etiqueta).
- Los 11 errores de partida se reproducen: 9 del GT de 30 s sobre 723 casadas y 2 de la hoja de
  120.

| criterio | resultado | ¿cumple? |
|---|---|---|
| corrige ≥ 6 de los 11 | **0 de 11** | no |
| excluye ≤ 3 % de las observaciones A/B | **3,26 %** | no |
| 0 errores nuevos | 0 | sí |

- **Por qué no corrige nada**: en las ventanas de 1,5 s de los 11 errores **no hay NI UN recorte
  anormal**. Son 0 de 7-15 recortes en cada una. La puerta no podía tocarlos.
  - Ni siquiera el caso del árbitro (18:23,9): su caja se alarga, pero el árbitro ya es alto y la
    caja no llega a 1,4 × el alto esperado.
  - El error de equipo que queda NO vive en cajas de forma rara.
- **Lo que excluye**: el 10,6 % de TODAS las detecciones. Son sobre todo staff (13.763, fuera del
  campo y en el banquillo), porteros de A (1.308, cortados por el borde inferior, como se avisó) y
  detecciones sin identidad. De las A/B, el 3,26 %.
- **Intento 2: no se hace.** Aflojar los umbrales sube el porcentaje excluido, que ya pasa del 3 %,
  y no hay ningún recorte anormal que cazar en los casos de error. Es la lección de «comprobar la
  premisa antes de construir»: bastaba la última tabla.
- Poder estadístico, como se dijo: 11 casos. Aun así, 0 de 11 con 0 recortes anormales en sus
  ventanas no es un problema de muestra, es de mecanismo.
- **El código queda en la rama** (`src/team_classification/calidad_caja.py` y el flag
  `excluir_cajas_anormales`, apagado), sin fusionar.

## 2. Color estable ≥ 1 s en el dibujo: NO CUMPLE (3 de 10)

`python scripts/diag28g.py eventos`. Clip renderizado con la histéresis y el rótulo en pantalla:
`outputs/diagnostico_28oct_g/clip_1_color_estable.mp4`.

| # | evento (clip) | rachas de color < 1 s: crudo → dibujado | ¿deja de verse como parpadeo? |
|---|---|---|---|
| 1 | 0:04 B689 y A683 naranjas | 0 → 0 | no: sin cambio de color en sus etiquetas |
| 2 | 0:15 cambio de id (colores bien) | 0 → 0 | no: no es color |
| 3 | 0:21 el blanco pierde la caja | — (ninguna identidad cambia) | no: es una caja que se pierde |
| 4 | 0:40-0:41 A683 detrás de B708 | 0 → 0 | no |
| 5 | 0:44 la caja se vuelve naranja | 0 → 0 | no |
| 6 | 1:00-1:01 A683 pasa a B683 | 0 → 0 | no (dura ~1 s, no es corta) |
| 7 | 1:06-1:07 A708 y B525 en una caja | **3 → 0** | **sí** |
| 8 | 0:00-0:33 el portero de A | 0 → 0 | no: rachas largas |
| 9 | 1:11 el árbitro desaparece | **2 → 0** | **sí** |
| 10 | 1:30 el árbitro pasa a A | **1 → 0** | **sí** |

- **Criterio: 3 de 10 < 8. No cumple.** La predicción decía 6-7; salió peor.
- **El hallazgo**: en 7 de los 10 eventos, las etiquetas de las identidades implicadas **no tienen
  ningún cambio de color corto**. Por ejemplo, en 0:04 la 689 es A y la 683 es B en las 40
  observaciones de la ventana.
  - Lo que Alex vio cambiar de color no es una identidad que cambia de etiqueta, sino una CAJA que
    pasa a otra identidad (o una caja que se pierde).
  - Eso es ASOCIACIÓN, y una histéresis de color por identidad no lo puede tapar.
- **Intento 2: no se hace.** Falla por lo que no es color, no por la regla.
- **Controles**:
  - la guarda `test_renderizadores_no_colapsan.py` pasa, con un caso nuevo: A 1 s → B se sigue
    viendo con los dos colores, y un parpadeo de 0,3 s desaparece;
  - los CSV no se tocan: la histéresis vive solo en el render. El CSV de la rama sale idéntico al
    de `main` (bloque 1).
- **El código queda en la rama**, sin fusionar:
  - `histeresis_visual` en `replay_tactico.py`, con `--histeresis-visual-s` (1,0 por defecto en
    `generar_replay.py`);
  - `HISTERESIS_VISUAL_S` en `render_clips_26oct.py`, con el rótulo.
  - Si Alex lo quiere igual como decisión de producto (quita 3 de los 10 parpadeos), basta con
    fusionarlo.

## Fusión

Ninguna de las dos mejoras pasa su criterio: a `main` va **solo este informe**. El código está en
la rama `mejoras-28oct-g`.
