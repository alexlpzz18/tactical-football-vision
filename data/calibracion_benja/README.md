# Calibración del campo de benjamines (fútbol 7)

Carpeta PROPIA del caso benjamín: no comparte ningún archivo con la
calibración de Villaviciosa (`data/calibracion/`), que sigue intacta.

## Qué poner aquí

1. **`frame.png`** — un fotograma del partido, nítido y con el campo lo más
   despejado posible (sin jugadores tapando las líneas del área cercana).
   La cámara es normal (sin ojo de pez), así que **no hace falta corregir
   distorsión**: vale el frame tal cual sale del vídeo.

Los otros dos archivos los generan los scripts:

2. `puntos_marcados_benja.json` — lo escribe `marcar_puntos.py`
3. `homografia_benja.npy` — la escribe `calcular_homografia.py`

## Flujo

```bash
# 1. Marcar los puntos (se abren en una ventana, con sus coordenadas)
python -m src.homography.marcar_puntos --config configs/campo_benja.yaml

# 2. Calcular la homografía y validarla visualmente
python -m src.homography.calcular_homografia --config configs/campo_benja.yaml

# 3. Auditar la escala: derivar las medidas REALES del campo
python scripts/auditar_escala.py --config configs/campo_benja.yaml
```

Las medidas de `configs/campo_benja.yaml` (62×40) son una **estimación**;
el paso 3 las contrasta con las marcas reglamentarias F7 (área 26×12,
penalti a 9, círculo r=6, portería 6) y dice si hay que corregirlas.

## Qué esperar de esta cámara (y qué no)

La cámara va baja y **detrás de la portería**, así que el eje largo del
campo se aleja del objetivo. Medido sobre una cámara sintética equivalente
(3 m de altura, 12 m tras la portería):

| distancia a cámara | metros por píxel | factor vs la zona cercana |
|---|---|---|
| 15 m (área cercana) | 0.06 | 1× |
| 32 m (medio campo)  | 0.28 | 4,5× |
| 57 m (área lejana)  | 0.89 | 14× |
| 71 m (fondo lejano) | 1.37 | 22× |

**La mitad lejana del campo ocupa solo el 14 % de los píxeles que ocupa la
cercana.** Con un ruido de clic realista (2 px), el error de calibración
resultante es de ~0,27 m en la mitad cercana y ~0,94 m en la lejana.

Esto es **física de la proyección, no un fallo del sistema**, y tiene tres
consecuencias prácticas:

- Al marcar puntos, **salta los del fondo lejano** si no los distingues con
  claridad: un clic a ojo allí contamina toda la homografía. La auditoría
  informa del residuo punto a punto para detectarlo.
- Los umbrales que dependen de la profundidad (asociación, velocidades)
  hay que **recalibrarlos para este campo**: los del F11 de Villaviciosa
  no valen.
- El análisis será fiable en la mitad cercana y progresivamente peor en la
  lejana. Conviene decirlo en el informe antes de que lo pregunte nadie.

A cambio, esta cámara **no tiene distorsión de lente**, así que se evita el
problema que ensucia la calibración de Villaviciosa (donde el residuo
radial impide cuadrar círculo y áreas a la vez).
