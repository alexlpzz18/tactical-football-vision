# Re-medición del v4 — qué se lanza cuando llegue `best_v4.pt`

El mAP no decide nada por sí solo: el criterio de este proyecto es que un
detector mejor tiene que moverse en el **banco de tracking**, que es donde
se ve el producto. Un mAP más alto que no sube la cobertura colectiva no
es un salto.

## Paso 1 — Regenerar los cachés en Colab (lo único con GPU)

```python
!sed -i 's|best_v4pre.pt|best_v4.pt|' configs/processor.yaml configs/processor_benja.yaml
# Villaviciosa: SOLO el tramo del banco, no el vídeo entero
!python scripts/procesar_partido.py --config configs/processor.yaml
!python scripts/procesar_partido.py --config configs/processor_benja.yaml
```

⚠️ Cuidado con lo que ya falló una vez: `configs/processor.yaml` apunta
al vídeo de Villaviciosa **sin tramo**, así que procesaría los 16.300
frames. Antes de lanzarlo hay que descomentar
`muestreo.tramo: {min_ini: 5.0, dur_seg: 60.0}` para que el caché salga
del mismo minuto que el banco. Si no, la comparación no es posible.

## Paso 2 — Todo lo demás, en local y sin GPU

```bash
python scripts/medir_v4.py --cache-v4 data/tracking/cache_detecciones_v4.pkl \
    --colores-v4 data/tracking/cache_colores_v4.pkl
```

Compara v4pre contra v4 en las dos patas y en los casos con nombre.

## Qué se mide, y qué contaría como éxito

**Villaviciosa (GT de tracking).** Referencia del v4pre: cobertura 0,559 ·
concurrencia 25 · IDF1 0,453 · 5 quimeras · equipos 0,671.

**Benjamín (mini-GT de equipos).** Referencia: accuracy por observación
0,883 · identidades limpias 0,903 · jugadores de campo 0,850 (17/20).

**Los casos con nombre**, que son la razón de fondo de este salto:

| caso | qué pasa hoy | qué sería un éxito |
|---|---|---|
| **id 4** | 570 obs, es A y sale B | que salga A |
| **id 32** | naranja (B) etiquetado como A | que salga B |
| **id 19 → 4** | el mismo jugador con dos ids | una sola identidad |

El id 4 es el caso decisivo: el barrido del fit demostró que **ninguna
configuración sana del clasificador lo arregla**, así que si el v4 no lo
endereza, el problema no está ni en el clasificador ni en el detector, y
habrá que buscarlo en el recorte o en la asociación.

## Criterio de adopción

El de siempre: se adopta si mejora la cobertura sin degradar quimeras,
IDF1 ni concurrencia. Y si mejora TODO sin degradar nada, se adopta
directamente y se marca como tal.

Aviso de encuadre que ya está escrito en `entrenar_v4.md` y conviene
recordar al leer los resultados: **más parámetros con 840 imágenes no
garantizan mejor mAP**. Si el medium no mejora, la conclusión no es que
medium sea peor, sino que el dataset es el límite.
