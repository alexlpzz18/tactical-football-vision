# La pizarra: fichas por equipo y persistencia (28-oct-2026)

Rama `pizarra-fichas`, sale de `main`. Solo CPU sobre cachés. Los CSV de DATOS no se tocan. Criterios
escritos y commiteados ANTES de medir. Máximo dos intentos. A `main` solo va documentación.

**La corrección de rumbo (Alex)**: la ruta (a) se descartó mirando solo el error de ETIQUETA (1,7 %).
Para la pizarra el problema es otro:
- la FICHA es la IDENTIDAD, y la identidad cambia de persona en los cruces entre rivales, mientras
  la etiqueta, que es por persona, acierta;
- de ahí las fichas que cambian de color tras ir metros de un color, y las que aparecen y
  desaparecen.

## Cómo se mide «lo que se ve»

No se mide el CSV, sino **lo que dibuja la pizarra**: el JSON `DATOS` que lleva dentro el HTML, con un
simulador en Python de su regla de dibujo (`posicionEn`, en `replay_tactico.py`):
- a tiempo T, una ficha se ve si tiene un fotograma clave ≤ T y el siguiente está a ≤ 3 s
  (`MAX_HUECO`): se interpola. Si es el último, se ve hasta 0,25 s después;
- su color es el de esa muestra (`ets`) o el de la identidad (`et`).
- Se muestrea a **10 Hz**.
- **Equipo** A = {A, portero_A} y B = {B, portero_B}. `otro` y `staff` cuentan como fichas, pero no en
  un equipo. El balón no está en este CSV.

## 1. Línea base en el tramo 14:00-15:30 del archivo (15:33-17:03 del reproductor), 90 s

Sobre la pizarra de `main` sin suavizado visual (`outputs/pizarra_28oct_h/`):
- **cambios de color por ficha**: transiciones de color entre dos muestras visibles seguidas de la
  misma ficha. Por minuto, en total, y su reparto por ficha;
- **fichas distintas por equipo** en el tramo, y **simultáneas por equipo** (p50, p95, máximo y % del
  tiempo con más de 7; en F7 son 7 por equipo CONTANDO al portero);
- **eventos de aparición y desaparición por minuto**: una ficha pasa de verse a no verse, o al revés,
  en un punto dentro del campo (0-62 × 0-40 m) Y dentro de la imagen de la cámara, a ≥ 40 px de los
  bordes (por la homografía inversa). Salir del plano por el borde no cuenta. Se excluyen los bordes
  de la ventana de 90 s;
- **salto de posición en los cambios de color**: la distancia entre la posición antes y después del
  cambio (p50 y p90).

## 2. El plan, solo para la pizarra

**(A) Fichas por equipo.** Una SEGUNDA etapa, solo de dibujo, que sustituye a las identidades:
- **entrada**: cada observación real (una detección asignada por el tracker), con su posición SIN
  suavizar (el pie proyectado, `mx`, `my` del caché) y su etiqueta por observación (la de `main`:
  ventana para A/B, regla de posición para porteros);
- **por grupo** (A, B, portero_A, portero_B) y frame a frame, Hungarian en metros entre las fichas
  vivas del grupo y sus observaciones:
  - la posición se predice a **velocidad constante**;
  - **puerta** = 1,0 m + 7 m/s × (tiempo desde la última observación), con un máximo de 3,0 m;
- **veto duro**: una observación A no puede continuar una ficha B, por construcción. Las fichas
  viven DENTRO de su grupo;
- **duplicados**: dos observaciones del mismo grupo a < 1,0 m en el mismo frame se funden en una;
- las observaciones sin casar abren ficha nueva. Una ficha sin observación durante 1,5 s se cierra;
- la posición dibujada es la media móvil de 5 observaciones (0,5 s) DENTRO de la ficha;
- `otro` y `staff` siguen como hoy (sus identidades, sin tocar).

**(B) Persistencia.**
- La ficha se mantiene hasta **1,5 s** después de su última observación, quieta en su última
  posición y atenuada (la pizarra ya atenúa por antigüedad; aquí con `max_edad_interp_s` = 1,5).
- Se **sombrea la zona del campo que la cámara no ve**: celdas de 0,5 m cuyo centro, proyectado a la
  imagen con la homografía inversa, cae fuera del fotograma.
- Para el sombreado se añade un parámetro opcional `zona_no_visible` a `replay_tactico.generar_replay`
  (apagado si no se pasa). Va solo en la rama.

## Criterios (los de Alex, antes de mirar)

- ⚠️ Los **cambios de color por ficha serán ≈ 0 POR CONSTRUCCIÓN** (una ficha vive en un grupo). Eso
  **NO cuenta como evidencia** y se informa solo para que conste.
