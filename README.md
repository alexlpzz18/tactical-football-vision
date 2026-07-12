# Tactical Football Vision System

Sistema de analítica táctica de vídeo para fútbol amateur y formativo
basado en Computer Vision e Inteligencia Artificial.

## Descripción

Pipeline end-to-end, 100 % automático, que procesa vídeos de partidos
grabados con una cámara fija gran angular y genera:

- Detección de jugadores diminutos (15-40 px) con YOLOv8 + SAHI
  (inferencia por recortes) y filtros validados
- Tracking offline propio EN METROS (coordenadas de campo) en dos etapas:
  tracklets conservadores + cosido de identidades, con perfiles
  seleccionables por config (`oficial` / `candidato`)
- Clasificación automática de equipos por color (2 fases, sin etiquetas)
  con regla posicional de porteros
- Proyección a metros por homografía y métricas colectivas por equipo
  → informe HTML

La calidad se mide contra ground truth etiquetado en CVAT con un banco
de evaluación propio (HOTA/IDF1/IDSW + cobertura colectiva, la métrica
de producto). Cada decisión de diseño está trazada con sus números en
`docs/experimentos_tracking.md`.

## Stack tecnológico

- **Detección:** YOLOv8 (Ultralytics) + SAHI
- **Tracking:** propio, offline en coordenadas de campo (asociación
  húngara en metros + cosido global en grafo) — la ventaja diferencial
- **Evaluación:** TrackEval + métricas propias contra GT de CVAT
- **Visión artificial:** OpenCV · **Deep Learning:** PyTorch
- **API:** FastAPI · **Despliegue:** Docker + AWS

## Estructura del proyecto

```
tactical-football-vision/
├── configs/                ← toda la configuración (tracking, evaluación,
│                             equipos, procesador end-to-end)
├── data/                   ← datos locales (gitignored; viven en Drive)
├── docs/                   ← experimentos y decisiones documentadas
├── notebooks/              ← registro de experimentos de Colab
├── scripts/
│   ├── procesar_partido.py ← CLI end-to-end (full / desde-caché)
│   └── evaluar_tracking.py ← banco de evaluación contra GT
├── src/
│   ├── tracking/           ← tracker en metros, cosido, perfiles
│   ├── evaluation/         ← banco: parser CVAT, métricas, TrackEval
│   ├── team_classification/← clasificador de equipos + porteros
│   ├── tracking_data/      ← procesador end-to-end (v2 + legacy)
│   ├── homography/         ← calibración píxel→metros
│   ├── metrics/            ← métricas colectivas del informe
│   └── report/             ← informe HTML
├── models/weights/         ← pesos entrenados (gitignored)
└── tests/                  ← pytest (91 tests)
```

## Instalación

```bash
conda create -n football-vision python=3.11.13
conda activate football-vision
pip install -r requirements.txt
```

## Uso

```bash
# Procesar un partido (modo y perfil en configs/processor.yaml)
python scripts/procesar_partido.py

# Medir el pipeline contra el ground truth
python scripts/evaluar_tracking.py --perfil candidato
```

## Estado del proyecto

🚧 En desarrollo activo

- ✅ Fundamentos: entorno conda, estructura, Git/GitHub, pre-commit
- ✅ Dataset y detección: YOLOv8 entrenado (mAP50 0.929) + SAHI
- ✅ Homografía píxel→metros calibrada
- ✅ Tracking propio en metros (2 etapas) + banco de evaluación con GT
  de CVAT: perfil de producto con cobertura colectiva 0.376 (×2.7 sobre
  el baseline)
- ✅ Clasificación de equipos 2 fases + regla de porteros (porteros 3/3)
- ✅ Integración end-to-end por config (full/desde-caché, legacy como
  fallback)
- 🚧 Validación del modo full con el modelo v3 en Colab
- ⏳ API REST + Docker · despliegue en AWS
