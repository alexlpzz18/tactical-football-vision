# Sesión de Colab: cachés de embeddings (19-ago-2026)

Genera los embeddings de los tres candidatos sobre los dos tramos del
banco. Necesita GPU; en el Mac no se puede (CLAUDE.md).

## Qué subes y qué bajas

**No subes nada nuevo.** Todo está ya en Drive: los vídeos y los cachés
de detecciones del v4. Solo hay que montar Drive y clonar el repo.

**Bajas 6 ficheros** (3 backbones × 2 partidos), 22.741 recortes en total
(10.621 de Villaviciosa + 12.120 del benjamín):

| backbone | dims | por partido | los dos |
|---|---|---|---|
| siglip-base-patch16-224 | 768 | ~16 / ~19 MB | **35 MB** |
| dinov2-base | 768 | ~16 / ~19 MB | **35 MB** |
| timm resnet50.a1_in1k | 2048 | ~44 / ~50 MB | **93 MB** |

**Total ≈ 163 MB.** Cabe de sobra y no hace falta PCA todavía.

**Sin PCA a propósito**: el benchmark mide el backbone, no la PCA. Además
las dimensiones son distintas (768 / 768 / 2048) y comprimirlas antes
sería comparar cosas distintas. La PCA a 128 se evalúa después, solo
sobre el ganador, como optimización de producción — ahí sí importa,
porque a escala de partido completo son 1,6 GB frente a 270 MB.

## Celdas

**Celda 1 — entorno**

```python
from google.colab import drive; drive.mount('/content/drive')
%cd /content
!git clone https://github.com/<tu-usuario>/tactical-football-vision.git 2>/dev/null || (cd tactical-football-vision && git pull)
%cd /content/tactical-football-vision
!pip -q install timm transformers
!nvidia-smi --query-gpu=name,memory.total --format=csv
```

**Celda 2 — enlazar los datos de Drive**

```python
import os
RAIZ = "/content/drive/MyDrive/<tu-carpeta>"   # ajusta a tu ruta
for sub in ("data/raw", "data/tracking", "data/tracking_benja"):
    os.makedirs(sub, exist_ok=True)
!ln -sf {RAIZ}/data/raw/* data/raw/ 2>/dev/null
!ln -sf {RAIZ}/data/tracking/*.pkl data/tracking/ 2>/dev/null
!ln -sf {RAIZ}/data/tracking_benja/*.pkl data/tracking_benja/ 2>/dev/null
!ls -la data/tracking/*v4*.pkl data/tracking_benja/*v4*.pkl
```

**Celda 3 — generar los seis cachés**

```python
TRAMOS = [
    ("villa", "data/tracking/cache_detecciones_v4.pkl",
     "data/raw/<video_villaviciosa>.mp4", "data/tracking"),
    ("benja", "data/tracking_benja/cache_detecciones_benja_v4.pkl",
     "data/raw/benja_gredos_p1_20min.mp4", "data/tracking_benja"),
]
for backbone in ("siglip", "dinov2", "resnet50"):
    for nombre, cache, video, destino in TRAMOS:
        !python scripts/generar_embeddings.py \
            --cache {cache} --video {video} \
            --backbone {backbone} \
            --salida {destino}/emb_{nombre}_{backbone}.pkl
```

**Celda 4 — copiar a Drive para bajarlos**

```python
!mkdir -p {RAIZ}/data/embeddings
!cp data/tracking/emb_*.pkl data/tracking_benja/emb_*.pkl {RAIZ}/data/embeddings/
!ls -lh {RAIZ}/data/embeddings/
```

## Tiempo esperado

Pocos minutos. El vídeo se decodifica **una sola vez por tramo** (1.100
frames en total) y los recortes van en lotes de 64. Lo que domina es la
descarga de los pesos la primera vez.

## Comprobación antes de fiarte del resultado

Cada caché guarda `backbone` y `cache_origen`. Si `cache_origen` no es el
caché de detecciones del v4, los `det_idx` no casan y el caché no vale
para nada: **son posiciones dentro de la lista de detecciones de cada
frame**, no identificadores estables. Es el mismo fallo que ya caducó un
mini-GT entero.

## Y después

El ganador se elige con el criterio ya escrito en
`docs/benchmark_embeddings.md` — TPR @ FPR 1 % en parejas de compañeros
del mismo equipo, en el bin de recortes < 20 px, contra la línea base del
histograma HSV. Ese criterio está fijado ANTES de ver un solo número.
