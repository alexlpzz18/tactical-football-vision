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