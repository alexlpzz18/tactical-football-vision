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
