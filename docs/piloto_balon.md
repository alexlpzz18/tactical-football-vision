# Piloto de balón — 5 min del benjamín (celdas de Colab)

El código está listo; falta la GPU. Estos son los pasos, en orden, y cada
uno decide algo del siguiente.

## Paso 1 — Elegir el umbral de operación (NO heredar el 0,3 de jugadores)

Para posesión y contactos, un falso positivo cuesta más que un fallo: un
balón fantasma en la banda inventa un pase que no existió. Así que el
umbral se elige con la curva, y ponderando precisión.

```python
from ultralytics import YOLO
m = YOLO('/content/drive/MyDrive/tactical/balon/best_balon_v1.pt')
print(f"{'conf':>6} {'P':>7} {'R':>7} {'F1':>7} {'F0.5':>7}")
for c in (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60):
    r = m.val(data='<tu data.yaml>', conf=c, imgsz=1280, verbose=False)
    P, R = float(r.box.mp), float(r.box.mr)
    f1 = 2*P*R/(P+R) if P+R else 0
    f05 = 1.25*P*R/(0.25*P+R) if (0.25*P+R) else 0   # pondera precisión
    print(f"{c:>6.2f} {P:>7.3f} {R:>7.3f} {f1:>7.3f} {f05:>7.3f}")
```

Coge el conf que maximiza **F0.5** (no F1) y ponlo en
`configs/processor_benja_balon.yaml` → `balon.confianza`.

## Paso 2 — ¿Hace falta SAHI?

Con imgsz=1280 puede que el frame entero baste, y SAHI cuesta ~10×.

```python
!python scripts/detectar_balon.py --config configs/processor_benja_balon.yaml \
    --comparar-sahi --frames 60
```

Imprime detecciones y ms/frame de las dos vías. Si SAHI no encuentra
bastantes más, déjalo en `activo: false` (que es el default).

## Paso 3 — Caché del balón del tramo de 5 min

```python
!python scripts/detectar_balon.py --config configs/processor_benja_balon.yaml
```

Muestrea 1 de cada 2 frames (~15 fps) frente a 1 de cada 3 de los
jugadores. **Es a propósito**: un jugador entre muestras se interpola sin
drama, pero un toque de balón entre muestras se pierde para siempre.

## Paso 4 — Caché de jugadores del mismo tramo

```python
!python scripts/procesar_partido.py --config configs/processor_benja_balon.yaml
```

## Paso 5 — De vuelta en local

Bájate los tres cachés a `data/tracking_benja/` y avísame: el CSV
conjunto, el vídeo con cajas de los dos modelos, el replay con el balón y
los números salen aquí sin GPU.

## Qué se mide después (paso 6 del encargo)

- % de frames con balón detectado
- % de esos frames en fase aérea (posición no fiable)
- nº de contactos y cuántos se atribuyen a un jugador
- lectura honesta de dónde falla

## Qué esperar, dicho antes de verlo

Con mAP50 0,789 sobre un dataset de 799 frames del propio benjamín, lo
razonable es que el balón se detecte bien en la mitad cercana y peor en
el fondo, donde mide 3-5 px. Las fases aéreas van a ser frecuentes en
fútbol base (mucho pelotazo), y ahí la posición proyectada NO es
utilizable: por eso se marcan en vez de suavizarse.
