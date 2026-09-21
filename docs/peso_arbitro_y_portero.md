# Cuánto pesan el portero de A (contado como árbitro) y el árbitro (contado como jugador)

21-sep-2026. Encargo de Alex: *"esto es más urgente que el catálogo. Antes de
tocar el umbral de saturación, mide cuánto pesa el portero de A mal contado
como árbitro en el CENTROIDE y el RECUENTO — puede que parte del ruido que
llevamos semanas persiguiendo sea esto y no el árbitro en absoluto. Con eso
decido si vale la pena arreglar el catálogo (BACKLOG 26)."*

Reproducir: `python scripts/peso_arbitro_y_portero.py`.

## Método

Dos contrafactuales sobre `posiciones_benja_p1_v2.csv` (producción), con las
definiciones de `scripts/oraculos.py`: centroide = media de x e y; anchura =
extensión en y; profundidad = extensión en x; por equipo y frame, con el
portero en su equipo.

1. **Portero de A → A.** Se DEVUELVEN a A / `portero_A` las filas que v2
   movió a `otro`, que no parecen árbitro y están en su área (497 filas, 13
   identidades, 496 frames). Comprobado a ojo en 8 recortes: todos son el
   portero de A (`outputs/portero_a_como_arbitro.png`).
2. **Árbitro → fuera.** Se SACAN de A/B las filas del árbitro (el proxy de
   `docs/arbitro_y_baile_de_colores.md`): 4.035 filas, 3.994 frames.

⚠️ No mide error contra la verdad (el GT no anota al árbitro ni cubre los
instantes del portero): mide cuánto SE MUEVE cada métrica.

## Resultado

| | **portero de A como árbitro** | **árbitro como jugador** |
|---|---|---|
| filas · frames afectados | 497 · 496 (**4,1 %**) | 4.035 · 3.994 (**33,3 %**) |
| equipo afectado | A | **B** (A: 80 filas, irrelevante) |
| **centroide x, en los frames afectados** | **−3,86 m** (p90 5,4) | +0,61 m (p90 1,2) |
| **profundidad del bloque, afectados** | **+15,05 m** (p90 19,2) | 0 |
| anchura, afectados | 0 | 0 |
| recuento = 7, en los afectados | 5 % → 39 % | 29 % → 56 % |
| **centroide, partido entero** | 0,159 m | **0,227 m** |
| profundidad, partido entero | 0,541 m | 0,052 m |
| **recuento = 7, partido entero** | 31,5 % → 32,9 % (+1,4) | 38,7 % → 47,6 % (**+8,9**) |

## Lo que dicen los números

- **Ninguno de los dos explica el ruido de semanas.** El error de centroide
  contra el GT es de ~1,0-1,5 m; el peso medio de cada uno sobre el partido
  entero es de 0,16 y 0,23 m: entre el 10 y el 15 %.
- **El portero de A es mucho más grave POR FRAME** (3,9 m frente a 0,6 m de
  centroide, y 15 m de profundidad) **pero ocurre en el 4 % de los frames**,
  y son dos tramos de unos 23 s (08:15-08:38 y 11:06-11:29) más restos. Justo
  en esos frames el bloque de A pierde a su último hombre: es el fallo que
  contamina la línea defensiva.
- **El árbitro pesa más EN CONJUNTO** (0,23 m; +8,9 puntos de recuento) porque
  ocurre en un tercio del partido, con un efecto pequeño en cada frame.
- **El recuento exacto** de B sube 8,9 puntos sacando al árbitro. Pero ese es
  justo el número que BACKLOG 24 propone retirar del informe.

⚠️ **El 1,2 % / el centroide del banco YA incluyen al árbitro contado en B**:
el «SISTEMA» de `oraculos.py` construye cada equipo con todas las filas
etiquetadas A o B. Lo que el banco NO contiene es el caso del portero: sus
instantes están fuera de la ventana del GT (325-355 s).

## Por qué el catálogo se lleva al portero: el arquetipo AZUL

El catálogo de `arbitro.py` tiene cinco arquetipos y **con la feature v1
(sin brillo) el `negro` no está activo**. El que dispara es
**`azul_electrico` (H 100-128, S ≥ 180)**:

- El portero de A viste **negro**, y en el histograma HS lee como
  **H=118, S=248**: cae dentro del azul eléctrico.
