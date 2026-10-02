# Colab: ¿el modelo ve el balón pegado al pie con confianza baja? (2-oct-2026)

Contexto en `docs/balon_en_vuelo.md`: en 9 frames con el balón visible (GT de Alex)
producción no tiene ninguna caja del balón cerca. Esta sesión mide si el modelo da una
señal DÉBIL (por debajo de 0,35) o nada. Tiempos: celda 1, unos minutos; celda 2, solo si
la 1 sale positiva, ~30-40 min de T4.

## Celda 0 — entorno

```python
from google.colab import drive; drive.mount('/content/drive')
!git clone -b experimento/asociacion-global https://github.com/alexlpzz18/tactical-football-vision.git
%cd tactical-football-vision
!pip -q install ultralytics sahi supervision "numpy<2.1"
import os
os.makedirs('data/raw', exist_ok=True); os.makedirs('models/weights', exist_ok=True)
D = '/content/drive/MyDrive/tactical-football-vision-data'
!ln -sf "{D}/videos/raw/benja_gredos_p1_20min.mp4" data/raw/benja_gredos_p1_20min.mp4
!ln -sf "{D}/best_balon_v1.pt" models/weights/best_balon_v1.pt
import cv2; cap = cv2.VideoCapture('data/raw/benja_gredos_p1_20min.mp4')
print(cap.isOpened(), cap.get(cv2.CAP_PROP_FRAME_COUNT))   # True y ~35966; si no, PARA
!nvidia-smi --query-gpu=name --format=csv
```

## Celda 1 — los 9 frames, a 0,35 (control) y a 0,05

```python
!python scripts/colab_balon_umbral_bajo.py \
    --config configs/processor_benja_balon_parte_entera.yaml \
    --salida "{D}/salidas/umbral_bajo"
```

