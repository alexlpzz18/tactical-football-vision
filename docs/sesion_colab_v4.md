# Sesión de Colab del v4 — cachés para la re-medición

Corta: dos tramos de un minuto. 10-15 min de T4.

**Los configs llevan el tramo escrito, no comentado.** Es a propósito: con
`processor.yaml` hay que acordarse de descomentarlo, y esa fue la trampa
que dejó el caché v2color de Villaviciosa inservible (procesó los 16.300
frames del vídeo entero en vez del minuto del banco).

## Qué tiene que haber en Drive

```
MyDrive/tactical/
├── modelos/best_v4.pt          ← el que estás entrenando
├── villaviciosa/partido.mp4
└── benja/partido_benja.mp4
```

## Celda única

```python
from google.colab import drive; drive.mount('/content/drive')
!git clone -b v4/caches-y-informe https://github.com/alexlpzz18/tactical-football-vision.git
%cd tactical-football-vision
!pip -q install ultralytics sahi supervision "numpy<2.1"

import os
os.makedirs('data/raw', exist_ok=True); os.makedirs('models/weights', exist_ok=True)
D = '/content/drive/MyDrive/tactical'
!ln -sf {D}/modelos/best_v4.pt        models/weights/
!ln -sf {D}/villaviciosa/partido.mp4  data/raw/
!ln -sf {D}/benja/partido_benja.mp4   data/raw/benja_gredos_p1_20min.mp4

# Comprobación de 10 s antes de gastar GPU: los dos vídeos deben abrirse
import cv2
for v in ('data/raw/partido.mp4', 'data/raw/benja_gredos_p1_20min.mp4'):
    cap = cv2.VideoCapture(v)
    print(v, cap.isOpened(), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))

!python scripts/procesar_partido.py --config configs/processor_v4.yaml
!python scripts/procesar_partido.py --config configs/processor_benja_v4.yaml
```

⚠️ Si el enlace del vídeo de Villaviciosa se llama distinto en tu Drive,
cambia el `ln -sf` para que el destino sea el nombre que pide
`configs/processor_v4.yaml` en `rutas.video`. El nombre de DESTINO es el
que manda, no el de origen.

## Qué subir a Drive al terminar

```python
!mkdir -p {D}/salidas_v4
!cp data/tracking/cache_detecciones_v4.pkl        {D}/salidas_v4/
!cp data/tracking/cache_colores_v4.pkl            {D}/salidas_v4/
!cp data/tracking_benja/cache_detecciones_benja_v4.pkl {D}/salidas_v4/
!cp data/tracking_benja/cache_colores_benja_v4.pkl     {D}/salidas_v4/
!ls -lh {D}/salidas_v4/
```

## Qué bajar a local

| archivo | carpeta local |
|---|---|
| `cache_detecciones_v4.pkl` · `cache_colores_v4.pkl` | `data/tracking/` |
| `cache_detecciones_benja_v4.pkl` · `cache_colores_benja_v4.pkl` | `data/tracking_benja/` |

Y avísame. La medición va sin GPU:

```bash
python scripts/medir_v4.py \
    --cache-v4 data/tracking/cache_detecciones_v4.pkl \
    --colores-v4 data/tracking/cache_colores_v4.pkl \
    --cache-benja-v4 data/tracking_benja/cache_detecciones_benja_v4.pkl \
    --colores-benja-v4 data/tracking_benja/cache_colores_benja_v4.pkl
```

Compara v4pre contra v4 en las dos patas del banco y en los tres casos con
nombre (id 4, id 32, id 19→4). Detalle de lo que cuenta como éxito, en
`docs/remedir_v4.md`.

## Comprobación rápida al bajarlos

Antes de medir, que los cachés cubran el tramo correcto:

```bash
python -c "
import pickle
for r in ('data/tracking/cache_detecciones_v4.pkl',
          'data/tracking_benja/cache_detecciones_benja_v4.pkl'):
    c = pickle.load(open(r,'rb'))['cache']
    print(r.split('/')[-1], len(c), 'frames', c[0]['frame_idx'], '-', c[-1]['frame_idx'])
"
```

Deben salir ~500 frames (Villaviciosa) y ~600 (benjamín). Si sale un
número de cinco cifras, el tramo no se aplicó y hay que repetir.
