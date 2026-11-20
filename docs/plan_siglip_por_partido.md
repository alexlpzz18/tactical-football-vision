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

---

## Resultado (20-nov)

Embeddings SigLIP del torso calculados en Colab (L4, 0,96 h en total, ~2,9 CU) para el benjamín (60 s)
y el alevín B (parte 1, 493.310 detecciones); los del alevín A, de la pasada en CPU del intento 1. La
subida del vídeo del alevín A a Colab falló con un 503 y la máquina se apagó sola. **Control**: los
embeddings del benjamín de la GPU y los de la CPU parten igual al 94 % y dan el mismo error contra el GT;
la evaluación responde a una mutación (con un 30 % de etiquetas cambiadas, el error pasa de 10 % a 32 %).

### Premisa: el selector

| pata | parejas | kappa HS | kappa SigLIP | 5 submuestras | elige |
|---|---|---|---|---|---|
| benjamín (60 s) | 131 | 1,000 | 1,000 | empate en las 5 | **HS** ✓ |
| alevín A (60 s) | **92** | 0,804 | 0,912 | SigLIP ≥ HS en las 5 | **HS** por la regla del mínimo de 100 parejas ✗ |
| alevín B (parte 1) | 2.058 | 0,612 | **0,800** | SigLIP > HS en las 5 (0,78-0,85 frente a 0,60-0,64) | **SigLIP** ✓ |

### Resultado con el método que elige el selector

| | criterio | con el selector | ¿cumple? |
|---|---|---|---|
| 1. alevín A, error con voto | ≤ 15 % (hoy 27,0 %) | 27,0 % (HS: faltan 8 parejas en 60 s) | **no**, por la regla del mínimo |
| 2. benjamín, error con voto | ≤ 6,6 % | 6,1 % (HS, sin cambio) | sí |
| 3. alevín B, mini-GT a ojo (79 jugadores) | no baja de hoy (79,7 %) | **89,9 %** (SigLIP con voto) · 91,1 % por recorte | sí |
| 4. ¿separa cerca/lejos? | reparto por franja coherente con la verdad | en el fondo, un grupo es el 27 % (51-57 % en el resto); el mini-GT dice que en el fondo el 88 % son blancos | sí |

Alevín B por franja (acierto sobre los que tienen etiqueta): producción 92,6 · 78,3 · 87,0 % (cerca ·
media · lejos); SigLIP con voto 100 · 83,3 · 95,7 %.

**Veredicto: cumple 3 de 4. El 1 falla por la regla fijada antes** (≥ 100 parejas para decidir) en una
pata que solo tiene 60 s procesados. En ella el selector favorece claramente a SigLIP (0,912 frente a
0,804, en las 5 submuestras), y con SigLIP el error baja de 27,0 a 12,6 %; pero eso sería decidir con
menos parejas de las fijadas. Es la misma cámara y el mismo campo que el alevín B, donde decide con
2.058 parejas. **No se adopta nada**: decide Alex. Para cerrarlo de verdad hacen falta los 20 min del
alevín A o su hoja de 300 recortes del alevín B.
