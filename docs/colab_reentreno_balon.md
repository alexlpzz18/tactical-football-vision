# Reentreno del balón: etiquetado en CVAT y comprobaciones previas (3-oct-2026)

Plan y criterio: `docs/plan_reentreno_balon.md`. **Nada se entrena hasta que Alex diga
que ha terminado de etiquetar.**

## 1. Etiquetar en CVAT (Alex)

En `outputs/pool_balon_pegado/` (lo genera `scripts/preparar_pool_balon_pegado.py`):

| tarea | imágenes | carpeta | preanotación |
|---|---|---|---|
| train | 117 (102 de entrenamiento + 15 de VALIDACIÓN, minutos 13 y 19) | `train/images/` | `cvat_train_preanotaciones_coco.zip` |
| test | 36 (minutos 0, 9, 10 y 17) | `test/images/` | `cvat_test_preanotaciones_coco.zip` |

Para cada tarea, por separado:

1. Crear tarea con UNA etiqueta, `balon` (rectángulo), y subir todas las imágenes de su
   carpeta `images/` (arrastrándolas; no hace falta zip, y un zip duplicaría ~400 MB).
2. *Acciones → Subir anotaciones → COCO 1.0* → el zip de preanotación: una caja
   pre-puesta por imagen donde el sistema cree que está el balón.
3. En cada imagen: ajustar la caja al balón visible (aunque esté medio tapado, cubre lo
   que se VE); moverla si el balón está en otro sitio; **borrarla si el balón no se
   ve** (la imagen queda como ejemplo sin balón).
4. *Acciones → Exportar dataset de la tarea → YOLO 1.1*, SIN imágenes. Los dos zips a
   `outputs/pool_balon_pegado/etiquetado/` como `train_yolo.zip` y `test_yolo.zip`.

Tiempo estimado: 35-50 min las 153, más ~10 min de crear las tareas y exportar.

Al terminar, se cuenta antes de entrenar:
```bash
python scripts/contar_etiquetado_pool.py --train outputs/pool_balon_pegado/etiquetado/train_yolo.zip --test outputs/pool_balon_pegado/etiquetado/test_yolo.zip
```
Dice positivos y negativos por split, avisa si los negativos pasan de la mitad del pool
o si el test tiene menos de 12 positivos, y reescribe el criterio 1 en balones.

## 2. Comprobaciones previas en Colab (sin entrenar)

Celda 0, la de siempre (`docs/colab_balon_umbral_bajo.md`), con
`D = '/content/drive/MyDrive/tactical-football-vision-data'`.

**De qué minutos sale el dataset original de v1** (799 frames del benjamín):
```python
!python scripts/colab_comprobaciones_reentreno.py minutos \
    --imagenes-zip "{D}/balon_benja_frames.zip" \
    --etiquetas-zip "{D}/balon_benja_labels..zip"
```
Imprime nombres de ejemplo, imágenes por minuto y cuántas caen en los minutos de test
(0, 9, 10, 17) y de validación (13, 19). ⚠️ Suponer que el número del nombre es el
frame es una hipótesis: se comprueba con los nombres de ejemplo. Si los nombres no dan
un frame, PARA y lo dice. Con `--manifiesto` (el `manifiesto.csv` del pool subido a
Drive) dice además qué frames del test están EXACTOS en el dataset original.

**La augmentation conserva el balón (≥ 95 %)**, con los valores de
`configs/entrenamiento_balon.yaml`:
```python
!python scripts/colab_comprobaciones_reentreno.py augmentacion \
    --imagenes-zip "{D}/balon_benja_frames.zip" \
    --etiquetas-zip "{D}/balon_benja_labels..zip" \
    --salida "{D}/salidas/reentreno_prev"
```
Mide SIN mosaico (la regla: un mosaico de cuatro imágenes taparía la pérdida de una) y,
como dato, con el mosaico de entrenamiento. Deja 12 imágenes aumentadas con su caja.

Tráeme las dos salidas de texto (y si quieres, las 12 imágenes).

## 3. Medida fina de la augmentation y cruce con el original (5-oct-2026)

Con el repo actualizado en Colab (`git pull`) y el paquete del pool subido a Drive como
`{D}/paquete_pool_yolo.zip` (69,5 MB, `scripts/empaquetar_pool_balon.py`; sin el test).

**Qué significa "conserva"**: que ultralytics no descarte la caja tras transformarla. La
descarta si, a la resolución de la red, mide ≤ 2 px de ancho o de alto, si tras recortarla
por el borde le queda < 10 % de su área o si su proporción pasa de 100. Cada caja perdida se
separa en: `fuera` (la traslación la sacó de la imagen: negativo CORRECTO), `recortado`
(asoma < 10 %) o `pequeno` (visible pero ≤ 2 px). Sin mosaico solo mueven cajas `scale` y
`translate`: la atribución es escala sola, traslación sola y ninguna (control).

## 4. Celda de entrenamiento — NO LANZAR hasta decidirlo

Lee `configs/entrenamiento_balon.yaml` (bloque `reentreno`) y **se niega a entrenar** mientras
`augmentation_medida` sea `false`. El split del original es el MISMO código de v1
(`notebooks/entrenamiento_balon_v1.ipynb`: semilla 42, 20 % a validación). ⚠️ Depende del
orden en que `glob` devuelva los ficheros tras descomprimir: es lo más parecido a v1 que se
puede reconstruir, no una garantía de que sea idéntico.

