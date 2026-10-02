# El balón se DETECTA y se ELIGE mal: el selector, medido con GT (1-oct-2026)

Hasta hoy no había ningún GT de posición de balón. Con dos GT pequeños etiquetados
por Alex se ve algo que llevaba meses tapado: **casi siempre que el balón "falla"
en el vídeo, el balón está detectado; lo que falla es cuál se elige y cómo se
encadena de un frame al siguiente.**

## Los dos GT

| GT | qué es | herramienta |
|---|---|---|
| posición (40 imágenes) | recortes con rejilla, Alex marca la celda del balón | `scripts/gt_posicion_balon.py` + `leer_gt_posicion_balon.py` |
| desempates (38 imágenes) | frames con varios candidatos numerados, Alex dice cuál es el balón | `scripts/gt_desempates_balon.py` |

⚠️ El GT de posición salió con dos defectos de diseño míos, y hay que leerlo con
ellos: (1) **15 de sus 20 frames de "candidato de baja confianza" eran la misma
marca fija** (se eligieron antes de quitar las marcas); (2) "fuera" significa "no
está en el RECORTE", no "no está en la imagen", así que solo 8 de 40 frames dan
posición. Los 8 se verificaron a ojo contra ±60 s: los 8 son balón real (3 en el
aire o en las manos: su posición en metros no vale).

## 1. La detección va bien; la elección, no

Sobre los 38 desempates:

| | |
|---|---|
| el balón está ENTRE los candidatos | **36 de 38** (en D22 estaba detectado y lo quitó el filtro de marcas) |
| el selector de hoy elige el balón | **14 de 38** |
| por estrato: control / ganador dentro de la caja de un jugador / todos dentro | 7/10 · 5/22 · 2/6 |
| reponderado a los 1.065 desempates del partido | **~40 %** |

Por qué el selector se equivoca: desempata por **cercanía a un jugador**, y un
falso positivo SOBRE un jugador (bota, calcetín, mano, **el dorsal "8"**) está por
construcción más cerca de él que el balón que lleva en los pies. Esa regla se
validó en su día (77,5 % contra 71,5 % de la confianza, `balon_fantasma.md`)
**solo contra marcas del campo**, nunca contra este tipo de falso positivo.

No es GreedyNMM: en 119 frames de saltos repetidos, solo en 3 hay una caja de más
confianza a ≤30 px de la elegida (las dos sobreviven por separado en el caché). Y
no es temblor de proyección: 108 de 119 saltan ≥40 px en la imagen (mediana 419).

## 2. Y la continuidad entre frames, peor

Lo vio Alex: *"en las imágenes sueltas acierta casi siempre, en el vídeo se ve
mal"*. Un "cambio de objeto" es un salto entre frames consecutivos por encima de
1.000 px/s (la puerta ya medida de `balon_sin_alas.md`: más rápido no es un vuelo).

| | |
|---|---|
| partido: cambios de objeto | **1.064 = 13,8 % de los pares consecutivos, ~53/min** |
| partido: frames en rachas de 1-3 frames (parpadeo) | 16 % |
| tramo 365-378 s, 44 rachas etiquetadas a ojo | balón 40 % · **zapato del entrenador 43 %** · botas 14 % |

El "balón debajo del entrenador" que vio Alex es un objeto de 5 px a sus pies
(1845, 747), que **no** es una de las 10 marcas y por eso no se filtra.

## 3. El staff contaba como "jugador" — medido aparte, ayuda poco

`jugadores_por_frame_de_balon` (`src/balon/carga.py:102`) no filtra por etiqueta:
el entrenador y el niño del banquillo cuentan como "jugadores" en el desempate y
en la guarda de "quieto y lejos". Simulado sin tocar producción:

| | hoy | sin staff |
|---|---|---|
| GT de desempates | 14/38 | 16/38 |
| zapato del entrenador en el tramo | 57/134 | 45/134 |
| cambios de objeto en el partido | 1.064 | 1.062 |
| duración máxima anclada / fracción en marcas | 5,3 s / 0 % | 4,3 s / 0 % |
| frames con balón | 8.086 | 8.072 |

