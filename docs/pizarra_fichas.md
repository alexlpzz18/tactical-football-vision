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
