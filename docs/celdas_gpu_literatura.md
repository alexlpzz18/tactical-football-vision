# Celdas de GPU de los métodos 3-6 (listas para lanzar; 20-nov-2026)

Tarea 6 de la cola de la noche. Cada script se ha probado en la CPU del Mac con 3 fotogramas (o en
ventanas de 60 s enteras). En Colab, la receta de una celda de CLAUDE.md, con la rama
`literatura-sota`. Los vídeos y cachés tienen que estar en `data/` del Colab (Drive montado), con las
mismas rutas relativas que aquí.

| método | script | prueba en CPU | ¿hace falta GPU? |
|---|---|---|---|
| 3. pelvis con pose | `scripts/lit_pose_suelo.py` + `lit_evaluar_pose.py` | 3 frames ✓, y las dos ventanas de 60 s completas ✓ | **no**: ya medido en CPU y **cerrado** (dos intentos, no cumple) |
| 4. recortes por franja lejana | `scripts/lit_franjas_lejanas.py` | 3 frames ✓ (control de reproducción 85,9 %: ver abajo) | para el partido entero; los 60 frames del GT corren en CPU |
| 5. SigLIP + UMAP + K-means | `scripts/lit_siglip_equipos.py` + `lit_evaluar_equipos.py` | 3 frames ✓ (74 recortes, 2 grupos) | para el alevín B entero; las ventanas de 60 s corren en CPU (~2-3 h cada una) |
| 6. WASB para el balón | — | — | **bloqueado** (abajo) |

## Celdas

Método 5, alevín B entero (para medirlo con la hoja de 300 recortes cuando Alex la marque):

```
!git fetch -q && git checkout -q literatura-sota && pip install -q -r requirements-colab.txt && pip install -q umap-learn==0.5.7 transformers && python scripts/lit_siglip_equipos.py --cache data/tracking_alevinb/cache_alevinb_p1.pkl --video data/raw/alevinb_p1.mp4 --largo 100 --ancho 64 --max-frames 3000 --dispositivo cuda --salida /content/siglip_alevinb.npz
```

Método 4, los 60 frames del GT del alevín A en GPU (para tener el control de reproducción de
producción, que la CPU no da):

```
!git fetch -q && git checkout -q literatura-sota && pip install -q -r requirements-colab.txt && python scripts/lit_franjas_lejanas.py --dispositivo cuda --salida /content/franjas
```

Método 3 (solo si se quisiera repetir en GPU; está cerrado):

```
!git fetch -q && git checkout -q literatura-sota && pip install -q onnxruntime-gpu rtmlib && python scripts/lit_pose_suelo.py --cache data/tracking/cache_detecciones_v4pre.pkl --video data/raw/partido.mp4 --k1 -1.5 --k2 0.5 --dispositivo cuda --salida /content/pose_villa.npz
```

Antes de cada lanzamiento completo, la misma línea con `--max-frames 3` (SigLIP, pose) o
`--chequeo 3` (franjas): es el chequeo previo de 3 fotogramas.

## Método 6 (WASB): bloqueado, y qué falta

- El repositorio (MIT) no publica el entrenamiento: «Training: TBA». Habría que escribirlo (red HRNet de
  3 fotogramas a 512×288, salida en mapa de calor) a partir del artículo: 1-2 días de trabajo.
- Sus pesos no tienen licencia declarada: solo valdrían para comparar, nunca para el producto.
- Y hacen falta etiquetas del balón EN JUEGO de nuestras cámaras: la hoja de 40 fotos
  (`outputs/hoja_balon_visible/index.html`) decide primero si una persona lo ve. Si lo ve en la mayoría,
  ~450 fotos etiquetadas (alevín B + cadete), unas 2 h de Alex.
