# Detector de balón — plan y decisiones (11-ago-2026)

Preparado ANTES de que lleguen las etiquetas, para que cuando estén solo
haya que lanzar el entrenamiento. Nada de esto se ha ejecutado: no hay
GPU en el Mac y aún no hay ground truth de balón.

## Decisión 1: ¿una clase más en el modelo actual, o un modelo dedicado?

**Recomendación: modelo DEDICADO al balón, entrenado aparte.**

El argumento no es de precisión abstracta, es de riesgo sobre lo que ya
funciona. El detector de jugadores está en mAP50 ≈ 0,90 (v4pre) y es la
base de todo el sistema: tracking, equipos, métricas e informe salen de
él. Añadirle una clase obliga a reentrenarlo entero, y eso pone en juego
ese 0,90 por un objeto que:

- aparece **una vez por frame** frente a ~20 jugadores, un desbalance de
  clase de 1:20 que empuja al modelo a ignorarlo (la pérdida casi no
  mejora acertándolo);
- mide **5-12 px** en este encuadre, contra 15-40 px de un jugador, así
  que quiere una resolución de entrada y un tamaño de tile de SAHI
  distintos de los que le convienen a los jugadores;
- se **desenfoca al moverse** y desaparece tras los cuerpos, de modo que
  su detección es intermitente por naturaleza y necesita otro umbral de
  confianza y otra lógica temporal.

Con dos modelos, cada uno se afina para su objeto y el de jugadores no se
toca. El coste es una segunda pasada de inferencia por frame, que es
asumible porque el balón admite un tile de SAHI más pequeño y sin tanto
solape.

**Cuándo reconsiderarlo**: si el modelo de balón se queda por debajo de
mAP50 ≈ 0,5 en solitario, la vía de 2 clases pasa a ser interesante —
compartir backbone puede ayudar a un objeto con pocas muestras, y ahí sí
compensaría asumir el riesgo de reentrenar. Es una decisión a tomar CON
la primera medida delante, no antes.

## Decisión 2: augmentation para un objeto diminuto y único

La regla que ordena todo: **nada que pueda hacer desaparecer al balón del
recorte**, porque una imagen etiquetada sin el objeto dentro le enseña al
modelo que ahí no hay nada.

| técnica | valor | por qué |
|---|---|---|
| `mosaic` | **1.0** | Sí, y es la más valiosa: mete 4 imágenes en una, así que cada batch ve 4 balones en vez de 1. Ataca de frente la escasez de muestras. |
| `scale` | **0.5** | Sí. Enseña el balón a varias distancias, que es justo lo que cambia entre el área cercana y el fondo. |
| `translate` | 0.1 | Suave. Con más, el balón se sale del recorte demasiado a menudo. |
| `fliplr` | 0.5 | Gratis y sin riesgo: un balón es simétrico. |
| `flipud` | 0.0 | No. La cámara nunca ve el campo del revés. |
| `hsv_v` | 0.4 | Sí, y generosa: el balón cambia mucho de brillo entre sol y sombra. |
| `hsv_s` / `hsv_h` | 0.5 / 0.015 | Estándar. |
| `mixup` | **0.0** | No. Mezclar dos imágenes deja balones semitransparentes: enseña a detectar cosas que no existen. |
| `copy_paste` | **0.0** | No sin máscaras de segmentación. Con solo cajas, pega recuadros de césped. |
| `erasing` | **0.0** | No. Borrar un trozo al azar tiene una probabilidad nada despreciable de borrar el único objeto de la imagen. |
| `crop_fraction` | vigilar | Cualquier recorte agresivo compite con el objetivo. Si se usa, comprobar en el dataset generado qué porcentaje de imágenes se queda sin balón. |

**Comprobación obligatoria antes de entrenar**: volcar 50 imágenes ya
aumentadas y contar cuántas conservan el balón. Si baja del 95 %, la
augmentation está en contra del objetivo, por buena que parezca la lista.

Config en `configs/entrenamiento_balon.yaml`.

## Decisión 3: plan de evaluación (¿qué GT?)

El GT de tracking existente (`data/annotations/ground_truth_tracking/`) NO
sirve: solo tiene `player` y `referee`. Hace falta etiquetar balón, y el
plan más barato que da una medida honesta es:

1. **GT de detección** — el mismo tramo de validación (min 5-6), 1 de
   cada 15 frames, con una caja de balón por frame cuando sea visible y
   ninguna cuando no lo sea. Son ~130 frames.

   **Los frames SIN balón visible son imprescindibles**, no un descarte:
   sin ellos no se puede medir el falso positivo, que en este problema es
   el error que más molesta (líneas del campo y manchas blancas se
   parecen mucho a un balón a 8 px).

2. **Métricas**, en este orden de importancia para el producto:
   - **precisión y recall a IoU 0,3**, no 0,5. Con un objeto de 8 px, un
     error de 2 px ya baja el IoU de 0,5, y una detección a 2 px del
     balón es perfectamente útil para saber por dónde va el juego.
   - **error de posición en METROS** tras la homografía, que es la
     unidad en la que se va a usar de verdad.
   - **continuidad temporal**: fracción de frames consecutivos con
     detección. Un balón detectado a trompicones no sirve para posesión.

3. **Criterio de adopción**: recall ≥ 0,6 con precisión ≥ 0,8 en el tramo
   de validación. Por debajo de eso, las métricas derivadas (posesión,
   centro de juego) serían ficción, y este proyecto ya tiene el criterio
   de no publicar números que no sostiene la medida.

## Qué hace falta de Alex

- Etiquetas de balón del tramo de validación (~130 frames, incluyendo los
  que no tienen balón).
- Idealmente, otro tramo distinto para test, aunque sea más corto: medir
  en el mismo tramo con el que se ajusta cualquier umbral infla el
  resultado.
