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

---

# Resultados (22-oct-2026)

Scripts: `scripts/diag22_balon.py`, `scripts/diag22_mascara_arbitro.py` y
`scripts/diag22_altura_contador.py`. Las salidas, en `outputs/diagnostico_22oct/` y
`outputs/diagnostico_balon/` (fuera de git). Producción de hoy: `outputs/arbitro_obs/` (benjamín) y
una pasada desde caché de Villaviciosa con espía (`outputs/diagnostico_22oct/villa/`).

## Bloque 1 — el balón

Tramo de 5:00-6:00 de archivo: 436 frames con balón en el vídeo y 594 filas de balón en la pizarra
(106 aéreas). Se proyecta la **base** de la caja, `((x1+x2)/2, y2)` (`detectar_balon.py`, l. 231).

| | resultado | control (sin efecto) |
|---|---|---|
| **1a** frames con balón en el vídeo y sin él en la pizarra | **0 %** (0 de 436): ningún hueco | 0 % |
| **1b** centro de la caja contra base, en metros (mediana / p90) | x 0-20: 0,57 / 0,83 · **x 20-40: 1,48 / 1,70** · x 40-62: 2,12 / 2,59 | un objeto de 0,22 m en el suelo: < 0,2 m |
| **1c** pasos de la pizarra a > 35 m/s · saltos > 10 m | **0,2 % · 0,4 %** | jugadores: 0 % · 0 % |
| **1d** posiciones fuera del campo · rodando a > 10 m del jugador más cercano | **15,0 %** · 0,6 % | — |

- **1a, ¿qué podría estar inventando?** La comparación es en el CSV, frame a frame. Que el replay
  pinte o no ese balón en ese instante (muestrea por tiempo y a otra cadencia que los jugadores) no
  está medido.
- **1b**: medio balón de alto (7-15 px) son 0,6-2,1 m en el suelo. Es la perspectiva amplificando
  píxeles, no un error de la homografía. Proyectar la base es lo correcto para un balón en el suelo y
  lo incorrecto para uno en el aire.
- **1d, qué son las de fuera**: el 70 % son filas `balon` (62 de 89) y caen en x ≈ 28-31 m,
  y ≈ 41-42 m. Ahí, detrás de la grada, está **el campo de al lado**, donde juegan otros niños con
  otro balón (se ve en los paneles).
- **106 frames tienen dos filas de balón** (`balon` + `balon_aereo`), pero en el MISMO punto (0,00 m):
  es la unión de un tramo de suelo con uno aéreo. Se pintan una encima de otra; es inofensivo.

**1e — 30 paneles** (10 suelo, 10 alto, 10 lejos; dos frames salieron en dos estratos, así que son 28
distintos), clasificados a ojo:

| estrato | ok | balón en el aire | salto entre candidatos (balón del campo de al lado) | otro |
|---|---|---|---|---|
| suelo | 10 | 0 | 0 | 0 |
| alto | 2 | 4 | 3 | 1 |
| lejos | 1 | 4 | 4 | 1 |
| **total** | **13** | **8 (47 % de los malos)** | **7 (41 %)** | 2 |

- **Balón en el suelo: bien.** La pizarra lo pone a 0,0-0,3 m de la proyección de la caja del vídeo,
  coherente con los jugadores.
- **Balón en el aire**: la caja está en el aire, su «base» se proyecta muy lejos (fuera del dibujo) y
  la pizarra pone una posición interpolada a 10-40 m. Es lo esperado por diseño (`balon_aereo` = posición
  no fiable).
- **El balón del campo de al lado** (f10166, f9306, f9360, f9738, f10472 y f10474): el selector elige
  como activo un balón que está FUERA, en el otro campo, detrás de la grada. **Ahí el vídeo tampoco
  está bien**: pinta un balón que no es el del partido. La pizarra lo pone a 50-80 m del juego.
- Otros: f8992 (caja junto al jugador, sin el balón dentro) y f10098 (caja sobre el muro, sin balón
  visible).

