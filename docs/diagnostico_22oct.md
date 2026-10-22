# Diagnóstico del 22-oct-2026 — SOLO MEDICIÓN

Rama `diagnostico-22oct` (sale de `clasificacion-benja`). Sin tocar producción ni configs: se usan las
cachés existentes y la salida de producción de hoy ya regenerada (`outputs/arbitro_obs/`). Cada bloque
lleva su criterio ESCRITO ANTES de medir (esta sección se commitea primero), un control exacto (qué
saldría si no hubiera efecto) y la pregunta «¿qué podría estar inventando este número?». Todo en
PÍXELES, no en histogramas, salvo cuando lo que se mide ES el histograma.

Tramo del benjamín: el de 60 s de siempre, minutos 5-6 de archivo (5:00-6:00; 6:33-7:33 en el
reproductor), sobre la salida de la parte entera.

## Criterios (fijados antes de medir)

### Bloque 1 — el balón: bien en el vídeo, mal en la pizarra 2D

**Los dos balones:**
- el del **vídeo** es el balón ACTIVO de `generar_video_detecciones.balon_activo`: las cajas del
  detector elegidas por el selector, sin rellenos;
- el de la **pizarra** son las filas `balon`/`balon_aereo` del CSV conjunto de
  `scripts/procesar_balon.py`, con el mismo caché (`cache_balon_p1.pkl`) y el CSV de jugadores de hoy.

**Control de Villaviciosa: NO MEDIDO.** No hay caché de balón de Villaviciosa (solo hay
`cache_balon_p1` y `cache_balon_piloto`, las dos del benjamín). Se dice ahora, no después.

- **1a.** % de frames con balón en el vídeo y SIN fila de balón en la pizarra en ese frame, y la
  longitud de esos huecos (en s). *Control*: sin pérdida, 0 %.
- **1b.** El píxel que se proyecta. Se lee del código (no se supone). Cambio en metros entre proyectar
  el centro y la base de la caja, con mediana y p90 por zona de distancia a la cámara (x 0-20, 20-40,
  40-62). *Control*: un objeto en el suelo de 0,22 m apenas cambia; si cambia metros, es la
  perspectiva amplificando un desfase de píxeles.
- **1c.** Pasos de la pizarra a > 35 m/s y saltos > 10 m entre filas consecutivas de balón. *Control*:
  las mismas métricas sobre las trayectorias de los jugadores, que no deberían saltar.
- **1d.** % de posiciones de balón fuera del campo, y % de posiciones de balón RODANDO (`balon`, no
  `balon_aereo`) a más de **X = 10 m** del jugador más cercano. X está fijado aquí: el balón real tiene
  un p95 de 8,3 m al jugador más cercano (`ParametrosBalon`, comentario de `dist_max_jugadores`).
- **1e.** 30 paneles estratificados (10 balón en suelo, 10 alto o aéreo, 10 zona lejana x ≥ 40), cada
  uno con el frame y el balón marcado + la pizarra con el balón proyectado, en `outputs/diagnostico_balon/`.
  Se clasifican a ojo: ok / balón en el aire / salto entre candidatos / hueco / deriva por homografía /
  otro.
- **Conclusión**: una causa se declara principal si explica **≥ 50 %** de los frames malos de 1e
  (malo = cualquier clase distinta de «ok»). Si ninguna llega, se dice. No se arregla nada.

### Bloque 2 — el sensor de color del árbitro

**Aviso, antes de medir:** la banda del chaleco que dio `arbitro_tono_brillo` (H 43-59, S ≥ 105) cae
ENTERA dentro de la máscara anti-césped de la feature (se borra H 35-85, S ≥ 40, V ≥ 40). Medir «qué
fracción del chaleco, definido por esa banda, sobrevive a la máscara» da 0 por aritmética. Lo que se
mide:
- **2a.** De los píxeles del centro del torso de las cajas del árbitro (filas que marca el proxy), qué
  fracción sobrevive a la máscara (es decir, la ve el histograma), y la misma fracción en cajas vacías
  de césped. *Control*: si la máscara solo quitara césped, el torso del árbitro sobreviviría casi entero
  y el césped casi nada.
- **2b.** Si sobrevive < 30 % del torso del árbitro: una máscara POR POSICIÓN. Un píxel es «no césped»
  si cae fuera del rectángulo (H, S, V) p1-p99 del césped de cajas vacías del MISMO frame. Se compara
  con 2a.
- **Criterio de que una máscara discrimina**: sobrevive ≥ 30 % del torso del árbitro Y ≤ 5 % del
  césped.

### Bloque 3 — la altura relativa de la caja como señal del árbitro (un adulto entre niños)

- **3a.** f(u, v) = altura esperada de una caja (px) según la posición de su pie en la imagen: ajuste
  CUADRÁTICO robusto (pérdida de Huber) sobre todas las detecciones del tramo. Por identidad (≥ 40
  observaciones reales), la mediana de h / f.
- **Quién es el árbitro**: en el benjamín, las identidades con ≥ 40 observaciones y > 50 % de sus
  filas marcadas por el proxy de píxeles. Jugadores: las identidades A/B (o portero) con ≥ 40
  observaciones y < 5 % de filas del proxy. En Villaviciosa, el GT SÍ anota al árbitro: es árbitro la
  identidad cuyas filas casan (1-a-1, 2 m) mayoritariamente con el track `referee`.
- **3b.** AUC del árbitro contra los jugadores. *Control*: «árbitro falso» = una identidad de jugador
  al azar tratada como árbitro, 500 veces; su AUC debe rondar 0,5.
- **3c. Criterio de adopción**: ≥ 80 % de las identidades de árbitro por encima de 1,15 **y** ≤ 2 % de
  las de jugador por encima. En Villaviciosa (adultos) **no debería** separar; si separa allí, la señal
  no es «adulto entre niños», es otra cosa.
- **3d. Aviso**: la altura adulta de referencia (1,75 m) es una suposición, no un dato. No se usa para
  nada: h / f es relativo al propio partido.

### Bloque 4 — contador sin GT

- **4a.** Nº de frames con más jugadores por equipo (portero incluido) de los que permite el reglamento:
  **> 7 en el benjamín (F7) y > 11 en Villaviciosa (F11)**. Se cuenta sobre las filas que se pintan
  (reales e interpoladas) y aparte solo las reales. Qué identidades aparecen en esos frames, y cuántos de
  esos frames contienen al árbitro (proxy de píxeles; en Villaviciosa, el `referee` del GT donde hay GT)
  o a alguien etiquetado `staff`. *Control*: sin errores, 0 frames.
- No hay criterio de adopción: es un contador.

Si un paso falla dos veces, se deja como «no medido» y se sigue.
