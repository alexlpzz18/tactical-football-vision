# Sesión de Colab: pose + los dos cronómetros (20-ago-2026)

Tres cosas en una sola pasada de GPU:

1. **¿Detecta RTMPose los tobillos en nuestros recortes?** Es el riesgo
   del anclaje por pose: se estima sobre el recorte, y en la banda lejana
   el recorte mide 13-20 px.
2. **Cronometrar el embedding** — el pendiente que bloquea llevar el
   perfil del v4 a producción.
3. **Cronometrar la pose**, por lo mismo, antes de comprometerse.

## Aviso de licencia, antes de nada

- **`rtmlib` es Apache-2.0** y no arrastra mmcv/mmpose/mmdet: solo numpy,
  opencv y onnxruntime. Cumple la regla (nada AGPL — por eso **no**
  YOLO-pose).
- **Pero la licencia de los PESOS no está declarada.** Salen de
  `download.openmmlab.com` y el modelo `body7` está entrenado con "7
  datasets" sin especificar cuáles.

→ Sirve para **experimentar** y decidir si el enfoque funciona. **Antes
de producción hay que resolver la procedencia o reentrenar**, igual que
con el checkpoint de GTA-Link.

## Celdas

**Celda 1 — entorno**

```python
from google.colab import drive; drive.mount('/content/drive')
%cd /content
!git clone https://github.com/<TU-USUARIO>/tactical-football-vision.git 2>/dev/null || (cd tactical-football-vision && git pull)
%cd /content/tactical-football-vision
!git checkout gt/identidad-benja && git pull
!pip -q install rtmlib onnxruntime-gpu transformers
!nvidia-smi --query-gpu=name,memory.total --format=csv
```

**Celda 2 — datos a disco LOCAL y comprobación antes de gastar GPU**

```python
import os, glob, shutil, time

RAIZ = "/content/drive/MyDrive/tactical-football-vision-data"

VIDEOS = {"/content/benja.mp4": f"{RAIZ}/videos/raw/benja_gredos_p1_20min.mp4"}
for local, origen in VIDEOS.items():
    if os.path.exists(local):
        print(f"ya estaba: {local} ({os.path.getsize(local)/1e9:.2f} GB)"); continue
    if not os.path.exists(origen):
        print(f"❌ NO existe en Drive: {origen}"); continue
    t = time.time(); shutil.copy(origen, local)
    print(f"copiado en {time.time()-t:.0f}s")

os.makedirs("data/tracking_benja", exist_ok=True)
os.makedirs("data/calibracion_benja", exist_ok=True)
!cp {RAIZ}/data/tracking_benja/cache_detecciones_benja_v4.pkl data/tracking_benja/ 2>/dev/null
!cp {RAIZ}/data/tracking_benja/cache_colores_benja_v4.pkl data/tracking_benja/ 2>/dev/null
!cp {RAIZ}/data/calibracion_benja/homografia_benja.npy data/calibracion_benja/ 2>/dev/null

faltan = [f for f in ("/content/benja.mp4",
                      "data/tracking_benja/cache_detecciones_benja_v4.pkl",
                      "data/calibracion_benja/homografia_benja.npy")
          if not os.path.exists(f)]
print(("❌ FALTAN: " + str(faltan)) if faltan else "✓ Todo en su sitio")
```

**Celda 3 — ¿encuentra los tobillos?**

```python
!python scripts/probar_pose.py \
    --config configs/processor_benja_emb.yaml \
    --video /content/benja.mp4 \
    --max-recortes 3000
```

Da el porcentaje de recortes con al menos un tobillo, **por franja de
tamaño (<20, 20-30, 30-45, >45 px) y por franja de profundidad**, más el
desfase mediano entre el tobillo y el borde inferior de la caja — que es
lo que dirá si la caja se queda corta y cuánto.

**Celda 4 — los dos cronómetros**

```python
!python scripts/cronometrar_embeddings.py \
    --config configs/processor_benja_emb.yaml \
    --video /content/benja.mp4 --max-recortes 4000
```

Separa **decodificar** (coste fijo, se paga igual), **recortar** e
**inferir**, y extrapola a un partido de 90 min. La pose se cronometra
sola en la celda 3.

## Qué mirar en los resultados

- **Si la pose encuentra tobillos en >80 % de los recortes >30 px pero se
  hunde por debajo de 20 px**, es el escenario esperado y toca el
  **híbrido**: pose donde se pueda, caja con la corrección por altura
  (0,129 × alto) donde no.
- **Si el desfase tobillo–caja es positivo y consistente**, confirma que
  el borde de la caja se queda corto y cuantifica el sesgo que la pose
  vendría a corregir.
- **Si la pose añade más minutos de GPU que la decodificación**, deja de
  ser gratis y hay que decidir si compensa con el temblor que ahorre.

La línea base contra la que comparar está en `docs/gt_identidad_benja.md`:
temblor crudo de **0,10 / 0,14 / 0,20 m** por franja de profundidad.