**Conclusión del bloque 1, por el criterio: ninguna causa llega al 50 %** (balón en el aire 47 %;
balón del campo de al lado 41 %; entre las dos, el 88 % de los frames malos). No hay pérdidas (1a = 0)
ni saltos (1c ≈ 0). ⚠️ Los estratos sobrerrepresentan a propósito los casos difíciles: en el tramo,
el 18 % de las filas de la pizarra son aéreas y el 15 % están fuera del campo. Y **«bien en el vídeo,
mal en la pizarra» no es exacto**: en el balón del otro campo, los dos están mal.

**Control de Villaviciosa: NO MEDIDO** (no existe caché de balón de Villaviciosa).

## Bloque 2 — el sensor de color del árbitro

Centro del torso, en píxeles, 20 frames por minuto: 60.820 píxeles del árbitro (filas del proxy) y
759.024 de césped (cajas vacías).

| máscara | sobrevive del torso del árbitro | sobrevive del césped | ¿discrimina? (≥ 30 % y ≤ 5 %) |
|---|---|---|---|
| **2a** la de la feature (borra H 35-85, S≥40, V≥40) | **7,3 %** | 4,6 % | **no** |
| **2b** por posición (fuera del p1-p99 del césped del mismo frame) | **98,5 %** | 8,4 % | **no**, por la letra |

- **2a: la feature de color está prácticamente ciega al chaleco.** Ve el 7 % del torso del árbitro,
  casi lo mismo que del césped. Confirma, medido, la explicación de CLAUDE.md: el histograma solo ve
  los restos que sobreviven a la máscara. **Es el problema del árbitro en una frase: la
  representación borra justo el color que lo distingue.**
- **2b: la máscara por posición conserva el torso del árbitro casi entero.** Pero el criterio pide
  ≤ 5 % de césped y deja pasar 8,4 %. ⚠️ **Fallo mío al fijar el criterio**: un rectángulo p1-p99 por
  canal, en tres canales, deja fuera por construcción ~6 % de un césped IDÉNTICO
  (1 − 0,98³ = 5,9 %), así que el 5 % no se podía cumplir ni sin efecto. El control exacto es ese
  5,9 %; el exceso real es de ~2,5 puntos. No cambio el veredicto: **no discrimina por la letra**,
  aunque la separación (98,5 % contra 8,4 %) es enorme.
- **¿Qué podría estar inventando?** Los píxeles del árbitro salen de las filas del PROXY, que está
  hecho con el histograma. Si en algún momento el chaleco no llega al proxy, esos instantes no están.
  Y el césped de cajas vacías no incluye el césped que hay DENTRO de una caja de jugador (a los lados
  del cuerpo).

## Bloque 3 — la altura relativa de la caja

f(u, v) cuadrática con pérdida de Huber, por partido; h / f por identidad (mediana, ≥ 40 obs).

| | árbitro (h/f) | jugadores: p50 · p90 · p99 | AUC | control «árbitro falso» (AUC media · p95) | ≥ 80 % árbitro > 1,15 y ≤ 2 % jugadores | |
|---|---|---|---|---|---|---|
| **benjamín** (60 s) | **1,22 y 1,23** (ids 292, 198) | 0,97 · 1,02 · 1,03 (22 ids) | **1,00** | 0,50 · 0,95 | 100 % · 0 % | **CUMPLE** |
| **Villaviciosa** (60 s, adultos) | **1,14** (id 32, el `referee` del GT) | 1,00 · 1,04 · 1,06 (37 ids) | **1,00** | 0,47 · 0,97 | 0 % · 0 % | no cumple |

- **Benjamín: separa limpio.** Las dos identidades de árbitro están en 1,22, y ningún jugador pasa
  de 1,03.
- **Villaviciosa, el control, NO sale como se esperaba**: no pasa el umbral (1,14 < 1,15), pero el
  árbitro **sigue siendo la caja más alta en proporción** (AUC 1,0; el p99 de los jugadores es 1,06).
  Entre adultos, la diferencia no puede ser de estatura. ⇒ **La señal no es solo «un adulto entre
  niños»**: algo hace la caja del árbitro más alta en los dos partidos (postura erguida, brazos
  arriba señalando, o cómo lo encaja el detector). En el benjamín se suma la estatura (1,22 frente a
  1,14), pero no es lo único.
