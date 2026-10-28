# Diagnóstico 28-oct (e): balón en la zona cercana y oráculo de rachas

Rama `medir-28oct-e`, sale de `medir-28oct-d`. **SOLO medir**: no se cambia ningún parámetro.
Criterios escritos y commiteados ANTES de abrir `~/Downloads/respuestas_gt_balon_cerca.csv`. Commit
solo con pytest en 0.

Relojes: archivo; reproductor = archivo + 1:33.

## 1. Balón en el juego cercano (la hoja de 60 frames)

- Se lee con `python scripts/diag28d.py leer ~/Downloads/respuestas_gt_balon_cerca.csv`.
- `no_se` se excluye y se cuenta.
- **Visible** = (acepta + clic) / respondidos.
- **Recall** = acepta / (acepta + clic), la definición de Alex. El `clic` incluye los frames SIN
  candidata, así que este recall cuenta también el fallo de detección, no solo el del selector.
- IC 95 % de Wilson. Se da también el recuento por episodio (20 episodios): 60 frames no son 60 casos
  independientes.
- **Criterio (el de Alex)**:
  - **visible ≥ 50 % y recall < 30 %** → es el **detector**. El siguiente paso son datos de
    entrenamiento de la zona cercana;
  - **visible < 50 %** → es el **encuadre**, y la pizarra debe tratar «balón fuera de plano» como un
    estado normal;
  - **visible ≥ 50 % y recall ≥ 30 %** → no cae en ninguna rama y se dice tal cual, con los dos
    números.
- ¿Qué podría estar inventando? La zona se calcula con los jugadores VISIBLES (28-oct d). Un frame
  con el juego pegado a la cámara y el balón fuera de plano es «no visible» por encuadre, que es
  justo lo que se quiere contar. Y el muestreo quitó los frames cerca de la hoja de 200, que tenía
  balón, así que la visibilidad puede salir algo baja.

## 2. Oráculo de rachas

Mismo GT, métricas e inyección que el 28-oct (d) (60 frames, 814 filas; cruce = alguien del equipo
contrario a ≤ 2 m), con dos cambios.

**(a) Rachas en vez de filas sueltas.**
- **Episodio de cruce** = una racha máxima de frames CONSECUTIVOS del GT (paso de 0,5 s) en que una
  misma persona está en cruce.
- Cada episodio invierte TODAS sus filas con probabilidad **p = 16,7 %**. Así, en esperanza, se
  invierte el 16,7 % de las filas de cruce, sea cual sea la longitud de los episodios.
- Las filas **fuera de cruce** siguen sueltas al 3,3 %: Alex solo pide rachas para los cruces, y se
  dice junto al número.
- Cada persona de un cruce es su propio episodio, independiente (un cambio A ↔ B real suele invertir
  a las dos a la vez: no se modela).
- 200 repeticiones, semillas 0-199. Se informa la fracción REAL de filas de cruce invertidas, como
  control de que da ~16,7 %.

**(b) Promedio en ventanas.**
- La ventana de 30 s se parte en ventanas **sin solape** de **0,5 (el instante), 1, 2, 3, 5, 10, 15 y
  30 s** (1, 2, 4, 6, 10, 20, 30 y 60 frames del GT, que dividen exacto los 60).
- En cada ventana y equipo, el centroide es la media de los centroides por frame y la anchura la
  media de las anchuras por frame, con etiquetas reales y con las invertidas.
- Desviación: la distancia euclídea del centroide y la |diferencia| de la anchura.
- p95 sobre todos los pares (ventana, equipo) de las 200 repeticiones.
- **Se hace con las dos inyecciones**: filas sueltas (la del 28-oct d) y rachas.
- **Respuesta**: la ventana MÁS CORTA en la que el p95 del centroide es ≤ 1 m **y** el de la anchura
  es ≤ 1,5 m, para cada inyección. Si ni 30 s cumple, se dice.

¿Qué podría estar inventando?
- Con ventanas largas hay pocas por repetición (2 de 15 s, 1 de 30 s): el p95 se apoya en la
  variación ENTRE repeticiones, no en el partido.
- Y la ventana es una sola, del minuto 5: el p95 de 30 s dice cómo varía la inyección, no cómo
  varían 30 s distintos del partido.

## 3. CLAUDE.md

En «Rutas cerradas», la línea de Alex sobre la medida del balón inventado por frames muestreados.

## 4. Fusiones

`medir-28oct-c` y `medir-28oct-d` a `main`, con `--no-ff` (d contiene a c). pytest en 0.
