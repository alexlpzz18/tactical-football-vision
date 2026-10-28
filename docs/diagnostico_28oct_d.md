# Diagnóstico 28-oct (d): control del balón inventado, oráculo del error de equipo y hoja cercana

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
