# Una parte entera del benjamín, de una sola pasada

**Estado: preparado, NO ejecutado.** Las celdas están listas con rutas
reales; la decisión de gastar la GPU es de Alex. Config:
`configs/processor_benja_parte_entera.yaml`.

Lo que hay abajo, en orden: primero **qué se sabe que va a cambiar al
escalar** (medido, no estimado a ojo), y después las celdas, con una
sonda que mide el ritmo real antes de comprometer la sesión entera.

---

## Lo que se va a procesar (medido sobre el fichero, no supuesto)

| | valor |
|---|---|
| vídeo | `data/raw/benja_gredos_p1_20min.mp4`, 286 MB |
| fps · frames · duración | 29,970 · 35.966 · **1200,1 s = 20,0 min exactos** |
| resolución | 1920×1080 |
| frames a procesar (`sample_every: 3`) | **11.988** |
| inferencias SAHI (2×4 = 8 recortes) | ~95.900 |

El piloto de 5 min ya procesado tiene **2997 frames**, así que esta
pasada es exactamente **×4,00**. Todo lo de abajo sale de comparar tres
longitudes reales del MISMO partido: 60 s, 5 min y la extrapolación a 20.

---

## Aviso 1 — La regla del portero se va a abstener (y ya falla hoy)

Este es el problema de verdad, y no es una predicción: **ya pasa en el
piloto de 5 minutos**.

`porteros.min_presencia: 0.50` pide que la identidad coronada esté
presente en más de la mitad **del tramo**. Presencia del mejor candidato
de cada lado:

| lado | 60 s | 5 min |
|---|---|---|
| bajo | id 24 — **87 %** (524/600) | id 24 — **49 %** (1467/2997) |
| alto | id 8 — **100 %** (599/600) | id 90 — 66 % · id 49 — 51 % · id 112 — 31 % · id 8 — 26 % |

A 5 minutos el lado bajo cae al 49 % y la regla **se abstiene** — con el
WARNING que se puso justo para esto:

> `SIN PORTERO en el lado de A: la mejor candidata (identidad 24) solo pisa el área el 88 % y está presente el 49 %.`

Fíjate en el dato que lo delata: **pisa el área el 88 %**. Es el portero,
sin discusión. Lo que falla no es identificarlo, es la puerta de
presencia. Y el resultado se ve en la cuenta: **2 porteros a 60 s, 1 a 5
minutos**.

Extrapolando el trozo dominante (524 frames a 60 s → 1467 a 5 min: el
tramo crece ×5 y el trozo solo ×2,8), a 20 minutos serían ~3500 de
11.988 = **~29 %**. Muy por debajo de 0,50: **se abstendrá en los dos
lados**.

**Y no es un umbral mal puesto, es un supuesto que se rompe.** Mira otra
vez el lado alto a 5 min: el portero no es *una* identidad, son cuatro
(66 %, 51 %, 31 %, 26 %). Bajar el mínimo coronaría al trozo mayor y
dejaría los otros tres con su etiqueta de color — que es poco fiable por
diseño, que es justo el riesgo que la regla existía para tapar. Sobre 20
minutos **el portero es N identidades**, y una regla que corona una por
lado se queda corta por construcción, con el umbral que le pongas.

No lo he tocado. Se decide midiendo contra las métricas de producto,
como todo, y eso es una tarea entera. Lo que sí hará el sistema es
avisar: el WARNING está puesto y saldrá en el log de Colab.

---

## Aviso 2 — El caché se escribe UNA sola vez, al final

En `procesar_full` (src/tracking_data/processor.py) el bucle acumula
`cache` y `colores` en RAM y el `pickle.dump` está **después** del
`while`. No hay checkpoint ni reanudación.

Traducido: si la sesión se cae en el minuto 55 de una pasada de 60,
**se pierde entera**. Y como el `logger.info` también está fuera del
bucle, la celda **no imprime nada** mientras corre: 45-60 minutos de
silencio en los que no se distingue "va bien" de "está colgado".

Por eso la celda 3 es una sonda de ritmo: 60 s de vídeo, cronometrados,
para saber la duración real ANTES de comprometer la sesión.

Arreglarlo son ~15 líneas (volcar cada N frames a las mismas rutas y
reanudar si el fichero existe) más un log de progreso. **No lo he hecho:**
toca el camino de producción y hoy tocaba preparar la pasada. Dime y va
en la siguiente sesión — y si la sonda dice que la pasada son 25 minutos,
igual no compensa.