```python
import glob, os, random, shutil, yaml, zipfile
from pathlib import Path
from ultralytics import YOLO

D = "/content/drive/MyDrive/tactical-football-vision-data"
MODELO_V1 = f"{D}/best_balon_v1.pt"   # la de docs/colab_balon_umbral_bajo.md; si no está, para
cfg = yaml.safe_load(open("configs/entrenamiento_balon.yaml"))
r = cfg["reentreno"]
assert r["augmentation_medida"], "la augmentation aún no está medida: NO se entrena"
assert Path(MODELO_V1).exists(), MODELO_V1

W = Path("/content/ds_reentreno")
if W.exists(): shutil.rmtree(W)
# ── el original, con el split de v1 ──
!unzip -q -o "{D}/balon_benja_labels..zip" -d /content/labels_balon
!unzip -q -o "{D}/balon_benja_frames.zip" -d /content/frames_balon
imgs = {os.path.splitext(os.path.basename(p))[0]: p
        for p in glob.glob("/content/frames_balon/**/*.jpg", recursive=True)}
txts = {os.path.splitext(os.path.basename(p))[0]: p
        for p in glob.glob("/content/labels_balon/**/*.txt", recursive=True)
        if os.path.basename(p) not in ("train.txt", "obj.data", "obj.names")}
pares = [(imgs[k], txts.get(k)) for k in imgs]
random.seed(42); random.shuffle(pares)
n_val = int(len(pares) * 0.2)
for split, sub in (("val", pares[:n_val]), ("train", pares[n_val:])):
    (W / split / "images").mkdir(parents=True); (W / split / "labels").mkdir(parents=True)
    for img, txt in sub:
        stem = Path(img).stem
        shutil.copy(img, W / split / "images" / f"{stem}.jpg")
        dst = W / split / "labels" / f"{stem}.txt"
        shutil.copy(txt, dst) if txt else dst.write_text("")
# ── el pool: train ×3 (enlaces, no copias) y su validación ──
with zipfile.ZipFile(f"{D}/paquete_pool_yolo.zip") as z: z.extractall("/content/pool")
P = Path("/content/pool")
for img in sorted((P / "images" / "train").glob("*.jpg")):
    for k in range(1, r["repeticion_pool"] + 1):
        (W / "train" / "images" / f"pool_{img.stem}_r{k}.jpg").symlink_to(img)
        (W / "train" / "labels" / f"pool_{img.stem}_r{k}.txt").symlink_to(
            P / "labels" / "train" / f"{img.stem}.txt")
for img in sorted((P / "images" / "val").glob("*.jpg")):
    shutil.copy(img, W / "val" / "images" / f"pool_{img.stem}.jpg")
    shutil.copy(P / "labels" / "val" / f"{img.stem}.txt", W / "val" / "labels" / f"pool_{img.stem}.txt")
(W / "data.yaml").write_text(f"path: {W}\ntrain: train/images\nval: val/images\nnames: {{0: balon}}\n")
print({s: len(list((W / s / "images").iterdir())) for s in ("train", "val")})  # ≈ 640+306, 159+15

model = YOLO(MODELO_V1)
model.train(
    data=str(W / "data.yaml"), imgsz=cfg["entrenamiento"]["imgsz"],
    epochs=r["epochs"], patience=r["patience"], batch=r["batch"],
    optimizer=r["optimizer"], lr0=r["lr0"], seed=r["seed"], deterministic=True,
    **r["augmentation"],
    project=f"{D}/salidas/reentreno_balon", name="balon-v2-pegado",
)
```

## 5. Medir el candidato (6-oct-2026) — un paso cada vez, con el OK de Alex

Celda 0, la de siempre (`docs/colab_balon_umbral_bajo.md`), y además el candidato enlazado:
```python
!ln -sf "{D}/salidas/reentreno_balon/balon-v2-pegado/weights/best.pt" models/weights/best_balon_v2_pegado.pt
```

**Paso 1 — Medida A (test del pool, v1 y candidato, ~5 min).** Necesita en Drive
`{D}/pool_balon/test_yolo.zip` y `{D}/pool_balon/manifiesto.csv` (16 KB entre los dos):
```python
!python scripts/colab_test_pool_balon.py \
    --test-zip "{D}/pool_balon/test_yolo.zip" \
    --manifiesto "{D}/pool_balon/manifiesto.csv" \
    --salida "{D}/salidas/reentreno_balon/medida_A.json"
```

**Paso 2 — Medida B: caché de balón de la parte entera con el candidato (~30-40 min).**
Las mismas condiciones que producción (`configs/processor_benja_balon_v2pegado.yaml`: solo
cambian el modelo y el nombre del caché). El caché se escribe directamente en Drive:
```python
!mkdir -p "{D}/salidas/reentreno_balon/cache" data
!ln -sfn "{D}/salidas/reentreno_balon/cache" data/tracking_benja
!python scripts/detectar_balon.py --config configs/processor_benja_balon_v2pegado.yaml
```

**Paso 3 — En el Mac (sin GPU):** los criterios 1-8 y la hoja de la medida C:
```bash
python scripts/medir_reentreno_balon.py --medida-a ".../salidas/reentreno_balon/medida_A.json" --cache-v2 ".../salidas/reentreno_balon/cache/cache_balon_p1_v2pegado.pkl"
```
El criterio 9 se lee de un CSV `n,juicio` (balon / basura / dudoso) con el juicio de las 30
casillas de la hoja, que se pasa con `--juicio-c`.
