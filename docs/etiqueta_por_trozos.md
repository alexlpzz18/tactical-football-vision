# Etiqueta por trozos de identidad cortados donde puede cambiar de persona (29-oct-2026)

Rama `etiqueta-por-trozos`, sale de `main`. Experimento SOLO de etiqueta, CPU sobre cachés, máximo
dos intentos. Sin código de producción: todo en `scripts/`, sobre un CSV aparte. Los CSV de datos no
se tocan (se comprueba el SHA-256). Criterios escritos y commiteados ANTES de medir. A `main` solo va
documentación.

## ¿Ya se probó? No: lo más parecido está cerrado, pero es otra cosa

| lo cerrado | qué hacía | en qué se diferencia |
|---|---|---|
| Suavizar el parpadeo (26-ago, `parpadeo.md`, 3 negativos) | mediana móvil > 1,5 s, histéresis de N frames, **congelar la etiqueta de ANTES del cruce** durante el cruce | no corta la identidad: o alarga una ventana fija o congela lo de antes |
| Tope de cardinalidad por trozos (22-oct e, cerrado) | MILP con «≤ 7 por equipo» sobre trozos FIJOS de 1,5 s | trozos fijos y otro decisor |
| Voto por identidad entera | una etiqueta por identidad | 16,0 % de error: un trozo único que abarca a varias personas |
| Corte en cruces B2 / sin color (22-23 oct) | cortar para RE-UNIR trayectorias | toca la asociación, no la etiqueta |

⚠️ **Lo que avisan esos cierres, antes de medir**: en `parpadeo.md`, alargar el voto más allá de
1,5 s EMPEORA el acierto (2,1 % → 3,0 % a 4 s), porque «es el voto por identidad volviendo». Un trozo
entre dos cruces puede durar decenas de segundos. Si la identidad cambia de persona SIN un cruce
detectado, el trozo vota a dos personas. Y el 28-oct (desglose) midió que los cambios de color que
quedan NO se concentran en los cruces (1,5×). **Predicción: es probable que el error suba.**

## El método (intento 1)

Para cada identidad de `main` (`captura_main.pkl`: sus observaciones, su etiqueta por observación
`final` y la posición del pie SIN suavizar del caché):

- **Solo se tocan las observaciones A/B de identidades A/B.** Igual que `etiquetar_por_observacion`:
  los porteros los decide la posición, y `otro` (catálogo arbitral, pista del árbitro) y `staff` no
  se tocan.
- **Episodio de cruce**: los frames seguidos en que la observación tiene a ≤ 2 m (pie sin suavizar,
  mismo frame) una observación de OTRA identidad con etiqueta del equipo CONTRARIO.
- **Salto imposible** entre dos observaciones seguidas de la identidad: desplazamiento > 12 m/s × Δt
  **y** > 3 × 3,5 px × metros por píxel en ese punto. Es local, porque en el fondo 1 px vale 0,42 m
  (CLAUDE.md).
- **Trozos**: las rachas de observaciones FUERA de los episodios de cruce, cortadas además en cada
  salto imposible. Las observaciones DENTRO de un cruce conservan su etiqueta por observación de hoy:
  ahí no se sabe de quién son.
- **En cada trozo**: UN equipo, la mayoría de sus etiquetas por observación A/B. En empate, cada
  observación conserva la suya.
- **El CSV de prueba**: el de `main` con la etiqueta cambiada en las filas reales que cambian. Una
  fila interpolada (`es_real = 0`) toma la etiqueta nueva de la fila real más cercana en el tiempo de
  su identidad, si tenía la misma que esa fila antes del cambio; si no, conserva la suya.

## Criterios (los de Alex, antes de mirar)

- **Exactitud**:
  - **GT de 30 s**: equipo equivocado con el casado 1-a-1 a 2 m de `comparar_escalas` (hoy 9 de 723);
  - **la hoja de 120 filas, con la caja correcta**: la marca contra la etiqueta del DUEÑO de la caja
    que vio Alex (hoy 2 de 120);
  - criterio: **el error no sube en NINGUNA de las dos** (≤ 9 y ≤ 2).
- **Pizarra**: cambios de color por minuto en el tramo 14:00-15:30 del archivo (15:33-17:03 del
  reproductor), **SIN histéresis** (`--histeresis-visual-s 0` y mediana visual apagada, como la línea
  base):
  - criterio: **bajan ≥ 80 %** respecto a 87,3, es decir, **≤ 17,5 por minuto**;
  - mismo simulador que siempre.
