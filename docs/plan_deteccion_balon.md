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

---

# PILOTO v1 (11-ago-2026, rama feature/balon)

Modelo `best_balon_v1.pt` entrenado (mAP50 0,789; yolov8s, imgsz 1280;
799 frames del benjamín: 502 con balón + 297 negativos, 524 cajas).
Código listo; **el caché necesita GPU** → celdas en `docs/piloto_balon.md`.

## Decisiones tomadas y por qué

**Umbral de operación: NO se hereda el 0,3 de jugadores.** Para posesión
y contactos, un falso positivo cuesta más que un fallo — un balón
fantasma en la banda inventa un pase que no existió. La celda de Colab
barre el umbral e imprime P, R, F1 y **F0,5** (que pondera precisión); se
elige el que maximiza F0,5, no F1. Queda 0,35 como provisional en el
config hasta que salga el barrido.

**SAHI: se mide, no se supone.** Con imgsz 1280 puede que el frame entero
baste, y SAHI cuesta ~10×. `--comparar-sahi` da detecciones y ms/frame de
las dos vías sobre 60 frames. Default `activo: false`.

**Muestreo independiente: balón 1/2, jugadores 1/3.** No es simetría mal
entendida: un jugador entre dos muestras se interpola sin drama porque se
mueve despacio y casi recto, pero el balón puede recibir un toque y
cambiar de dirección entre muestras, y ese contacto **se pierde para
siempre**. La fusión de cachés ya soporta frecuencias distintas.

## Tracking de balón v1 (`src/balon/tracking_balon.py`)

Tres problemas que no tiene un jugador, y cómo se atacan:

**Puede haber varios.** En fútbol base hay balones de calentamiento
parados en bandas y porterías, indistinguibles del bueno por apariencia.
Lo que los separa es el comportamiento, así que se descarta un candidato
solo si está quieto **Y** lejos de los jugadores. Las dos condiciones
juntas, porque cada una por separado le pasa al balón bueno: se para en
un saque de banda, y se aleja en un despeje largo.

**Vuela.** La homografía proyecta suponiendo que el objeto está EN EL
SUELO; un balón por el aire viola esa suposición y su posición se va
metros. Eso no es ruido que suavizar, es geometría que deja de aplicar,
así que se **marca** en vez de corregirse. Dos señales independientes:
velocidad proyectada imposible, y —la más específica— **tamaño
incoherente con la distancia**: un balón por el aire está más cerca de la
cámara que el punto del suelo al que se le proyecta, así que se ve más
grande de lo que le tocaría. Esta segunda no depende de la velocidad, así
que caza también los globos lentos.

**Los contactos son el dato.** Para el análisis táctico importa más quién
toca el balón y cuándo que dónde está exactamente. Un contacto es un
cambio brusco de dirección (>45°) con el balón en movimiento (>2 m/s, por
debajo el ángulo lo decide el ruido). Si no hay jugador a menos de 3 m,
**el contacto se registra igualmente sin dueño**: "hubo un contacto y no
sabemos de quién" es información honesta; atribuírselo al más cercano
esté donde esté sería inventar.

9 tests fijan estas tres cosas, incluidos los casos que distinguen el
criterio de su versión ingenua (el balón parado pero cerca no se
descarta; un parpadeo de un frame no es un vuelo; el balón casi quieto no
genera contactos por ruido).

## Estado

Hecho y testeado sin GPU: selección del activo, fases aéreas, contactos,
script de detección, config del piloto de 5 min y guía de Colab.

Pendiente de la pasada de GPU: el caché de balón, y con él el CSV
conjunto, el vídeo con cajas de los dos modelos, el replay con balón y
los números (% de frames con balón, % en fase aérea, nº de contactos).
