# SigLIP, intento 2: cada partido elige entre el histograma y SigLIP (plan, 20-nov-2026)

Rama `literatura-sota`. Segundo y último intento del método 5 de `docs/plan_literatura.md`. Escrito y
commiteado ANTES de medir. Solo pruebas: interruptores apagados, salidas en carpetas nuevas.

## Por qué

Intento 1 (`plan_literatura.md`), error de equipo contra el GT, mismas detecciones y mismo voto:

| | histograma HS | SigLIP + UMAP + K-means |
|---|---|---|
| alevín A (F11), con voto de 1,5 s | 27,0 % | **12,6 %** |
| benjamín (F7), con voto de 1,5 s | **6,1 %** | 9,8 % |

Ninguno de los dos sirve para todos los partidos, y cada uno gana claramente en uno. La semana pasada
la consistencia física eligió bien entre tono y brillo en las tres patas
(`docs/plan_equipos_consistencia.md`). Aquí se usa el mismo árbitro para elegir entre HS y SigLIP.

## La señal (la misma de `seleccion_feature.py`)

Parejas de ventanas de 1,5 s de la MISMA identidad, en tramos AISLADOS (nadie a < 2 m: sin cruce
posible), separadas ≤ 6 s y con un cambio de profundidad ≥ 6 m. Para cada método, la etiqueta de cada
ventana:
- **HS**: K-means de 2 sobre las medias HS de las ventanas (como hasta ahora);
- **SigLIP**: la mayoría de las etiquetas de SigLIP (UMAP 3D + K-means de 2) de sus detecciones.

Puntuación = kappa de Cohen de las parejas. Se elige SigLIP si su kappa supera a la de HS en ≥ 0,05; si
no, o con menos de 100 parejas, HS.

## Criterios

**Premisa** (antes de construir el interruptor): el selector elige SigLIP en el alevín A y HS en el
benjamín, y el orden aguanta en 5 submuestras del 50 % de las identidades. Si falla una pata, se cierra.

**Resultado** (el método elegido en cada partido, con el voto de 1,5 s):
1. alevín A: error ≤ 15 % (hoy 27,0 %);
2. benjamín: error ≤ 6,1 % + 0,5 puntos (no sube);
3. alevín B: lo que elija el selector, medido contra el mini-GT a ojo (79 jugadores) y, cuando Alex la
   marque, contra la hoja de 300 recortes. Con SigLIP, el acierto no puede bajar del de hoy;
4. ¿qué podría estar inventando? SigLIP podría separar «cerca / lejos» o «sol / sombra» en vez de
   equipos: la condición de cambio de profundidad de las parejas es justo lo que lo castiga, y se
   informa también del reparto de los dos grupos por franja de profundidad.

## Coste

Embeddings SigLIP de las detecciones de producción en GPU (Colab, trabajo `siglip_equipos` de
`gpu_colab.py`): benjamín 60 s, alevín A 60 s y alevín B parte 1 (~250.000 recortes). Estimado < 1 h de
L4 (< 2 CU). UMAP y K-means, en la CPU del Mac.