- **La evidencia es contra el GT de 30 s** (frames 9750-10635, 60 frames del GT, 5:25-5:55 del
  archivo):
  - **IDF1 dentro del equipo**: en cada frame del GT, las fichas VISIBLES del color del equipo contra
    las personas del GT de ese equipo, casado 1-a-1 a ≤ 2 m. Luego la asignación global óptima
    ficha ↔ persona y IDF1 = 2·IDTP / (detecciones del GT + detecciones de fichas), por equipo;
  - **(A)+(B) cumple** si su IDF1 es **≥ el de la línea base en LOS DOS equipos**.
- **Tope de fichas simultáneas por equipo**, en el tramo y en la ventana del GT:
  - el % del tiempo con más de 7 **no sube** respecto a la línea base;
  - y el p95 es ≤ 7.
- **Eventos de aparición y desaparición por minuto**, en el tramo 14:00-15:30: **bajan ≥ 50 %**
  respecto a la línea base.
- Las tres a la vez. Si falla alguna, se dice cuál.
- **Control**: los CSV de datos (`posiciones_main.csv` y el de la parte entera) salen idénticos byte
  a byte antes y después. Las fichas se escriben en un CSV APARTE, solo para el dibujo.
- **Intento 2**: solo si el 1 falla por algo de los parámetros de la etapa, con el criterio nuevo
  escrito antes.

¿Qué podría estar inventando?
- (A) puede tapar un cambio de persona DENTRO del mismo equipo (dos compañeros que se cruzan), y el
  color no lo delata. Por eso el IDF1 por equipo es la medida, y no el color.
- La persistencia puede SUMAR fichas simultáneas (una que se va y otra que entra en su sitio), y por
  eso el tope está en el criterio.
- La ventana del GT es de 30 s del minuto 5. El tramo de Alex no tiene GT: allí solo hay recuentos.
- Mismo simulador para las dos pizarras: si el simulador se equivoca, se equivoca igual para las dos.
  Se comprueba contra la vista en el navegador.

**La pizarra para Alex**: el mismo tramo 14:00-15:30 con (A)+(B), al lado de la de `main`.

---

## Intento 1: NO CUMPLE nada (resultados abajo). Criterio del intento 2, escrito ANTES de correrlo

**Diagnóstico del intento 1**:
- de 2.465 fichas, el 60 % vive < 2 s;
- **964 (39 %) renacen** donde una ficha del MISMO grupo murió hace < 1,6 s, a una mediana de
  2,0 m;
- solo 307 nacen junto a una ficha del otro equipo (cambio de etiqueta).
- ⇒ No es el veto, es el SEGUIMIENTO dentro del grupo:
  - la velocidad instantánea (diferencia de dos observaciones a 0,1 s, con el temblor del fondo de
    0,42 m/px) es ruido amplificado, y al predecir tras un hueco la ficha deriva hasta 8 m/s × 1 s;
  - la puerta fija en metros no sabe que en el fondo un píxel vale 0,4 m.
- Es la lección «el umbral tiene que ser LOCAL» (CLAUDE.md, suavizado).

**Intento 2, solo tres parámetros (todo lo demás igual)**:
- **velocidad** = el desplazamiento de la ficha en su último ≥ 0,5 s de observaciones; 0 si lleva
  menos de 0,5 s;
- **la extrapolación** se corta a 0,3 s como máximo (después, la ficha se predice quieta);
- **puerta LOCAL**: max(1,0 m, 3 × 3,5 px × metros por píxel en el punto predicho) + 7 m/s × Δt,
  con un máximo de **4,0 m**. 3,5 px es el `jitter_px` medido.

**Mismos criterios** que el intento 1, sin cambiar nada: IDF1 ≥ base en los dos equipos, tope de
simultáneas (no sube el % con más de 7 y el p95 ≤ 7) en las dos ventanas, y eventos −50 % en el
tramo. Es el último intento.

---

# Resultados

`python scripts/fichas_pizarra.py todo --intento 1|2` → `outputs/pizarra_fichas_intento{1,2}/`
(`resultado.json` y las pizarras).

**Controles**:
- los CSV de datos (`posiciones_main.csv` y `posiciones_benja_p1.csv`) salen **idénticos byte a
  byte** antes y después;
- el intento 1 se volvió a correr tras añadir el 2 y se reproduce exacto (2.465 fichas, IDF1
  0,615 / 0,441, 81,3 eventos/min);
- ⚠️ un fallo mío cazado por un número imposible: la primera pasada daba **0,0 eventos/min en las
  dos pizarras**. La coordenada homogénea de esta homografía sale NEGATIVA y mi «está en la cámara»
  exigía que fuera positiva, así que ningún punto estaba en la cámara. Corregido antes de leer nada.

## 1. Línea base (la pizarra de `main`, sin suavizado visual)

