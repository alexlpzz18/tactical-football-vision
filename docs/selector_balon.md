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
