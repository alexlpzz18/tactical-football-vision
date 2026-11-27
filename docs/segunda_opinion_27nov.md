# Segunda opinión, 27-nov-2026: embudo del tercio lejano (F11), las 6 marcas del mini-GT y la revisión del repo de posesión

Rama `alevinb-preparacion`. Solo lectura: no toca producción.

## 1. ¿Dónde muere el 47 % que falta en el tercio lejano del alevín A?

`scripts/embudo_tercio_lejano.py` sigue a cada persona del GT (A/B, 30 s) por las etapas y anota la
PRIMERA en la que se pierde. **Control**: el CSV de la pasada (configs de `main` exportados con
`git show`) es idéntico byte a byte al del oráculo, y el tercio lejano da 46,5 % de faltan (el 47 %).

Tercio lejano: 868 personas, faltan 404.

| etapa donde se pierde | % de las que faltan | alto mediano |
|---|---|---|
| E1 detector: no está en el caché (SAHI, conf ≥ 0,3, ya fusionado) | **49,8 %** | 18 px |
| E2 filtrada antes del tracking | 0 % | — |
| E3 tracking: la detección llega al tracker y no entra en ninguna identidad | **10,1 %** | 19 px |
| E4 su identidad no tiene fila en ese frame | 0 % | — |
| E5a la fila está a > 2 m, pero porque **la propia detección** ya está a > 2 m | **30,9 %** | 20 px |
| E5b la detección está cerca y es la fila la que se mueve (suavizado / identidad) | 5,9 % | 20 px |
| E6 el casado 1-a-1 le da su fila a otra persona | 3,2 % | 20 px |

(Para comparar: en el tercio medio faltan el 16 %, y el 88,5 % de esas son E5.)

**E1, desglosado con SAHI en CPU, umbral 0,05 y sin fusión** (`scripts/embudo_detector_lejano.py`;
control: reproduce el 94,9 % de las personas que el caché sí tiene; dos pasadas, mismo resultado):

| de las 201 que el detector pierde | % | % de TODAS las que faltan |
|---|---|---|
| existen con conf ≥ 0,3 y las absorbe la FUSIÓN (GREEDYNMM) | 25,4 % | 12,6 % |
| solo con conf 0,2-0,3 | 18,9 % | 9,4 % |
| solo con conf 0,1-0,2 | 22,9 % | 11,4 % |
| solo con conf 0,05-0,1 | 9,5 % | 4,7 % |
| no salen ni con 0,05 | 20,4 % | 10,1 % |
| salen en la CPU y no en el caché (diferencia de máquina) | 3,0 % | 1,5 % |

**Bajar el umbral a secas no paga** (`scripts/embudo_umbral_lejano.py`, mismos 74 frames, tercio
lejano): 0,3 → 0,2 sube el recall de 68,7 a 73,6 % y los falsos positivos de 0,35 a 1,00 por frame;
a 0,1, 79,6 % y 2,72. Entra más basura que personas. De los falsos positivos nuevos, el 20 % (a 0,2) y
el 41 % (a 0,1) son QUIETOS (mismo píxel ± 2 px en otro frame del GT a ± 1,2 s): con la cámara a 0,22
px, eso se puede quitar; el resto no.

**La fusión no se arregla con un umbral de solape.** Las 51 absorbidas están contenidas ENTERAS en
otra caja (IOS = 1,0 en todas), casi igual de alta (×1,10) y mucho más ancha (IoU 0,51): una caja que
cubre a DOS jugadores de pie. Probada fuera de línea una fusión que no absorbe una caja de altura
completa (`scripts/embudo_fusion_lejano.py`; control: la reimplementación reproduce el GREEDYNMM de
SAHI en 74 de 74 frames): recall lejano 68,7 → 71,6 %, pero falsos positivos 0,35 → 1,26 en el fondo y
0,12 → 1,28 en el medio, porque la caja de las dos personas se queda como falso positivo. Tal cual,
negativo; un segundo intento tendría que quitar o partir esa caja.

**E5a no es presencia, es píxel.** No hay sesgo: el pie de la detección y el del GT coinciden en
mediana (0,0 px; 0,04 m en profundidad), con un intercuartil de ± 1,3 px. En el fondo 1 px de pie vale
~0,9 m de profundidad, así que ese temblor normal ya da ± 1,2 m y la cola pasa de 2 m (mediana de las
E5a: 2,8 m). Parte del temblor es del propio GT (una caja anotada a mano también se mueve ± 1 px), y
no se puede separar sin una segunda anotación. ⇒ Un radio fijo de 2 m es ~2 px en el fondo: cuenta
como «falta» lo que es error de localización. Para el producto el error es real igual (la anchura en
F11 es la dispersión en profundidad), pero no se arregla con presencia.

