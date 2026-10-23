# Diagnóstico 23-oct (b): qué cortes sirven, corte en cruces SIN color, auditoría visual

Rama `fix-23oct-b`, sale de `fix-23oct-a`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque, solo con pytest en código 0. Producción solo cambia tras flag (apagado = idéntico a
`main`).

---

## Bloque 0 — completar el informe de ayer

- otro ≥ 2 en el partido entero, hoy y con B2, en las dos patas (de los CSV del 23-oct a).
- Huecos > 2,5 s sin posición como **% del tiempo-jugador**:
  - tiempo-jugador = Σ por identidad (último instante − primero), sobre todas las filas;
  - huecos = Σ de los intervalos > 2,5 s entre filas consecutivas de la misma identidad.

## Bloque 1 — ¿qué cortes sirven? (medición)

- **Dónde se mide**: la salida de ByteTrack de hoy (donde actuaría el corte), en las ventanas del
  GT de las dos patas.
- **Cambio verdadero**: dos observaciones casadas consecutivas de la misma identidad (frames del
  GT f y g) con personas distintas; su intervalo es [t_f, t_g].
- **Un corte** es la entrada en una racha «en cruce» de la identidad (paso de limpia a cruce),
  evaluada en TODOS los frames del caché dentro de la ventana.
- Un cambio queda **cubierto** si su identidad tiene un corte en [t_f − 0,5 s, t_g + 0,5 s].

Tres definiciones de «en cruce» para una detección:
- **(a)** otra detección a < 2 m en METROS (la del 22-oct f);
- **(b)** IoU en píxeles con otra caja > 0,1 (la de B2);
- **(c)** IoU > t, con t fijado midiendo: se barre t ∈ {0, 0,05, 0,1, 0,2, 0,3, 0,4, 0,5} y se queda
  el MAYOR t (menos cortes) con recall ≥ 80 % en las dos patas.

Por definición y pata:
- **recall** = cambios verdaderos cubiertos;
- **precisión** = cortes que caen a ±0,5 s de un cambio verdadero de su identidad;
- **cortes por persona-minuto** = cortes / (Σ personas del GT por frame × paso del GT, en minutos).

**Criterio de elección**: la definición con **recall ≥ 80 % en las dos patas** y menos cortes por
persona-minuto. Si ninguna, se dice.

**Hipótesis a contrastar** (no medida aún): en Villaviciosa 2 m son 4-5 px y por eso (a) corta de
más. Se mide cuántos píxeles son 2 m en las detecciones de cada pata (homografía inversa).

## Bloque 2 — corte en cruces SIN color (ruta nueva; flag `tracking.corte_cruces_sin_color`)

- Corta con la definición ganadora del bloque 1 y reenlaza por continuidad de movimiento en
  metros, sin color.
- **Puerta que crece con el hueco**: dist_max = **1,5 m + 3,0 m/s × hueco**, con hueco ≤ **2,5 s**.
  A 2,5 s son 9 m. 3 m/s es la mitad de un sprint de niño de 8-9 años: la incertidumbre de
  dónde reaparece.
- Coste del reenlace: distancia / dist_max. El resto del pipeline, igual.
- Es el mismo módulo `corte_en_cruces.py`, con color desactivado, la definición de cruce elegida y
  la puerta creciente. Flag en los YAML de tracking, apagado.

**Criterios** (antes de medir, todo relativo a hoy):

| pata | métrica | criterio |
|---|---|---|
| benjamín | árbitro dentro de un equipo (ventana GT; el GT no lo anota: el proxy fijado del 22-oct e) | 53,5 % → **≤ 10 %** |
| benjamín | equipo equivocado con voto | ≤ 1,2 + 0,3 |
| benjamín | centroide | ≤ hoy |
| benjamín | B > 7 (partido) | ≤ 20 % |
| benjamín | huecos > 2,5 s | ≤ hoy + 0,5 puntos de tiempo-jugador |
| benjamín | IDF1 | ≥ hoy − 0,02 |
| Villaviciosa | A > 11 | ≤ 54,6 + 2 |
| Villaviciosa | centroide | ≤ 4,37 + 0,10 |
| Villaviciosa | IDF1 | ≥ 0,442 − 0,02 |
| Villaviciosa | equipo equivocado | ≤ 23,6 + 0,5 |

**Controles:**
- **(i) Cortes en tiempos ALEATORIOS**: el mismo número de cortes por identidad, en instantes al
  azar (semilla 0), con el mismo reenlace. Si el árbitro dentro de un equipo también baja (a
  menos de 15 puntos del de los cortes reales), el efecto es «partir» y no «partir en el cruce».
- **(ii)** La misma ejecución en las dos cachés de 60 s del benjamín (v3 y v4):
  - árbitro dentro de un equipo, con el proxy disponible en esas cachés: % de frames de la ventana
    del GT sin ningún `otro` en el campo;
  - equipo equivocado.

  La mejora tiene que tener el mismo signo en las dos.

