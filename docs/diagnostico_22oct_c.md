# Diagnóstico 22-oct (c): decodificador, corte duro del balón, v3 intento 2, filas desplazadas

Rama `fix-22oct-c`, sale de `fix-22oct-b` (necesita la feature v3 y su flag, que no están en
`main`). Criterios escritos y commiteados ANTES de medir; un commit por bloque. Si algo falla dos
veces, se documenta como «no medido» y se sigue. Producción solo cambia en el bloque 1, tras un flag
apagado por defecto; con el flag apagado la salida tiene que ser idéntica a `main`.

Relojes del vídeo del benjamín: se dan los dos, el del ARCHIVO y el del reproductor de Alex
(+1:33).

---

## Bloque 0 — decodificador (prerrequisito)

- **0a.** Con qué decodificador se calculó cada columna de la tabla del bloque 3 de
  `diagnostico_22oct_b.md`. Si v3 hubiera salido de cv2/AVFoundation y «hoy» de la caché de
  producción (FFmpeg en Colab), la comparación estaría confundida y habría que rehacer v3 con el
  ffmpeg de línea de comandos y repetir (i)-(iv). Se comprueba por las MARCAS DE TIEMPO de los
  ficheros, no de memoria: la caché v3 tiene que ser la del intento 2 (control 100 %) y el CSV v3
  posterior a ella.
- **0b.** Test de regresión: con el ffmpeg de línea de comandos, reproducir ≥ 99 % de las features
  de la caché de producción (distancia < 1e-6) en 50 frames FIJOS; el test falla si no. Se salta si
  no están el vídeo o las cachés (viven en Drive).
- **0c.** Re-medir con ffmpeg, con los MISMOS scripts y criterios (solo cambia el decodificador):
  - `scripts/diag22_mascara_arbitro.py`: fracción del torso del árbitro y del césped que sobrevive
    a la máscara actual y a la de posición (el «7,3 %»);
  - `scripts/puerta_chaleco_cesped.py`: H/S/V del chaleco y del césped por minuto (las cifras de
    CLAUDE.md: chaleco S 171-178, H ≈ 46, V ≈ 247; césped H ≈ 55, V ≈ 113-128).
  Se reportan las viejas (cv2) y las nuevas (ffmpeg) lado a lado.
- **0d.** Antes de lanzar nada que lea > 5 min de vídeo, estimar el coste: velocidad de
  decodificación medida en 30 s × duración leída.
- **0e.** Añadir a CLAUDE.md el aviso del decodificador con la guarda (texto de Alex).

¿Qué podría estar inventando? Un 100 % de coincidencia en 50 frames del principio no garantiza el
partido entero: el control del intento 2 del 22-oct (b) lo comprobó sobre las 209.705 cajas.

## Bloque 1 — balón: corte duro (flag `balon.descartar_fuera_m`)

- **1a.** Tras un flag (`ParametrosBalon.descartar_fuera_m`, `None` = apagado, que es el defecto),
  se descarta el balón ELEGIDO si cae a más de `descartar_fuera_m` fuera del campo. Sin buscar
  alternativa y SIN interpolar a través de los frames descartados: ni recta con futuro, ni mantener
  la posición, en un hueco que contenga un frame descartado. Se lee del bloque `balon:` del config
  de campo (`configs/campo_benja.yaml`), que es el config que comparten el vídeo
  (`generar_video_detecciones.py`) y la pizarra (`procesar_balon.py`), y los dos llaman a la MISMA
  función de corte. *Comprobación*, con el flag encendido: la selección que pinta el vídeo y la
  trayectoria de la que sale la pizarra son el MISMO dict (mismos frames, mismas detecciones), y
  ningún frame descartado aparece en el CSV de la pizarra (ni real ni relleno).
- **1b. Criterio**, con el flag a 3,0 m, sobre la parte entera:
  1. de los 7 paneles «campo de al lado» del 22-oct (6 frames: f9306 ×2, f9360, f9738, f10166,
     f10472, f10474) quedan **≤ 1** con el balón a > 3 m fuera, en el vídeo Y en la pizarra;
  2. **ningún otro panel** de los 28 pierde el balón (más estricto que «ningún ok»: los «ok» del
     22-oct no se guardaron por frame, así que se exige a todos los que no son «campo de al lado»);
  3. los frames con el balón a 0-3 m fuera (saques de banda) son **idénticos a `main` fila a fila**
     (frame, x, y, es_real, etiqueta).
  Se reporta cuántos frames se descartan y cuántos caen entre 3 y 6 m (zona ambigua).
