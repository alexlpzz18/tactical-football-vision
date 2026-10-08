# Ablación 1/3 contra 1/1 — SOLO PREPARADA (8-oct-2026)

Hoy el caché procesa 1 de cada 3 frames (≈ 10 por segundo). La pregunta es si procesarlos todos
mejora la asociación lo bastante como para pagar ×3 de GPU. **Nada de esto se ha lanzado.** El
criterio está en `scripts/ablacion_muestreo.py::CRITERIO` y se commitea antes de que exista el
caché 1/1.

Fuera de alcance a propósito: ni tracking en metros (ya perdió) ni capa de identidad con roster
(identidad individual, aparcada).

## 1. Inventario: qué está en frames y qué en segundos

`python scripts/ablacion_muestreo.py inventario` lo imprime. Solo cuenta lo que corre en
producción (perfil `bytetrack`) o lo que decide una etiqueta. Con la convención de hoy, 1 muestra
= 0,1 s (dt = 3 / 29,97).

| parámetro | unidad hoy | a 1/1 | qué se hace |
|---|---|---|---|
| `bytetrack.buffer_perdido_s` (2 s) | segundos | igual | nada |
| `bytetrack.usar_fps_efectivo` | se adapta | igual | nada |
| `bytetrack.min_frames_consecutivos` (1) | frames | 1 = sin requisito | nada |
| `bytetrack.umbral_emparejamiento` (0,995) | 1−IoU **por paso** | las cajas se solapan más | no es una unidad: es parte de lo que se mide |
| filtro de Kalman de supervision | **por paso**, sin dt | 3× pasos | irreducible: es el efecto que se quiere medir |
| `cosido_pureza` max_hueco, tol_por_seg, v_max_salto | s, m/s | igual | nada |
| `cosido_pureza.solape_max_frames` (0) | frames | cero es cero | nada |
| **`cosido_pureza._velocidad_final(ventana=3)`** | **3 muestras, escrito en el código** | 0,3 s → 0,1 s | **×3 en la ablación** (parche en el script, no en producción) |
| `escalado_resolucion.jitter_px` (3,5) | px por paso, **medido a 1/3** | puede cambiar | **re-medir a 1/1** con el mismo método antes de correr (paso 3) |
| `suavizado.ventana_s` (0,5) | segundos | igual | nada |
| suavizado: tope de 61 muestras | muestras, en el código | 6,1 s → 2,0 s | comprobar si llega a tocarse (con la ventana base de 15 muestras a 1/1, hace falta un factor de resolución > 3) |
| `interpolacion` max_hueco, hueco_min | s | igual | nada |
| consolidación y corte de velocidad | frames | — | no corren con `bytetrack` |
| `puerta_reentrada.min_obs_firma` | obs | — | la puerta está apagada |
| `agregacion.por_observacion.ventana_s` (1,5) | s | igual | nada |
| **`agregacion.min_obs_para_otro`** (25) | obs = 2,5 s | 0,83 s | **×3 → 75** |
| **`staff.min_observaciones`** (5) | obs = 0,5 s | 0,17 s | **×3 → 15** |
| **`staff.min_obs_lento`** (25) | obs = 2,5 s | 0,83 s | **×3 → 75** |
| **`arbitro.min_observaciones`** (25) | obs = 2,5 s | 0,83 s | **×3 → 75** |
| `entrenamiento.min_features` (300) | recortes | se alcanza antes | nada: es un tamaño de muestra, no un tiempo |
| `porteros.min_frames_nuevos` (0,50) | fracción | igual | nada |
| 25 en `avisar_tercer_grupo`, 100 en `arbitro` | obs, en el código | — | solo deciden un aviso del log, no una etiqueta |

La conversión la aplica `convertir_configs()` sobre una copia del YAML. **Producción no se toca.**
Si 1/1 se adoptara, antes habría que pasar a segundos de verdad los cuatro recuentos y la ventana de
`_velocidad_final`. Comprobación de seguridad para ese día: a 1/3, el CSV tiene que salir idéntico
byte a byte.