## Bloque 3 — auditoría visual

- **Variante**: la mejor de B2 (23-oct a) y la del bloque 2. Es la que cumpla más criterios del
  benjamín del bloque 2; con empate, la del bloque 2.
- **20 frames con B > 7** de esa variante (semilla 0, partido entero). Panel con todas las cajas y
  su etiqueta; se describe qué es la fila de más: árbitro / staff / jugador duplicado / caja
  fantasma / otro.
- **Vídeo + pizarra** del tramo 10:00-10:45 del archivo (11:33-12:18 del reproductor), con hoy y
  con la variante, para Alex: `generar_video_detecciones.py` con el CSV de cada uno y la pizarra
  (`generar_replay.py`) del mismo tramo.

---

## Resultado del bloque 0

`scripts/diag23b_bloque0.py`, sobre los CSV del 23-oct (a).

| | otro ≥ 2 (partido / tramo) | tiempo-jugador | huecos > 2,5 s | **huecos en % del tiempo-jugador** |
|---|---|---|---|---|
| benjamín hoy | 12,19 % | 18.446 s | 94 s | **0,51 %** |
| benjamín B2 | 7,19 % | 18.651 s | 219 s | **1,17 %** |
| Villaviciosa hoy | 4,2 % | 1.446 s | 0 | 0 % |
| Villaviciosa B2 | 20,4 % | 1.485 s | 0 | 0 % |

- En % del tiempo-jugador, los huecos de B2 son 1,2 %: se duplican, pero son una fracción pequeña.
- El tiempo-jugador de B2 es algo MAYOR: más identidades cortas que suman vida.
- En Villaviciosa (60 s) no hay huecos > 2,5 s ni hoy ni con B2; lo que B2 empeora allí es el
  recuento (otro ≥ 2 del 4 al 20 %).

**¿Qué podría estar inventando?** El tiempo-jugador suma la vida de cada identidad, también la de
las quimeras y los fragmentos. No es el tiempo de las personas reales: es el de las fichas.

---

## Resultado del bloque 1 — gana el IoU > 0,1 (por poco); la hipótesis de Villaviciosa no se sostiene

`scripts/diag23b_cortes.py`, salida de ByteTrack de hoy, ventanas del GT. Cambios verdaderos:
benjamín 41, Villaviciosa 116.

| definición | benjamín: recall · precisión · cortes/persona-min | Villaviciosa: recall · precisión · cortes/persona-min |
|---|---|---|
| (a) otra detección a < 2 m | **0,659** · 0,245 · 28,3 | 0,819 · 0,252 · 28,2 |
| IoU > 0 | 0,805 · 0,178 · 34,8 | 0,784 · 0,207 · 29,7 |
| IoU > 0,05 | 0,732 · 0,190 · 34,9 | 0,793 · 0,208 · 29,3 |
| **(b) IoU > 0,1** | **0,805** · 0,228 · 34,9 | **0,802** · 0,225 · 26,1 |
| IoU > 0,2 | 0,659 · 0,192 · 24,6 | 0,690 · 0,246 · 20,2 |
| IoU > 0,3 | 0,415 · 0,190 · 14,7 | 0,448 · 0,226 · 13,2 |
| IoU > 0,4 | 0,293 · 0,356 · 6,6 | 0,284 · 0,241 · 7,1 |
| IoU > 0,5 | 0,146 · 0,438 · 2,4 | 0,069 · 0,132 · 2,4 |

- **(c)**: el mayor t con recall ≥ 80 % en las dos patas es **t = 0,1**, el mismo valor que (b).
- **Elección: IoU > 0,1**, la única definición con recall ≥ 80 % en las dos patas. Llega justa:
  33 de 41 y 93 de 116.
- (a) se queda en 66 % en el benjamín.
- **La hipótesis «en Villaviciosa 2 m son 4-5 px y por eso (a) corta de más» NO se sostiene.**
  Medido con la homografía inversa sobre las detecciones, 2 m son **~20 px** en Villaviciosa (45 en
  el benjamín). Y (a) no corta más allí que en el benjamín (28 por persona-minuto en las dos).

**¿Qué podría estar inventando?**
- **La precisión es baja en todas**: solo ~1 de cada 4 cortes cae en un cambio real. Un cruce casi
  nunca intercambia a las personas: la mayoría de los cortes serán reenlaces correctos que, si
  fallan, ROMPEN una identidad buena. Es el precio que se vio en B2.
- **Los recalls salen de 41 y 116 cambios**: IC 95 % de ±12 y ±7 puntos. El 80 % es una línea fina.
- La curva no es monótona (IoU > 0 cubre más que > 0,05): con umbrales bajos las rachas de cruce se
  alargan y el corte, que es la ENTRADA en la racha, se adelanta fuera del margen de ±0,5 s.
