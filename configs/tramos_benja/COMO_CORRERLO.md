# 5 tramos de 4 min

Cada tramo es UNA sesión de Colab. Se solapan 5 s para que
una sesión caída no deje un agujero en la costura; la fusión descarta los
frames repetidos.

## En cada sesión de Colab

```python
from google.colab import drive; drive.mount('/content/drive')
%cd /content/tactical-football-vision
!python scripts/procesar_partido.py --config configs/tramos_benja/tramo_01.yaml
```

cambiando `tramo_01` por el que toque. Los cachés parciales van a
`/content/drive/MyDrive/tactical/tramos`.

## Cuando estén todos

```bash
python scripts/fusionar_caches.py \
    --detecciones /content/drive/MyDrive/tactical/tramos/cache_t*.pkl \
    --colores /content/drive/MyDrive/tactical/tramos/colores_t*.pkl \
    --salida-detecciones data/tracking_benja/cache_detecciones_benja.pkl \
    --salida-colores data/tracking_benja/cache_colores_benja.pkl
```

Avisa si queda algún hueco temporal, que es la forma de darse cuenta de
que una sesión murió sin que nadie lo notara. A partir de ahí, todo el
trabajo local es el de siempre:

```bash
python scripts/procesar_partido.py --config configs/processor_benja.yaml --modo desde_cache
```