- **Flag apagado**: el CSV del balón idéntico byte a byte a `main`, y el dict del vídeo igual.

¿Qué podría estar inventando? Un hueco nuevo puede arrastrar cambios lejos del corte: las fases
aéreas y la puerta de píxeles miran a los vecinos. Por eso el (3) se mide fila a fila y no por
recuento.

## Bloque 2 — v3, intento 2 (el último de esta ruta)

- **2a. Cobertura** = % de las personas-jugador del GT (por frame, sin árbitro) casadas 1-a-1 a ≤ 2 m
  con una fila A, B, portero_A o portero_B. Se mide para hoy, v3 y v3+devolver. Y el desglose de las
  3.889 filas no-árbitro que v3 manda a `otro`:
  - en la ventana del GT: casadas con un jugador del GT / sin casar;
  - en todo el partido: **staff** (fuera del campo > 2 m) · **árbitro por identidad** (su identidad
    de hoy tiene > 50 % de detecciones del proxy) · **resto** (jugador probable);
  - y por MECANISMO: identidad entera en `otro` (voto de identidad, lo que `devolver` puede tocar)
    contra observaciones sueltas de una identidad A/B (catálogo por observación, que `devolver` no
    toca).
- **2b.** Aclarar la etapa de cada cifra del 22-oct (b): «filas A del árbitro 130 → 1.461» y
  «(ii) 39,5 → 16,2 %».
- **2c.** v3 + `arbitro.uno_solo: true` + `arbitro.devolver_por_color: true` (claves que ya existen;
  se pasan por config en el script, sin tocar producción). **Criterio**, todos a la vez:
  1. cobertura ≥ hoy − 0,5 puntos;
  2. equipo equivocado (jugadores) ≤ hoy + 0,3 puntos;
  3. detecciones de árbitro dentro de un equipo ≤ 20 % (mismo árbitro fijado que en el 22-oct b);
  4. tercer grupo ≤ 3 identidades (el aviso `avisar_tercer_grupo` del log).
  Se reportan los frames con > 7 en B. Villaviciosa: sin vídeo en local, «no medido», y por la regla
  de las dos patas **no se adopta** pase lo que pase.

¿Qué podría estar inventando? La cobertura cuenta una persona como cubierta aunque la fila sea del
equipo contrario; por eso va junto al error de equipo. Y el GT son 30 s de un minuto bueno, que no
contienen los minutos 10-12 donde se concentra el cambio.

## Bloque 3 — filas «desplazadas» (el 43 % de las sin casar del bloque 1)

- **3a. Definición** (la del bloque 1 del 22-oct b, `diag22b_filas.py`): fila de un frame del GT que
  no se casa 1-a-1 a ≤ 2 m, que no es staff/árbitro, que está a ≥ 1,5 m de toda persona casada (no
  es duplicado) y a ≤ 5 m de alguna persona del GT (no es fantasma). Descomposición, en las dos patas:
  - **distancia** a la persona del GT más cercana (1,5-2 · 2-3 · 3-4 · 4-5 m);
  - **zona** por profundidad (x 0-20 · 20-40 · 40-62 m en el benjamín; tercios del largo en
    Villaviciosa);
  - **¿de quién es?**: la persona más cercana está SIN casar (la fila es suya, mal puesta: falta +
    sobra a la vez) o YA casada con otra fila (es una fila de más cerca de alguien);
  - **causa**:
    - *interpolada* (`es_real=0`);
    - *punto del pie*: la detección de la fila (su caja, vía `cajas.pkl`) TAMBIÉN está a > 2 m de
      la persona: el error está en la caja/proyección antes del tracking;
    - *post-proceso*: la detección está a ≤ 2 m pero la fila no (el suavizado la movió);
  - **cambio de identidad**: en el frame del GT anterior y en el siguiente (±15 frames), ¿con quién
    se casa esa misma identidad? Con la misma persona más cercana de ahora (no hay cambio), con OTRA
    persona (la identidad cambia de persona en esta ventana), o con nadie.
  Solo medición: no se cambia nada.