---

## Aviso 3 — Memoria y tiempo de fit: NO son el problema

Aquí la sospecha no se confirma, y conviene decirlo con el número
delante para no gastar esfuerzo donde no hace falta.

| | 60 s | 5 min | 20 min (×4) |
|---|---|---|---|
| recortes con color | 10.867 | 55.875 | ~224.000 |
| caché de colores en disco | 22,7 MB | 116,7 MB | **~467 MB** |
| caché de detecciones | 1,2 MB | 6,2 MB | ~25 MB |
| cargarlo | 0,1 s | 0,3 s | ~1,2 s |
| **fit de color** (`n_init: 50`) | 1,1 s | 5,4 s | **~22 s** |

- **RAM**: 224.000 features × 256 float64 ≈ 513 MB vivos, sobre los ~12,7
  GB de una sesión estándar. Cabe de sobra. El `pickle.dump` de 467 MB
  tampoco duplica: escribe a fichero, no a memoria.
- **El fit escala LINEAL** (×5,1 recortes → ×4,9 tiempo), así que
  `n_init: 50` —adoptado midiendo sobre 60 s— cuesta ~22 s sobre la parte
  entera. No hay que revisarlo.
- **Descartado a propósito: pasar la feature a `float32`.** Halvaría el
  caché a ~234 MB y la pérdida de precisión sería irrelevante (~1e-7
  contra umbrales de 1e-2). Pero cambiaría el contenido bit a bit de los
  cachés y, con el fit siendo la pieza frágil que es
  (`docs/suelo_de_ruido.md`), no vale la pena mover la entrada del
  KMeans para ahorrar disco.
- **`cv2.undistort` ya no se ejecuta.** Con `k1=k2=0` era la identidad
  —comprobado bit a bit sobre 10 frames reales— y costaba 27,8 ms por
  frame a 1080p: **5,6 minutos de CPU** sobre esta pasada, alimentando a
  la GPU. Ahora se salta (`_corregir_distorsion`, con tests).

---

## Aviso 4 — Las demás reglas de tramo corto: cuáles se mueven

Comparando 60 s contra 5 min, con el pipeline de producción entero:

| | 60 s | 5 min | qué significa |
|---|---|---|---|
| identidades | 67 | 254 | ×3,8 al crecer ×5 el tramo → **~900 a 20 min** |
| observaciones de la mediana | 54 | **40,5** | los tramos largos NO dan identidades más largas: dan más trozos |
| identidades con ≥25 obs | 43 (64 %) | 141 (56 %) | pero en absoluto son ×3,3 → **~550 candidatas** |
| etiquetadas `staff` | 49 % | 63 % | crece: más trozos cortos y lejanos |
| tercer grupo (`otro`) | 2 identidades | 5 | el árbitro se parte en más trozos |

Qué hacer con cada parámetro calibrado en corto:

- **`staff.vel_max_lento: 2.75`** (velocidad media de TODA la identidad)
  — el miedo era que en 20 minutos un entrenador promediara más alto y
  se escapara de la rama lenta. **No aplica**: las identidades no se
  alargan, la mediana de observaciones incluso baja. Se queda.
- **`arbitro.min_observaciones: 25`** y **`agregacion.min_obs_para_otro:
  25`** — como fracción son más exigentes (64 % → 56 % de identidades
  pasan), pero en número absoluto habrá ~550 candidatas en vez de 43. La
  exclusividad `un_solo_arbitro` corona por evidencia (`n_obs ×
  distancia_relativa`) y su margen de 3,0× está medido sobre 43. **A
  mirar en el log**: el WARNING de `avisar_tercer_grupo` dirá cuántas
  quedan. Si el tercer grupo se llena, es ahí.
- **`staff.min_observaciones: 5`** — irrelevante a esta escala, ni se
  toca.
- **`agregacion.por_observacion.ventana_s: 1.5`** — está en segundos, no
  en fracción de tramo. Escala solo. Se queda.

Y lo que **no** se puede saber sin correrlo: si el fit único aguanta 20
minutos de cambio de luz. Ese es medio motivo de hacer la pasada.

---

# Las celdas

## Celda 1 — Entorno