El zapato sigue en 45 frames porque **en 43 es el ÚNICO candidato** (el balón no
se detecta en ese frame): sin desempate, el selector acepta lo que haya aunque
esté a 30 m de donde iba el balón. Eso solo lo arregla la continuidad con un
estado "sin balón" — Plan 1 (1b), pendiente de aprobar.

## 4. El filtro de marcas: lo que encontró el Plan 2 antes de pararse

`marcas_estaticas.py` mide la presencia de una celda como último tiempo menos
primero (≥120 s): **dos visitas sueltas separadas por minutos cuentan como
presencia**. Por eso 5 de las 10 "marcas" son balón real parado:

| celda | qué es |
|---|---|
| punto central | saques de centro (0, 455, 644, 1189 s) |
| (122, 57) | la falta, 55-80 s (vuelve a pasar en t=785 s) |
| esquina del área | saques de puerta |
| (53, 57) | balón del partido en **saques de banda** (935-957 s), en una esquina que la cámara apenas cubre — lo miró Alex en el vídeo (15:35-15:57); **no** es el de repuesto |
| (147, 59), banquillo | **un SEGUNDO balón**, de repuesto, junto al niño y el entrenador |

Las 5 marcas de verdad miden 5 px y aparecen en 15-16 de 20 minutos (agrupando
celdas contiguas); las de balón, en ≤6. El criterio por fracción de minutos las
separaría — pero **recuperarlas resucita el fantasma del banquillo**: a t=137,5 s
hay dos balones a la vez, el del partido en juego y el de repuesto parado. **Es el
único episodio real del fantasma**: los otros cuatro son el balón del partido. Y la
guarda de "quieto y lejos" no lo quita aunque se saque al staff (jugador más
cercano a 5,1 m < 10 m). **Parado por decisión de Alex**: el filtro de marcas no
puede ser quien quita un segundo balón; eso es trabajo del selector (continuidad).

## 5. Plan 1, construido y medido (1-oct-2026): ADOPTADO 1a + 1b + 1c

Banco de medida, el mismo para todas las variantes (scripts de trabajo, no en el repo):
el GT de 38 desempates; dos tramos con **todos** los candidatos etiquetados a ojo
(365-378 s, el del entrenador, usado para ajustar; y 990-1005 s, el de más cambios de
objeto hoy, **solo para validar**); muestras aleatorias de 40 frames perdidos y 40
cambiados en el resto del partido; y las dos métricas de adopción.

⚠️ Las 44 rachas del tramo 365-378 se etiquetaron otra vez, y mejor: como pistillas
de TODOS los candidatos (22), no solo de lo que se elegía, porque el Viterbi puede
elegir otra cosa. Las etiquetas viejas no se guardaron.

### 1a. El staff fuera de la cercanía — adoptado

`jugadores_por_frame_de_balon(..., excluir_etiquetas=("staff",))`. GT 14 → 16 de 38.
Se pierden 14 frames, revisados uno a uno: **7 son el zapato del entrenador** (se
gana) y **7 un balón real FUERA de juego**, detrás de la línea de fondo (x = 64 m)
mientras un niño lo recoge. Ese es el coste exacto.

### 1b. Continuidad (Viterbi) — NEGATIVO sola

⚠️ **Mi diseño tenía un error**: con todo gratis salvo "sin balón" (λ por frame), λ no
es un parámetro — multiplicarlo por cualquier número da la misma solución. El problema
era "cubrir el máximo de frames con una pista continua". El parámetro de verdad es el
**coste de saltar** a un objeto que no continúa la pista, en frames "sin balón" (L).

Y "cubrir el máximo de frames" tiene el fallo que avisa CLAUDE.md: **premia lo que se
detecta mucho, y lo que más se detecta es lo QUIETO**. En el tramo del entrenador:

| 365-378 s | balón | zapato | bota/otro | balón visible perdido |
|---|---|---|---|---|
| hoy (1a) | 71 | 45 | 14 | 0 |
| 1b sola (L = 0,5-16, igual) | 45 | **74** | 4 | 4 |

En validación (990-1005 s) mejoraba claro (balón 148 → 158, malos 20 → 4), y el GT
subía a 25. Pero perdía balón real donde había un objeto quieto: no se adopta sola.

### 1c. Tamaño — lo que faltaba

