# Staff que entra en el campo: etiqueta por observación DENTRO (30-oct-2026)

Rama `staff-dentro-del-campo`, sale de `main`. Cambio de producción detrás de un flag. Criterios
escritos y commiteados ANTES de medir.

## El caso

En la salida A1 (13:15.7-13:45.7 del archivo, 14:48.7-15:18.7 del reproductor), el lateral derecho
de A no entra en el contorno de su equipo.
- Es la identidad **590**. De 11:41 a ~13:05 del archivo es una persona parada fuera de la banda
  derecha: mediana a −0,7 m de la línea, 0,32 m/s.
- Después salta al lateral y lo sigue hasta 13:28.
- La regla de staff decide **por identidad entera**, y `etiquetar_por_observacion` se salta a las
  identidades de staff («el staff no juega en ninguna»). Así, los ~25 s del lateral salen grises.
- En los 20 min hay 287 filas de staff dentro del campo, a > 2 m de las líneas: el 2 % del staff,
  ~29 s, en 3 identidades (590: 226; 442: 42; 545: 19).
- Alex: **es imprescindible que el lateral salga bien**, aunque pese poco, porque cae en una salida
  de balón.

## La regla (la de Alex, acotada a lo que se puede medir)

- **Fuera del campo, nadie cuenta.** Ya es así en la pizarra y en el informe; no cambia.
- **Dentro del campo, una observación de una identidad de staff se etiqueta como la de un
  jugador**: ventana de color de 1,5 s, catálogo arbitral, y después la pista del árbitro.
  - «Dentro» = el pie a ≥ 1,0 m de las cuatro líneas, para que el temblor de la proyección no meta
    al entrenador de la banda (0,42 m/px en el fondo).
  - La ventana solo promedia observaciones de DENTRO, para que los recortes del entrenador no voten
    por el lateral.
- Flag: `agregacion.por_observacion.staff_dentro_del_campo` (`activo`, `margen_m`) en
  `team_classification_benja.yaml`. Con él apagado, la salida es la de siempre.
- **Lo que NO se hace aquí**: reconocer al entrenador que entra en el campo por su color, aprendiendo
  antes el del árbitro en los primeros minutos.
  - Es el «tercer grupo por color», cerrado tres veces: en un recorte de 15-40 px, el árbitro está
    tan cerca de su prototipo como un jugador (0,884 frente a 0,936) (`docs/arbitro.md`).
  - Un entrenador de otro color tiene el mismo problema: el clasificador es de dos clases y le
    asignará A o B.
  - El criterio 2 dice si en este partido algún miembro del staff entra en el campo. Si nadie
    entra, ese caso no existe aquí.

## Criterios

1. **El lateral**: las filas de la 590 dentro del campo (margen 1 m) en [785, 808,3] s llevan
   etiqueta **A en ≥ 90 %**. Además, Alex lo ve bien en el visor.
2. **¿Qué podría estar inventando?** Una miniatura de cada racha que pasa de staff a A/B en los
   20 min, con la caja de la PROPIA detección de la fila. Ninguna puede ser alguien que no juega
   (entrenador, línier, suplente). Si alguna lo es, se dice, con su número.
3. **No rompe**:
   - GT de 30 s ≤ 9/723 y hoja de 120 ≤ 2/120;
   - solo cambian filas de identidades de staff: todas las demás, idénticas;
   - **Villaviciosa**: CSV idéntico byte a byte (allí `por_observacion` está apagado).
4. Informativo: fichas de A de media en A1, antes y después.

Pasa si se cumplen 1, 2 y 3, con pytest en 0 y un test de comportamiento del flag. No se fusiona a
`main` sin el OK de Alex.

---

# Intento 1: NO CUMPLE el criterio 2 (mete al entrenador)

`python scripts/staff_dentro.py correr` y `… medir` → `outputs/staff_dentro/` (`rachas.html`).

**Controles**:
- con el flag apagado, el CSV es idéntico byte a byte al de `main` (el del arreglo de interpoladas);
- Villaviciosa, idéntico byte a byte.

| criterio | resultado |
|---|---|
| 1. lateral 590: filas dentro en [785, 808,3] s | **233 de 233 en A (100 %)** → sí |
| 3. GT de 30 s / hoja de 120 | 9 → 9 / 2 → 2 → sí |
| 3. solo cambian identidades de staff; resto idéntico | sí (441 filas) |
| **2. ninguna racha es alguien que no juega** | **NO** |

