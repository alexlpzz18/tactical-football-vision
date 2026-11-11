# Balón del Alevín B: caché en GPU (11-nov-2026)

Primera pasada de balón sobre la cámara de Villaviciosa (F11, panorámica, imagen ORIGINAL con la
lente nueva). Solo la parte 1 (decisión de Alex).

## Antes de gastar GPU: ¿cuánto mide el balón aquí?

Diámetro de un balón de 0,21 m proyectado con la lente (`camara_alevinb.npz`), en píxeles del
original 2560×1064:

| y (m desde la banda cercana) \ x (m) | 5 | 25 | 50 | 75 | 95 |
|---|---|---|---|---|---|
| 2 | 0,8 | 3,0 | **12,8** | 3,0 | 0,8 |
| 10 | 1,5 | 3,3 | 8,1 | 3,3 | 1,5 |
| 20 | 1,7 | 3,3 | 5,6 | 3,3 | 1,7 |
| 32 | 1,8 | 3,0 | 4,0 | 3,0 | 1,8 |
| 45 | 1,8 | 2,6 | 3,1 | 2,6 | 1,8 |
| 62 | 1,7 | 2,1 | 2,4 | 2,1 | 1,7 |

El detector (`best_balon_v1`, entrenado en el benjamín) nunca encontró un balón de menos de 7,1 px
(`docs/sahi_balon.md`). **Aquí solo el centro de la banda cercana pasa de 7 px.** Lo esperable es
balón detectado cerca y al centro, y casi nada en los fondos y las esquinas. Es la misma lección de
los panorámicos (`docs/plan_generalizacion_f11.md`): la palanca es la cámara.

## Prueba en CPU (30 fotogramas de la p1, uno por minuto)

| esquema | fotogramas con alguna candidata |
|---|---|
| frame entero, imgsz 1280 | 4 de 30 |
| SAHI 3×5, solape 0,15, imagen entera | 11 de 30 |

Hay candidatas que se repiten en el MISMO píxel en minutos distintos (2356,794 ×2; 412,715 ×3;
307,845 en fotogramas seguidos): marcas o conos. Las filtra después `src/balon/marcas_estaticas.py`
(lo que se mueve como un balón, CLAUDE.md). **Sin GT de balón aquí, estas cifras no dicen cuántas son
balón**: solo que SAHI es el que encuentra algo.

## Lo que se lanza

`scripts/colab_alevinb_balon.py` (envuelve `detectar_balon.py`, con su checkpoint y su firma) y
`configs/balon_alevinb.yaml`:

- imagen original, homografía identidad → (mx, my) del caché en PÍXELES; los metros, en el Mac con
  la lente;
- esquema `sahi` 3×5 (el `mixto` de producción deriva su franja de la homografía, que aquí no hay);
- 1 de cada 2 fotogramas: 22.775 en la p1.

Lanzado detrás de los jugadores con el vídeo subido desde el Mac (`--video-desde mac`): Drive pide un
permiso por máquina y no iba a haber nadie para darlo. Probado en CPU de punta a punta (12 frames:
caché completo, `completo: True`).

## Pendiente

- Pasar el caché a metros con la lente y por `tracking_balon` (balón activo, fases aéreas, contactos).
- Medir qué es balón: hoja de recortes con la caja de la fila, y la regla «¿se mueve como un balón?».
