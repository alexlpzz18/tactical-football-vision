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
