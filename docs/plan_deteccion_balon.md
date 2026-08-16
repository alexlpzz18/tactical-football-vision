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

## Bug del piloto: 0 frames en Colab (11-ago-2026)

`detectar_balon.py` procesaba **0 frames en los dos modos**, escribía un
caché vacío, imprimía un `✓ Caché de balón` engañoso y reventaba con una
división por cero en el resumen. Costó una sesión de GPU.

**La causa no era la selección de frames**: el mismo bucle, con el mismo
vídeo y el mismo config, lee correctamente en local. Es el
posicionamiento: `cap.set` da el salto por bueno —`cap.get` devuelve la
posición pedida— y deja el lector inservible, de modo que el primer
`read()` devuelve False, el bucle sale a la primera y el resultado es
cero frames sin un solo mensaje de error. Depende del build de OpenCV, y
por eso en local no se reproducía.

Es la tercera vez que `cap.set` muerde en este proyecto, y esta vez la
lección es más fina que las anteriores: **verificar la posición
DECLARADA no basta; hay que verificar LEYENDO**. Ahora `iter_frames()`
lee un fotograma de prueba y, si no llega, rebobina y decodifica desde el
principio.

Cambios, todos con test (`tests/test_detectar_balon.py`, con un
VideoCapture falso que reproduce el fallo):

- posicionamiento verificado por lectura, con rebobinado de emergencia;
- validación de rutas de vídeo y modelo **antes** de cargar la red, para
  que un fallo de config no cueste medio minuto de GPU y aparezca donde
  no es;
- "0 frames" es ahora un error con diagnóstico (ruta, nº de frames del
  vídeo, tramo, muestreo) **y no se escribe ningún caché**;
- el `✓` solo se imprime después de validar el contenido. Un tick sobre
  un archivo vacío es peor que un error, porque se cree.

Riesgo abierto: el modo `full` del processor (jugadores) usa el mismo
salto sin blindar. Queda avisado en la guía de Colab.

### Umbral de operación adoptado

Del barrido con F0,5 (pondera precisión, porque un balón fantasma inventa
un pase que no existió): **conf = 0,35** — P 0,958 / R 0,836 / F0,5 0,931,
con meseta hasta 0,40. Fijado en `configs/processor_benja_balon.yaml`.

---

# PILOTO COMPLETADO — 5 min del benjamín (16-ago-2026)

Con el modelo v1 (mAP50 0,789) a conf 0,35, 1 de cada 2 frames.

## Números

| | |
|---|---|
| frames del tramo | 4.495 |
| con balón detectado | **2.373 (53 %)** |
| tras seleccionar el activo | 2.373 (100 % de los detectados) |
| en **fase aérea** | 447 (**19 %** de las observaciones de balón) |
| contactos detectados | 415 |
| con jugador atribuido | 289 (70 %) |

## Lectura honesta

**El 53 % de detección es el techo del piloto, y es bajo para posesión.**
Casi la mitad del tiempo no sabemos dónde está el balón. Para "por dónde
va el juego" sirve; para medir posesión con rigor, no.

**El selector de balón activo no descartó nada** (2.373 de 2.373). O no
había balones de calentamiento en el tramo, o el criterio —quieto **y**
lejos— es demasiado estricto para cazarlos. No se puede saber sin mirar
el vídeo, así que queda como pendiente de verificación visual, no como
"funciona".

**El 19 % de fase aérea confirma lo que se esperaba** de fútbol base: uno
de cada cinco instantes con balón tiene la posición proyectada no fiable,
porque la homografía supone suelo. Se marcan en vez de corregirse, y en
el replay se pintan translúcidos.

**415 contactos son demasiados: 83 por minuto.** Un partido real tiene
del orden de 20-30 toques por minuto, así que el detector está disparando
con ruido. El criterio (>45° con el balón a >2 m/s) es demasiado laxo
para un balón muestreado a 15 fps cuya posición tiembla. Antes de usar
los contactos para nada hay que endurecerlo y medirlo — con qué, es el
problema: no hay GT de contactos. La vía barata sería etiquetar a mano
los contactos de 30 segundos y barrer el umbral contra eso.

## Entregables

- `data/tracking_benja/posiciones_conjunto.csv` — jugadores y balón en el
  mismo CSV. El balón va con `id_jugador` −1 (raso) y −2 (aéreo): el
  replay asigna UNA etiqueta por identidad, así que separarlos es lo que
  conserva la marca de "no fiable".