**E3 es asociación, no `min_hits`.** De 50 detecciones que el tracker deja fuera, 36 tienen la misma
detección (a < 15 px) en los 4 fotogramas muestreados de alrededor, y muchas veces esa vecina SÍ está
en una identidad. No son destellos sueltos: una pista absorbe a dos personas próximas y la otra
detección se queda huérfana. Con `umbral_activacion` 0,10 todas las detecciones ≥ 0,3 son de alta
confianza en ByteTrack: no es un umbral.

## 2. Las 6 marcas del mini-GT del alevín B sin fila de equipo

| | marcas | qué pasa |
|---|---|---|
| a staff | 3 | las tres son la MISMA identidad (2246, 2.137 observaciones: ~3 min) que mezcla jugadores verdes y blancos junto a la portería (x 92-97 m). La regla de staff decide sobre la identidad entera y se lleva a los jugadores de dentro. Es el riesgo ya descrito de las reglas sobre medias de identidad (`docs/reglas_sobre_medias_de_identidad.md`) |
| sin fila | 3 | la detección existe (conf 0,37-0,78) y llega al tracker, pero no entra en ninguna identidad: la misma etapa E3 del F11 |

## 3. El repositorio `404-Possession-Not-Found`

Sin fichero de licencia (todos los derechos reservados por defecto): se toman ideas, no código.

| pieza | ¿para la prueba #4? | por qué |
|---|---|---|
| Viterbi de 3 estados con costes (`src/hmm.py`) | **sí**, reimplementado | 40 líneas; convierte evidencia escasa en pocas fases limpias. Sus costes (12 y 48 nats a 25 fps en modo reglas) se pasan a la mitad para nuestras 12,5 muestras/s |
| modo por reglas (`src/team.py`, `src/dead.py`) | **sí, en parte** | ventaja del más cercano (≤ 2 m fuerte, ≤ 4 m débil) y jugadores lentos / balón fuera para el balón muerto. Fuera la pista «balón sin ver > 2 s» (aquí salta siempre) y la de Smart Tagging (no la tenemos). Aviso de ellos mismos: sus reglas se quedaron cerca de la línea base (0,36 frente a 0,24 de spellF1) y solo el modelo entrenado la dobló |
| detector de toques (`src/touch_features.py`) | **no** | pide cada fotograma de [t − 5, t + 5] observado a 25 fps (~0,44 s seguidos) con ~0,2 m de ruido. En 3:00-6:00 hay 9 rachas así en 3 minutos, y nuestro ruido de balón en el fondo es de metros |
| señales colectivas (`src/frame_features.py`) | **una**: el empuje | la velocidad media de cada equipo hacia la portería rival (su `vx`) se mete en el HMM solo donde no hay evidencia de balón. Las demás (gente por detrás del balón, presión alrededor del balón) necesitan el balón |
| sus 90 rasgos y el modelo entrenado con Bundesliga | no | decisión de Alex |

El plan de la prueba, con los criterios congelados antes de etiquetar: `docs/plan_posesion_prueba.md`.

## 4. Resumen del embudo y opciones baratas (sin reentrenar)

De las 404 personas que faltan en el tercio lejano: **detector 50 %** (fusión 13 %, conf 0,1-0,3 21 %,
conf < 0,1 o nunca 15 %), **tracking 10 %**, **localización de píxel 31 %**, el resto 9 %.

1. **Umbral bajo SOLO para continuar pistas** (el diseño original de ByteTrack). Re-detectar el tramo
   de 60 s con conf 0,1 (Colab, ~1 CU) y subir `umbral_activacion` a 0,3: las detecciones de 0,1-0,3
   solo pueden alargar una pista que ya existe, nunca crear otra. Apunta al 21 % de las que faltan, y
   la basura de umbral bajo casi nunca cae sobre una pista viva. Antes, el filtro de quietos (0,22 px).
   Riesgo: una caja débil que se pega a la pista de un vecino (asociación). Criterio: recall lejano
   arriba y «sobran» sin subir, en las dos patas.
2. **Detecciones huérfanas como presencia anónima** para las métricas colectivas: una detección que
   no entra en ninguna identidad y no tiene fila a < 1,5 m se exporta como fila sin identidad, con la
   etiqueta de equipo de su propio recorte. Desde caché, sin GPU. Apunta al 10 % del tracking y a las
   3 marcas «sin fila» del mini-GT. Riesgo: los falsos positivos del detector (0,35 por frame en el
   fondo) pasan a ser «sobran».