¿Qué podría estar inventando? El GT del benjamín es una plantilla fija de 40×18 px con el «pie» en el
pecho para el portero cercano: una «desplazada» puede ser un clic del GT, no un fallo del sistema. Se
reporta cuántas personas DISTINTAS sostienen cada celda (una persona puede llenar una zona).

---

## Resultado del bloque 0 — decodificador

**0a. La tabla del bloque 3 del 22-oct (b) NO estaba confundida.**
- **«hoy»** sale de la caché de producción, calculada en Colab (FFmpeg).
- **«v3»** sale de `cache_colores_v3.pkl`, calculada con el ffmpeg de línea de comandos (intento 2;
  el intento 1 con cv2/AVFoundation se descartó por su control).
- Comprobado por las marcas de tiempo:
  - la caché v3 y su control (100 % idénticas, p99 0,0) se escribieron a las 10:37:23;
  - el CSV v3 (`posiciones_v3.csv`), a las 10:38:55, después;
  - el script de medida no regenera el CSV si ya existe, así que el CSV no podía venir del intento 1.

No hace falta rehacer v3 ni la tabla (i)-(iv).

**0b. Guarda** en `tests/test_decodificador_produccion.py`, con el lector compartido en
`src/utils/video_ffmpeg.py`:
- toma 50 frames fijos del primer minuto (unas 1.000 cajas) y exige que ≥ 99 % de las features
  coincidan con la caché;
- pasa (14 s);
- **mutación comprobada**: cambiando el lector por `cv2.VideoCapture`, coinciden 1 de 907 y el test
  FALLA, que es lo que tiene que hacer.

**0c. Re-medidas con ffmpeg** (mismos scripts y criterios; solo cambia el decodificador, ahora
`--decodificador`, que por defecto es ffmpeg):

| cifra | cv2 (vieja) | ffmpeg (nueva) |
|---|---|---|
| torso del árbitro que sobrevive a la máscara actual | 7,3 % | **7,7 %** |
| césped que sobrevive a la máscara actual | 4,6 % | 4,8 % |
| torso del árbitro que sobrevive a la máscara por posición | 98,5 % | 98,7 % |
| césped que sobrevive a la máscara por posición | 8,4 % | 8,4 % |
| chaleco: mediana de S por minuto | 162-178 | 163-178 |
| chaleco: mediana de H / V por minuto | 45-46 / 244-250 | 45-46 / 244-249 |
| chaleco, p1-p99 de S (minutos de S alta) | 51-255 | 42-255 |
| césped x 0-20 / 20-40 / 40-62: mediana de H | 55 / 54 / 53 | 55 / 55 / 53 |
| césped x 0-20 / 20-40 / 40-62: mediana de V | 113 / 122 / 128 | 111 / 120 / 126 |
| minutos «S alta» / «mixto» (umbral S ≥ 170) | 17 / 3 | 18 / 2 |

Los mismos píxeles: 60.820 de árbitro y 759.024 de césped, con las mismas cajas.

**Lectura.** Las ESTADÍSTICAS de píxel aguantan como número, no solo como dirección: se mueven ≤ 2
unidades. Lo que no aguanta es la FEATURE exacta: un histograma HS de 256 bins sobre un recorte de
15-40 px cambia de bin con desplazamientos de 1-2 unidades, y por eso el intento 1 de v3 solo
coincidía en el 0,27 %. El único cambio de clase es el minuto 15 (S mediana 168 → 170), que cruza
el umbral de 170 justo en el borde: es un artefacto del umbral, no del decodificador.
`tono_brillo` no se ha re-medido (no lo pedía el bloque).

**¿Qué podría estar inventando?** Que coincidan las medianas no prueba que coincidan las colas: el
p1 de S del chaleco baja de 51 a 42. Ninguna conclusión del 19 ni del 22-oct depende de ese p1.

**0d. Coste estimado ANTES de lanzar.**
- ffmpeg decodifica 30 s de 1080p en 3,4 s (medido), así que leer hasta el minuto 19 cuesta unos
  2,3 min por script; los dos, unos 5-6 min. Se lanzó.
- Nada más del diagnóstico lee > 5 min de vídeo: el bloque 2 usa la caché v3 ya calculada.