## 2. La comparación

**Tramo**: el piloto de 5 min, de 5:00 a 10:00 de archivo (de 6:33 a 11:33 del reproductor),
frames 8991-17981. Contiene la ventana del GT (de 5:25 a 5:55 de archivo, de 6:58 a 7:28 del
reproductor).

**Un solo caché 1/1 de Colab, y de él salen los cuatro brazos.** El 1/3 no se reutiliza del caché
viejo, sino que se submuestrea del 1/1: mismo detector, misma versión, mismos frames. Así la única
diferencia entre brazos es el muestreo.

- **1/1**: los 8.991 frames, con los parámetros convertidos a segundos.
- **1/3, fase 0, 1 y 2**: los frames con `f % 3 == fase`, con los parámetros de hoy. La fase 0 son
  exactamente los frames de producción.

**Control de ruido** (lo que pidió Alex): las tres fases son tres corridas «iguales» que solo
cambian qué frames ven. **El ruido de cada métrica es el rango (máx − mín) de las tres fases.**
Repetir la misma corrida dos veces no vale: el pipeline es determinista desde el caché y daría
ruido 0 (`docs/suelo_de_ruido.md`). En las fases 1 y 2 los frames del GT no están en el caché: se
evalúa en el más cercano, a 33 ms, donde un jugador a 7 m/s se mueve 0,23 m.

**Métricas** (`metricas_de()`, ya probada sobre el 1/3 de hoy, abajo):

| métrica | de dónde | dirección |
|---|---|---|
| embudo: detecciones en campo por frame | caché | **control: tiene que salir IGUAL** (mismo detector) |
| faltan / sobran por equipo y frame | `cuenta_de_recuento` del desglose, radio 2 m, filas reales | menos es mejor |
| fragmentaciones | `calcular_metricas_tracking` (propia, 2 m) | menos |
| identidades por persona | casado 1-a-1 a 2 m, ids distintos por persona del GT | menos |
| quimeras | identidades casadas con ≥ 2 personas, la segunda en ≥ 3 frames | menos |
| DetA, AssA, IDF1 | TrackEval, cajas sintéticas de 2 m | más |

**Prueba del banco sobre el 1/3 de hoy** (`ablacion_muestreo.py prueba`, sin GPU): 13,72
detecciones en campo por frame; **faltan 0,758 y sobran 0,842 por equipo y frame (las cifras del
desglose, 0,76 y 0,84)**; 45 fragmentaciones; 3,07 identidades por persona; 10 quimeras;
DetA 0,329; AssA 0,259; IDF1 0,354.

## 3. Criterio de adopción (fijado antes)

Δ = valor de 1/1 − media de las tres fases; cuenta solo si |Δ| > ruido.

1. **Control**: las detecciones en campo por frame tienen que salir iguales (|Δ| ≤ ruido + 0,10).
   Si no, el banco está roto: **NO CONCLUYENTE**.
2. **Ninguna métrica empeora** más que el ruido.
3. **Los faltantes bajan** más que el ruido. Es lo que motivaría el cambio: el 41 % del error del
   centroide.
4. **Y al menos una de DetA, AssA o IDF1 sube** más que el ruido.

Aunque pase, se adopta solo con el OK de Alex, porque cuesta ×3 de GPU y ×3 de disco (el caché de
colores, de ~117 MB a ~350 MB por cada 5 minutos).

## 4. Pasos

1. **Colab** (celdas abajo, **sin lanzar**): el caché 1/1 del tramo, con checkpoint en Drive.
2. **Local**: control del detector. En los frames de la fase 0, las cajas del caché 1/1 contra las
   del `cache_detecciones_benja_piloto5min.pkl` de hoy. Si no coinciden, el detector o la versión
   de SAHI han cambiado, y se dice antes de seguir.
3. **Local**: re-medir `jitter_px` a 1/1 con el método de `docs/experimentos_tracking.md` (residuo
   del pie respecto a un ajuste lineal local; √2 × rms). Si difiere, el brazo 1/1 usa el medido.