Los fallos que dejaba 1b eran **pequeños**: 6 botas pegadas al balón en el GT (dentro
de la misma puerta; desempataba la cercanía, que gana la bota) y el zapato (5 px).
El tamaño esperado sale de la FÍSICA, no de un ajuste: un balón de 0,20 m proyectado con
la homografía en el pie de la caja (`tamano_relativo`). En los 36 balones del GT,
lado/esperado tiene **mediana 1,90 (p10 1,77, p90 2,19)**; lo que no es balón, 0,87.

- Desempate por tamaño: entre candidatos que continúan igual de bien, el más grande.
- Un candidato con tamaño relativo < `continuidad_umbral_pequeno` **vale lo mismo que
  no ver nada** (coste 1, como un frame sin balón: es la definición, no un ajuste).

Mesetas: el umbral da lo mismo en GT, tramos y cambios entre **0,8 y 1,8**; a 2,0 ya
castiga balones (GT 25, −870 frames) → **1,2**. Con 1c puesto, L da 2-3 cambios/min
entre 0,5 y 16; a 32 pierde balón real (24 en el tramo) → centro geométrico, **L = 3**.
El GT confirma, no elige (L = 1: 34; L = 3: 31; L = 8: 31).

### Resultado adoptado (L = 3, umbral 1,2)

| | hoy (antes de 1a) | final |
|---|---|---|
| GT de desempates | 14/38 | **31/38** |
| cambios de objeto | 53/min | **2/min** |
| frames en rachas de 1-3 | 16 % | 1 % |
| 365-378 s: balón / no balón | 71 / 59 | **80 / 0** |
| 990-1005 s (validación): balón / no balón / balón perdido | 148 / 20 / 0 | **159 / 3 / 1** |
| frames con balón | 8.086 | 7.169 (−11 %) |
| fracción en marcas | 0 % | 0 % |
| duración máxima anclada | 5,3 s | 5,6 s — **un córner real** (98-104 s), mirado a ojo |

**Qué se pierde y qué cambia, en el resto del partido** (muestras de 40, a ojo):
- 844 frames dejan de tener balón: **3 de 40 eran balón real** (uno en juego, uno en las
  manos en un saque de banda, uno fuera del campo), 11 dudosos (casi todos objetos
  diminutos: 642 de los 844 eran "pequeños"), 26 bota, dorsal u otro.
- 492 frames cambian de objeto: de los 18 decidibles, **acierta el nuevo en 15**, el
  viejo en 2. Los fallos del nuevo caen en el episodio del balón de repuesto (130-135 s).
- Enganches quietos nuevos (≥ 2 s en 15 px que antes no se elegían): 9 frames, 8 del
  **balón de repuesto del banquillo** (grande y real: ni continuidad ni tamaño lo quitan,
  es trabajo del Plan 2) y 1 del córner.

Lo que **no** se ha podido medir: Villaviciosa no tiene caché de balón. Queda pendiente
para cuando lo haya; no se ha usado ningún sustituto.

Código: `seleccionar_balon_activo(..., tiempos, homografia)` con `continuidad_*` en
`ParametrosBalon`; sin tiempos u homografía **falla** en vez de elegir otra cosa. La
homografía sale del config de campo (`cargar_homografia_de_campo`). Tests en
`tests/test_seleccion_por_continuidad.py` y `tests/test_balon_sin_staff.py`.

## 6. Plan 2, retomado con 1b/1c debajo (2-oct-2026): ADOPTADO

### Qué era de verdad el "balón de repuesto"

No era un balón parado: es **un niño del banquillo (staff, de azul) que juega con
otro balón FUERA de la banda** (y ≈ −0,7 m), en cuatro episodios (126-147, 240,
428-439 s; 183 frames). Mientras el del partido no se detecta en el medio campo, el
del niño es el ÚNICO candidato, y es grande y real: **ni la continuidad ni el tamaño
lo quitan**. Lo confirma la medida: con el filtro de marcas nuevo y sin regla de
staff, el selector lo elige en 314 frames (216 antes de recuperar las marcas).

### La regla: balón de un staff fuera del campo (`quitar_balones_de_staff`)

Se quita una detección si está **fuera de las líneas**, con **un staff más cerca que
cualquier jugador** y **ningún jugador a `dist_max_contacto` (3 m)**: nadie del partido
puede estar tocándolo. Los 3 m son el parámetro que ya existía, no uno elegido aquí.