**0e.** Añadido a CLAUDE.md (principios, «Sobre el método») el texto pedido, con la guarda y una
línea con el resultado de 0c.

---

## Resultado del bloque 1 — corte duro del balón (flag `balon.descartar_fuera_m`): NO CUMPLE

**Implementación (tras flag; apagado = `null` en `configs/campo_benja.yaml`).**
- `ParametrosBalon.descartar_fuera_m` (por defecto `None`).
- `descartar_balon_fuera()` quita el balón ELEGIDO de los frames en que cae a más de esos metros
  fuera del campo y devuelve esos frames aparte.
- `preparar_balon(..., vetados=...)` no los cruza con nada: ni el suavizado, ni la recta de un
  vuelo, ni el relleno (recta con futuro o mantener). El balón de después abre un tramo nuevo, para
  que el replay no lo una con el de antes.
- Los dos consumidores leen los parámetros de la misma función
  (`src.balon.carga.parametros_balon_de_campo`, bloque `balon:` del config de campo, que da error
  con una clave que no exista) y llaman al mismo corte: el vídeo (`generar_video_detecciones.py`)
  y la pizarra (`procesar_balon.py`).
- 6 tests en `tests/test_corte_duro_balon.py`. Uno es la guarda de comportamiento: encenderlo
  cambia el resultado. Otro comprueba con un control que, sin veto, el suavizado SÍ cruza el
  salto.

**Flag apagado = main**: el CSV del balón (`procesar_balon.py`, parte entera) es idéntico byte a
byte al de `main`. En el vídeo, con `null` el corte devuelve el mismo dict, como comprueba el test.

**Mismo balón en el vídeo y en la pizarra** (flag encendido, `scripts/diag22c_balon.py`):
- la selección del vídeo es la de antes menos los 604 frames, con las mismas detecciones;
- no queda ninguna fila de la pizarra (real ni rellena) en un frame descartado;
- toda fila real de la pizarra está en la selección del vídeo.

**Cuánto se descarta**: **604 frames** de 8.607 con balón (los mismos 604 del 2a del 22-oct b).
De la selección sin corte:

| distancia fuera del campo | frames |
|---|---|
| 0-3 m (saques de banda, no se tocan) | 501 |
| 3-6 m (zona ambigua) | 179 |
| > 6 m | 425 |

**Criterio 1b:**

| | resultado | ¿cumple? |
|---|---|---|
| 1. paneles «campo de al lado» que siguen mal (de 7) | **0** (en los 6 frames el balón desaparece del vídeo y de la pizarra) | sí |
| 2. otros paneles que pierden el balón | **9 de 21** | **NO** |
| 3. filas a 0-3 m fuera idénticas a main fila a fila | **534 de 947** | **NO** |

Los 9 paneles que pierden el balón:

| panel | archivo | reproductor | balón del vídeo, fuera del campo |
|---|---|---|---|
| alto_9896 | 5:30.2 | 7:03.2 | 3,8 m |
| lejos_10514 | 5:50.8 | 7:23.8 | 9 m |
| alto_10516 | 5:50.9 | 7:23.9 | 10 m |
| alto_10518 | 5:51.0 | 7:24.0 | 9 m |
| lejos_10526 | 5:51.2 | 7:24.2 | 1,5 m, pero la pizarra lo pierde: su hueco tenía un veto |
| alto_10550 y lejos_10550 | 5:52.0 | 7:25.0 | 10 m |
| alto_10554 | 5:52.2 | 7:25.2 | 37 m |
| lejos_10624 | 5:54.5 | 7:27.5 | 71 m |

Son, sobre todo, paneles de **balón en el aire**: en el 22-oct, «alto» tenía 2 ok y 4 en el aire,
y aquí pierden el balón 5 «alto», así que al menos un «ok» cae.

**Por qué: el corte no separa el balón del campo de al lado del balón EN EL AIRE.**
- **Los 604 descartados son, todos, frames que el sistema ya marca como aéreos.**
- 432 caen **detrás de la portería del fondo** (x mediana 90 m, y 15 m). Es un balón por el aire
  proyectado con la homografía de SUELO, que lo lanza decenas de metros más allá. En el vídeo esa
  caja ES el balón del partido, y el corte la borra.
