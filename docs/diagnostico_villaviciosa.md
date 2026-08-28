# Villaviciosa: es el ESCENARIO, y el techo es el TAMAÑO DEL RECORTE

Diagnóstico pedido por Alex (28-ago-2026) antes de decidir qué hacer con
la segunda pata: 23,6 % de observaciones con el equipo equivocado contra
1,2 % del benjamín, y un mes sin moverse.

Reproducir: `python scripts/diagnostico_villaviciosa.py`

## 1. El desglose del 23,6 %

| pata | identidades | mixtas | **mal en PURAS** | mal en mixtas |
|---|---|---|---|---|
| benjamín (F7) | 937 | 62 % | **0,0 %** | 7,4 % |
| Villaviciosa (F11) | 115 | 58 % | **12,7 %** | 31,2 % |

**La contaminación es la MISMA en las dos patas** (62 % contra 58 % de
identidades que mezclan personas). Así que no es que la asociación de
Villaviciosa sea peor.

La diferencia está en las identidades **PURAS**, donde no hay excusa de
contaminación: el benjamín falla el **0,0 %** y Villaviciosa el **12,7 %**.
Es el clasificador de color, no el seguimiento.

## 2. ¿Y por qué falla el clasificador allí? No es por las equipaciones

Era la hipótesis natural —azul y amarillo separan peor que naranja y
blanco— y **es falsa**:

| pata | alto de la caja | p10 | **separación A−B** | distancia del jugador a su prototipo |
|---|---|---|---|---|
| benjamín | 60 px | 44 | **0,978** | **0,57** de la separación |
| Villaviciosa | **26 px** | **20** | **0,961** | **0,94** de la separación |

**Los dos prototipos están igual de lejos entre sí** (0,978 contra 0,961):
las equipaciones separan lo mismo. Lo que cambia es que en Villaviciosa
**un jugador está casi tan lejos de su propio prototipo como los dos
prototipos entre sí** — relación señal/ruido ≈ 1, contra 1,75 en el
benjamín.

Y la causa está en la primera columna: **26 px de altura contra 60**.

## 3. La medida que lo cierra

Acierto del color sobre un recorte suelto, por tamaño de recorte:

| alto del recorte | Villaviciosa | benjamín |
|---|---|---|
| < 20 px | **57,6 %** | — |
| 20-25 px | **60,1 %** | — |
| 25-30 px | 78,1 % | — |
| 30-40 px | 86,0 % | 90,5 % |
| 40-60 px | **93,7 %** | **95,9 %** |
| > 60 px | — | 90,6 % |

> **A igualdad de tamaño de recorte, las dos patas rinden lo mismo.**
> Villaviciosa no es un partido más difícil: es un partido con menos
> píxeles por jugador.

El techo es abrupto: **por debajo de 25 px el color no lleva casi
información** (57-60 %, una moneda con sesgo). Y la mediana de
Villaviciosa son 26 px, con el p10 en 20.

## Veredicto y recomendación

**Es el ESCENARIO, no el sistema.** Y no es "el F11 es difícil": es que
una panorámica de 2560 px sobre un campo de 105 m deja al jugador en 26
píxeles. La única palanca real es **más píxeles por jugador**, y eso no
es software: es la cámara.

De las tres opciones de Alex, la evidencia apunta a **(c) sustituirla por
el partido de banda (Villaviciosa vs Bazán)**:

- **(a) invertir en arreglarla** — no hay qué arreglar en el sistema: a
  igualdad de píxeles ya rinde igual. Lo que haría falta es re-detectar
  con recorte y zoom sobre regiones, que es otro proyecto.
- **(b) declararla fuera de alcance** — cierto pero pierde la segunda
  pata, y el banco de dos patas es lo que ha evitado adoptar cosas que no
  viajan.
- **(c) sustituirla** — mantiene la segunda pata, y con un partido que se
  parece más a lo que Alex quiere vender.

### La predicción falsable, para no comprar esto a ciegas

Antes de adoptar el partido de Bazán como segunda pata, **medir la altura
mediana de sus jugadores**. La curva de arriba predice:

| si el jugador mide | acierto de color esperado |
|---|---|
| ≥ 40 px | ~93 % (como el benjamín) |
| 30-40 px | ~86 % |
| < 25 px | ~60 %, y no sirve como pata |

Si sale por encima de 40 px, el partido es utilizable y la sustitución
está justificada por una medida, no por una intuición. Si sale en 26 como
la panorámica, no hemos ganado nada y toca la opción (b).

⚠️ Y un aviso sobre el banco: **cambiar de segunda pata invalida todos los
negativos medidos contra Villaviciosa** (la puerta de distancia, el
`margen_equipo`, el `por_observacion`...). No hay que borrarlos —
siguen siendo ciertos para una panorámica— pero sí re-medirlos en la pata
nueva antes de darlos por vigentes allí.