```python
from google.colab import drive; drive.mount('/content/drive')
!git clone -b experimento/asociacion-global https://github.com/alexlpzz18/tactical-football-vision.git
%cd tactical-football-vision
!pip -q install ultralytics sahi supervision "numpy<2.1"

import os
os.makedirs('data/raw', exist_ok=True)
os.makedirs('models/weights', exist_ok=True)
D = '/content/drive/MyDrive/tactical'
# ⚠️ El nombre de DESTINO debe ser el que pide el config (rutas.video).
!ln -sf {D}/benja/benja_gredos_p1_20min.mp4  data/raw/benja_gredos_p1_20min.mp4
!ln -sf {D}/modelos/best_v4pre.pt            models/weights/best_v4pre.pt
!nvidia-smi --query-gpu=name,memory.total --format=csv
```

Si en tu Drive el vídeo o los pesos están en otra carpeta, se cambia
**aquí** y en ningún sitio más.

## Celda 2 — Comprobaciones que no gastan GPU

Todo lo que puede tirar la pasada en el minuto 0, comprobado en 10
segundos. **Si algo sale ✗, no sigas.**

```python
import os, shutil, cv2, yaml, numpy as np, sys
sys.path.insert(0, os.getcwd())
from src.tracking_data.processor import validar_config, _CLAVES_FULL, _rango_de_frames

CFG = 'configs/processor_benja_parte_entera.yaml'
cfg = yaml.safe_load(open(CFG))
ok = True
def chk(cond, msg):
    global ok
    ok &= bool(cond); print(('✓ ' if cond else '✗ ') + msg)

validar_config(cfg, _CLAVES_FULL); print('✓ config válida para modo full')
for clave in ('video', 'homografia'):
    p = cfg['rutas'][clave]; chk(os.path.exists(p), f'existe {clave}: {p}')
chk(os.path.exists(cfg['deteccion']['modelo']), f"existe el modelo: {cfg['deteccion']['modelo']}")

cap = cv2.VideoCapture(cfg['rutas']['video'])
chk(cap.isOpened(), 'el vídeo se abre')
n, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()
chk(abs(n/fps - 1200.1) < 5, f'duración {n/fps:.1f} s ({n/fps/60:.1f} min), esperado 1200,1')
chk((w, h) == (1920, 1080), f'resolución {w}×{h}')
print(f'  → frames a procesar: {int(n)//cfg["muestreo"]["sample_every"]}')
chk(_rango_de_frames(cfg['muestreo'], fps) == (0, None), 'tramo: null → vídeo ENTERO')

H = np.load(cfg['rutas']['homografia']); chk(H.shape == (3, 3), f'homografía {H.shape}')
chk(shutil.disk_usage('.').free/1e9 > 3, f"disco libre {shutil.disk_usage('.').free/1e9:.1f} GB (hacen falta ~0,5)")
import psutil; chk(psutil.virtual_memory().available/1e9 > 4,
                   f'RAM libre {psutil.virtual_memory().available/1e9:.1f} GB (el caché de colores pide ~0,5)')
chk(not os.path.exists(cfg['rutas']['cache']), 'el caché de salida NO existe todavía (no se pisa nada)')
print('\n' + ('TODO OK, sigue a la sonda.' if ok else '⚠️ ARREGLA LO DE ARRIBA ANTES DE SEGUIR.'))
```

## Celda 3 — Sonda de ritmo: cuánto va a tardar de verdad

**Esta es la celda que justifica el documento entero.** Procesa 60
segundos con el mismo modelo y el mismo SAHI, lo cronometra y
extrapola. Escribe en rutas de sonda, así que no toca nada.