- 156 caen por las bandas (y > 43 o y < -3, con x 33-57 m) y 16 detrás de la portería cercana.
- El 22-oct (b) ya daba la mediana de los de fuera en x ≈ 74 m; entonces se leyó como «el campo de
  al lado» y no lo era: el campo de al lado está a un LADO (x 28-31 m, y 41-42 m, 22-oct 1d).

**Las filas de banda que cambian** (413 de 947):
- **403 son filas NO reales** (`es_real=0`: rectas de vuelo y rellenos) en huecos que contenían un
  frame descartado. Desaparecen (356) o se mueven, que es exactamente lo que el flag pide: no
  interpolar a través. El criterio, escrito antes, pedía también que fueran idénticas, y las dos
  cosas no pueden cumplirse a la vez cuando un saque de banda linda con un vuelo descartado.
- **10 son reales**:
  - 7 se mueven 0,15-0,74 m, porque el suavizado ya no cruza el veto;
  - 3 desaparecen: f22134 (12:18.5 de archivo, 13:51.5 del reproductor), f27404 (15:14.4 /
    16:47.4) y f35256 (19:36.4 / 21:09.4). Probablemente pasan a aéreas al recalcular las fases
    con vecinos distintos y caen por el veto; no está verificado.
- Además, 523 de las idénticas solo cambian de id de tramo, que es lo esperado.

**¿Qué podría estar inventando?**
- El «0 de 7» es real, pero lo consigue borrando una CLASE entera (balón aéreo lejos del campo),
  de la que el campo de al lado es una parte pequeña.
- En la pizarra de `main` ninguna fila de balón cae a más de 3 m fuera: el balón malo se pintaba
  como una fila AÉREA interpolada dentro del campo (f9306: 16,8 m, 32,4 m, `es_real=0`). Lo que la
  pizarra pierde con el corte son esas filas inventadas. Lo que pierde el vídeo, en cambio, son
  cajas REALES del balón en el aire.

**Decisión de los datos: el flag se queda APAGADO** (segundo intento de la vía «prior de campo»;
con el del 22-oct b son dos, y la vía se abandona tal como está planteada).

Lo que separaría las dos clases, como dato para un plan futuro y no como tercer intento:
- el **lado** por el que sale: el campo de al lado está detrás de la grada, por la banda de
  y ≈ 41-42 m; el balón aéreo, detrás de la portería del fondo;
- y que el balón aéreo VUELVE al suelo dentro del campo y por continuidad, que es la forma de
  `readmitir_vuelos`.

---

## Resultado del bloque 2 — v3, intento 2 (v3 + un solo árbitro + devolver): NO CUMPLE

`scripts/diag22c_v3.py`: tres pasadas `desde_cache` de la parte entera. Solo cambian la caché de
color y, en la tercera, `arbitro.devolver_por_color: true` (una clave que ya existe, pasada por un
YAML temporal). Producción no se toca.
- *Control*: la pasada «hoy» reproduce byte a byte el CSV con el que se midió el 22-oct (b).
- El árbitro son las mismas 10.414 detecciones fijadas que el 22-oct (b).

| | hoy | v3 | v3 + devolver | criterio (v3 + devolver) |
|---|---|---|---|---|
| **cobertura** (personas-jugador del GT casadas con una fila de equipo) | 90,05 % (733/814) | 90,05 % | 90,05 % | ≥ hoy − 0,5 → **sí** |
| equipo equivocado (jugadores) | 1,2 % | 1,1 % | 1,1 % | ≤ hoy + 0,3 → **sí** |
| detecciones del árbitro dentro de un equipo | 39,5 % | 16,2 % | **36,6 %** | ≤ 20 % → **NO** |
| tercer grupo (aviso del log) | **7** | 14 | 1 | ≤ 3 → sí |
| identidades de árbitro | 9 | 9 | 9 | (informativo) |
| filas A / B por frame | 5,83 / 7,12 | 6,15 / 6,24 | 6,52 / 6,42 | |
| frames con > 7 en A / en B | 501 / 4.747 | 1.761 / 793 | **3.072 / 1.427** | (se reporta) |
| detecciones del árbitro etiquetadas A / B / otro | 130 / 4.075 / 6.118 | 1.461 / 264 / 8.598 | 3.409 / 486 / 6.428 | |

Villaviciosa: **no medido** (no está su vídeo en local). Por la regla de las dos patas, no se
adopta aunque cumpliera.

