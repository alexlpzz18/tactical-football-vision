 Tactical Football Vision System

Sistema de analítica táctica de vídeo para fútbol amateur y formativo
basado en Computer Vision e Inteligencia Artificial.

## Descripción

Pipeline end-to-end que procesa vídeos de partidos grabados con trípode
y genera automáticamente:

- Detección de jugadores en cada frame (YOLOv8)
- Seguimiento de trayectorias individuales (ByteTrack)
- Clasificación automática de equipos por color
- Mapa radar 2D con la posición de todos los jugadores en tiempo real

## Stack tecnológico

- **Detección:** YOLOv8 (Ultralytics)
- **Tracking:** ByteTrack
- **Visión artificial:** OpenCV
- **Deep Learning:** PyTorch
- **API:** FastAPI
- **Despliegue:** Docker + AWS

## Estructura del proyecto
tactical-football-vision/
├── data/
│   ├── raw/                ← vídeos originales
│   ├── processed/          ← frames extraídos
│   └── annotations/        ← etiquetas de entrenamiento
├── notebooks/              ← experimentos y exploración
├── src/
│   ├── detection/          ← módulo de detección YOLO
│   ├── tracking/           ← módulo de tracking
│   ├── homography/         ← módulo de homografía
│   ├── team_classification/← módulo de clasificación de equipos
│   └── utils/              ← funciones auxiliares
├── models/weights/         ← pesos entrenados
├── outputs/                ← vídeos y mapas generados
├── tests/                  ← tests automáticos
└── docker/                 ← configuración Docker
└── docker/                 ← documentación técnica del proyecto 

## Instalación

```bash
conda create -n football-vision python=3.11.13
conda activate football-vision
pip install -r requirements.txt
```

## Estado del proyecto

🚧 En desarrollo activo

### ✅ Sprint 1 — Fundamentos de ingeniería
Entorno conda Python 3.11, estructura profesional, Git + GitHub configurado.

### ✅ Sprint 2 — Dataset y detección
- 5 vídeos de fútbol amateur descargados (Sunday League, Villaviciosa, Trival, Canillas)
- 178 imágenes etiquetadas en Roboflow con 3x augmentation
- Modelo YOLOv8n entrenado: **mAP50 = 0.929 | Precision = 0.935 | Recall = 0.908**

### ✅ Sprint 3 — Tracking y clasificación de equipos
- ByteTrack integrado con IDs persistentes (lost_track_buffer = 150 frames)
- Clasificación de equipos por color de camiseta con K-Means en espacio HSV
- Entrenamiento del clasificador con 30 frames para mayor robustez
- Pipeline end-to-end generando vídeo anotado con jugadores, IDs y equipos

### 🚧 Sprint 4 — Homografía dinámica (en curso)
### ⏳ Sprint 5 — API REST + Docker
### ⏳ Sprint 6 — Despliegue en AWS