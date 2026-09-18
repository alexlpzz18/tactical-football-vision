# La homografía queda exculpada, y el "1,29 m cerca de la cámara" era UNA PERSONA

18-sep-2026. Hipótesis de Alex: *"cerca de la cámara un píxel vale 3 cm y
en el fondo 50, así que la precisión debería ser MUCHO MEJOR cerca, no tres
veces peor. Va contra la geometría. Mi hipótesis: la homografía está
EXTRAPOLANDO ahí, porque en mi sesión de clics salté los corners cercanos."*

**La objeción geométrica era correcta y ha destapado el fallo. La causa
propuesta, no: la homografía no extrapola mal.** El "1,29 m" no era una
propiedad de la zona — era **el portero cercano, un solo track**, que aporta
el 70 % de las observaciones de esa zona.

## 0. Primero, la geometría que hacía sospechar (confirmada)

Metros por píxel sobre el eje del campo, derivados de la propia homografía:

| x (m) | m/px (mín–máx) |
|---|---|
| 9 (área cercana) | 0,011 – 0,034 |
| 20 | 0,017 – 0,086 |
| 31 (medio campo) | 0,024 – 0,162 |
| 62 (fondo) | 0,042 – **0,501** |

Alex tenía razón en el orden de magnitud: **cerca, 1 px ≈ 1-3 cm; en el
fondo, 1 px ≈ 50 cm.** Para producir 1,29 m de error cerca harían falta
**38 px** de error. Eso no es ruido de nada: tenía que haber una causa.

## 1. La homografía NO extrapola mal. Tres pruebas independientes.

### a) Ruido de clic propagado (Monte Carlo, 300 refits con ±2 px)

Se perturban los 19 clics con 2 px de ruido, se reajusta H y se mide cuánto
se mueve cada punto del campo:

| x | y=7 | y=20 | y=33 |
|---|---|---|---|
| 5 | 0,19 | 0,13 | 0,20 |
| **12** | 0,14 | **0,09** | 0,14 |
| 31 | 0,14 | 0,12 | 0,14 |
| 62 | 0,33 | **0,29** | 0,41 |

**La zona cercana es la MÁS estable de todo el campo** (0,09 m), y la
inestable es el fondo (0,29-0,41 m). Es lo contrario de la hipótesis. Una
homografía no interpola entre puntos: es una transformación proyectiva
global de 8 parámetros, así que "quedarse fuera de la nube de puntos" no la
hace doblarse — solo amplifica el error del ajuste, y aquí esa
amplificación va hacia el fondo, no hacia la cámara.

### b) La envolvente de los 19 puntos no coincide con la zona de error

| x | dentro (D) / fuera (f) para y = 3, 7, 12, 20, 28, 33, 37 |
|---|---|
| 5 | f f f f f f f |
| 9 | f f f **D** f f f |
| **12-20** | f **D D D D D** f |
| 25-62 | D D D D D D D |

Solo se extrapola en **x < 9** y en las dos franjas de banda (y<7, y>33).
La zona del error (x 0-20) está **dentro** de la envolvente casi entera.

### c) Dos clics estaban pegados al borde de la imagen — y aun así no son la causa

`box_left_top` en el píxel **x = 0** y `box_left_bottom` en **x = 1919**
(la imagen mide 1920): son los dos corners del área cercana, y el clic cayó
en el borde mismo. Casi con seguridad **el punto real estaba fuera de
plano y se clicó el filo**. La auditoría de escala ya lo delataba sin que
lo supiéramos: *ancho del área izquierda 23,99 m contra 26 reglamentarios
(−7,7 %)*, mientras el área derecha da −0,7 %.

Pero quitarlos y reajustar con 17 puntos **no arregla nada**: el residuo
mediano cercano pasa de 0,82 a 0,92 m y las posiciones se mueven 0,1-0,45 m.
La homografía es robusta a esos dos clics. **Negativo apuntado.**

### d) NEGATIVO: reajustar minimizando píxeles en vez de metros es PEOR

`findHomography(píxel → metros)` minimiza el residuo en metros, lo que deja
que los puntos del fondo —donde 1 px vale medio metro— dominen el coste.
Parecía el fallo. Se probó el ajuste inverso (metros → píxel, minimizando
píxeles, e invertir):

| ajuste | residuo mediano cerca (x≤20) | lejos |
|---|---|---|
| actual (metros) | **0,82 m** | 0,93 m |
| alternativo (píxeles) | **2,24 m** | 0,45 m |

Mejora el fondo y **destroza la zona cercana**. No se adopta.

## 2. Entonces, ¿de dónde salía el 1,29 m? De un solo jugador.

