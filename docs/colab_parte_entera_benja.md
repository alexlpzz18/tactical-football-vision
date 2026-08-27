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

## Aviso 1 — La regla del portero: ARREGLADO (26-ago-2026)

Este era el problema de verdad, y no era una predicción: **ya fallaba en
el piloto de 5 minutos**, con el portero delante pisando el área el 88 %.

`min_presencia: 0.50` pedía que la identidad coronada estuviera presente
en más de la mitad **del tramo**. Pero el portero no es una identidad:

| lado | 60 s | 5 min |
|---|---|---|
| bajo | id 24 — **87 %** | id 24 — **49 %** (+ 225, 139, 162, 173) |
| alto | id 8 — 100 % | id 90 66 % · id 8 26 % |

Los cinco trozos del lado bajo viven en el mismo metro cuadrado
—(7,2 · 20,4), (8,3 · 20,3), (6,5 · 23,7), (6,9 · 23,0), (6,6 · 24,4)—
y **solapan cero frames entre sí**: son la misma persona, uno detrás de
otro. Y el GT de Villaviciosa lo confirma sin ambigüedad: los ids 16 y
37 son **los dos el `obj 1`**, el mismo portero_B.

**La regla ahora corona al CONJUNTO** y mide la presencia de la UNIÓN de
sus frames. Con una restricción física añadida: un fragmento presente en
los MISMOS frames que otro ya coronado no es su continuación, es el
portero detectado dos veces, y coronar los dos lo metía dos veces en el
centroide de su equipo (medido en Villaviciosa: +0,86 m antes de añadir
la restricción; con ella, 0,00).

Lo que se midió (`scripts/adoptar_portero_conjunto.py`), centroide
mediano contra el GT:

| pata | antes | ahora |
|---|---|---|
| benja 60 s | 1,30 m | **1,30 m** (idéntico) |
| benja 5 min | 5,30 m | **1,25 m** |
| Villaviciosa 60 s | 4,49 m | **4,49 m** (idéntico) |

Y lo que importaba de verdad, que es **la invariancia a la escala**:
antes la misma regla daba 1,30 m a 60 s y 5,30 m a 5 min — se degradaba
4× solo por alargar el tramo. Ahora da 1,30 y 1,25. Caso negativo: 4 de
4 en las dos patas (borrado el portero del caché, se abstiene en su
lado). Detalle en `docs/portero.md`.

## Aviso 2 — El caché a medias: ARREGLADO (26-ago-2026)

Antes, `procesar_full` acumulaba todo en RAM y el `pickle.dump` estaba
**después** del bucle: una caída en el minuto 55 de una pasada de 60 lo
perdía todo, y como el log también estaba fuera del bucle, la celda no
imprimía nada en 45-60 minutos.

Ahora, con `checkpoint: {cada_frames: 500, reanudar: true}` en el config:

- **Vuelca cada 500 frames procesados**, de forma atómica (temporal +
  rename): o está el checkpoint anterior o está el nuevo, nunca medio
  fichero. Coste medido: ~2,8 s por volcado con el caché lleno, ~0,6 min
  en toda la pasada.
- **Reanuda solo**. Si vuelves a lanzar la celda, arranca donde lo dejó.
- **Se niega a reanudar sobre otra configuración de detección.** El
  checkpoint guarda una firma (vídeo, modelo, confianza, SAHI, k1/k2,
  sample, tramo); si no coincide, avisa y lo rehace. Mezclar dos
  detectores en un mismo caché es peor que perder la pasada — los
  umbrales van pegados al detector.
- **Imprime progreso** en cada volcado: frames hechos, porcentaje,
  ms/frame y minutos que faltan.

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
RAIZ = '/content/drive/MyDrive/tactical-football-vision-data'

# ⚠️ El nombre de DESTINO debe ser el que pide el config (rutas.video y
# deteccion.modelo), no el que tenga en Drive.
# ⚠️ El modelo es best_v4pre, NO best_v4: el v4 no está adoptado (mejora
# el mAP pero no la asociación, y su caja de cambios es otra).
!ln -sf {RAIZ}/videos/raw/benja_gredos_p1_20min.mp4  data/raw/benja_gredos_p1_20min.mp4
!ln -sf {RAIZ}/best_v4pre.pt                         models/weights/best_v4pre.pt
!nvidia-smi --query-gpu=name,memory.total --format=csv
```

La homografía del benjamín (`data/calibracion_benja/homografia_benja.npy`)
**sí viene en el repo**, comprobado con `git ls-files`; el vídeo y los
pesos no, por eso los enlaces. Si mueves algo en Drive, se cambia
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
if os.path.exists(cfg['rutas']['cache']):
    import pickle
    from src.tracking_data.processor import _firma_de_deteccion
    prev = pickle.load(open(cfg['rutas']['cache'], 'rb'))
    misma = prev.get('firma') == _firma_de_deteccion(cfg)
    print(('✓ ' if misma else '⚠️ ') + f"ya hay un caché de {len(prev.get('cache', []))} frames: "
          + ('se REANUDA' if misma and not prev.get('completo')
             else 'se SOBRESCRIBE (completo)' if misma else 'se SOBRESCRIBE (otra config)'))
else:
    print('✓ no hay caché previo: pasada desde cero')
print('\n' + ('TODO OK, sigue a la sonda.' if ok else '⚠️ ARREGLA LO DE ARRIBA ANTES DE SEGUIR.'))
```

