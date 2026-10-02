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

## Celda 2 — SOLO si la 1 sale positiva: el COSTE en el partido entero

Bajar el umbral mete ruido en todo el partido (marcas, botas, dorsales), no solo en 9
frames. Esta celda rehace el caché de balón de la parte entera a 0,05 guardando la
confianza de cada caja; con él, cualquier umbral ≥ 0,05 se simula aquí en el Mac, con
todo el banco (GT de desempates, tramos etiquetados, continuidad, métricas de adopción),
sin volver a Colab.

```python
import yaml
cfg = yaml.safe_load(open('configs/processor_benja_balon_parte_entera.yaml'))
cfg['balon']['confianza'] = 0.05
cfg['rutas']['cache_balon'] = f'{D}/salidas/umbral_bajo/cache_balon_p1_conf005.pkl'
yaml.safe_dump(cfg, open('/content/cfg_conf005.yaml', 'w'), allow_unicode=True)
!python scripts/detectar_balon.py --config /content/cfg_conf005.yaml
```

Tiene checkpoint con reanudación: si la sesión se cae, volver a lanzar la misma celda
continúa. **Tráeme `cache_balon_p1_conf005.pkl`** a `data/tracking_benja/`.
