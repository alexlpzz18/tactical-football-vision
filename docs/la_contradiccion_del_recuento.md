# La contradicción del recuento: no había nada roto

> ⚠️ **CORREGIDO AL DÍA SIGUIENTE — ver `docs/homografia_zona_cercana.md`.**
> El punto 3 de este documento presenta **1,29 m de error de posición cerca
> de la cámara contra 0,41 m en el centro** como un hallazgo de zona. Es
> falso: **son 57 observaciones del portero de A**, que es el único que
> habita esa zona, con un sesgo propio de 1,44 m. Los tres jugadores de
> campo que pasan por allí dan 0,23 m, y sin el portero el error crece con
> la profundidad (0,33 · 0,33 · 0,48 · 0,77 m) como manda la óptica. Se cae
> con ello el corolario de que "A está castigado en toda métrica con
> radio". Lo demás del documento —la combinatoria, el reparto
> defecto/exceso, las identidades con nombre y el negativo de quitarlas—
> sigue en pie.

17-sep-2026. La pregunta de Alex: *"1,2 % de observaciones con equipo
equivocado y solo 45 % de frames con el recuento de B correcto. Hemos
descartado el encuadre, el tracking y la detección. Algo falla y no
sabemos dónde."*

**No falla nada más. Los dos números son correctos y compatibles**, y
medían cosas distintas sin que lo supiéramos.

## 1. Por defecto o por exceso: los dos equipos fallan al revés

| | correcto (=7) | por DEFECTO | por EXCESO |
|---|---|---|---|
| **A** | 31,5 % | **66,3 %** | 2,2 % |
| **B** | 38,7 % | 28,4 % | **33,0 %** |

Leer "45 % correcto" como "faltan jugadores" era la mitad de la historia:
**a B le sobra uno casi tan a menudo como le falta.** A sí se queda corto
casi siempre, que es el encuadre ya medido.

Los dos a la vez (7 y 7): **16,0 %**. Al menos uno correcto: 54,2 %.

## 2. La explicación: el recuento exacto es FRÁGIL por construcción

Medido contra el GT con radio de 2 m, cada persona anotada tiene una fila
del sistema a menos de 2 m el **86,5 %** de las veces (86,2 % en A).

Si las siete fueran independientes:

> P(las 7 presentes) = 0,865⁷ = **36,2 %**

| | predicho por combinatoria | observado en el partido |
|---|---|---|
| equipo A | 35,5 % | 31,5 % |
| equipo B | **36,2 %** | **38,7 %** |

**Coinciden.** No hace falta ningún fallo adicional para explicar el
38,7 %: sale de exigir que SIETE cosas del 86,5 % ocurran a la vez.

Y el 1,2 % de equipo equivocado es otra cosa: es un error **por
observación y entre las que sí casan**. Un sistema puede tener 1 % de
error por observación y fallar el recuento exacto la mayoría de los
frames. No se contradicen; miden cosas distintas.

⚠️ Corolario incómodo: **"recuento exacto = 7" no es una buena métrica de
producto.** Castiga al sistema por un único desajuste entre catorce
personas y no distingue "falta un jugador" de "sobra el árbitro". Para el
informe sirve mejor el recuento MEDIANO o el error por observación.

## 3. El 60 % de lo que "falta" es lo mismo que "sobra"

De las 111 personas del GT sin fila, **67 (el 60 %) tienen una fila
sobrante a menos de 4 m en el mismo frame**, a una mediana de **2,48 m**.

Son la misma persona, contada como ausencia Y como exceso, solo porque su
posición cae fuera del radio de 2 m.

Y el error de posición parecía no estar repartido (⚠️ **la tabla que
sigue es la que quedó refutada**, ver la cabecera):

| zona | error mediano | p90 |
|---|---|---|
| **x 0-20 (donde defiende A)** | **1,29 m** | 1,73 m |
| x 20-35 | 0,41 m | 1,06 m |
| x 35-50 | 0,51 m | 1,22 m |
| x 50-62 | 0,70 m | 1,53 m |