- De las filas movidas a `otro` cuyo tono cae en ese arquetipo: **592, el 68 %
  en el área del portero de A**, de 20 identidades.
- **El 67 % de las filas etiquetadas `portero_A` también cae en él**, y solo
  las salva que su identidad ya está etiquetada portero (el catálogo por
  observación solo mira identidades A/B). Las que la regla del portero NO
  etiquetó, se van a `otro`.
- Ninguna fila etiquetada A o B cae ahí en condiciones normales. De las 592, **404
  son el portero de A y 188 son gente de la banda** (x≈32, y≈−1: el entrenador
  de chaqueta oscura, que debería ir a `staff` de todos modos). **Ninguna
  parece árbitro** (masa flúor 0): en este partido el árbitro viste verde y el
  arquetipo azul no ha cazado ninguno.

Es la misma familia que `arbitro.py` ya documenta con el naranja de B (*«la
REGLA DE CONFLICTO no es un adorno»*): un arquetipo que choca con una
equipación del partido se desactiva. **El portero es una equipación del partido
y la regla de conflicto no lo mira** (solo mira los prototipos A y B).

## ¿Vale la pena arreglar el catálogo?

Mi lectura, para que decidas tú:

1. **El fallo del portero es barato y sin riesgo de inventar**: extender la
   regla de conflicto a la equipación de los porteros ya identificados, o
   desactivar `azul_electrico` cuando el portero cae en él. Quita 592 falsas
   capturas y no pierde ningún árbitro en este partido. Es lo más
   defendible.
2. **El umbral de saturación (BACKLOG 26) vale mucho menos**: mueve el
   centroide de B 0,23 m de media y el recuento exacto, que iba a retirarse.
   Y tiene el coste conocido (bajar S con la regla actual captura el 6,4 % de
   las ventanas A/B).
3. **El problema real de centroide está en otro sitio**: el árbitro y el
   portero juntos suman ~0,3 m de un error de ~1-1,5 m.

## La segunda fila verde (417 frames): NO es el mismo patrón

| quién | filas | qué es |
|---|---|---|
| **conos de la banda** (ids 106, 262, 369, 144: x≈35, y≈−2,4) | 219 | un cono naranja detectado como persona, etiquetado `staff` (fuera del campo). Inofensivo para los equipos |
| portero de A (id 162) | 28 | las botas y los guantes lima disparan el proxy; está bien etiquetado `portero_A` |
| **portero de B** (ids 62, 504: x≈64, tras la línea de fondo) | 77 | camiseta lima; etiquetado `B` en vez de `portero_B`. El equipo es el correcto |
| resto | ~93 | sin mirar |

Efecto sobre `docs/arbitro_y_baile_de_colores.md`: el proxy cuenta ~417 filas
que no son el árbitro (4 %), así que la cifra de árbitro en B (37,8 %) está
inflada como mucho en ~0,7 puntos.

## La discrepancia 1,2 % contra 1,7 %: resuelta, con TU protocolo

`scripts/comparar_escalas.py` (el del banco, casado 1-a-1 a ≤ 2 m):

| CSV | personas del GT | casadas | a staff/otro | **equipo equivocado** |
|---|---|---|---|---|
| `posiciones_benja_p1.csv` | 814 | 723 | 0 | **9 = 1,2 %** |
| `posiciones_benja_p1_v2.csv` | 814 | 723 | 0 | **9 = 1,2 %** |

**Reproduce la cifra documentada.** Mi 1,7 % (12 de 703) salía de un casado
húngaro entre TODAS las filas del frame, incluidas `otro` y `staff`; no lo
uso más. Y este protocolo **sí** cuenta las mandadas a `staff/otro` (0), así
que mi frase «mi métrica no veía lo que se manda al cajón» era cierta de mi
script, no del banco: lo que pasa es que la ventana del GT no incluye ninguno
de los instantes del portero.

## La investigación sobre objetos pequeños y rápidos

Alex indicó que la tengo «en el artifact/documento que generé» y que la pegue
en `docs/investigacion_objetos_pequenos.md`. **No tengo acceso a ese documento**:
no está en el repo ni en esta sesión, ni entre tus 11 artifacts (lo comprobé; el
más reciente es del 14-sep), y no voy a reconstruirlo de memoria (sería
inventar una investigación y citarla como si fuera la suya). Falta que Alex la
pegue. BACKLOG 29 ya la referencia.
