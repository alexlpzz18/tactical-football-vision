# Entrenar el v4 — dos celdas de Colab

Todo lo demás ya está preparado. Estas dos celdas son literalmente lo
único que hay que pegar.

## Antes: qué tiene que haber en Drive

```
MyDrive/tactical/datasets/
├── lote_alex_478/        (images/ + labels/, formato YOLO)
└── lote_ayudante_360/    (images/ + labels/)
```

## Celda 1 — Ensamblar y AUDITAR

```python
from google.colab import drive; drive.mount('/content/drive')
!git clone -b v4/preparacion-dataset https://github.com/alexlpzz18/tactical-football-vision.git
%cd tactical-football-vision
!pip -q install ultralytics wandb "numpy<2.1"

D = '/content/drive/MyDrive/tactical/datasets'
!python scripts/ensamblar_dataset_v4.py \
    --lote {D}/lote_alex_478 \
    --lote {D}/lote_ayudante_360 \
    --salida /content/dataset_v4_840
```

**La auditoría PARA el ensamblaje si encuentra diferencias sistemáticas
entre los dos lotes** — cajas por frame, tamaño de caja o numeración de
clases. No es un aviso que se pueda ignorar por descuido: si salta, hay
que mirarla. El fallo que persigue es el que no rompe nada y arruina el
entrenamiento en silencio: que tu ayudante no etiquete a los jugadores
del fondo, o que encuadre más apretado que tú.

Si las diferencias son reales pero aceptables, se repite con `--forzar`.

Además deja `/content/dataset_v4_840/revision_2pct/` con ~17 imágenes al
azar de **los dos lotes**, cada una con su `.txt`. **Míralas antes de
entrenar**: la auditoría automática mide lo medible, pero el criterio de
encuadre solo lo juzga un ojo.

## Celda 2 — Entrenar, con el dataset versionado en W&B

```python
import wandb, yaml
from ultralytics import YOLO

cfg = yaml.safe_load(open('configs/entrenamiento_v4.yaml'))
w = cfg['wandb']
run = wandb.init(project=w['proyecto'], entity=w['entidad'],
                 tags=w['tags'], job_type='train')

# El dataset queda versionado ANTES de entrenar: sin esto, dentro de tres
# lotes nadie sabrá con qué imágenes se entrenó cada modelo.
art = wandb.Artifact(w['artifact_dataset'], type='dataset',
                     metadata={'lotes': ['alex_478', 'ayudante_360'],
                               'total': 840})
art.add_dir('/content/dataset_v4_840')
run.log_artifact(art)

e, a = cfg['entrenamiento'], cfg['augmentation']
YOLO(cfg['modelo']['base']).train(
    data='/content/dataset_v4_840/data.yaml',
    epochs=e['epochs'], imgsz=e['imgsz'], batch=e['batch'],
    patience=e['patience'], cos_lr=e['cos_lr'], seed=e['seed'],
    project='v4', name='yolov8m_840', **a)
run.finish()
```

Al acabar, copia `v4/yolov8m_840/weights/best.pt` a Drive como
`best_v4.pt` y avísame: la comparación contra el v4pre **en el banco de
tracking** la hago yo en local.

## Por qué medium

Decidido contigo: mejor modelo = mejor pre-anotación para los siguientes
lotes, y etiquetar es hoy el cuello de botella. El coste de inferencia se
optimiza más adelante — destilar a small con el medium de maestro sigue
disponible entonces.

Un aviso de encuadre honesto: **más parámetros con 840 imágenes no
garantiza mejor mAP**. El v4pre sacó 0,90 con small y 478. Si el medium
no mejora, la conclusión no es que medium sea peor, sino que el dataset
es el límite — y eso también es información útil para decidir dónde
meter el siguiente esfuerzo.

## Lo que NO se toca en este salto

La augmentation se hereda del v4pre tal cual. Cambiar el tamaño del
modelo y la augmentation a la vez haría imposible atribuir el resultado.
