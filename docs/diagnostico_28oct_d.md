# Diagnóstico 28-oct (d): control del balón inventado, oráculo del error de equipo y hoja cercana

> ⚠️ **CORRECCIÓN (28-oct f)**: el oráculo del punto 2 inyecta 16,7 % / 3,3 %, tasas que venían de una hoja mal casada. El error real es ~1,7 % (2 de 120). Con 1,7 % el instante y las ventanas cumplen ya a 3 s (`diagnostico_28oct_f.md`). El oráculo es correcto como «¿qué pasaría si…?», no como descripción del sistema.


Rama `medir-28oct-d`, sale de `medir-28oct-c`. **SOLO medir**: no se cambia ningún parámetro y no se
fusiona nada. Criterios escritos y commiteados ANTES de abrir la mini-hoja de control. Commit solo
con pytest en 0.

Relojes: archivo; reproductor = archivo + 1:33.

## 1. Balón inventado, último intento: el control

- Se lee `~/Downloads/respuestas_gt_balon_control.csv` con
  `python scripts/gt_balon_control_28oct.py leer …` (20 frames, 10 por ventana).
- **La medida es la misma** que en el 28-oct (c), sin tocar nada. Un frame con candidata elegida es
  **inventado** si:
  - el GT dice `rechaza_no_visible` (no hay balón);
  - o el GT dice `clic` y el balón marcado está a más de **2 m** del elegido, con la escala local
    (`escala_px_por_m` en el punto marcado).
- **Control** (fijado ya en el 28-oct c): la medida tiene que marcar **al menos un frame inventado
  en CADA una** de las dos ventanas, 14:46-14:48 y 15:12-15:15 del archivo.
  - **Si no marca alguna, la medida no vale y se para**: no se da ninguna cifra.
  - Se informa además cuántos de los 10 frames de cada ventana marca, para que se vea si lo que
    marca es lo que vio Alex (la mano de B711 en la primera; balones por todo el campo en la
    segunda).
- **Si pasa, la cifra final** es la de la hoja de 200: inventados / frames con candidata elegida,
  con IC 95 % de Wilson, y por zona. Los 20 frames del control **no entran en la cifra**: se
  eligieron en dos ventanas malas a propósito.

¿Qué podría estar inventando? La medida sale de las marcas de Alex, así que el control no comprueba
un proxy contra el GT: comprueba que la DEFINICIÓN (rechaza, o clic a > 2 m) recoge lo que él vio.
Un balón inventado a menos de 2 m del real (la mano del jugador que lo lleva) no cuenta.

## 2. Oráculo con error de equipo inyectado (la ventana de 30 s del GT)

- **GT**: `data/annotations/gt_benja/annotations.xml` (offset 9750, paso 15) con `gt_a_por_frame`
  y la homografía del benjamín. Posiciones = el pie proyectado; equipo = el atributo `team`, con los
  porteros en su equipo (`portero_A` → A), igual que `banco_producto.py`. El GT no anota al
  árbitro, así que no entra.
- **Cruce**, la misma definición del 26-oct (b): la fila tiene a **≤ 2 m** a otra persona del
  equipo CONTRARIO en el mismo frame. Aquí, con los equipos reales del GT.
- **Inyección**: en cada repetición, cada fila invierte su equipo (A ↔ B) con probabilidad
  **16,7 %** si es de cruce y **3,3 %** si no, de forma independiente. **200 repeticiones**, semillas
  0-199.
- **Métricas**, las de `banco_producto.py` y `desglose_error.metricas_de_puntos`:
  - **centroide** de cada equipo y frame (media de x, y). Desviación = distancia euclídea al de las
    etiquetas reales;
  - **anchura del bloque** de cada equipo y frame (extensión en y). Desviación = |diferencia|;
  - **ocupación de zonas 3 × 3** por equipo sobre la ventana entera (campo de 62 × 40 m).
    Desviación = la mitad de la suma de |diferencias| (la fracción de masa mal repartida), en %.
- **Cómo se resume**:
  - centroide y anchura: la **media** y el **percentil 95** de la desviación sobre TODOS los pares
    (frame, equipo) de las 200 repeticiones juntas. Es el error del instante, el que se ve en la
    pizarra. Se da además el p95 de la media por repetición, el error del informe agregado;
  - ocupación: un valor por repetición; media y p95 sobre las 200;
  - un equipo que se queda con menos de 2 jugadores en un frame no da anchura: se cuenta aparte.