4. **Local**: `ablacion_muestreo.py correr` (4 pasadas de ~25 s) y `medir`.

## 5. Celdas de Colab — NO LANZADAS

Antes, en Drive: `MyDrive/tactical/benja/partido_benja.mp4` y `MyDrive/tactical/modelos/best_v4pre.pt`
(los de `docs/sesion_colab_completa.md`). Hace falta GPU (T4 basta).

**Celda 1 — entorno**
```python
from google.colab import drive; drive.mount('/content/drive')
!git clone -b experimento/asociacion-global https://github.com/alexlpzz18/tactical-football-vision.git
%cd tactical-football-vision
!pip -q install ultralytics sahi supervision "numpy<2.1" "scipy<1.14"
import os
D = '/content/drive/MyDrive/tactical'
os.makedirs('data/raw', exist_ok=True); os.makedirs('models/weights', exist_ok=True)
!ln -sf {D}/benja/partido_benja.mp4 data/raw/benja_gredos_p1_20min.mp4
!ln -sf {D}/modelos/best_v4pre.pt   models/weights/
# Los checkpoints van DIRECTOS a Drive: si se corta la sesión, no se pierden.
!mkdir -p {D}/ablacion_1a1 && rm -rf data/ablacion_1a1 && ln -s {D}/ablacion_1a1 data/ablacion_1a1
!nvidia-smi --query-gpu=name,memory.total --format=csv
import cv2; cap = cv2.VideoCapture('data/raw/benja_gredos_p1_20min.mp4')
print(cap.isOpened(), cap.get(cv2.CAP_PROP_FRAME_COUNT))   # True y ~35.960; si no, PARA
```

**Celda 2 — cronómetro con 120 frames (antes de comprometer la sesión)**
```python
import yaml
c = yaml.safe_load(open('configs/processor_benja_piloto5min_1a1.yaml'))
c['muestreo']['max_frames'] = 120
c['checkpoint']['cada_frames'] = 0
for k in ('cache', 'cache_colores', 'salida_csv', 'salida_meta'):
    c['rutas'][k] = '/content/prueba_' + os.path.basename(c['rutas'][k])
yaml.safe_dump(c, open('/content/prueba.yaml', 'w'))
!python scripts/procesar_partido.py --config /content/prueba.yaml 2>&1 | grep -E "ms/frame|frames|Error|Traceback"
# ms/frame × 8.991 = lo que tardará la celda 3. Si pasa de ~2,5 h, se parte en dos tramos
# (scripts/planificar_tramos.py + fusionar_caches.py) en vez de arriesgar la sesión.
```

**Celda 3 — el caché 1/1 (reanudable: si se corta, se vuelve a ejecutar la celda 1 y esta)**
```python
!python scripts/procesar_partido.py --config configs/processor_benja_piloto5min_1a1.yaml 2>&1 | grep -vE "^INFO.*detecciones$"
```

**Celda 4 — comprobar antes de bajar nada**
```python
import pickle
d = pickle.load(open('data/ablacion_1a1/cache_detecciones_benja_piloto5min_1a1.pkl', 'rb'))
f = [e['frame_idx'] for e in d['cache']]
print('sample', d['sample'], '(debe ser 1) · completo', d.get('completo'),
      '· frames', len(f), f[0], f[-1], '(debe ser 8991, 8991-17981)')
c = pickle.load(open('data/ablacion_1a1/cache_colores_benja_piloto5min_1a1.pkl', 'rb'))
print('colores', len(c), '· detecciones', sum(len(e['dets']) for e in d['cache']))
!ls -lh {D}/ablacion_1a1/
```

**Qué bajas a local**: los dos `.pkl` de `MyDrive/tactical/ablacion_1a1/` a `data/ablacion_1a1/`
(~20 MB y ~350 MB; comprobar `df` antes). El CSV de Colab no hace falta: las pasadas se repiten en
local con el código de la rama.