```python
import time, yaml, copy, os
cfg_sonda = copy.deepcopy(yaml.safe_load(open(CFG)))
cfg_sonda['muestreo']['tramo'] = {'min_ini': 5.0, 'dur_seg': 60.0}
for k, v in (('cache','_sonda_det.pkl'), ('cache_colores','_sonda_col.pkl'),
             ('salida_csv','_sonda.csv'), ('salida_meta','_sonda.json')):
    cfg_sonda['rutas'][k] = 'data/tracking_benja/' + v
yaml.safe_dump(cfg_sonda, open('configs/_sonda.yaml','w'), sort_keys=False, allow_unicode=True)

t0 = time.time()
!python scripts/procesar_partido.py --config configs/_sonda.yaml
seg_60 = time.time() - t0

# El número de frames NO se supone: se lee del caché que acaba de salir.
from src.tracking.cache_io import cargar_cache
n_sonda = len(cargar_cache('data/tracking_benja/_sonda_det.pkl')['cache'])
n_total = 11988
ritmo = seg_60 / n_sonda
print(f'  sonda: {n_sonda} frames en {seg_60/60:.1f} min')
print(f'\n──────── SONDA ────────')
print(f'  {ritmo*1000:.0f} ms por frame')
print(f'  parte entera: {ritmo*n_total/60:.0f} min de GPU')
print(f'  caché de colores estimado: {os.path.getsize("data/tracking_benja/_sonda_col.pkl")/1e6*n_total/n_sonda:.0f} MB')
print('  → si pasa de ~70 min, NO lances la pasada entera: el caché se')
print('    escribe solo al final y una caída lo pierde todo. Avísame y')
print('    meto el checkpoint, o tira por tramos (configs/tramos_benja).')
```

## Celda 4 — La pasada entera

```python
import time
t0 = time.time()
!python scripts/procesar_partido.py --config configs/processor_benja_parte_entera.yaml
print(f'\nTardó {(time.time()-t0)/60:.1f} min')
```

⚠️ **No imprime nada hasta el final** (aviso 2). Que esté callada 40
minutos es lo normal, no es que se haya colgado. Y no cierres la pestaña.

Lo que **sí** hay que leer cuando acabe, en el log:

- `SIN PORTERO en el lado de ...` → lo esperado (aviso 1). Apunta la
  presencia que reporta: es el número con el que se recalibra.
- `TERCER GRUPO CON N IDENTIDADES` → si N es mucho mayor que 5, el
  catálogo arbitral está robando jugadores a esta escala.
- `Detección cacheada: N frames, M features` → N debe ser **11.988**.
  Si sale mucho menos, el lector se paró antes y el caché está cojo.

## Celda 5 — A Drive, INMEDIATAMENTE

No dejes esto para después de mirar resultados: mientras no esté en
Drive, sigue colgando de que la sesión no se caiga.

```python
!mkdir -p {D}/salidas
!cp data/tracking_benja/cache_detecciones_benja_p1.pkl {D}/salidas/
!cp data/tracking_benja/cache_colores_benja_p1.pkl     {D}/salidas/
!cp data/tracking_benja/posiciones_benja_p1.csv        {D}/salidas/
!cp data/tracking_benja/posiciones_benja_p1_meta.json  {D}/salidas/
!ls -lh {D}/salidas/
```

## Celda 6 — Control de sanidad antes de bajarlo

```python
import pickle
from src.tracking.cache_io import cargar_cache
d = cargar_cache('data/tracking_benja/cache_detecciones_benja_p1.pkl')
col = pickle.load(open('data/tracking_benja/cache_colores_benja_p1.pkl','rb'))
c = d['cache']
print(f"frames        {len(c):>7}   (esperado 11.988)")
print(f"detecciones   {sum(len(e['dets']) for e in c):>7}   (esperado ~225.000)")
print(f"features      {len(col):>7}")
print(f"t de {c[0]['t']:.1f} s a {c[-1]['t']:.1f} s   (esperado 0,0 → 1199,9)")
print(f"frame_idx de {c[0]['frame_idx']} a {c[-1]['frame_idx']}   (esperado 0 → 35.964)")
print(f"longitud de la feature: {len(next(iter(col.values())))}  (esperado 256)")
```

Los `frame_idx` son **globales del vídeo** y aquí arrancan en 0 (sin
`tramo` no hay desplazamiento). El GT del benjamín está indexado sobre
los frames globales del mismo vídeo, así que sigue casando.

---

## Cuando esté en local

El mismo config, sin GPU:

```bash
python scripts/procesar_partido.py --config configs/processor_benja_parte_entera.yaml --modo desde_cache
```

Bajar `cache_*_benja_p1.pkl` a `data/tracking_benja/`. Y lo primero que
hay que mirar, en este orden:

1. **¿Se abstuvo la regla del portero?** (aviso 1). Es la predicción
   concreta de este documento y la primera que hay que confirmar o
   tumbar.
2. **El fit único**: ¿los dos prototipos separan igual de bien en el
   minuto 19 que en el 1? Es medio motivo de la pasada.
3. **El replay**, que es lo que de verdad se ve.
