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

## Resultado del bloque 2 — selector de balón (flag `prior_campo_activo`): NO CUMPLE

Implementado en `src/balon/tracking_balon.py` (`ParametrosBalon.prior_campo_activo`, **False por
defecto**; `_prior_de_campo`), con 4 tests. Antes de la selección por continuidad, en cada frame quita
los candidatos a > 3 m fuera del campo y los que exigirían > 35 m/s desde el último candidato válido.
Si no queda ninguno, el frame se queda como estaba.

**Flag apagado: el CSV del balón sale IDÉNTICO byte a byte al de `main`** (`cmp` sobre la salida de
`procesar_balon.py` en la parte entera).

**2c, con el flag encendido:**

| | sin flag | con flag | criterio |
|---|---|---|---|
| paneles «campo de al lado» (7, uno repetido) | 7 | **6**: solo cambia f10166 (5:39,2 de archivo, 7:12,2 del reproductor), y se queda SIN balón | ≤ 1 → **NO** |
| paneles «ok» que empeoran | — | 0 (ninguno cambia) | 0 → sí |
| frames del tramo sin balón | 51,6 % | 49,4 % | no suben > 2 puntos → sí |
| frames del partido con el balón > 3 m fuera | 604 | **649** | (lo que inventa) |

- **Control del saque de banda**: de 369 frames con el balón a 0,5-3 m fuera, el flag cambia 12 y deja
  5 sin balón. Lo que debía conservar, lo conserva casi entero.
- **Lo que inventa**: **101 frames NUEVOS con el balón a > 3 m fuera** (100 de ellos no tenían balón
  antes). Al cambiar las listas de candidatos, la selección por continuidad rellena con un balón de
  fuera frames que antes dejaba vacíos. El prior quita fuera en un sitio y lo mete en otro.
- **Por qué no puede funcionar así** (predicho en 2a antes de implementar): en el 89 % de los frames
  con el balón fuera NO hay otro candidato dentro, y la regla «sin candidato válido, conserva lo de
  siempre» se queda con el de fuera.

**¿Qué podría estar inventando?** «Campo de al lado» es mi clase a ojo en 30 paneles: los 6 que siguen
igual tienen el balón activo a 19-38 m fuera, sin ambigüedad. El 2a es de todo el partido; los paneles
son de un minuto.

**Decisión de los datos**: el flag se queda APAGADO. Lo que separaría el balón del campo de al lado no
es elegir entre candidatos (casi nunca hay alternativa), sino **no tener balón** en esos frames. Eso es
el cambio que la regla prohibía, para proteger los saques de banda. Y el control dice que los saques de
banda están a menos de 3 m: un prior que DESCARTE (en vez de buscar alternativa) los candidatos a más
de 3 m no los tocaría. Eso sería otro intento, con su criterio.

## Resultado del bloque 3 — feature de color con máscara por posición (flag `deteccion.mascara_color`): NO CUMPLE

**Implementación (detrás de flag, por defecto `verde` = lo de hoy).** `extraer_color_torso` acepta un
`rango_cesped` opcional. `src/team_classification/mascara_posicion.py` lo calcula POR FRAME: el
rango HSV (p1-p99) del césped en cajas vacías desplazadas a los lados de las detecciones (sin
persona encima, comprobado en metros). En lugar de «todo lo verde es césped», borra «lo que se
parece al césped DE ESTE FRAME». El chaleco (H≈46, S≈175, V≈247) queda fuera de ese rango. En
`processor.py` (modo `full`) se lee `deteccion.mascara_color: verde | posicion`; con `posicion`
y la feature v2 da error. Ningún YAML cambia, y 4 tests en `tests/test_mascara_posicion.py`.

**Coste.** No hay que re-ejecutar el detector: las cajas son las de la caché de producción, y solo
se relee el vídeo para recortar (`scripts/diag22b_feature_v3.py`, CPU, una pasada de 20 min).

**Intento 1 de la caché v3: control FALLIDO.** La v1 recalculada en local tenía que reproducir la
caché de producción. Solo era idéntica en el 0,27 % de las cajas (p99 de distancia 1,08). Ningún
desfase de frame (±3) lo explicaba. **Causa: en macOS, `cv2.VideoCapture` decodifica con
AVFoundation, que da píxeles distintos de los de FFmpeg (Colab)**; `cv2.CAP_FFMPEG` no abre el
vídeo.
**Intento 2: control CORRECTO.** Con el vídeo decodificado por el CLI de `ffmpeg` (tubería
`rawvideo bgr24`), la v1 reproduce la caché de producción en el **100 %** de 209.705 cajas (p99 0,0).
De 11.989 frames, 24 no tienen rango de césped y en ellos se usa la v1.

⚠️ **Lo que ese hallazgo pone en duda (no se re-mide aquí).** Todas las medidas de color en PÍXELES
hechas en local con `cv2.VideoCapture` usaban píxeles de AVFoundation, no los de producción:
- la puerta del chaleco sobre césped;
- `tono_brillo`;
- el «la máscara ve el 7 % del torso del árbitro» del diagnóstico del 22-oct;
- los H/S del chaleco citados en CLAUDE.md.