Revisado a ojo, grupo a grupo, lo que lleva esa firma en el partido: los 183 frames del
niño (los quita todos), 24 de un balón junto al banquillo con el entrenador señalando
(355-359 s, probablemente el del partido fuera de juego) y **el coste: 5 frames del
balón del partido EN JUEGO, disputado sobre la línea delante del entrenador**
(762-780 s). Con 4 m serían 2, pero sería elegir el umbral sobre estos 8 frames.

### El filtro de marcas, corregido (`min_fraccion_minutos`)

Se añade, sin quitar los 120 s: el grupo de celdas contiguas tiene que aparecer en al
menos **la mitad de los minutos** del partido. Marcas de verdad: 15-16 de 20 minutos
(agrupando la que cae entre dos celdas); balón parado: 3-6. Recupera las 5 "marcas"
falsas, revisadas a ojo: saques de centro (0, 455, 643, 1.187 s), saques de puerta,
la falta de 55-80 s, el episodio de (53, 57) y el balón del niño (que ya quita la regla).

### Medida (configuración final contra el Plan 1 solo)

| | Plan 1 | + regla staff | + marcas nuevas, sin staff | **+ las dos** |
|---|---|---|---|---|
| GT de desempates | 31/38 | 32/38 | 30/38 | **32/38** |
| frames con balón | 7.169 | 6.995 | 8.239 | **8.009** |
| balón del niño elegido | 216 | 0 | **314** | **0** |
| cambios de objeto/min | 2 | 2 | 2 | 2 |
| tramos etiquetados (balón / malos) | 239 / 3 | 239 / 3 | 239 / 4 | 239 / 4 |
| fracción en marcas de verdad | 0 % | 0 % | 0 % | 0 % |
| duración máxima anclada | 5,6 s | 5,4 s | 19,4 s | **19,4 s** |

⚠️ **La duración anclada sube a 19,4 s y hay que leerlo**: es exactamente la alarma de
"¿se engancha a algo quieto?". Los dos tramos largos son balón real parado, mirados a
ojo: 936-960 s en (53, 57), que Alex verificó en el vídeo como el balón del partido (en
el plano entero se ve un balón quieto junto a un jugador de blanco y a 961 s ya no
está: una parada de juego), y la falta de 55-80 s (18,2 s). La métrica no distingue un
balón de partido parado de un objeto fijo: es su falso positivo conocido.

Resto conocido: 6 frames del balón del niño a 139 s y 3 a 1.128 s, en (147, 59), que la
regla no quita (no cumplen las tres condiciones a la vez).

## 7. Qué cambia aguas abajo: posesión y contactos (`procesar_balon`, partido entero)

Selector de antes de hoy (`3ae98d5`) contra el adoptado. Sin GT de posesión ni de
contactos en el partido entero: son cambios, no aciertos.

| | antes | ahora |
|---|---|---|
| frames con balón activo | 8.086 | 8.009 |
| observaciones marcadas "aéreas" | **30 %** | **10 %** |
| cortes de la puerta de píxeles | 65 | 11 |
| filas de balón MEDIDAS (`es_real`) | 5.676 | **7.186 (+27 %)** |
| posesión A / B (dueño a ≤ 3 m) | 40,9 / 59,1 % | 38,5 / 61,5 % |
| filas con dueño staff | 231 | **28** |
| contactos | 536 (26,8/min) | **654 (32,7/min)** |
| contactos atribuidos a staff | 13 | **0** |

Lo grande es lo de las aéreas: el 30 % de "vuelos" eran, en su mayoría, **cambios de
candidato disfrazados de vuelo** (la lección de `balon_sin_alas.md`), y al dejar de
saltar de objeto vuelven a ser posiciones medidas. La posesión se mueve 2,4 puntos.

⚠️ **Los contactos suben a 32,7/min, por encima de los 20-30 de un partido real** que
se usaron para endurecer el detector (`ParametrosBalon`, 16-ago). Hay más trayectoria
continua sobre la que detectar toques, pero sin GT de contactos en el partido entero no
se sabe cuántos de los 118 nuevos son reales. Queda para medir contra el GT de los clips.
