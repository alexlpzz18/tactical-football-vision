# ¿Se está comiendo jugadores el postproceso de SAHI? (celdas de Colab)

BACKLOG 19. El mecanismo está demostrado sobre el balón
(`docs/sahi_balon.md`): `get_sliced_prediction` fusiona con `GREEDYNMM` y
métrica **`IOS`**, y una caja grande que contiene a otra pequeña da
IOS = 1,00 con un IoU real de 0,006. La fusión se queda con la
**confianza de la pequeña y la geometría de la grande**.

El detector de jugadores usa el mismo camino
(`src/tracking_data/processor.py:721`, sin parámetros de postproceso, o
sea los defaults).

## ⚠️ Antes de lanzar: lo que ya está medido EN LOCAL y acota el resultado

**El detector NO se queda corto de cajas.** Sobre la parte entera:
**17,6 detecciones por frame** de media (mediana 18, p10 14, p90 21),
cuando en un fútbol 7 hay 14 jugadores + 2 porteros = 16 personas en
campo, 17 con el árbitro.

O sea que **el recuento corto (5-6 contra 7-8) no puede nacer en la
detección**: hay cajas de sobra. Nace después — tracking, clasificación de
equipos o la forma de contar.

Eso NO cierra esta prueba, porque 17,6 cajas no garantiza que sean las 16
correctas: puede haber banquillo y público dentro mientras falta un
jugador del campo. Lo que hace es **cambiar la expectativa**: si el
experimento sale positivo, el efecto será de orden 0,5 jugadores por
frame, no de 2.

### Dos huellas locales que NO sirvieron (negativos)

1. **Cajas gigantes.** Para el balón, lo que se lo traga es una caja
   absurda. Para un jugador es la caja de **otro jugador**, perfectamente
   plausible: la absorción es invisible en el tamaño. Medido: solo el
   0,16 % de las cajas implican más de 2,5 m de altura.
2. **"No deberían quedar pares anidados".** Falso, y el error fue mío:
   **GreedyNMM es greedy, no exhaustivo** — consume la caja de mayor score,
   fusiona lo que casa con ella y la saca del conjunto, así que un par
   anidado entre dos cajas ya consumidas sobrevive. En el caché quedan
   5.851 pares con IOS > 0,5 (0,49 por frame), y reaplicar el postproceso
   al propio caché le quita **otro 2,9 %**. Su presencia no prueba nada.

Por eso hace falta GPU: el caché solo tiene el DESPUÉS.

## Las celdas

Sobre el entorno de siempre (`docs/colab_parte_entera_benja.md` para el
montaje de Drive y el clon del repo).

### 1. Un tramo corto y las dos métricas

```python
!python - <<'PY'
import sys, pickle, yaml, cv2, numpy as np
sys.path.insert(0, ".")
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

CFG = "configs/processor_benja_parte_entera.yaml"
cfg = yaml.safe_load(open(CFG))
det = cfg["deteccion"]
modelo = AutoDetectionModel.from_pretrained(
    model_type="ultralytics", model_path=det["modelo"],
    confidence_threshold=det["confianza"], device="cuda")

cap = cv2.VideoCapture(cfg["rutas"]["video"])
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
sh, sw = h // det["sahi"]["filas"], w // det["sahi"]["columnas"]
sol = det["sahi"]["solape"]

# 300 frames repartidos por los 20 min, no los 300 primeros: el juego
# cambia de zona y los primeros minutos son OTRO RÉGIMEN (CLAUDE.md).
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
objetivo = set(np.linspace(0, total - 1, 300).astype(int))

filas = []
idx = 0
while objetivo:
    ok, frame = cap.read()
    if not ok: break
    if idx in objetivo:
        objetivo.discard(idx)
        r_ios = get_sliced_prediction(frame, modelo, slice_height=sh, slice_width=sw,
                                      overlap_height_ratio=sol, overlap_width_ratio=sol,
                                      verbose=0)
        r_iou = get_sliced_prediction(frame, modelo, slice_height=sh, slice_width=sw,
                                      overlap_height_ratio=sol, overlap_width_ratio=sol,
                                      postprocess_match_metric="IOU", verbose=0)
        filas.append((idx,
                      [(*p.bbox.to_xyxy(), p.score.value) for p in r_ios.object_prediction_list],
                      [(*p.bbox.to_xyxy(), p.score.value) for p in r_iou.object_prediction_list]))
    idx += 1
cap.release()
pickle.dump(filas, open("/content/ios_vs_iou.pkl", "wb"))
n_ios = np.mean([len(f[1]) for f in filas]); n_iou = np.mean([len(f[2]) for f in filas])
print(f"frames: {len(filas)}")
print(f"  IOS (producción hoy): {n_ios:.2f} detecciones/frame")
print(f"  IOU                 : {n_iou:.2f} detecciones/frame   ({n_iou-n_ios:+.2f})")
PY
```

**Cómo leerlo.** Si `IOU` no sube, la vía está cerrada y no hace falta
nada más. Si sube, **no adoptar todavía**: más detecciones no es mejor,
puede ser una caja grande partida en dos. Pasa a la celda 2.

### 2. El control: ¿son jugadores de verdad los recuperados?

```python
!python - <<'PY'
import sys, pickle, yaml, numpy as np
sys.path.insert(0, ".")
from src.tracking.plausibilidad_fisica import escalas_locales

cfg = yaml.safe_load(open("configs/processor_benja_parte_entera.yaml"))
H = np.load(cfg["rutas"]["homografia"])
filas = pickle.load(open("/content/ios_vs_iou.pkl", "rb"))

def alto_m(caja):
    x1, y1, x2, y2 = caja[:4]
    lat, _ = escalas_locales(H, (x1 + x2) / 2, y2)
    return (y2 - y1) * lat

def casa(a, b, tol=6.0):
    return abs((a[0]+a[2])/2 - (b[0]+b[2])/2) < tol and abs(a[3] - b[3]) < tol

nuevos, altos = 0, []
for _idx, ios, iou in filas:
    for c in iou:
        if not any(casa(c, d) for d in ios):
            nuevos += 1
            altos.append(alto_m(c))
altos = np.array(altos)
print(f"cajas que IOU recupera y IOS no tenía: {nuevos} "
      f"({nuevos/len(filas):.2f} por frame)")
if len(altos):
    print(f"  altura implícita: p10 {np.percentile(altos,10):.2f} m · "
          f"mediana {np.median(altos):.2f} · p90 {np.percentile(altos,90):.2f}")
    plausibles = ((altos > 1.0) & (altos < 2.2)).mean()
    print(f"  con altura de PERSONA (1,0-2,2 m): {100*plausibles:.0f} %")
    print("  ← si esto es bajo, IOU está añadiendo basura, no jugadores")
PY
```

### 3. Si los dos anteriores salen bien: el banco

Solo entonces, y contra **las dos patas**. El control que manda: **los
frames donde el recuento YA era correcto no pueden empeorar**.

```python
!python scripts/evaluar_tracking.py --config configs/processor_benja_parte_entera.yaml
```

## Criterio de adopción

1. `IOU` recupera detecciones **y** el 80 %+ tienen altura de persona.
2. El recuento por equipo se acerca a 7-8 sin pasarse.
3. Ningún frame que ya cuadraba empeora.
4. El banco no se degrada en ninguna de las dos patas.

Si falla cualquiera, se documenta el negativo y se cierra: es un
parámetro, no un modelo, así que el coste de dejarlo como está es cero.