- **Criterio (el de Alex)**: el error de equipo **no importa al informe** si el **p95 del centroide
  ≤ 1 m** y el **p95 de la anchura ≤ 1,5 m**, sobre el error del instante. Si no, se dice cuál lo
  rompe.
  - La ocupación no tiene umbral fijado: se informa.

¿Qué podría estar inventando?
- La inversión es **independiente por fila**. En el sistema el error va en RACHAS: una identidad
  mezclada se equivoca varios frames seguidos. Para el error del instante da igual, porque la
  distribución por frame es la misma. Para el agregado (la media por repetición y la ocupación),
  la independencia lo **subestima**, porque los errores se cancelan entre frames. Se dice junto al
  número.
- El oráculo solo mide la ETIQUETA. Las posiciones son las del GT, sin filas que falten ni sobren:
  el 6 % del margen de `docs/desglose_del_error.md`, no el resto.
- La ventana es de 30 s y del minuto 5, con su proporción de cruces. Se informa qué fracción de
  filas es de cruce ahí, frente al 16,6 % del partido.

## 3. Hoja nueva de balón: 60 frames de juego en la zona CERCANA

- **Zona cercana del juego**, la misma definición del 14,9 % y del 28-oct (c): la **mediana de x**
  de las filas reales de jugador dentro del campo está a **x < 62/3 m**. Es lo mismo que «la mayoría
  de los jugadores en el tercio cercano».
  - Comprobado antes de muestrear, sin mirar el balón: son 1.219 de 11.989 frames, **122 s del
    partido (10,2 %)** en **15 episodios**.
- **Muestreo sin mirar la candidata**:
  - de los frames de balón (el caché de balón) cuya zona del juego es la cercana;
  - se quitan los de la hoja de 200 y los del control, y los que están a < 1 s de ellos;
  - 60 frames repartidos por igual a lo largo de la lista ordenada en el tiempo (uno cada ~2 s de
    juego cercano).
- **Mecánica**: la misma página de `gt_balon_rapido.py` (A / R / clic / N), con la candidata elegida
  dibujada si la hay. Otra clave del navegador y otro CSV de descarga
  (`respuestas_gt_balon_cerca.csv`), para no mezclar con las otras hojas.
- **Para qué**: separar encuadre de detector en la zona cercana. Hacen falta **≥ 15 frames con balón
  visible**. Si salen menos, la hoja no decide y se dice.

¿Qué podría estar inventando? 60 frames de 15 episodios no son 60 casos independientes. El IC por
frames será optimista, y se dará también el recuento por episodio.

---

# Resultados

## 1. Balón inventado: el CONTROL FALLA. La medida no vale y se para

`python scripts/diag28d.py control` → `outputs/diagnostico_28oct_d/control.json`.

| ventana (archivo / reproductor) | frames | con candidata | respuestas | inventados |
|---|---|---|---|---|
| 14:46-14:48 / 16:19-16:21 | 10 | 6 | 6 acepta · 3 clic · 1 no_se | **0** |
| 15:12-15:15 / 16:45-16:48 | 10 | 3 | 3 acepta · 3 clic · 4 no_se | **0** |

- **Por la regla fijada: no se da ninguna cifra.** Era el último intento de esta medida; queda
  cerrada.
- Por qué falla, sin cambiar la medida:
  - **las 9 candidatas elegidas que salen en el control son el balón REAL**, y Alex las acepta las
    9. Ejemplos: f26586 (14:47,1 / 16:20,1), el balón en el césped; f27356 (15:12,8 / 16:45,8), el
    balón en las manos del portero tras blocar (recortes en `outputs/diagnostico_28oct_d/`);
  - los 6 `clic` son frames **sin candidata**: un balón perdido, no inventado;
  - el balón inventado que Alex vio en el vídeo cae **entre** los frames muestreados (uno cada
    ~0,3 s). En el 28-oct, la alternancia de 15:12-15:15 iba entre (984, 602) px, que según esta hoja
    es el portero con el balón, y (1.003, 691), y esta no sale en ninguno de los 10 frames.
- **Lo que significa**: un balón inventado dura décimas de segundo. Una hoja de frames sueltos
  espaciados no lo ve, ni con el GT. Medirlo pide marcar SEGUIDOS los frames de balón de un tramo
  (todos, uno de cada 2), y eso es un plan nuevo.