3. **Medir la localización aparte de la presencia.** El 31 % de E5a es temblor de ± 1-2 px que el
   radio fijo de 2 m cuenta como «falta». Repetir el oráculo con un radio por profundidad (≈ 2 px de
   pie) para saber cuánto de la prioridad es presencia de verdad (detector + tracking: ~28 % de las
   personas del fondo, no 47 %), y medir la anchura del bloque con un estadístico robusto (la mediana
   espacial de la nota 4 de Alex).

La fusión (13 %) se queda fuera de las baratas: el primer intento fuera de línea fue negativo.

## 5. Opción 3: el oráculo con radio por profundidad, y la mediana espacial (27-nov, tarde)

`scripts/oraculo_f11_radio_profundidad.py`, sobre el mismo CSV de `main`.

**Radio por profundidad.** Una fila casa con una persona si está a ≤ max(2 m, K px × metros por
píxel vertical en su pie). K se mide, no se elige: el p90 de la diferencia vertical entre el pie de
la detección y el del GT en el tercio lejano, **3,5 px**. En el fondo el radio queda en 2,9-4,3 m
(mediana 3,5).

| | radio fijo 2 m | radio por profundidad |
|---|---|---|
| faltan en el tercio lejano | 46,5 % | **35,0 %** |
| faltan en total | 27,5 % | 21,1 % |
| anchura: parte de Shapley de «faltan» | 60 % | **60 %** |
| anchura: arreglando SOLO «faltan» | −59 % | **−59 %** |
| anchura: arreglando SOLO localización | −1 % | −5 % |
| centroide: etiqueta · faltan | 42 · 38 % | 46 · 38 % |

**La presencia real sigue rompiendo la anchura.** Al reclasificar el temblor de píxel, un cuarto de
los «faltan» del fondo pasa a «casados», pero el peso de «faltan» en la anchura no se mueve (60 %) y
el criterio (> 30 %) se sigue cumpliendo con holgura. Los que faltan de verdad son los que definen
la anchura (los del fondo, la banda lejana). ⇒ la opción 1 (umbral bajo solo para continuar pistas)
está justificada. En el centroide manda la etiqueta de equipo (46 %).

**Mediana espacial: no** (sistema sin arreglos contra el GT con el MISMO estimador, 200 pares
frame-equipo):

| métrica | media (hoy) | alternativa | |
|---|---|---|---|
| centroide | **4,82 m** | mediana 7,08 m (6,74 en mediana) · contra la media del GT 5,71 | peor |
| líneas (defensa/medio/ataque) | **5,01 m** | mediana dentro de cada línea 5,28 m | peor |
| anchura | **5,71 m** | 2.º máx − 2.º mín 5,88 m | peor |

La mediana no absorbe las filas desplazadas porque el error dominante no son unos pocos puntos
raros: faltan personas enteras (las del fondo) y otras llevan la etiqueta del otro equipo. Con un
conjunto sesgado así, la mediana es más ruidosa que la media (usa menos información) y no corrige el
sesgo. Y recortar extremos en la anchura empeora, como avisaba Alex: borra al lateral que la define.

## 6. La regla de staff en el alevín B: encender el interruptor que ya existe (27-nov, tarde; NO integrado)

No hace falta una regla nueva: `main` ya tiene la versión por observación,
`agregacion.por_observacion.staff_dentro_del_campo` (`docs/staff_dentro_del_campo.md`, adoptada el
30-oct solo en el benjamín). Las observaciones de una identidad de staff con el pie a ≥ 1 m DENTRO
de las líneas, y en trozos que corren (≥ `staff.vel_max_lento`), se etiquetan como las de un
jugador; fuera sigue siendo staff.

**Por qué la 2246 era staff**: de 626 a ~680 s sigue a jugadores dentro del campo; luego pasa 4 min
plantada 1,6 m detrás de la línea de fondo, junto a la portería (x ≈ 101,6, 0,9 m/s de media). La rama
de staff lento marca la identidad ENTERA.

**Medido** (banco con el interruptor encendido solo en el alevín B, `outputs/alevinb_staff_dentro/`):
- mini-GT a ojo **86,1 → 89,9 %** (recupera las 3 marcas mandadas a staff);
- solo cambian filas que eran staff (1.387 de 512.923, en 53 identidades); las posiciones, idénticas;
- cambios de color por minuto 87,5 → 90,3.