**Por qué falla `devolver`: el árbitro es N identidades, y la regla supone una.**
- `un_solo_arbitro` corona a UNA identidad y devuelve las demás «a su equipo por color». Pero el
  árbitro está partido en ~9-10 identidades: las no coronadas son sobre todo OTROS TROZOS DEL
  ÁRBITRO.
- Con v3 el color ya ve el chaleco, y lo que se parece a él es el prototipo A: el árbitro va al
  equipo A (3.409 detecciones).
- El tercer grupo baja a 1 justamente porque se vacía de árbitro, no porque se limpie de jugadores.
- Es el principio de CLAUDE.md «UNA PERSONA ES N IDENTIDADES»: la exclusividad que funciona con
  una identidad por persona rompe cuando hay muchas.

**2a — la cobertura no ve nada.** Las tres pasadas dan EXACTAMENTE 733 de 814: la ventana del GT
(30 s del minuto 5) no contiene los instantes que cambian, que se concentran en los minutos 10-12.
⇒ «Cobertura igual» no es «no rompe nada»: aquí es «el GT no llega». Es el aviso de siempre de
que el GT de una ventana no representa el partido.

**2a — desglose de las 3.889 filas no-árbitro que v3 manda a `otro`** (hoy A/B → v3 `otro`;
«no-árbitro» = la detección no es del proxy):

| | filas |
|---|---|
| de una identidad que HOY es árbitro en > 50 % (árbitro por identidad) | **2.917 (75 %)** |
| resto (jugador probable) | 969 (25 %) |
| staff (> 2 m fuera del campo) | 3 |
| *por mecanismo*: la identidad entera va a `otro` (voto de identidad) | 3.592 |
| *por mecanismo*: observación suelta de una identidad A/B (catálogo por observación) | 297 (todas en «resto») |
| en la ventana del GT | 4, y ninguna casada con un jugador del GT |

Salen de 21 identidades de hoy distintas.

⚠️ **Esto corrige la lectura del 22-oct (b).** Allí se dijo que el 58 % de lo que entra en `otro`
«no es el árbitro», con el proxy POR DETECCIÓN. Por IDENTIDAD, el 75 % es de identidades que hoy ya
son mayoritariamente árbitro: son detecciones del árbitro que el proxy (calculado con la feature
v1, ciega al chaleco) no marca. Los jugadores probables son como mucho 969 filas, y de ellas 297
las mueve el catálogo por observación. El argumento de los «≥ 2 `otro` en el mismo frame» del
22-oct (b) era débil por la misma razón: dos trozos del árbitro a la vez son un duplicado, no dos
personas.

**¿Qué podría estar inventando el 75 %?** Que una identidad sea «árbitro en > 50 %» no hace árbitro
a cada fila suya: una identidad mezclada (CLAUDE.md: el id 292 mezcla árbitro y jugadores) aporta
filas de jugador a este grupo. El 75 % es una cota SUPERIOR de lo que es árbitro, y el 25 % una cota
INFERIOR de lo que son jugadores.

**2b — en qué etapa está cada cifra del 22-oct (b).** Las dos salen de la MISMA etapa y la MISMA
población: la etiqueta FINAL del CSV, después de todas las reglas (incluido el voto por
observación), sobre las 10.646 filas reales que caen en una detección del árbitro fijada.
- (ii) = (A + B) / 10.646: hoy (130 + 4.075) = 39,5 %; v3 (1.461 + 264) = 16,2 %.
- «A pasa de 130 a 1.461» es un SUMANDO de ese mismo numerador. A sube 1.331, pero B baja 3.811, y
  el neto es la caída de (ii).
- No se contradicen: el árbitro sale de B en bloque y una parte cae en A.

**Decisión: la ruta v3 se cierra** (segundo y último intento).
- v3 sola: cumple (i) y (ii), pero no (iii); sin Villaviciosa.
- v3 + devolver: no cumple el árbitro (36,6 %).
- El flag `deteccion.mascara_color` se queda en `verde`.

Lo que deja como dato: el sensor v3 SÍ ve el chaleco (detecciones del árbitro en B: de 4.075 a
264). El obstáculo es el de siempre, la ASOCIACIÓN: con el árbitro en ~10 identidades, cualquier
regla que decide por identidad lo reparte.