- ⚠️ **Corrección al 28-oct**: allí se escribió que la candidata de (751, 662) px en 886,62 s era «la
  mano de B711». En f26586 (887,1 s), la candidata de (756, 646) es el balón en el césped. Aquella
  atribución no estaba comprobada.

## 2. Oráculo con error de equipo inyectado: el error de equipo SÍ importa al instante

`python scripts/diag28d.py oraculo` → `outputs/diagnostico_28oct_d/oraculo.json`.

- GT: 60 frames, **814 filas**, **125 en cruce (15,4 %)**, frente al 16,6 % del partido. La inversión
  media inyectada sale **5,4 % por fila** (0,73 filas por frame), en línea con el 5,5 % reponderado
  del 28-oct (c).

| métrica | media | p50 | **p95** | p99 | % sin cambio |
|---|---|---|---|---|---|
| centroide, instante | 0,92 m | 0,19 m | **3,62 m** | 5,26 m | 49 % |
| anchura, instante | 0,35 m | 0,00 m | **2,58 m** | 5,88 m | 85 % |
| centroide, media por repetición | 0,92 m | 0,92 m | 1,16 m | — | — |
| anchura, media por repetición | 0,35 m | 0,33 m | 0,54 m | — | — |
| ocupación 3 × 3 (por repetición) | 1,55 % | 1,47 % | 2,58 % | 2,95 % | — |

- **Criterio: NO se cumple, y lo rompen LAS DOS métricas**:
  - centroide: p95 3,62 m > 1 m;
  - anchura: p95 2,58 m > 1,5 m.
- La anchura cambia en pocos instantes (85 % sin cambio), pero cuando cambia lo hace mucho: un
  jugador invertido en la banda estira el bloque del otro equipo. Mediana 1,7 m y p95 6,5 m en los
  (frame, equipo) que se mueven.
- El centroide se mueve en la mitad de los instantes. Un jugador mal etiquetado a ~10 m desplaza
  el centroide de un equipo de 7 en ~1,5 m.
- **Lo que aguanta es el agregado**: la ocupación de zonas (1,6 % de la masa mal repartida) y la
  anchura media de la ventana (p95 0,54 m). El centroide medio de la ventana se queda en el límite
  (p95 1,16 m).
- ¿Qué podría estar inventando?
  - La inversión es independiente por fila. Para el agregado eso es **optimista**: en el sistema
    el error va en rachas y no se cancela entre frames.
  - Solo se mide la etiqueta, con las posiciones perfectas. En el sistema este error se SUMA al de
    asociación y presencia.
  - Lectura para el producto: la **pizarra** (un instante) lo nota; un **informe de medias** por
    tramo casi no. Encaja con lo que vio Alex en el vídeo: «en la pizarra se nota muchísimo».

## 3. Hoja de balón del juego cercano: preparada

`python scripts/diag28d.py hoja` → `outputs/gt_balon_cerca/index.html`. Se lee con
`python scripts/diag28d.py leer ~/Downloads/respuestas_gt_balon_cerca.csv`.

- Elegibles: 1.648 frames de balón con juego cercano, a ≥ 1 s de las hojas anteriores. **60
  elegidos**, repartidos en **20 episodios**.
- **Solo 4 de los 60 tienen candidata elegida.** No es mala suerte del muestreo: en todo el partido,
  con juego cercano hay balón elegido en el **12,2 %** de los frames de balón (y alguna detección en
  el 60,6 %), contra el **51,9 %** (83,2 %) del resto.
  - Lo que sí puede pesar: al quitar los frames cerca de la hoja de 200, que se eligió CON
    candidata, se quitan frames con balón.
- Con tan pocas candidatas, la hoja se decidirá casi entera por **visible o no** (clic / R). Eso
  es justo lo que separa encuadre de detector: si el balón se ve y no hay candidata, es del
  detector; si no se ve, del encuadre.
- ⚠️ La zona del juego se calcula con los jugadores VISIBLES. Con el juego pegado a la cámara,
  muchos están fuera del plano (ver `outputs/diagnostico_28oct_d/muestra_hoja_cerca.jpg`), así que
  «la mayoría en la zona cercana» se mide con los que quedan dentro.