Imprime, por caso, si el CONTROL a 0,35 reproduce el caché local (si dice "NO
COINCIDE", la sesión no es producción y el resto no vale) y las cajas a 0,05 que caen
sobre el balón, con su confianza. Deja en `salidas/umbral_bajo/` un recorte por caso (el
círculo amarillo es dónde marcó Alex el balón; rojo, cajas ≥ 0,35; magenta, < 0,35) y
`resultado.json`. **Tráeme `resultado.json` y los recortes.**

## Resultado de la celda 1 (2-oct-2026)

Control OK en los 9 (a 0,35 reproduce el caché local). A 0,05, caja sobre el balón en
4 de 9 (V03 0,17 · V05 0,097 · V08 0,288 · V12 0,154). Mirando los recortes (Alex), la
de V05 cae a la derecha del balón y no cuenta: **3 de 9 recuperables a umbral bajo, 6
sin señal ni a 0,05** (V05, V06, V15, V16, V18, V24).

## Celda 2 — el COSTE en el partido entero, con su control

⚠️ No vale "detectar a 0,05 y quedarse con lo que pase de 0,35", por tres razones:

1. SAHI cambia SOLO el postproceso a NMS/IOU por debajo de 0,1 (el aviso
   "Switching postprocess…"); producción usa GREEDYNMM/IOS. SAHI lo deja fijar con
   `force_postprocess_type=True`.
2. Aun fijándolo, la fusión depende del umbral: GreedyNMM se queda con la UNIÓN de las
   cajas que fusiona, así que una débil agranda a una fuerte.
3. La deduplicación del mixto tira una caja buena de la franja si se solapa con una
   débil del frame entero (`tests/test_cache_balon_umbrales.py`).

Así que `scripts/colab_cache_balon_umbrales.py` guarda lo de ANTES de cualquier fusión
(postproceso identidad registrado en SAHI) y, para cada umbral (0,05 … 0,35), aplica la
cadena de producción tal cual. Una pasada de GPU, siete cachés. **Control 1, dentro de
la pasada**: en los primeros 300 frames corre además el camino de producción literal a
0,35 y PARA si no sale idéntico. **Control 2, en el Mac**: el caché reconstruido a 0,35
contra `cache_balon_p1.pkl` de producción (mide además si la versión de SAHI de Colab ha
cambiado desde agosto).

```python
!python scripts/colab_cache_balon_umbrales.py \
    --config configs/processor_benja_balon_parte_entera.yaml \
    --salida "{D}/salidas/umbral_bajo"
```

Unos 30-40 min de T4, con checkpoint: si la sesión se cae, la misma celda reanuda. Tiene
que imprimir `CONTROL OK: 300 frames idénticos a producción`; si para con "CONTROL
FALLA", no sigas y tráeme el mensaje. **Tráeme los siete
`cache_balon_p1_confNNN.pkl`** a `data/tracking_benja/umbral_bajo/`.

## Criterio de adopción, fijado ANTES de ver números

Escrito como código en `scripts/medir_umbral_balon.py` para que no se mueva. Un umbral
intermedio (0,10-0,25) se adopta solo si cumple TODO:

0. Control: el reconstruido a 0,35 es producción (≥ 99 % de frames idénticos); si no,
   todo se compara con el reconstruido a 0,35 de la misma sesión, y se dice.
1. GT de desempates sin bajar de producción con la misma vara (35/38 con la caja a
   ≤ 15 px; con la caja exacta eran 34).
2. Cambios de objeto ≤ 3/min (producción: 2,85).
3. Fracción en las 5 marcas de verdad = 0.
4. Duración anclada ≤ 19,4 s; si la supera, se mira a ojo y solo vale si es una parada.
5. En los tramos etiquetados a ojo, lo que no es balón no sube.
6. BENEFICIO: de los 14 casos visibles con posición del GT de vuelo, ≥ 3 recuperados
   más que a 0,35.
7. COSTE: de 30 frames ganados al azar, a ojo, ≥ 2/3 balón real y ≤ 1/6 basura clara.

Si pasan varios, el centro del tramo que pasa. Si el ruido sube sin que suba lo
recuperado, se cierra. Probado de punta a punta con el caché de producción en cada
umbral: control 100 %, todas las filas iguales.

## Preparado, NO lanzado: etiquetado dirigido de los 6 sin señal

`scripts/preparar_etiquetado_balon_dirigido.py` → `outputs/etiquetado_balon_dirigido/`:
30 imágenes (6 casos × el frame del GT y dos muestreados a cada lado), una caja
pre-puesta por imagen en YOLO y en COCO, y `hoja.jpg` para revisarlas. La caja va donde
Alex dijo que estaba el balón: el círculo verde/rojo que nombró (posiciones medidas por
el sistema justo antes/después) o, si no nombró ninguno, el centro de su celda; con la
celda sola caía lejos del balón (V06, en el cielo). ⚠️ Si se reentrena con esto, no se
puede medir en estos frames ni en sus vecinos: es el mismo partido que el banco. V06 es
un balón ALTO contra el cielo (~15 px, bien visible): el único caso real de la pista de
la resolución.

## Resultado de la celda 2 (2-oct-2026): NINGÚN umbral pasa. No se adopta nada.

Control en Colab: 300 frames idénticos a producción. Control en el Mac: el reconstruido
a 0,35 coincide en 17.669 de 17.983 frames (98,3 %, bajo el 99 % fijado); lo que difiere
es ruido numérico (298 frames con las mismas cajas a ≤ 1,8 px y ≤ 0,0009 de confianza) y
16 frames con distinto número de cajas (24.907 contra 24.901). Por el criterio 0, todo se
compara contra el reconstruido a 0,35, que da las mismas métricas que producción.

| umbral | GT desempates | cambios/min | marcas | anclada | frames con balón | GT vuelo recuperados | t365 bal/malo/sin et. | t990 |
|---|---|---|---|---|---|---|---|---|
| 0,05 | 33 | 11,80 | 0 | 19,6 s | 10.993 | 7 | 78/0/52 | 158/3/4 |
| 0,10 | 34 | 8,15 | 0 | 19,6 s | 10.130 | 5 | 78/0/50 | 159/3/3 |
| 0,15 | 35 | 6,10 | 0 | 19,6 s | 9.565 | 3 (V03, V08, V12) | 79/0/43 | 160/3/1 |
| 0,20 | 35 | 4,80 | 0 | 19,9 s | 9.310 | 1 | 79/0/38 | 160/3/0 |
| 0,25 | 35 | 3,80 | 0 | 19,9 s | 9.026 | 1 | 79/1/35 | 159/3/0 |
| 0,30 | 35 | 3,30 | 0 | 19,8 s | 8.691 | 0 | 79/1/29 | 160/3/0 |
| **0,35** | **35** | **2,85** | 0 | 19,4 s | 8.608 | 0 | 79/0/28 | 159/3/0 |

Criterio: 0,10 falla 1, 2 y 4; 0,15 falla 2 y 4; 0,20 falla 2, 4 y 6; 0,25 falla 2, 4, 5
y 6. **El que manda es el 2: los cambios de objeto suben en cuanto se baja el umbral** —
ya a 0,30 (3,30/min) se pasa de 3—, y a 0,15, el único que recupera los 3 casos que se
vieron a 0,05, se duplican (6,10/min) por 957 frames más. El ruido sube mucho más rápido
que lo recuperado: **se cierra la vía del umbral**. El criterio 7 (mirar los ganados) no
hizo falta: todos fallan antes. Lo que queda es el detector (etiquetado dirigido,
preparado en `outputs/etiquetado_balon_dirigido/`).
