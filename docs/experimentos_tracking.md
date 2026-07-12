# Experimentos de optimización del tracking (Tarea 3)

Cada variante se prueba UNA A UNA contra el banco de evaluación
(`scripts/evaluar_tracking.py`) y solo se conserva si mejora IDF1/HOTA sin
subir los ID switches. Métrica oficial: **umbral por profundidad**
`clip(0.4 + 0.045·my, 1.0, 4.0) m` sobre los 100 frames comunes GT∩caché
del tramo min 5-6.

## Baseline (rama feature/banco-evaluacion, commit 7e3b7d4)

Pipeline: Etapa A conservadora + cosido v2 solo-movimiento
(309 tracklets → 89 identidades; sin caché de colores).

| métrica | oficial (profundidad) | fijo 2.0 m | TrackEval (cajas 2×2 m) |
|---|---|---|---|
| IDF1 | **0.229** | 0.226 | 0.104 |
| ID switches | **130** | 111 | 51 |
| Fragmentaciones | **163** | 148 | 94 |
| Recall/frame | **0.259** | 0.245 | — |
| Precision/frame | **0.730** | 0.692 | — |
| HOTA | — | — | 0.106 (DetA 0.085 / AssA 0.133) |
| MOTA | — | — | −0.176 |

Contexto clave: solo el **34 %** de las detecciones del caché acaba en
tracklets ≥3 frames (mediana 5 frames/tracklet) — el cuello de botella del
baseline es la **cobertura**, no los switches.

---

## Variante 3a — Interpolación de huecos dentro de identidades

**Qué:** relleno lineal de los frames de caché que caen entre dos
observaciones reales consecutivas de la misma identidad (nunca extrapolar),
con hueco máximo configurable. Implementación: `src/tracking/interpolacion.py`,
config `interpolacion:` en `configs/tracking.yaml`, flag `--interpolar` en el
script.

**Medición (métrica oficial, barrido de max_hueco):**

| variante | IDF1 | IDSW | Frag | recall | precision |
|---|---|---|---|---|---|
| sin interpolar (baseline) | 0.229 | 130 | 163 | 0.259 | 0.730 |
| interp. max_hueco=0.5 s | 0.227 | 135 | 166 | 0.264 | 0.716 |
| interp. max_hueco=1.0 s | 0.228 | 138 | 167 | 0.269 | 0.702 |
| interp. max_hueco=2.0 s | 0.231 | 134 | 159 | 0.281 | 0.672 |
| interp. max_hueco=3.0 s | 0.230 | 147 | 165 | 0.303 | 0.633 |
| interp. max_hueco=6.0 s | 0.223 | 205 | 206 | 0.402 | 0.474 |

**Decisión: RECHAZADA como palanca aislada** (config `activa: false`).
Sube mucho el recall (0.26→0.40 con 6 s) pero la precisión cae más deprisa
y los IDSW se disparan: la interpolación propaga los errores de identidades
mal cosidas. El mejor punto (2 s) da +0.002 IDF1 con +4 IDSW → no cumple el
criterio.

**Aprendizaje:** la interpolación no crea identidad, la amplifica. Re-medir
esta variante DESPUÉS de mejorar la calidad del cosido (veto de color,
segunda pasada, cosido global): con identidades más puras, el mismo relleno
debería convertir cobertura en IDF1.
