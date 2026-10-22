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

---

## Resultado del bloque 1 — filas de más (22-oct-2026)

`scripts/diag22b_filas.py` (un fallo propio corregido: una columna `eq` chocaba con el método
`DataFrame.eq`).

**1a — filas sin casar en los frames del GT (2 m, húngaro)**

| | filas | sin casar | staff/árbitro | **duplicado** | fantasma | desplazada (1,5-5 m) |
|---|---|---|---|---|---|---|
| benjamín (60 frames) | 873 | 140 (16 %) | 58 (todas reales) | **8** (6 reales + 2 interp.) | 14 (13 + 1) | 60 (54 + 6) |
| Villaviciosa (100 frames) | 2.429 | 822 (34 %) | 219 (199 + 20) | **113** (77 + 36) | 46 (11 + 35) | 444 (320 + 124) |

**1b — ¿exceso total o desequilibrio?** **Desequilibrio, en las dos patas.**

| | filas A por frame | filas B | frames A > cabe | frames B > cabe | los dos a la vez | ventana del GT: filas − personas (A, B) |
|---|---|---|---|---|---|---|
| benjamín (cabe 7) | 5,83 | **7,12** | 501 | **4.747** | 136 | −0,17 · **+0,65** |
| Villaviciosa (cabe 11) | **13,86** | 8,19 | **437** | 0 | 0 | **+2,21** · −1,38 |

**1c — pares a < 1,5 m durante ≥ 1 s (filas reales)**

| | pares del mismo equipo | pares de equipos contrarios (control) | tasa por par posible: mismo / contrario |
|---|---|---|---|
| benjamín | 32 | 147 | 0,0018 / **0,0108** |
| Villaviciosa | 2 | 10 | 0,0005 / **0,0097** |

**1d — cajas con IoU > 0,5 en el mismo frame, antes del tracker**: benjamín 940 pares, 1.876 cajas
(**0,9 %** de 206.812); Villaviciosa 46 pares, 92 cajas (0,8 %).

**Lectura**
- **Las filas de más NO son duplicados de identidad.** En el benjamín los duplicados son 8 de 140
  sobrantes. Y el control lo confirma por otro lado: estar pegados ≥ 1 s es **6 veces MENOS frecuente
  entre compañeros que entre rivales**, que es lo que hace el juego (los marcajes). Si hubiera una
  persona en dos identidades, la tasa del mismo equipo superaría la del contrario.
- **El exceso es un DESEQUILIBRIO de etiqueta**:
  - en el benjamín, el B se pasa y el A se queda corto (frente al GT: +0,65 / −0,17 por frame); el
    árbitro, que va al B en el 38 % de sus filas, explica una parte;
  - en Villaviciosa es el A, y mucho más (+2,2 / −1,4): es el 23,6 % de equipo equivocado de esa
    pata, no presencia.
- Los sobrantes del benjamín son sobre todo **staff o árbitro (41 %)** y **filas desplazadas 1,5-5 m
  (43 %)**. Esas filas son el DES conocido: caja del detector en proximidad
  (`docs/traza_por_etapas.md`).
- **Las teselas de SAHI no duplican cajas**: el 0,9 % de las cajas tiene IoU > 0,5 con otra.

**¿Qué podría estar inventando?**
- Una «desplazada» puede ser la fila BUENA de una persona cuyo clic del GT está 2-5 m más lejos (el
  sesgo de la caja en proximidad ya medido): no es una fila de más, es localización.
- Un «duplicado» a < 1,5 m de una persona casada puede ser OTRA persona real que el GT no anotó
  (el GT del benjamín no anota al árbitro, y en el benjamín se aparta con el proxy).
- En 1b, «filas por frame» incluye las interpoladas; el desequilibrio se mantiene en la ventana del
  GT, que se compara con personas reales.

## Bloque 2 — 2a medido, y una predicción escrita ANTES de implementar 2b

**2a** (partido entero, balón ACTIVO de `generar_video_detecciones.balon_activo`): de 8.607 frames
con balón activo, **604 (7,0 %) lo tienen a > 3 m fuera del campo**, con la mediana en x ≈ 74 m,
y ≈ 16 m (detrás de la portería del fondo, x > 62). **Solo en 65 de esos 604 (11 %) había otro
candidato dentro del campo**, con una confianza mediana de 0,74 respecto al elegido (p10-p90:
0,57-1,08).

**Predicción, antes de implementar:** el flag pedido descarta los candidatos fuera y, si no queda
ninguno, conserva el comportamiento actual (para no borrar los saques de banda). En el 89 % de los
frames con el balón fuera NO hay alternativa dentro, así que el flag se quedará con el balón de fuera.
**Espero que el criterio 2c («campo de al lado» de 7 a ≤ 1) NO se cumpla.** Se implementa y se mide
igualmente, tal como está escrito.