**¿Qué podría estar inventando?** Hoja de 74 rachas con la caja de la propia detección
(`scripts/staff_dentro_alevinb.py` → `outputs/alevinb_staff_dentro/hoja/`; control: la pasada de la
hoja es idéntica byte a byte a la del banco). Revisadas a ojo:
- la gran mayoría son **jugadores junto a la banda lejana** (42 rachas, 339 filas con y ≥ 50 m) y el
  primer minuto de la 2246: vuelven bien;
- **~10 rachas cortas (~60 filas, ~7 s en 30 min) son una persona de ROJO plantada en la línea de
  fondo junto al poste** (x 96-100, y 17-23) que da pasos dentro del campo. No es el portero de A: en
  los mismos instantes el portero está a y ≈ 24-27. Salen sobre todo como B;
- 3-4 rachas dudosas (una figura de azul junto al banderín, dos junto a la barandilla cercana).

Es el mismo tipo de error conocido del benjamín (el adulto de 10:54, 3 s), aquí con ~2-3 veces más
filas. Decisión de Alex. Si se quiere evitar, la opción sin color sería pedir más margen DENTRO solo
junto a las líneas de FONDO (la persona de rojo no pasa de ~4 m de la línea; el portero lo decide su
propia regla); no se ha medido.

## 7. `staff_dentro_del_campo` encendido en F11 (27-nov, aprobado por Alex; solo en la rama)

En `configs/team_classification_alevinb.yaml` y `configs/team_classification.yaml` (alevín A), con
`margen_m` 1,0 y trozos rápidos, sin margen extra en las líneas de fondo. Medido: alevín B, mini-GT
89,9 %; alevín A, salida **idéntica byte a byte** con y sin el interruptor (en esos 60 s nadie del
staff entra en el campo). El benjamín no cambia (usa su propio config). Error conocido: ~7 s en 30
min de una persona de rojo junto al poste (sección 6).

## 8. El «fantasma del portero» y las verdes que sobran en el 3:00.0 (27-nov, noche)

**El patrón** (`scripts/fantasmas_interpolados.py`): una fila INTERPOLADA que, en su mismo fotograma,
está a ≤ 1,5 m de una fila REAL del mismo equipo o de un portero. En el 3:00.0 del alevín B, el
portero verde real (id 16) y, a 0,57 m, una pista solo interpolada (id 713) etiquetada como jugador
de campo: el bloque verde pasa de 29 a 79 m.

| | alevín B (parte 1) | alevín A (60 s) |
|---|---|---|
| fotogramas con algún fantasma | 38 % | 37 % |
| fantasmas por fotograma | 0,56 | 0,39 |
| de las filas interpoladas, fantasmas | 7,3 % | 13,2 % |
| (fotograma, equipo) cuyo largo de bloque cambia > 5 m | 1,6 % | 3,0 % |
| cambio del largo de bloque: medio · p99 | 0,5 m · 19,9 m | 1,0 m · 35,1 m |
| contra el GT (todas las filas, como pinta la pizarra): profundidad | — | 7,40 → **6,48 m** |
| anchura · centroide | — | 4,89 → 4,90 m · 4,41 → 4,34 m |

Raro pero brutal cuando pasa (p99 de 20-35 m), y quitarlo baja el error de profundidad un 12 % sin
tocar la anchura. Lo que podría estar inventando: quitar a un jugador real que en ese instante no se
detecta y está pegado a un compañero; contra el GT, ni la anchura ni el centroide empeoran.

**Las verdes que sobran en el 3:00.0**, con la caja PROPIA de cada fila (control: la pasada de la
captura es idéntica byte a byte a la de la demo). En ese fotograma hay 10 verdes de campo con
detección real + el portero, pero:
- la **301 es el árbitro** (amarillo flúor) con etiqueta de verde (en F11 no hay regla de árbitro);
- la **328 y la 716 son la misma persona en dos identidades** a 1,2 m, con equipos DISTINTOS: la 716
  (un jugador de verde etiquetado como blanco) es real y la 328 está interpolada en ese instante. La
  regla «mismo equipo o portero» no la coge; con «cualquier equipo» sí;
- la **727** es una pista interpolada que entra desde detrás de la línea de fondo (x 104 → 98).

**Demo**: por defecto (modo reunión) la pizarra quita los fantasmas (interpolada en el instante y a
≤ 1,5 m de una detección real del mismo equipo o de un portero), sin aros ni botones. Las marcas de
diagnóstico van detrás del interruptor «Diagnóstico», apagado.