## Celda 3 — Sonda de ritmo: cuánto va a tardar de verdad

**Esta es la celda que justifica el documento entero.** Procesa 600
frames con el mismo modelo y el mismo SAHI y saca el ritmo real.

Dos detalles que la hacen honesta y que costaron una lectura del código:

1. **Sin `tramo`, con `max_frames`.** Un tramo que empiece en el minuto 5
   obliga a `posicionar_en_frame` a decodificar hasta allí, y eso son 27 s
   en este vídeo (está medido en su propio docstring). Arrancando en el
   frame 0 no hay salto, y además es el mismo camino que recorre la
   pasada entera.
2. **El ritmo se lee del LOG, no del reloj de pared.** El procesador ya
   imprime sus propios ms/frame cronometrados *después* de cargar el
   modelo, así que ese número no lleva dentro los ~20 s de arranque de
   YOLO+SAHI. Sale por **stderr**, de ahí el `2>&1`.

```python
import time, yaml, copy, os, re
cfg_sonda = copy.deepcopy(yaml.safe_load(open(CFG)))
cfg_sonda['muestreo'].pop('tramo', None)       # arranca en el frame 0: sin salto de lector
cfg_sonda['muestreo']['max_frames'] = 1800     # 1800 / sample 3 = 600 frames procesados
cfg_sonda['checkpoint'] = {'cada_frames': 500, 'reanudar': False}
for k, v in (('cache','_sonda_det.pkl'), ('cache_colores','_sonda_col.pkl'),
             ('salida_csv','_sonda.csv'), ('salida_meta','_sonda.json')):
    cfg_sonda['rutas'][k] = 'data/tracking_benja/' + v
yaml.safe_dump(cfg_sonda, open('configs/_sonda.yaml','w'), sort_keys=False, allow_unicode=True)

t0 = time.time()
salida = !python scripts/procesar_partido.py --config configs/_sonda.yaml 2>&1
reloj = time.time() - t0
print('\n'.join(salida[-15:]))

from src.tracking.cache_io import cargar_cache
n_sonda = len(cargar_cache('data/tracking_benja/_sonda_det.pkl')['cache'])
n_total = 11988
medidos = re.findall(r'([\d.]+) ms/frame', '\n'.join(salida))
ritmo = float(medidos[-1])/1000 if medidos else reloj/n_sonda   # log si lo hay, reloj si no

print(f'\n──────── SONDA ────────')
print(f'  {n_sonda} frames en {reloj:.0f} s de reloj')
print(f'  {ritmo*1000:.0f} ms/frame ({"del log" if medidos else "del reloj, INFLADO por la carga del modelo"})')
print(f'  → parte entera: {ritmo*n_total/60:.0f} min de GPU')
mb = os.path.getsize('data/tracking_benja/_sonda_col.pkl')/1e6*n_total/n_sonda
print(f'  → caché de colores: ~{mb:.0f} MB (lo esperado son ~467)')
print('\n  Con el checkpoint puesto, una caída ya no cuesta la pasada:')
print('  relanzas la celda 4 y sigue donde lo dejó.')
```

## Celda 4 — La pasada entera

```python
import time
t0 = time.time()
!python scripts/procesar_partido.py --config configs/processor_benja_parte_entera.yaml
print(f'\nTardó {(time.time()-t0)/60:.1f} min')
```

Ahora imprime una línea de progreso cada 500 frames con los minutos que
faltan (aviso 2). Si la sesión se cae, **vuelve a lanzar esta misma
celda**: reanuda donde lo dejó.

Lo que **sí** hay que leer cuando acabe, en el log:

- `Portero de X: N fragmento(s) [...]` → lo esperado. Si en vez de eso
  sale `SIN PORTERO en el lado de ...`, el arreglo del aviso 1 no ha
  aguantado los 20 minutos y hay que mirarlo antes de seguir.
- `TERCER GRUPO CON N IDENTIDADES` → si N es mucho mayor que 5, el
  catálogo arbitral está robando jugadores a esta escala.
- `Detección cacheada: N frames, M features` → N debe ser **11.988**.
  Si sale mucho menos, el lector se paró antes y el caché está cojo.

## Celda 5 — A Drive, INMEDIATAMENTE

No dejes esto para después de mirar resultados: mientras no esté en
Drive, sigue colgando de que la sesión no se caiga.

```python
!mkdir -p {RAIZ}/salidas
!cp data/tracking_benja/cache_detecciones_benja_p1.pkl {RAIZ}/salidas/
!cp data/tracking_benja/cache_colores_benja_p1.pkl     {RAIZ}/salidas/
!cp data/tracking_benja/posiciones_benja_p1.csv        {RAIZ}/salidas/
!cp data/tracking_benja/posiciones_benja_p1_meta.json  {RAIZ}/salidas/
!ls -lh {RAIZ}/salidas/
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

1. **¿Cuántos fragmentos coronó por lado?** (aviso 1). Sobre 20 minutos
   deberían ser más que los 5 y 2 del piloto. Si coronó 0, la regla se
   ha vuelto a romper a esta escala.
2. **El fit único**: ¿los dos prototipos separan igual de bien en el
   minuto 19 que en el 1? Es medio motivo de la pasada.
3. **El replay**, que es lo que de verdad se ve.