| | tramo 14:00-15:30 (90 s) | ventana del GT 5:25-5:55 (30 s) |
|---|---|---|
| fichas dibujadas | 38 | 20 |
| **cambios de color por minuto** | **87,3** | 130,0 |
| cambios por ficha (p50 · p90 · máx.) | 1,5 · 9,3 · 16 | 1 · 9,1 · 12 |
| salto de posición en el cambio de color (p50 · p90) | 0,14 · 0,36 m | 0,14 · 0,38 m |
| fichas distintas A · B | 29 · 30 | 15 · 15 |
| simultáneas A: p50 · p95 · máx. · % > 7 | 6 · 7 · 8 · 4,9 % | 7 · 7 · 9 · 4,1 % |
| simultáneas B: p50 · p95 · máx. · % > 7 | 7 · 8 · 9 · 7,7 % | 7 · 8 · 10 · 29,7 % |
| **apariciones/desapariciones por minuto** (dentro del campo visible) | **27,3** | 22,4 |

- **Lo que vio Alex, en números**:
  - una ficha cambia de color **87 veces por minuto** en el tramo, y en el sitio (el salto mediano
    es de 0,14 m): no es la ficha saltando a otra persona lejos, es el color cambiando sobre la
    misma ficha;
  - **27 apariciones o desapariciones por minuto** dentro de lo que la cámara ve;
  - **29-30 fichas distintas por equipo en 90 s**, para 7 jugadores.

## 2. (A) fichas por equipo + (B) persistencia

| | base | intento 1 | intento 2 |
|---|---|---|---|
| cambios de color/min (≈ 0 por construcción, **no cuenta**) | 87,3 | 0 | 0 |
| **IDF1 A** (GT) | 0,646 | 0,615 | **0,684** |
| **IDF1 B** (GT) | 0,605 | 0,441 | 0,502 |
| % del tiempo con > 7 A · B (tramo) | 4,9 · 7,7 | 25,8 · 37,0 | 20,2 · 37,8 |
| % > 7 A · B (GT) | 4,1 · 29,7 | 30,1 · 49,3 | 32,8 · 69,9 |
| p95 de simultáneas B (GT) | 8 | 11 | 13 |
| **eventos/min (tramo)** | **27,3** | 81,3 | 68,7 |
| fichas dibujadas en el tramo | 38 | 85 | 75 |

- **Criterios, los dos intentos: NO CUMPLEN ninguno.**
  - IDF1: el intento 2 gana en A (+0,038) pero pierde en B (−0,10);
  - el tope de simultáneas empeora mucho;
  - los eventos SUBEN (×2,5-3), no bajan.
- **Por qué** (diagnóstico del intento 1, que el 2 mejora poco):
  - las fichas por equipo FRAGMENTAN: 2.465 fichas en 20 min, el 60 % de menos de 2 s;
  - cada fragmento es una aparición y una desaparición;
  - con la persistencia, cada fragmento muerto se queda 1,5 s quieto mientras su sucesor ya está
    al lado. Eso infla las simultáneas.
  - El tracker en metros sobre el pie SIN suavizar no aguanta lo que aguantan las identidades de
    `main` (ByteTrack en píxeles + cosido): el temblor del pie en el fondo es de metros.
- **No es el veto**: solo 307 de 2.465 fichas nacen junto a una del otro equipo.
- **Lo que sí sale**: la idea de partida es correcta en A, donde el intento 2 sigue a la misma
  persona MEJOR que la identidad (0,684 contra 0,646). En B hay más observaciones sueltas
  (p95 de 13 fichas B simultáneas en la ventana del GT). Hipótesis sin medir: el árbitro etiquetado
  B en observaciones sueltas, más la persistencia.
- **Ruta cerrada a los dos intentos.** Reabrirla pide un plan nuevo. Las dos pistas que deja:
  - separar (A) de (B): medir las fichas sin persistencia;
  - asociar sobre las identidades de `main` partiéndolas solo cuando la etiqueta cambia de forma
    sostenida, en vez de rehacer el seguimiento desde las detecciones.

## Las pizarras para Alex (mismo tramo, 14:00-15:30 / 15:33-17:03)

- `main`: `outputs/pizarra_fichas_intento2/base_tramo_14_00_15_30.html`
- intento 1: `outputs/pizarra_fichas_intento1/fichas_tramo_14_00_15_30.html`
- intento 2: `outputs/pizarra_fichas_intento2/fichas_tramo_14_00_15_30.html`
- En las de fichas, la zona sombreada es la que la cámara no ve (la franja cercana a la cámara).

## Código

En la rama `pizarra-fichas`, sin fusionar:
- `scripts/fichas_pizarra.py`;
- el parámetro opcional `zona_no_visible` de `replay_tactico.generar_replay` (no cambia nada si no
  se pasa);
- el flag `--zona-no-visible` de `generar_replay.py`.

A `main` va solo este informe.
