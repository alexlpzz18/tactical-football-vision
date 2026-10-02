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
