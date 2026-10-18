# Qué puede decir el sistema HOY, con su fiabilidad medida (28-ago-2026)

Encargo de Alex: *"la lista de TODO lo que el sistema puede decir hoy con
fiabilidad medida — no lo que se puede calcular, sino lo que aguanta un
GT o un análisis de sensibilidad. Con su margen de error al lado."*

⚠️ **Todo lo de abajo es del BENJAMÍN (F7).** Villaviciosa está en 3,55 m
de centroide y sin diagnosticar: nada de esta lista está validado allí.

## A. Con NÚMERO: aguanta un GT

Contrastado contra el GT de CVAT del benjamín (60 frames anotados,
814 personas, casado 1-a-1 por posición con radio 2 m).

| lo que dice | valor | margen | cómo se midió |
|---|---|---|---|
| **A qué equipo pertenece cada jugador** | — | **1,2 % de observaciones con el equipo equivocado** (9 de 723) | GT, casado 1-a-1. ⚠️ El nivel depende del radio: 3,1 % a 1,0 m · 6,5 % a 5,0 |
| **Dónde está el centro del bloque de cada equipo** | — | **0,97 m de error mediano** (media 1,43 · p90 3,39) | GT |
| **Cómo de abierto juega cada equipo** (anchura del bloque) | — | **0,40 m de error mediano** | GT |
| **Cuánto ocupa cada equipo cada zona del campo** | 9 zonas | **2,8 % de diferencia** con el GT | GT |
| **Quién es el portero de cada equipo** | — | 8 de 8 aciertos en las dos patas, y **4 de 4 abstenciones** correctas cuando no está | GT, con caso negativo |
| **Cuántos jugadores tiene cada equipo en pista** | ~7 | ⚠️ **sesgo constante**: A saca 5-6 donde B saca 7-8 | estructural, sin GT |

**Y que estos números aguantan un partido entero**: entre 5 y 20 minutos
el equipo equivocado va de 1,2 % a 1,2 %, y el fit no deriva (los tramos
de 5 a 20 aprenden los mismos prototipos, la distancia a su prototipo
BAJA de 0,798 a 0,748 y el margen A−B SUBE).

## B. Con número, PERO recién medido y con reserva

| lo que dice | valor | margen | reserva |
|---|---|---|---|
| **Posesión por equipo** | ej. 30/70 | sesgo **+0,3 pts** tras corregir por zona (fuera de muestra, \|error\| 1,1) | Medido sobre 764 instantes de **51 s** de juego con dueño inequívoco, en tres clips que son un **TECHO** (más fáciles que el partido medio). El ruido de muestreo a 5 min es ±13,9 pts; a 90 min, ±3,4 |

**La corrección de zona es lo que lo desbloquea** (28-ago-2026). El sesgo
que parecía de equipo —el balón se ve el 86,3 % del tiempo con A y el
69,7 % con B— **es de ZONA en un 98 %**: dentro de la misma franja del
campo la diferencia entre equipos cae a **+0,4 puntos**.

| franja | balón visto |
|---|---|
| < 30 m | 88,0 % |
| 30-35 m | 90,1 % |
| 35-40 m | 74,2 % |
| **> 40 m** | **57,8 %** |

Repesando por zona, el error del reparto pasa de **+4,7 a +0,4 puntos**
(y de +4,6 a +0,3 con las tasas estimadas **fuera de muestra**).

> **Predicción falsable**: si el sesgo es de zona, **se invertirá en la
> segunda parte** al cambiar de campo. Es la comprobación que lo cierra y
> no se puede hacer hasta procesar una segunda parte.

## C. Solo como TENDENCIA, sin número

| lo que dice | por qué no lleva número |
|---|---|
| **Quién dominó la posesión** | Con el error corregido (~±4 pts a 90 min) el signo aguanta a partir de una diferencia de 8 puntos. Por debajo de **54-46 no se puede afirmar nada** |
| **Qué equipo juega más adelantado** | Sale del centroide, que sí tiene número — pero la comparación entre equipos hereda dos errores |
| **Si un equipo se abre o se cierra a lo largo del partido** | La anchura tiene 0,40 m de error, pero su DERIVA no está validada contra GT |

## D. Lo que el sistema NO puede decir, y no debe intentarlo

| | por qué, medido |
|---|---|
| **Quién tocó el balón** | 36,4 % de acierto justo tras un cambio de dueño: **peor que una moneda** |
| **Pases, robos y transiciones** | Necesitan atribuir el toque, que es lo anterior |
| **Número de contactos** | El detector da 7,4/min o 40,8/min según la vía, cuando lo real son 20-30 |
| **Dónde está el árbitro** | En un recorte suelto no existe: 0,884 contra 0,936 de un jugador, solapados |
| **Cualquier cosa sobre Villaviciosa (F11)** | 3,55 m de centroide, sin diagnosticar |
| **Posición precisa en la mitad lejana** | A x=43 m un píxel vale 0,274 m; a x=50, 0,345 |

## El criterio que Alex puso, y que ordena todo esto

> *"Un número falso destruye la credibilidad de todo el informe; una
> etiqueta honesta no."*

Por eso la sección A puede llevar cifra, la B cifra con su reserva
escrita, la C solo etiqueta, y la D no aparece — ni siquiera como
"aproximado".
