# Diagnóstico 22-oct (b): filas de más, selector de balón y feature con máscara por posición

Rama `fix-22oct-b` (sale de `diagnostico-22oct`). Criterios ESCRITOS Y COMMITEADOS ANTES de medir; un
commit por bloque. Producción solo cambia en los bloques 2 y 3, detrás de un flag que por defecto deja
el comportamiento actual, y con el flag apagado la salida tiene que ser IDÉNTICA a `main`.

**Avisos que condicionan lo que se puede saber, dichos antes de medir:**
- El GT de Villaviciosa cubre **60 s** (100 frames), no 30: se usa entero.
- **Bloque 3 en Villaviciosa: NO MEDIBLE en local.** El vídeo de Villaviciosa no está en `data/raw/`
  y la feature nueva hay que calcularla sobre los píxeles. Sus criterios (i) y (iv) quedan «no
  medidos» salvo que el vídeo aparezca.
- **El bloque 3 NO re-ejecuta el detector**: las cajas ya están en la caché. Solo se relee el vídeo del
  benjamín y se recalcula la feature sobre esas cajas, con el mismo recorte que el modo `full`.

## Bloque 1 — filas de más (solo medición)

Salida de producción de hoy (benjamín: `outputs/arbitro_obs/posiciones.csv`; Villaviciosa:
`outputs/diagnostico_22oct/villa/posiciones.csv`).

- **1a.** En los frames del GT, casado 1-a-1 (húngaro) entre TODAS las filas y las personas del GT,
  **umbral 2 m** (el del banco y del desglose). Las filas sin casar se clasifican, en este orden:
  1. **staff/árbitro**: etiqueta `staff` u `otro`; en Villaviciosa, además, la que está a < 2 m del
     árbitro del GT; en el benjamín, la que marca el proxy de píxeles;
  2. **duplicado**: a < 1,5 m de una persona del GT que YA está casada con otra fila;
  3. **fantasma**: a > 5 m de toda persona del GT;
  4. **desplazada**: el resto (1,5-5 m de alguien, sin ser duplicado). La clase no estaba en el
     encargo; se añade para que la clasificación sea exhaustiva.

  Siempre separando filas reales de interpoladas. *Control*: sin filas de más, 0 sin casar.
- **1b.** Por frame (partido entero y ventana del GT): filas A (con portero_A), B (con portero_B) y
  total, contra lo que cabe (7/7/14 en el benjamín, 11/11/22 en Villaviciosa) y, en la ventana del
  GT, contra las personas del GT de cada equipo. Se informa la media de exceso por equipo: **«exceso
  total»** si los dos equipos se pasan; **«desequilibrio»** si uno se pasa y el otro se queda corto.
- **1c.** Pares de identidades simultáneas a < 1,5 m durante ≥ 1 s seguido (filas reales). Cuántos
  pares, y si comparten etiqueta (mismo equipo). *Control*: el mismo recuento entre equipos
  CONTRARIOS, que mide la cercanía normal del juego (marcajes). Los duplicados son el EXCESO de pares
  del mismo equipo sobre ese control, normalizado por el número de pares posibles.
- **1d.** En la caché de detección, tras los filtros de producción y antes del tracker: cajas con
  IoU > 0,5 con otra caja del mismo frame (¿duplicados de teselas de SAHI?). *Control*: con un
  postproceso perfecto, 0.

## Bloque 2 — selector de balón (flag)

- **2a.** En los frames en que el balón ACTIVO cae a > 3 m fuera del campo: ¿había otro candidato
  dentro del campo? % y confianza relativa (la del de dentro dividida por la del elegido).
- **2b.** Tras un flag en `ParametrosBalon` (apagado por defecto): un **prior de campo** (descartar
  candidatos a > 3 m fuera del campo) **más continuidad** con la posición anterior del balón activo, y
  **velocidad ≤ 35 m/s** desde ella. Si en un frame ningún candidato pasa, se conserva el
  comportamiento actual (para no borrar los saques de banda).
- **Flag apagado**: el CSV del balón idéntico byte a byte al de `main`.
- **2c. Criterio**:
  - en los 30 paneles de `outputs/diagnostico_balon/`, los «campo de al lado» pasan de 7 a ≤ 1;
  - ningún panel «ok» empeora;
  - los frames sin balón del tramo no suben más de 2 puntos.

  *Control*: un tramo en que el balón sale DE VERDAD por la banda (buscado a ojo antes de mirar el
  efecto) tiene que seguir mostrando el balón fuera.

## Bloque 3 — feature de color con máscara por posición (flag)

- **3a.** Una feature «v3»: la misma que usa producción (la v1, histograma HS 16×16 del pecho),
  cambiando SOLO la máscara. En vez de borrar H 35-85, S≥40, V≥40, se borran los píxeles que caen
  dentro del rectángulo (H, S, V) p1-p99 del césped de ESE frame (cajas vacías, como en el diagnóstico
  del 22-oct). Tras un flag, apagado por defecto. Como mucho dos intentos.
  - *Control exacto del montaje*: con la máscara de siempre, el recálculo desde el vídeo tiene que
    reproducir la caché de producción (distancia < 1e-6 en el 99 % de las cajas). Si no, el montaje
    no reproduce el modo `full` y no se lee nada.
- **3b. Criterios** (benjamín; Villaviciosa no medible, ver arriba):
  1. error de equipo contra el GT (jugadores, `comparar_escalas.py`) ≤ el actual + 0,3 puntos;
  2. filas de árbitro dentro de un equipo: del 38,6 % actual a **≤ 20 %**. El árbitro son las
     DETECCIONES (frame, caja) que hoy marca el proxy de píxeles: se fija antes, porque el proxy se
     calcula sobre la feature que se cambia;
  3. nº de identidades de árbitro (≥ 40 obs, > 50 % detecciones de árbitro) baja respecto a hoy;
  4. Villaviciosa no cambia: NO MEDIBLE.
- **3c.** Si las vías de color cerradas merecen reabrirse con este sensor, sin reabrirlas.
- Si hiciera falta el detector sobre más de 2 min de vídeo, se para y se documenta el coste (no hace
  falta: ver arriba).