Las miniaturas, con la caja de la propia detección de cada fila:
- **bien, son jugadores**: 590 (el lateral, 233 filas), 93 (un naranja junto a la banda, 31) y
  625 (un blanco en la banda, 3);
- **mal: el entrenador, o staff de oscuro, a 1-2,5 m dentro de la línea**: 323 (22), 353 (1),
  442 (121, en tres rachas) y 545 (30, banda lejana). Unas **174 filas de no-jugadores pasarían a
  A/B**.

El margen de 1 m no los separa: el entrenador pisa dentro (o la proyección lo mete).

# Intento 2 (criterio escrito antes de medirlo)

**La señal ya está medida y adoptada en el proyecto: el STAFF LENTO.**
- Quien está cerca de la línea y se mueve despacio es staff: `vel_max_lento: 2.75` m/s de
  `velocidad_media` (recorrido / tiempo real), con `tolerancia_lento_m: -1.5` (hasta 1,5 m dentro).
- Hoy se aplica a la identidad ENTERA.

**El cambio**:
- las observaciones dentro del campo de una identidad de staff se parten en TROZOS (observaciones
  seguidas dentro, con huecos ≤ 1 s);
- un trozo se etiqueta por observación solo si su `velocidad_media` (la MISMA función,
  `staff.velocidad_media`) es **≥ `vel_max_lento`** (2,75, el valor adoptado, sin retocar).
- Si no, sigue siendo staff: un trozo lento dentro del campo es alguien plantado en la banda, no un
  jugador.

**Criterios**: los mismos 1, 2 y 3 del intento 1. Es el último intento: si no pasa, la ruta se cierra.

¿Qué podría estar inventando?
- Un lateral QUIETO, abierto y esperando el pase, es lento. Si su trozo dentro es corto y está
  parado, seguirá gris. El 590 es un trozo de 23 s corriendo, así que no debería pasarle, pero se
  dirá.
- `velocidad_media` incluye el temblor de la proyección, que infla la velocidad del que está
  quieto. Por eso se usa el umbral ya medido con esa misma función.

## Resultado del intento 2: el lateral, bien; el entrenador junto a la banda, fuera; queda UN caso de 3 s

Las salidas del intento 1 se guardaron en `outputs/staff_dentro/intento1/`.

**Controles**: con el flag apagado, igual byte a byte a `main`; Villaviciosa, idéntico byte a byte.

| criterio | intento 1 | intento 2 |
|---|---|---|
| 1. lateral 590 en A (filas dentro, [785, 808,3] s) | 233/233 | **233/233 (100 %)** → sí |
| 3. GT de 30 s / hoja de 120 | 9 / 2 | **9 / 2** → sí |
| 3. solo cambian filas de staff; resto idéntico | sí (441) | **sí (266)** |
| 2. rachas que pasan a A/B y NO son jugadores | 4 identidades, ~174 filas | **1: la 545, 30 filas (3 s)** → **no** |

- **Se van**: 323, 353 y 442. Eran el entrenador plantado a 1-2,5 m dentro de la banda.
- **Se pierde** la 93, un naranja junto a la banda (31 filas), que vuelve a staff porque su trozo es
  lento. Es dejar de acertar, no inventar.
- **Quedan**: 590 (el lateral, bien), 625 (un blanco pegado a la banda, 3 filas, bien) y **545: un
  adulto con chaqueta oscura que entra en el campo a recoger un balón** en la banda lejana, a las
  10:54.5-10:57.4 del archivo (12:27.5-12:30.4 del reproductor). Camina deprisa, así que pasa el
  filtro, y sale A durante 3 s.
- **Por la letra del criterio 2, el intento 2 NO CUMPLE**, por un caso de 3 s en 20 min.
- **Ese es el caso que Alex describía**: alguien de otro color dentro del campo. Separarlo por color
  es la ruta cerrada del tercer grupo. No se intenta aquí.
- **Regla de dos intentos**: no hay intento 3 sin un plan nuevo. La decisión es de Alex: adoptar
  sabiendo que esos 3 s salen mal, o cerrar.

`tests/test_staff_dentro_del_campo.py`:
- con el flag apagado, el staff no se toca;
- encendido, solo se etiqueta el trozo que corre dentro, y ni el de fuera ni el plantado.

La mutación que ignora el filtro de velocidad hace fallar el test; se comprobó que el fichero había
cambiado y se restauró.

**No se fusiona a `main`**: es producción y no cumple todos los criterios.