⚠️ Se leyó como *"tres veces más error cerca de la cámara, donde la
homografía trabaja peor"*. **No es cierto**: la homografía es ahí donde
mejor trabaja, y ese 1,29 m es el portero de A arrastrando la mediana de
una zona que solo habita él.

⚠️ El radio manda sobre todo lo demás: las ausencias van de **1,85 por
frame a 2 m** a **0,80 a 5 m**. El p90 del casado óptimo es 2,76 m, así
que un radio de 2 m corta el 13 % de las parejas buenas.

## 4. Lo que sobra, con nombres y apellidos

151 filas sobrantes en 60 frames (2,52 por frame, radio 2 m):

| qué es | filas | % |
|---|---|---|
| **no hay nadie del GT cerca** (árbitro y no-jugadores) | 73 | 48,3 % |
| **la misma persona a 2-4 m** (artefacto del radio) | 45 | 29,8 % |
| **duplicado del mismo equipo** | 26 | 17,2 % |
| **equipo equivocado** | 7 | 4,7 % |

Las 73 "no hay nadie" salen de **8 identidades**, y las conocemos:

| id | etiqueta | obs | vel m/s | qué es |
|---|---|---|---|---|
| **292** | B | 4.106 | 1,10 | la identidad que **mezcla al árbitro** con jugadores (ya fichada en CLAUDE.md) |
| **62** | B | 3.229 | 1,20 | **un balón** detectado como persona (BACKLOG 16) |
| 286 | B | 1.931 | 1,63 | jugador no anotado o mezcla |
| 313, 323 | A, staff | 14, 100 | 0,14, 0,78 | **banquillo**: 100 % en la banda |

Un jugador de campo va a 1,5-2,5 m/s de mediana. El 292 y el 62 van a
1,10 y 1,20: **no se mueven como jugadores.**

## 5. Lo que falta, con nombres y apellidos

111 personas del GT sin fila (1,85 por frame):

| qué pasa | personas | % |
|---|---|---|
| nadie del sistema en 2 m | 81 | 73,0 % |
| **la ocupó otra fila del mismo equipo** (identidad partida) | 25 | 22,5 % |
| hay una fila del otro equipo en su sitio | 5 | 4,5 % |

⚠️ Ese 73 % **no es "no detectado"**: el detector encuentra al 96,7 %
(`docs/backlog23_no_hay_deficit.md`). Es sobre todo el radio de 2 m
mordiendo el error de posición, que es justo el punto 3.

## NEGATIVO: quitar identidades no arregla el recuento

Lo natural sería quitar a los sospechosos. Medido sobre el partido entero,
el efecto en el porcentaje de frames con B=7:

| | B=7 |
|---|---|
| como está | 38,7 % |
| sin id 292 | 40,8 % (+2,1) |
| sin id 288 | 40,8 % (+2,1) |
| sin id 525 | 34,9 % (**−3,8**) |
| **sin las 3 primeras juntas** | 36,2 % (**−2,4**) |

Quitar la identidad que más sobra **empeora** el recuento, porque en los
frames donde B estaba correcto pasa a faltar. El exceso está repartido y
no tiene dueño.

## Veredicto

- **La contradicción no existía.** Un 86,5 % por persona da un 36 % de
  recuentos exactos por pura combinatoria, y eso es lo que se observa.
- Lo único accionable de verdad son **dos identidades con nombre**: el
  292 (árbitro mezclado) y el 62 (el balón como persona), y ninguna de las
  dos se arregla borrándola.
- ~~El error de posición cerca de la cámara (1,29 m) es el hallazgo nuevo.~~
  **RETIRADO**: era un solo track. Ver la cabecera.
- La métrica de recuento exacto debería retirarse del informe en favor de
  la mediana o del error por observación.