El error con SIGNO sobre las 771 parejas casadas 1-a-1 ya lo decía: en la
zona cercana el error no es ruido, es un **sesgo de −1,26 m** con el p25 y
el p75 (−1,57 y −0,12) **los dos del mismo lado**. Un sesgo tiene dueño.

Desglosado por track, en x < 20:

| track | quién | n | sesgo dx |
|---|---|---|---|
| 0 | A | 15 | +0,40 m |
| 1 | A | 6 | −0,03 m |
| 10 | B | 3 | +0,17 m |
| **6** | **portero de A** | **57** | **−1,44 m** |

**El portero aporta 57 de las 81 observaciones de la zona** — porque es el
único que vive ahí — y es el único con sesgo. Los tres jugadores de campo
que pasan por su área dan **+0,23 m de sesgo conjunto**.

### La tabla corregida

| zona | n | error mediano | p90 |
|---|---|---|---|
| x 0-20 **con** el portero | 81 | 1,26 m | 2,02 |
| **x 0-20 SIN el portero** | 24 | **0,33 m** | 0,56 |
| x 20-35 | 378 | 0,33 m | 1,10 |
| x 35-50 | 203 | 0,48 m | 2,19 |
| x 50-62 | 109 | 0,77 m | 2,38 |

**Sin el portero, el error crece monótonamente con la profundidad
—0,33 → 0,33 → 0,48 → 0,77— que es exactamente lo que predice la óptica.**
La zona cercana no es la peor: es la mejor, empatada con el medio campo.
No hay ninguna anomalía geométrica que explicar.

## 3. ¿Y el portero? No lo sabemos, pero está acotado

El GT lo pone en x = 8,10 (p95 9,78) y el sistema en x = 6,62 (p95 7,44):
los dos dentro de su área, los dos plausibles. Lo que sí sabemos:

- `docs/backlog23_no_hay_deficit.md` ya midió que **el pie del GT del track
  6 está 47 px por encima de la detección más cercana**, contra −1,8 px de
  un jugador del medio campo. A 0,034 m/px eso son ~1,3 m: **el mismo
  número, medido por otro camino.**
- Es el único caso donde la **plantilla fija de 40×18 px del GT** tiene que
  cubrir un cuerpo de **114 px** (mediana del detector en x 0-10). Con 3×
  de desajuste, dónde queda el borde inferior deja de ser obvio.

### NEGATIVO: la plantilla no lo explica como regla general

Se probó a predecirlo a ciegas: subir el pie del GT `(alto_detector−40)/2`
px y ver cuánto se mueve en metros. Cerca acierta (−1,49 predicho contra
−1,26 medido) **pero predice −1,7 m en el medio campo, donde el sesgo
medido es +0,13**. El modelo "el anotador centra la plantilla en el cuerpo"
queda refutado por su propio control: el acierto de la zona cercana era
coincidencia. En el medio campo el anotador sí pone el pie en el pie.

⇒ Queda como **una anomalía de un track**, no una ley de la zona, y no se
puede resolver sin mirar los recortes de ese portero. Coste de dejarlo: 57
observaciones de 771.

## Veredicto

1. **La homografía queda exculpada** por tres vías: el Monte Carlo, la
   envolvente y el reajuste sin los clics del borde. No hace falta
   recalibrar, ni marcar puntos nuevos, ni restringir su zona válida.
2. **El hallazgo de ayer era falso.** No hay un gradiente de error contra la
   geometría: sin el portero, el error va de 0,33 m cerca a 0,77 m en el
   fondo, como manda la óptica.
3. Se cae con él **el corolario de que A está castigado por construcción en
   toda comparación entre equipos**: su zona no se mide peor.
4. Queda vivo, y menor, el caso del portero cercano y los dos clics del
   borde (que además explican el área izquierda medida en 23,99 m).

## La lección

Dije *"el error de posición cerca de la cámara es 1,29 m"* cuando lo medido
era *"el portero de A tiene un sesgo de 1,44 m, y como es el único que
vive en esa zona, arrastra la mediana de la zona entera"*. **Una zona con
24 observaciones de tres personas y 57 de una cuarta no es una zona: es esa
cuarta persona con ruido alrededor.** El aviso estaba a la vista —el error
cercano era un SESGO con todo el intercuartil del mismo lado, y un sesgo
tiene dueño mientras que el ruido no— y no lo miré.

Y lo que lo destapó no fue una medición nueva, sino **Alex contrastando el
número contra la física del problema**: si un píxel vale 3 cm, 1,29 m son
38 px y eso no puede ser. El control *"¿es este número compatible con lo que
ya sé del dominio?"* volvió a valer más que cualquier medición.
