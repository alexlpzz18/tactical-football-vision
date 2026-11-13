# Plan: elegir la feature de equipo con la CONSISTENCIA FÍSICA del seguimiento (sin etiquetas)

Escrito el 12-nov-2026, ANTES de medir. Alex se ha ido y ha pedido seguir mejorando en autónomo.
Vía nueva tras el negativo de la silueta (`docs/plan_equipos_seleccion_automatica.md`).

## Diagnóstico que la motiva (mini-GT del alevín B, clasificador de producción)

Predicción del recorte SUELTO con los prototipos de producción:

| franja | blancos → A / B | verdes → A / B | brillo del pecho (bin medio) blanco · verde |
|---|---|---|---|
| cerca | 19 / 1 | 3 / 8 | 7,9 · 5,6 |
| media | 7 / 1 | **10 / 6** | 8,9 · 5,6 |
| lejos | 21 / 0 | 3 / 0 | 8,6 · 7,3 |

En la franja media el TONO del verde (H 7,7, S 2,7 en bins) cae casi encima del blanco (8,2, 3,3): la
máscara anti-césped borra el verde de la camiseta y queda lo que sobrevive. El BRILLO sí separa. Pero
el brillo empeora el benjamín, y la silueta elige al revés. Hace falta un árbitro sin etiquetas que
mida si la partición es la de los EQUIPOS, no si es compacta.

## La señal: una persona no cambia de equipo

Para cada espacio candidato (H = HS; V = HS + brillo + pantalón, peso 1), KMeans de 2 sobre las medias
de 1,5 s dentro del campo. Después, parejas de ventanas de la MISMA identidad:
- separadas ≤ 6 s, con las dos ventanas y todo lo de en medio AISLADO (ninguna otra detección a
  < 2 m en ningún fotograma: sin cruces, así que es la misma persona);
- y con un cambio de profundidad ≥ 6 m entre ellas (control incorporado de «¿qué podría estar
  inventando?»: una partición que separe cerca/lejos o sol/sombra cambiaría de grupo en esas parejas;
  una de equipos, no).

Puntuación = acuerdo corregido por azar (kappa de Cohen sobre las parejas). Se elige V si su kappa
supera a la de H por ≥ 0,05.

## Criterios de la premisa (antes de construir nada)

1. Ordena bien las TRES patas: H en benjamín y Villaviciosa, V en el alevín B. Si falla una, se cierra.
2. Al menos 100 parejas por pata (si no, la señal no existe en esa pata y se dice).
3. Estable: mismo orden en 5 submuestras del 50 % de las identidades.
4. Control: la misma kappa SIN la condición de profundidad, para ver si la condición cambia el orden
   (si lo cambia, la de sin profundidad estaba midiendo otra cosa).

Si pasa: interruptor `clasificador_color.seleccion_automatica: consistencia` (apagado por defecto) y
medida completa en las tres patas con los criterios de siempre.

---

## Resultado (12-nov)

### Premisa: PASA en las tres patas

Kappa de las parejas aisladas con cambio de profundidad ≥ 6 m (5 submuestras del 50 % de las
identidades entre corchetes):

| pata | parejas | H (tono) | V (brillo + pantalón) | elige | debería |
|---|---|---|---|---|---|
| benjamín, parte entera (20 min, caché v2 nuevo) | 824 | **0,975** [0,95-0,97] | 0,954 [0,92-0,95] | H | H ✓ |
| Villaviciosa (60 s) | 65 | **0,968** [0,90-0,94] | 0,841 [0,61-0,73] | H | H ✓ |
| alevín B (20 min) | 3.031 | 0,608 [0,59-0,63] | **0,749** [0,73-0,77] | V | V ✓ |

El orden aguanta en las 5 submuestras de las tres patas con la regla del margen (V solo si gana por
≥ 0,05). **Control (criterio 4)**: sin la condición de profundidad, el benjamín sale AL REVÉS
(V 0,984 contra H 0,954). La condición es la que separa «equipos» de «cerca/lejos»: sin ella, la
señal premiaba otra cosa. Villaviciosa tiene 65 parejas en su tramo (< 100, criterio 2): en el
producto ahí manda el mínimo y se queda la base.

Caché de color v2 del benjamín ENTERO recalculado en el Mac (`scripts/colores_v2_mac.py`, 6 min):
control del bloque v1 igual al de producción en el **100 %**.

### Construido detrás de un interruptor

`entrenamiento.seleccion_automatica.activo` (apagado por defecto), `src/team_classification/
seleccion_feature.py`. Con él, el ajuste va después del tracking (solo `bytetrack`, como las medias),
se calculan las dos kappas y, si la alternativa gana por el margen, se aplican sus cambios (medias de
1,5 s, brillo y pantalón con peso 1, k 2). Con menos de 100 parejas, la base. La decisión queda en el
meta (`seleccion_feature`). Tests: dos partidos sintéticos (uno de cada tipo), el caso sin parejas y
el processor entero (este último cazó un fallo de cableado del meta que el banco había destapado).

### Medida en las tres patas («dentro del campo + voto por ventana» + selección automática)

| pata | qué elige | resultado | sin selección |
|---|---|---|---|
| benjamín | base (kappa 1,000 contra 0,954, 131 parejas) | **1,245 % · 0,469 m** | 1,245 % · 0,469 m |
| Villaviciosa (ventana v2) | base (63 parejas, mínimo) | **17,5 % · 4,01 m** | 17,5 % · 4,01 m |
| alevín B (mini-GT) | **alternativa** (0,724 contra 0,609, 2.058 parejas) | **79,7 %** (cerca 81 · media **75** · lejos 83) | 73,4 % (media 54) |

Cumple los tres criterios: benjamín sin cambio, Villaviciosa sin cambio, alevín B en el mejor de los
dos brazos (79,7 %). La franja media, la que fallaba, pasa del 54 al 75 %. Mejora una pata sin
degradar ninguna.

⚠️ Lo que NO dice: el alevín B sigue por debajo del objetivo del 85 % (falla sobre todo «blanco
etiquetado verde»: 3 de 45, y 7 verdes a blanco); y Villaviciosa decide por el mínimo de parejas, no
por la señal (con 20 min, la premisa dice que elegiría la base igual).