Las cachés de producción y todo lo medido sobre ellas siguen siendo válidos. La DIRECCIÓN de esas
medidas probablemente aguanta (la máscara borra el chaleco: lo reproducen los tests con píxeles
sintéticos), pero sus NÚMEROS exactos no están comprobados.

**3b** (`scripts/diag22b_bloque3_medir.py`, benjamín, parte entera, producción `desde_cache`
cambiando SOLO la caché de color). El árbitro se fija ANTES: son las 10.414 detecciones (frame,
caja cruda) que marca hoy el proxy de masa. Ese proxy se calcula con la feature v1, así que no
puede juzgar a la v3 con sus propios ojos.

| criterio | hoy (v1) | v3 | ¿cumple? |
|---|---|---|---|
| (i) equipo equivocado, jugadores (GT, 1-a-1, 2 m) | 1,2 % | 1,1 % | **sí** (≤ +0,3) |
| (ii) detecciones del árbitro dentro de un equipo | 39,5 % | **16,2 %** | **sí** (≤ 20 %) |
| (iii) identidades de árbitro (≥ 40 obs, > 50 % árbitro) | 9 | 9 | **NO** (no baja) |
| (iv) Villaviciosa no cambia | — | — | **NO MEDIDO**: no está su vídeo en local, y la v3 necesita píxeles |

**El criterio (iii) no se cumple, y (iv) no se puede medir ⇒ el flag se queda APAGADO.**

**¿Qué podría estar inventando el 16,2 %?** Dos cosas, y las dos están:
1. **El árbitro no sale de los equipos: cambia de equipo.** Sus detecciones etiquetadas B pasan de
   4.075 a 264, y las etiquetadas A de 130 a **1.461**. Una parte del (ii) es el árbitro mudándose
   de B a A, no saliendo.
2. **El cajón `otro` se llena de jugadores** (la segunda medida de todo criterio que mueve filas a
   un cajón).
   - Pasan a `otro` 6.749 filas; **3.889 (58 %) NO son detecciones del árbitro según el proxy**.
   - Podrían ser árbitro que el proxy v1 no ve, pero en el 71 % de sus frames (2.591 de 3.636) ya
     hay ≥ 2 filas `otro`: con un solo árbitro, al menos una es otra persona.
   - Se concentran en los minutos 10-12 y 1, en la mitad del fondo (x p10-p90 34-54 m).
   - Las identidades con mayoría `otro` pasan de 8 a **16**. La pasada v3 avisa de «TERCER GRUPO
     CON 14 IDENTIDADES … el catálogo puede estar robando jugadores». En la de hoy no hay log para
     comparar el aviso.

**Lo que sí mejora, y cómo puede mentir.** El desequilibrio del bloque 1 casi desaparece:
- filas A/B por frame: de 5,83/7,12 a 6,15/6,24;
- frames con B > 7: de 4.747 a 793;
- frames con A > 7: de 501 a 1.761.

3.804 filas no-árbitro pasan de B a A. Contra el GT de 30 s el error no sube (1,2 → 1,1 %), pero esa
ventana es el 2,5 % del partido y no incluye los minutos 10-12, donde se concentra el cambio. Sin GT
allí, **no se sabe si esas 3.804 filas corrigen etiquetas o las rompen**. La v3 cambia el FIT de
color: los prototipos A/B se mueven, no solo el árbitro.

**3c — ¿merecen reabrirse las vías de color cerradas con este sensor? (sin reabrirlas)**
- **Tercer grupo por color** (3 intentos) y **puerta de distancia al prototipo**: se cerraron
  porque «el árbitro no está lejos de los prototipos en un histograma HS». Ese histograma tenía el
  chaleco BORRADO por la máscara, así que la premisa se midió con un sensor ciego a lo que
  buscaba. **Merecen reabrirse**, pero el aviso de los 14 candidatos dice que el riesgo de siempre
  (robar jugadores, 8 por árbitro) sigue: el criterio tendría que llevar la segunda medida desde el
  principio.
- **Umbral de saturación** (S≈248 / S≈72-104 según el minuto): esos S se midieron con píxeles de
  AVFoundation. Antes de reabrirlo hay que re-medir con `ffmpeg`.
- **Árbitro por observación / catálogo**: el sensor nuevo ve el chaleco, pero el resultado de hoy
  (la mitad de lo que entra en `otro` no es el árbitro) repite el patrón que lo cerró. No merece
  reabrirse sin una señal NO de color al lado (las «dos señales débiles»).
- **No reabre** «detección como palanca» ni el reentreno: la v3 no toca el detector.

**Flag apagado = main.**
- Con `verde`, `rango` es `None` y se llama a `extractor(crop)` como antes.
- El control del intento 2 usa esa misma llamada sin rango y reproduce la caché de producción en el
  100 % de las cajas.
- El modo `desde_cache` no pasa por este código, y ningún YAML cambia (`git diff main -- configs`
  vacío).