- `..._contactos.csv` — timestamp, posición, ángulo y jugador más cercano.
- `outputs/replay_conjunto_balon.html` — balón blanco a medio radio,
  translúcido en fase aérea, con su entrada en la leyenda.
- `outputs/detecciones_conjunto_balon.mp4` — 2.997 frames con las cajas
  crudas de jugadores y el balón rodeado en blanco.

## Revisión visual del piloto (16-ago-2026)

### Bug de colores: no era el balón

En el vídeo conjunto los jugadores salían todos verdes. La causa no fue
añadir el balón: el meta del tramo se llama
`posiciones_benja_meta_piloto5min.json` —con el sufijo DESPUÉS de "meta"—
y la herramienta buscaba `posiciones_benja_piloto5min_meta.json`. Sin
meta no hay colores de equipo, y el verde es el color por defecto. Ahora
`buscar_meta()` prueba el convenio y, si falla, coge el meta del mismo
directorio cuyo nombre más se parezca.

### Fase aérea: por qué la RECTA y no las otras dos

Se probaron las tres opciones que planteó Alex:

- **congelar** en la última posición fiable: el salto no desaparece, se
  aplaza al aterrizaje. Medido, seguía habiendo un 5 % de pasos
  imposibles, ahora todos concentrados en el bote;
- **ocultar**: rompe la continuidad y se pierde el hilo del juego;
- **recta entre despegue y bote** (adoptada): es continua y **no afirma
  nada que no se haya medido** — une dos puntos reales. Lo único que no
  sabemos, la curva por la que pasó, es justo lo que no se dibuja como
  cierto: va atenuado y con `es_real=0`.

El balón se exporta como UNA identidad continua (`id -1`), con una ficha
aparte (`id -2`) solo como marcador de "en el aire".

### Lo que NO está resuelto

**Persiste un 5,5 % de pasos por encima de 25 m/s**, y no están en las
fases aéreas sino **entre observaciones de suelo consecutivas**. O sea:
el detector de fase aérea no las está marcando. Se intentó tres veces
—marcar saltos indefendibles saltándose el filtro de duración, congelar,
y la recta— y el porcentaje no baja, así que la hipótesis de trabajo
(eran fases aéreas mal filtradas) es falsa o incompleta.

Siguiente paso cuando se retome, y hay que hacerlo con datos y no a
ojo: coger los 130 pasos imposibles, mirar sus cajas en el vídeo y
responder si son (a) el mismo balón mal proyectado, (b) dos balones
distintos que el selector de activo confunde, o (c) falsos positivos del
detector. Cada respuesta lleva a un arreglo distinto y ahora mismo no hay
evidencia para elegir.

### Contactos: de pasarse a quedarse corto

Endurecido el criterio (ángulo 45°→70°, velocidad 2→4 m/s, exigencia de
que el cambio se sostenga 2 frames, y descarte de los contactos en fase
aérea): **415 → 37 contactos, o sea de 83 a 7 por minuto**.

Lo real son 20-30, así que ahora se queda corto. Sin GT no se puede
afinar: es exactamente el hueco que cubre la propuesta de Alex.

**Clip elegido para el GT barato: del 9:15 al 9:45** de
`benja_gredos_p1_20min.mp4`. Es el mejor tramo de 30 s del piloto: 327
observaciones de balón en suelo y solo 11 aéreas, o sea juego rasante
donde los toques se ven. El sistema detecta ahí **7 contactos**.

## GT de contactos: el criterio del ángulo es ESTRUCTURALMENTE ciego (16-ago-2026)

Alex etiquetó a mano el clip 9:15-9:45 del archivo (10:48-11:18 de
YouTube; el archivo va 1:33 por detrás), con quién toca, de qué equipo y
qué tipo de acción. **20 toques**, 12 del equipo blanco y 8 del naranja.

### Resultado

| tolerancia | TP | precision | recall | F1 | equipo correcto |
|---|---|---|---|---|---|
| ±0,5 s | 4 | 0,57 | 0,20 | 0,30 | 1/4 |
| **±1,0 s** | **5** | **0,71** | **0,25** | **0,37** | **2/5** |
| ±1,5 s | 6 | 0,86 | 0,30 | 0,44 | 2/6 |

Y lo peor está donde importa: en **juego continuo detecta 2 de 11**; en
juego parado, 3 de 9. Justo al revés de lo deseable.

### La causa, y no es de calibración

Los 6 toques de la conducción del #10 (10:50-10:54) se pierden **todos**.
Midiendo el balón en esos 6 segundos (74 muestras):

- ángulo entre pasos consecutivos: **mediana 5°**, p90 18°
- pasos que superan el umbral de 70°: **2 de 72**

