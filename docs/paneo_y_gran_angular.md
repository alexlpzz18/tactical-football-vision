# Qué rompería el pipeline con PANEO y con 0,5x (gran angular) — lista priorizada (3-oct-2026)

Sin construir nada: la evidencia es el código. Orden: lo que rompe TODO primero.

## Con paneo (la cámara se mueve durante el partido)

| # | qué se rompe | evidencia | por qué |
|---|---|---|---|
| 1 | **Toda posición en metros** | `src/tracking_data/processor.py:623`: `H = np.load(cfg["rutas"]["homografia"])`, UNA homografía para el vídeo entero | Con paneo, cada frame necesita su H. Con la fija, cada metro que sale del sistema está mal, y todo lo de abajo se apoya en eso: el tracking en metros (la ventaja diferencial), las reglas de posición (portero, staff, árbitro) y el informe. |
| 2 | **El caché guarda los metros ya calculados** | formato del caché: `(mx, my, x1, y1, x2, y2, conf)`, con `(mx, my)` proyectados al detectar | Arreglarlo después no exige GPU (las cajas en píxeles están), pero sí una H por frame y reproyectar. |
| 3 | **La asociación de ByteTrack es en píxeles** | `src/tracking/asociacion_bytetrack.py` (IoU de cajas), `umbral_emparejamiento: 0.995` | Un paneo rápido desplaza todas las cajas entre frames: cae el IoU y se trocean las identidades (o, peor, se empareja con el vecino, el mecanismo de la 525). |
| 4 | **Umbrales en función de la zona** | `src/tracking/resolucion.py:130` calcula los metros por píxel de cada zona con la H fija; los usan `cosido_pureza`, `suavizado`, `consolidacion` y `corte_velocidad` | Con paneo, "el fondo" deja de ser una zona fija de la imagen: los márgenes de ruido se aplicarían donde no toca. |
| 5 | **Filtro de plausibilidad física** | `processor.py:822` (H fija) | Mide en metros lo que hay dentro de cada caja con la escala de la H; con la H equivocada, descarta personas o deja pasar líneas. |
| 6 | **Balón: marcas estáticas y franja lejana** | `src/balon/marcas_estaticas.py`, `src/balon/franja_lejana.py`, `tracking_balon.escala_px_por_m` | Las marcas del campo se filtran por acumular cientos de detecciones en la MISMA celda de 12×12 px; con paneo se mueven y volverían a pasar por balón (el caso de los 47 huecos). La franja de SAHI del fondo ya no es fija, pero se calcula UNA vez por vídeo. |
| 7 | La calibración en sí | 19 clics por campo (`src/homography/marcar_puntos.py`) | Con paneo no hay "un frame" que clicar: hace falta calibrar sola cada vista (`docs/calibracion_automatica.md`). |

## Con 0,5x (gran angular, con distorsión)

| # | qué se rompe | evidencia | por qué |
|---|---|---|---|
| 1 | **Los jugadores quedan por debajo de 25 px** | diagnóstico de Villaviciosa: el detector se degrada por debajo de 25 px | 0,5x es la mitad de focal: la mitad de píxeles por jugador. El benjamín está hoy en ~59 px de mediana (cajas del detector, 10 frames) y bajaría a ~30, con el fondo por debajo del umbral. `src/validacion_video.py` lo avisa al recibir el vídeo. |
| 2 | **El modelo de lente es fijo y supone focal = ancho** | `processor.py:44-47`: `_build_camera_matrix(w, h, focal_factor=1.0)` → `fx = fy = w`; `k1, k2` a mano por config (Villaviciosa: `k1 = -1.5`) | Una 0,5x tiene otra focal y otra distorsión. Con K mal, `undistort` deja un residuo radial, y Villaviciosa ya lo sufre: no cuadran a la vez el círculo y las áreas. |
| 3 | **Las líneas dejan de ser rectas** | la homografía es un modelo de plano SIN distorsión | El residuo radial curva las líneas en los bordes: falla la H manual (los clics de los bordes no cuadran) y la automática, que busca rectas y círculos. |
| 4 | **Coste de corregir la distorsión** | `processor.py:349`: 27,8 ms por frame a 1080p (5,6 min de CPU por parte) | Hoy el benjamín se lo salta (k1 = k2 = 0); una 0,5x no puede. |
| 5 | **Teselas de SAHI y umbrales en píxeles** | `deteccion.sahi` (2×4), `jitter_px: 3.5`, `puerta_reentrada` y los cruces por IoU | Están medidos para una escala de imagen concreta; a la mitad de tamaño habría que volver a medirlos. CLAUDE.md: "los umbrales van pegados al detector". |

## Prioridad para el producto ("cualquier cámara")

1. **Una H por frame** (o por plano estable) en lugar de una por vídeo: es lo que bloquea el paneo
   entero, y exige antes una calibración automática que funcione.
2. **Tamaño mínimo de jugador**: avisar al recibir (hecho) y, con 0,5x, subir la resolución o
   recortar la zona de juego antes de detectar.
3. **Calibración de lente automática** (K y distorsión), porque los dos parámetros a mano
   no escalan a cámaras de usuario.
4. Re-medir los umbrales en píxeles para cada escala.