- **¿Qué podría estar inventando?** Que el árbitro sean **2 identidades en el benjamín y 1 en
  Villaviciosa** (60 s). Con tan pocas, un AUC de 1,0 dice «es la más alta», no una tasa: el control
  de un jugador al azar llega a 0,95-0,97 en su p95. Hace falta más tiempo (la parte entera) antes de
  creérselo. Y la identidad del árbitro en el benjamín viene del proxy de color; que sea el árbitro de
  verdad está comprobado a ojo en septiembre, no hoy.
- **3d**: la altura adulta de 1,75 m no se usa; h/f es relativo al propio partido.

## Bloque 4 — el contador sin GT

| | frames con más jugadores por equipo de los que caben | con árbitro | con staff |
|---|---|---|---|
| benjamín (> 7), todas las filas | **5.112 de 11.989 (43 %)**: B 4.747, A 501; máximo 12 | 75 % (base: 84 %) | 80 % (base: 75 %) |
| benjamín, solo filas reales | 4.133 (34 %) | 76 % | 78 % |
| Villaviciosa (> 11), todas | 437 de 500 (87 %) | 98 % | 100 % (base: 100 %) |
| Villaviciosa, solo reales | 275 (55 %) | 97 % | 88 % |

- **El control (tasa base) cambia la lectura.** El árbitro está en el 84 % de TODOS los frames del
  benjamín y en el 75 % de los que tienen exceso: **no está enriquecido**, no explica el exceso. El
  staff, casi igual (80 % frente a 75 %).
- **El exceso es casi entero del equipo B** (4.747 frames contra 501) y llega a 12 filas. Encaja con
  el árbitro etiquetado B (38 % de sus filas), pero el árbitro solo suma una fila; un exceso de hasta
  5 tiene que venir de **la misma persona en varias identidades a la vez** (los duplicados de
  CLAUDE.md) o de filas interpoladas: con solo las reales baja del 43 % al 34 %.
- **¿Qué podría estar inventando?** Contar `portero_B` con el B: dos fragmentos simultáneos del
  portero suman dos. Y en Villaviciosa (equipo equivocado 23,6 %) el contador mide sobre todo la
  confusión de equipos, no la presencia.
- Las identidades más frecuentes en esos frames son, en los dos partidos, las identidades LARGAS (las
  que están siempre). No señalan a una culpable.

---

## Resumen

| bloque | qué se midió | resultado | ¿cumple el criterio? | causa probable | siguiente paso propuesto |
|---|---|---|---|---|---|
| 1 balón | vídeo contra pizarra; 30 paneles | 0 % de huecos, 0,2 % de saltos; 15 % fuera del campo; malos: aire 47 %, otro campo 41 % | **ninguna causa ≥ 50 %** (dos suman el 88 %) | balón en el aire (por diseño) y **el balón del campo de al lado elegido como activo** | medir cuántas filas son el balón del otro campo en el partido entero; una zona prohibida por posición ya existe para el staff |
| 2 color árbitro | qué ve la feature del torso | feature: 7,3 % del árbitro frente a 4,6 % del césped; por posición: 98,5 % frente a 8,4 % | **no** (la feature no discrimina; por posición falla por mi umbral) | **la máscara anti-césped borra el chaleco** | rehacer el criterio de 2b con el control 1 − 0,98³ antes de seguir |
| 3 altura | h/f por identidad | benjamín 1,22 frente a ≤ 1,03 (AUC 1,0); Villaviciosa 1,14 frente a ≤ 1,06 (AUC 1,0) | **benjamín sí**, Villaviciosa no (como se pedía) | estatura + algo más que también separa entre adultos | repetir en la parte entera (más identidades de árbitro) antes de creérselo |
| 4 contador | frames con exceso por equipo | benjamín 43 % (casi todo B, hasta 12); Villaviciosa 87 % | contador, sin criterio | **no el árbitro ni el staff** (están a su tasa base); duplicados simultáneos | medir duplicados simultáneos (dos identidades a < 1 m en el mismo frame) en esos frames |

**Producción sin tocar**: `git diff --stat main -- src configs` vacío al cerrar (comprobado abajo).
