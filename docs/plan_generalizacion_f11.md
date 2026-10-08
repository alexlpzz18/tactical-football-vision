# Plan: test de generalización con un partido F11 (8-oct-2026) — SOLO MEDICIÓN

Encargo de Alex: mientras no hay vídeo nuevo, probar el sistema en un partido F11 que ya
tenemos. No se toca producción ni nada calibrado para el benjamín, y nada que se ajuste para
ese campo puede empeorar el benjamín.

## Qué hay

- **Vídeos en Drive** (`tactical-football-vision-data/videos/raw/`, no en local):
  `advdo_bazan_p1.mp4` (370 MB) y `_p2` (417 MB); `arganzuela_p1.mp4` (283 MB) y `_p2` (345 MB).
- **En local**, solo frames sueltos: 90 por parte de cada partido (`~/Downloads/bazan/`),
  de 1920×798.
- **Los dos partidos son del MISMO campo y la misma cámara**: panorámica desde la grada a la
  altura del medio campo, con mucha distorsión (el borde del tejado sale curvado). La cámara
  parece del mismo tipo que la de Villaviciosa (también 1920×798; su frame corregido mide
  2560×1064, exactamente ×4/3), pero **el campo es otro**, y aquí ocupa más altura de imagen.

## Paso 1: lo barato, antes de gastar GPU en un tramo

`scripts/colab_altura_jugadores.py`: 20 frames repartidos por cada parte, sacados con
`posicionar_en_frame()`, el detector de jugadores del benjamín (`best_v4pre.pt`) con el SAHI
de producción (2×4, solape 0,2, confianza 0,3, cajas > 5 % del frame fuera). Se mide la altura de
las cajas.

- **Solo las cajas con el pie sobre el césped** (`src/validacion_video.mascara_cesped`, que
  calibra el tono del césped en cada vídeo). Sin este filtro entra el público de la grada
  cercana, que sale grande en la imagen e infla la mediana.
- **En bruto y con la corrección de distorsión de Villaviciosa** (k1 = −1,5, k2 = 0,5,
  `configs/processor.yaml`). El 26 px de Villaviciosa se midió sobre el frame corregido, así
  que la comparación con la predicción es la corregida. ⚠️ Usar la lente de Villaviciosa es
  una HIPÓTESIS (parece la misma cámara): la de este vídeo no está calibrada.
- **Predicción a comprobar** (`docs/diagnostico_villaviciosa.md`): ≥ 40 px, el campo sirve de
  pata; ~26 px, no aporta; entre 30 y 40, zona intermedia (~86 % de acierto de color esperado).
- Se miden los dos partidos en la misma celda y se elige con el número. A igualdad, Bazán:
  hay juego en marcha y sus equipaciones (amarillo contra blanco) se distinguen.

**Relojes**: el script da el tiempo de ARCHIVO de cada frame. El desfase del reproductor de
Alex (+1:33 en el benjamín) **no se sabe para estos vídeos**: hay que confirmarlo con un
instante que se vea en los dos (por ejemplo, el saque inicial).

## Pasos 2 y 3 (solo si el paso 1 pasa)

2. Elegir un frame para calibrar con la herramienta de 6 clics (despejado, campo entero) y un
   tramo de 3-5 min con juego continuo.
3. Procesar el tramo tal cual y decir QUÉ FALLA y en qué etapa (encuadre, detección, color,
   calibración con distorsión) antes de proponer nada. Sin suponer un eje de profundidad: la
   distancia a la cámara se aproxima por el tamaño aparente de la caja.

## Resultado del paso 1 (8-oct-2026): NO APORTAN — se para aquí

| vídeo | resolución | duración | mediana corregida | p10 / p90 | < 25 px | mediana en bruto |
|---|---|---|---|---|---|---|
| Bazán p1 | 1920×798, 25 fps | 45,9 min | **22,8 px** | 16,5 / 40,4 | 61 % | 22,2 |
| Bazán p2 | 1920×798, 25 fps | 49,0 min | **23,4 px** | 17,2 / 38,6 | 58 % | 22,6 |
| Arganzuela p1 | 1920×798, 25 fps | 47,4 min | **23,8 px** | 18,6 / 36,5 | 56 % | 23,3 |
| Arganzuela p2 | 1920×798, 25 fps | 49,0 min | **23,3 px** | 17,5 / 33,9 | 65 % | 21,7 |

**La predicción se cumple: 23 px, por debajo incluso de los 26 de Villaviciosa.** Ninguno de los
cuatro sirve de pata (hacían falta ≥ 40 px). Comprobaciones del proxy:
- 22-23 cajas con el pie en el césped por frame (mediana), lo que corresponde a 22 jugadores más
  el árbitro: el filtro deja fuera al público y no se deja jugadores.
- Si el detector perdiera jugadores lejanos (los más pequeños), la mediana real sería MÁS BAJA:
  el veredicto solo puede empeorar.
- Las cuatro partes coinciden (22,8-23,8 px). Corregir la distorsión apenas cambia el número.

Pasos 2 y 3 no se hacen: procesar un tramo mediría otra vez lo ya sabido de Villaviciosa (a 26 px
el acierto de color cae a ~60 %). Es la misma conclusión de `docs/diagnostico_villaviciosa.md`:
la palanca es la CÁMARA (más píxeles por jugador), no el software. Para una segunda pata F11 hace
falta otro vídeo, grabado más cerca o con más resolución.