O sea: **durante una conducción el balón va prácticamente recto**, porque
el jugador lo empuja hacia delante una y otra vez en la misma dirección.
Un criterio basado en el cambio de dirección no puede verlo, y bajar el
umbral a 5° dispararía con todo.

**El detector de contactos por ángulo solo puede ver pases, tiros y
rebotes.** La conducción —6 de los 20 toques de este clip, un 30 %— le es
invisible por construcción. Eso pone un techo estructural al recall que
ningún ajuste de umbral levanta, y explica por qué endurecerlo llevó de
83 contactos/min a 7 sin acercarse a los 20-30 reales: se estaba
recortando ruido y precisión a la vez que se dejaba intacto el agujero.

### Qué hace falta (diseño, no ajuste)

Un segundo criterio para la conducción, basado en una señal distinta:

- **oscilación de velocidad**: cada toque acelera el balón y entre toques
  se frena. Es medible y no depende de la dirección.
- **posesión por proximidad**: el balón se mantiene a 1-2 m del mismo
  jugador mientras avanza; los toques son los mínimos de distancia.

El de velocidad parece el más barato y el más independiente de la calidad
del tracking de jugadores, que hoy es el eslabón débil.

### Atribución de equipo: 2 de 5

Peor que una moneda. Pero es un problema aguas abajo: hereda el 15 % de
observaciones mal atribuidas del tracking, y con solo 5 aciertos la cifra
tampoco es concluyente. No se puede arreglar la atribución antes que el
recall.

### Nota metodológica de Alex, que hay que respetar al leer esto

El clip tiene mucho juego parado (saque de puerta pitado, portero con la
mano, saque en corto), así que **la tasa real de toques en juego continuo
es más alta** que los 20/30 s de este clip. La cifra de contactos por
minuto del piloto (7) es aún peor de lo que parece.

## Segundo criterio: oscilación de velocidad (16-ago-2026)

Implementado tras el hallazgo anterior. Cada toque ACELERA el balón y
entre toques se frena por rozamiento; se buscan los picos de subida de
velocidad. Es una señal independiente de la dirección, que es justo lo
que le faltaba al criterio angular.

### Medido contra el GT de Alex (20 toques del clip)

| criterio | n | precisión | recall | F1 | equipo ok | juego continuo |
|---|---|---|---|---|---|---|
| **ángulo (actual)** | 7 | **0,71** | 0,25 | 0,37 | 2/5 | 2/11 |
| velocidad, acel 2,0 | 45 | 0,33 | **0,75** | 0,46 | 6/15 | 8/11 |
| **velocidad, acel 3,0** | 35 | 0,43 | **0,75** | **0,55** | 5/15 | **8/11** |
| velocidad, acel 4,0 | 24 | 0,38 | 0,45 | 0,41 | 2/9 | 5/11 |
| velocidad, acel 6,0 | 15 | 0,53 | 0,40 | 0,46 | 2/8 | 4/11 |
| fusión ángulo+vel 3,0 | 37 | 0,41 | 0,75 | 0,53 | 5/15 | 8/11 |

**Triplica el recall** (0,25 → 0,75) y **cuadruplica la detección en
juego continuo** (2/11 → 8/11), que es la parte que importa. El precio
es la precisión: 0,71 → 0,43.

En el piloto entero, el ritmo pasa de **7 a 38 contactos por minuto**.
Lo real son 20-30, así que ahora se pasa por arriba en vez de por abajo
— pero por primera vez está en el orden de magnitud correcto.

La **fusión no aporta** (F1 0,53 vs 0,55 del criterio de velocidad solo):
los pases y tiros que veía el ángulo ya los ve la velocidad, porque
también aceleran el balón.

### Dos avisos honestos

**El umbral 3,0 está AJUSTADO sobre el mismo clip que sirve de GT.** No
es una validación, es un ajuste: con 20 toques de un solo tramo, elegir
el valor que maximiza F1 sobre esos mismos 20 es sobreajustar. Hace falta
un segundo clip para validarlo, y ahí es donde el número puede caer.

**La atribución de equipo sigue mal**: 5 de 15. Es aguas abajo del 15 %
de observaciones mal atribuidas del tracking, y no se arregla desde aquí.

### Estado

`--criterio angulo|velocidad|ambos` en `scripts/procesar_balon.py`, con
`angulo` de default. **NO se adopta como default**: la precisión baja, así
que no cumple la excepción de "mejora todo sin degradar nada" y la
decisión es de Alex, con la tabla delante.
