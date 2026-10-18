# BACKLOG 23: no faltan 1,6 personas por frame. No falta casi ninguna.

17-sep-2026. La pregunta era *"¿qué 1,6 personas por frame no ve el
detector?"*. La respuesta es que **esa pregunta no tenía objeto**, y los
tres motivos son errores míos encadenados.

## Error 1, el que lo explica casi todo: cuántos son un equipo de fútbol 7

Yo venía calculando **"14 jugadores de campo + 2 porteros = 16 personas"**,
más el árbitro, 17.

**En fútbol 7 son 7 por equipo INCLUYENDO al portero.** Son **14 personas
en el campo**, no 16. Y el GT lo dice directamente: **14 tracks — 6 A,
6 B y 2 porteros**.

Con la cifra correcta (14 + árbitro = 15), el embudo de los frames limpios
—15,39 detecciones dentro del campo— deja de ser un déficit de 1,61 para
ser un **excedente de 0,39**.

## Error 2: el GT es una PLANTILLA de tamaño fijo

Todas las cajas del GT miden **40×18 px exactos**: un solo valor en 814
cajas. El GT sirve para la POSICIÓN, no para el tamaño.

Consecuencia para el emparejado: un jugador pegado a la cámara mide más de
100 px, así que el anotador encaja la plantilla sobre su cuerpo y **el
"pie" de la plantilla no es su pie**. Medido sobre el portero de A:

| track | dy del pie a la detección más cercana |
|---|---|
| **6 (portero A, el que defiende cerca)** | **+47,0 px** |
| 2 (un jugador del medio) | −1,8 px |

Con un umbral de 20 px sobre el pie, el portero de A sale **sin detectar
en 59 de 59 frames — el 100 %**. Y está ahí: en los recortes se le ve de
negro con el 1 a la espalda.

⚠️ Ese 100 % era el hallazgo más llamativo de la sesión y **era un
artefacto de mi criterio de medida**.

## Error 3: el IoU tampoco vale aquí

Emparejar por IoU daba 4,65 sin detectar por frame con IoU≥0,3 y 9,92 con
IoU≥0,5. También artefacto: las cajas del detector son **1,47× más altas y
1,28× más anchas** que la plantilla del GT, así que una persona
perfectamente detectada no puede pasar de IoU ≈ 0,53.

El control que lo demostró: entre parejas emparejadas **sin condicionar en
la distancia**, el desplazamiento es de **0,1 px en x y 2,2 px de error
mediano en el pie**. La posición del GT es excelente; lo que no coincide
es el tamaño.

## El número honesto

| criterio | sin detectar | por frame |
|---|---|---|
| pie a < 20 px | 97 de 814 | 1,62 |
| centro dentro de la caja detectada | 42 de 814 | 0,70 |
| **centro dentro O pie a < 20 px** | **27 de 814** | **0,45 (3,3 %)** |

**El detector encuentra al 96,7 % de las personas anotadas.**

## ¿Son siempre las mismas? No: ROTAN

| track | equipo | sin detectar |
|---|---|---|
| 6 | portero_A | 6 de 59 (10 %) |
| 5 | A | 6 de 60 (10 %) |
| 12 | B | 3 de 60 (5 %) |
| 3, 10 | A, B | 3 cada uno (6 %) |
| 9, 11 | B | 2 cada uno (3 %) |
| 13, 8 | B | 1 cada uno (2 %) |

**5 de los 14 tracks no fallan ni una vez**, el máximo en un frame son 2, y
**36 de los 60 frames no tienen ninguna ausencia**. No hay víctima
sistemática: es ruido repartido.

## El control: ¿cuántas están legítimamente ausentes?

| | fuera del campo | fuera de la imagen | x<20 | 20-45 | x≥45 |
|---|---|---|---|---|---|
| las 27 ausencias | **7,4 %** (2) | 0 % | 22 % | 63 % | 15 % |
| todas las anotadas (814) | 1,1 % | 0 % | 10 % | 71 % | 19 % |

- **2 de las 27 proyectan fuera del campo** (un jugador saliendo por la
  banda): ausencias legítimas. Quedan **25, el 3,1 %**.
- **Ninguna está fuera de la imagen**: el GT solo anota lo que se ve.
- Por zona, las ausencias pesan algo más en el lado cercano (22 % contra
  10 % de base) y **menos en el fondo** (15 % contra 19 %). Así que la
  pista del "jugador pequeño del fondo" **tampoco se sostiene** en el GT:
  lo que hay es una ligera sobrerrepresentación del borde cercano, que es
  justo donde la plantilla de 40 px peor encaja sobre jugadores grandes.
- **Tamaño en píxeles: no se puede medir con este GT**, porque todas las
  cajas miden lo mismo. Queda dicho en vez de inventado.

## Y de esas 27, varias son deriva del GT

En los recortes (`outputs/gt_sin_detectar.png`, verde = GT, rojo =
detecciones) se ve el recuadro verde **sobre césped vacío** en varios
casos, con el jugador claramente a un lado. El detector no puede encontrar
a alguien donde no hay nadie.

No las cuantifico una a una porque hacen falta ojos, pero el orden de
magnitud ya no mueve nada: el resto de 27 sobre 814 es ruido.

## Entonces, ¿de dónde sale el recuento corto?

Con la plantilla correcta de 7 por equipo, en los frames limpios:

| | detectados | esperados |
|---|---|---|
| equipo A (campo + portero) | **6,17** | 7 |
| equipo B (campo + portero) | **7,38** | 7 |

**B está completo.** El que falta es **A, y es el equipo que defiende el
lado que se ve al 15 %.**

⇒ **La hipótesis original de Alex era correcta**: el recuento corto es del
encuadre. Lo que la hacía parecer falsa era mi error de plantilla, que
inventaba dos jugadores por equipo y repartía la culpa sobre el detector.

## La lección

Tres criterios de medida distintos —pie a 20 px, IoU, contención— dan
1,62, 4,65 y 0,45 por frame sobre **los mismos datos**. El resultado no
estaba en los datos: estaba en el criterio.

Y el error de fondo no era técnico. Era **no saber cuántos jugadores tiene
un equipo de fútbol 7**, en un proyecto cuyo mercado inicial es el fútbol
7. Los tres controles que lo destaparon —el GT tiene 14 tracks, las cajas
miden todas 40 px, y el desplazamiento del portero es de 47 px— estaban
disponibles desde el principio.