- **Las dos a la vez.**
- **Además se informa** (sin umbral):
  - **duración de los episodios de error**, antes y después: en el GT de 30 s, por persona del GT,
    las rachas de frames seguidos del GT (a 0,5 s) en que su fila casada tiene el equipo equivocado.
    Número, mediana y máximo en segundos;
  - cuántas observaciones cambian, cuántos trozos y cómo de largos.
- **Control**: los CSV de datos (`posiciones_main.csv` y `posiciones_benja_p1.csv`) salen con el mismo
  SHA-256 antes y después.
- **Intento 2**: solo si el 1 falla por un parámetro del corte (radio, umbral de salto), con el
  criterio nuevo escrito antes.
- **Si cumple**: se genera la pizarra del tramo con las etiquetas por trozo.

¿Qué podría estar inventando?
- La pizarra baja el parpadeo casi por construcción: un trozo tiene un solo color. Por eso manda la
  exactitud.
- 9 + 2 errores es poca muestra para «no sube». Una subida de 1-2 casos puede ser ruido, y se dice
  con su número, no solo con el sí o el no.
- Y el GT de 30 s es del minuto 5, con su proporción de cruces.

---

# Resultados (intento 1): NO CUMPLE la pizarra; la exactitud no cambia. Ruta cerrada sin intento 2

`python scripts/etiqueta_por_trozos.py --intento 1` → `outputs/etiqueta_por_trozos_intento1/`.

**Control**: los CSV de datos salen con el mismo SHA-256. Las etiquetas del CSV de `main` coinciden
con las de la captura en 20.000 de 20.000 filas reales muestreadas.

**Los trozos**:
- en los 20 min, 23.637 observaciones A/B caen en un cruce (rival a ≤ 2 m) y hay 4.036 cortes por
  salto imposible;
- quedan 7.641 trozos, con una duración de **mediana 0,1 s** (p90 3,3 s, máximo 67 s): la mayoría
  de los trozos es UNA observación;
- cambian 1.034 observaciones (1.062 filas del CSV), y solo **54 en el tramo de Alex**.

| | `main` | por trozos | criterio |
|---|---|---|---|
| GT de 30 s: equipo equivocado | 9 / 723 | **9 / 723** | no sube → **sí** |
| episodios de error (GT) | 9, todos de 0,5 s (un frame del GT) | 9, todos de 0,5 s | (informativo) |
| hoja de 120 (caja correcta) | 2 / 120 | **2 / 120** (los mismos: 09_1-16.0 y 113_18-23.9) | no sube → **sí** |
| pizarra 14:00-15:30, sin histéresis: cambios/min | 87,3 | **87,3** | ≤ 17,5 → **NO** |
| cambios entre filas reales del tramo (datos) | 74 | 73 | — |

**Por qué no mueve la pizarra, medido en el tramo** (51 cambios A ↔ B entre observaciones seguidas
de identidades A/B):
- **18 tocan una observación EN CRUCE**, que el diseño deja como está a propósito;
- **8 coinciden con un SALTO IMPOSIBLE** del pie sin suavizar, que es un punto de corte: el cambio
  cae justo en la frontera entre dos trozos. Es el 15,7 % de los cambios, frente a un 4,0 % de saltos
  imposibles en cualquier paso: **4× enriquecido**, la firma de una identidad que salta a otra
  persona;
- los 25 restantes caen en trozos tan cortos (mediana 0,1 s) que la mayoría es la propia
  observación.
- ⇒ **Por construcción, al menos 26 de 51 cambios (51 %) no los puede quitar ningún parámetro del
  corte.** El techo queda por debajo del −80 %. Por eso no hay intento 2: la regla era hacerlo solo
  si fallaba un parámetro, y esto es estructural.
- Alargar los trozos (cortar menos) es el voto por identidad volviendo: `parpadeo.md` ya midió que
  pasar de 1,5 s sube el error.

**Lo que deja**:
- la etiqueta por trozo no es la palanca de la pizarra. Una parte de los cambios de color vive en
  los cruces, y otra coincide con saltos imposibles de la identidad, es decir, con que la ficha
  cambia de persona (asociación);
- es coherente con el desglose del 28-oct: 4 de las 5 fichas con más cambios pasan la mitad del tramo
  de cada color;
- **los episodios de error en el GT duran todos un frame del GT (0,5 s)**, antes y después: el error
  de etiqueta que queda es suelto, no en rachas.

**No se genera la pizarra «si cumple»** porque no cumple. La de prueba está en
`outputs/etiqueta_por_trozos_intento1/por_trozos.html`, al lado de `base.html`.

**Código**: `scripts/etiqueta_por_trozos.py` (y la copia del simulador `scripts/fichas_pizarra.py`),
en la rama `etiqueta-por-trozos`, sin fusionar. A `main`, solo este informe.
