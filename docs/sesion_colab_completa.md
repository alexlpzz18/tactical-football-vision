# Sesión única de Colab: piloto de balón + cachés de color v2

Las dos cosas que necesitan GPU, en una sola sesión. El orden importa:
los pasos 2 y 3 **deciden parámetros** que usan los siguientes, así que
no se saltan.

Tiempo estimado: 35-50 min de T4. Cabe de sobra en una sesión.

---

## Antes de empezar: qué tiene que haber en Drive

```
MyDrive/tactical/
├── benja/
│   ├── partido_benja.mp4          (el vídeo del benjamín, 20 min)
│   └── best_balon_v1.pt           (el modelo de balón que entrenaste)
├── villaviciosa/
│   └── partido.mp4                (el vídeo de Villaviciosa)
└── modelos/
    └── best_v4pre.pt              (el detector de jugadores)
```

Si tus rutas son otras, solo hay que cambiar los enlaces del paso 1.

---

## Paso 1 — Preparar el entorno

```python
from google.colab import drive; drive.mount('/content/drive')
!git clone -b feature/balon https://github.com/alexlpzz18/tactical-football-vision.git
%cd tactical-football-vision
!pip -q install ultralytics sahi supervision "numpy<2.1"

import os
os.makedirs('data/raw', exist_ok=True)
os.makedirs('models/weights', exist_ok=True)
D = '/content/drive/MyDrive/tactical'
!ln -sf {D}/benja/partido_benja.mp4        data/raw/benja_gredos_p1_20min.mp4
!ln -sf {D}/benja/best_balon_v1.pt         models/weights/
!ln -sf {D}/modelos/best_v4pre.pt          models/weights/
!ln -sf {D}/villaviciosa/partido.mp4       data/raw/
!nvidia-smi --query-gpu=name,memory.total --format=csv
```

⚠️ La homografía y los configs vienen en el repo; el vídeo y los pesos NO
(están en .gitignore a propósito), por eso los enlaces.

---

## Paso 2 — DECIDE: umbral de operación del balón

No se hereda el 0,3 de jugadores. Para posesión y contactos un falso
positivo cuesta más que un fallo —un balón fantasma inventa un pase que
no existió—, así que se elige por **F0,5**, que pondera precisión.

```python
from ultralytics import YOLO
m = YOLO('models/weights/best_balon_v1.pt')
print(f"{'conf':>6} {'P':>7} {'R':>7} {'F1':>7} {'F0.5':>7}")
mejor = (0, 0)
for c in (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60):
    r = m.val(data='<TU data.yaml del dataset de balón>', conf=c,
              imgsz=1280, verbose=False)
    P, R = float(r.box.mp), float(r.box.mr)
    f1  = 2*P*R/(P+R) if P+R else 0
    f05 = 1.25*P*R/(0.25*P+R) if (0.25*P+R) else 0
    print(f"{c:>6.2f} {P:>7.3f} {R:>7.3f} {f1:>7.3f} {f05:>7.3f}")
    if f05 > mejor[1]: mejor = (c, f05)
print(f"\n→ pon balon.confianza = {mejor[0]} en configs/processor_benja_balon.yaml")
```

```python
# Aplícalo (sustituye 0.35 por el que salga)
!sed -i 's/^  confianza: 0.35/  confianza: {}/' configs/processor_benja_balon.yaml
```

---

## Paso 3 — DECIDE: ¿SAHI o frame entero?

Con imgsz 1280 puede que el frame completo baste, y SAHI cuesta ~10×.

```python
!python scripts/detectar_balon.py --config configs/processor_benja_balon.yaml \
    --comparar-sahi --frames 60
```

Imprime detecciones y ms/frame de las dos vías. **Si SAHI no encuentra
bastantes más, déjalo desactivado** (que es el default). Para activarlo:

```python
!sed -i 's/    activo: false/    activo: true/' configs/processor_benja_balon.yaml
```

---

## Paso 4 — Caché de BALÓN del tramo de 5 min (1 de cada 2 frames)

```python
!python scripts/detectar_balon.py --config configs/processor_benja_balon.yaml
```

El muestreo denso es deliberado: un jugador entre muestras se interpola
sin drama, pero un toque de balón entre muestras se pierde para siempre.

---

## Paso 5 — Caché de JUGADORES del MISMO tramo (1 de cada 3)

```python
!python scripts/procesar_partido.py --config configs/processor_benja_balon.yaml
```

---

## Paso 6 — Cachés con la FEATURE DE COLOR V2

Añade el canal V (desbloquea el arquetipo negro del catálogo arbitral:
árbitros y entrenadores de negro) y el histograma del pantalón. Los 256
primeros valores son bit a bit la v1, así que ningún umbral calibrado
cambia de escala. Rutas de salida propias: **no pisa nada**.

```python
# Villaviciosa (tramo del banco) y benjamín (mismo tramo de 1 min)
!python scripts/procesar_partido.py --config configs/processor_v2color.yaml
!python scripts/procesar_partido.py --config configs/processor_benja_v2color.yaml
```

Control rápido en la propia sesión: la longitud de la feature debe ser
336, y sus 256 primeros valores deben coincidir con la v1.

```python
import pickle, numpy as np
c = pickle.load(open('data/tracking/cache_colores_v4pre_v2color.pkl','rb'))
f = next(iter(c.values()))
print('longitud:', len(f), '(debe ser 336)')
print('norma del bloque HS:', round(float(np.linalg.norm(f[:256])), 3), '(debe ser ~1.0)')
```

---

## Paso 7 — Subir todo a Drive y avisarme

```python
!mkdir -p {D}/salidas
!cp data/tracking_benja/cache_balon_piloto.pkl              {D}/salidas/
!cp data/tracking_benja/cache_detecciones_benja_piloto5min.pkl {D}/salidas/
!cp data/tracking_benja/cache_colores_benja_piloto5min.pkl     {D}/salidas/
!cp data/tracking/cache_colores_v4pre_v2color.pkl          {D}/salidas/
!cp data/tracking/cache_detecciones_v4pre_v2color.pkl      {D}/salidas/
!cp data/tracking_benja/cache_colores_benja_v2color.pkl    {D}/salidas/
!cp data/tracking_benja/cache_detecciones_benja_v2color.pkl {D}/salidas/
!ls -lh {D}/salidas/
```

## Qué bajas a local

Todo lo de `MyDrive/tactical/salidas/`, respetando estas carpetas:

| archivo | destino local |
|---|---|
| `cache_balon_piloto.pkl` | `data/tracking_benja/` |
| `cache_*_benja_piloto5min.pkl` | `data/tracking_benja/` |
| `cache_*_v4pre_v2color.pkl` | `data/tracking/` |
| `cache_*_benja_v2color.pkl` | `data/tracking_benja/` |

Y me avisas. A partir de ahí, sin GPU, remato:

- **piloto de balón**: tracking (balón activo, fases aéreas, contactos),
  CSV conjunto, vídeo con cajas de los dos modelos, replay conjunto y los
  números (% con balón, % en fase aérea, nº de contactos);
- **re-medición v2**: paso 0 de control (debe dar exactamente 0,575 /
  0,444 / 5 quimeras usando solo el bloque HS), arquetipo negro para
  árbitro y entrenadores, re-barrido del cosido con la señal de color
  nueva, y si el **id 4** del benjamín se endereza.
