# Banco de métricas de PRODUCTO (20-ago-2026)

> ⚠️ **Antes de citar cualquier número de Villaviciosa de este documento,
> lee `docs/suelo_de_ruido.md`.** Medido el 25-ago-2026: quitando CINCO
> detecciones al azar de 10.040, la cobertura de Villaviciosa se mueve
> 0,047, la accuracy de equipos 0,085 y el centroide 0,83 m de mediana.
> La causa es el umbral de fusión del fit de color, que se elige por
> argmax sobre una rejilla y salta de escalón en 2 de cada 10
> perturbaciones. **El benjamín no se mueve nada.**
>
> Eso NO convierte en falsas las diferencias pequeñas medidas aquí —un
> A/B determinista sobre el mismo caché no tiene ruido— pero sí significa
> que **una diferencia pequeña medida una sola vez puede no viajar**. El
> test que hay que pasar antes de darla por buena es repetir el A/B sobre
> entradas perturbadas y comprobar que el SIGNO aguanta.

`scripts/banco_producto.py`. Nace de una corrección: el centroide de
equipo agrupa los puntos por `(frame, equipo)` y **no usa la identidad**.
Tres agrupaciones distintas de las mismas observaciones —14 identidades y
1.914— dan el mismo centroide. Estuvimos una semana decidiendo con una
métrica que no medía lo que creíamos.

Ahora las métricas van en **dos familias etiquetadas**.

## FAMILIA A — dependen de la IDENTIDAD

Las que un entrenador lee por jugador, y las que se degradan cuando el
tracker falla. Emparejamiento identidad↔persona **uno a uno** por solape
máximo (húngaro), como IDF1: sin eso, varias identidades reclamarían a la
misma persona y las cifras saldrían infladas.

| métrica | valor |
|---|---|
| error de posición por jugador | mediana **0,62 m** · p90 4,85 m |
| cobertura de la identidad asignada | mediana **92 %** |
| recorrido total | GT 751 m · sistema 654 m (**−13 %**) |
| **estabilidad: identidades distintas por jugador** | mediana **6** · máx 10 |

Por jugador, la cobertura va del 25 % al 100 %: hay cuatro jugadores por
debajo del 50 %, y sus recorridos se desvían mucho (el 9 pasa de 130 m
reales a 78 m medidos, −40 %; el 4 al revés, de 83 a 107 m, +29 %).

## FAMILIA B — NO dependen de la identidad

⚠ **Insensibles al tracker.** Se conservan a propósito, porque dicen algo
importante de producto — pero no sirven para juzgar la asociación.

| métrica | valor |
|---|---|
| centroide del equipo | 1,55 m |
| anchura del bloque | 0,93 m |
| profundidad del bloque | 1,48 m |
| ocupación por zonas (3×3) | 15,5 % de la masa mal repartida |

## La lectura de producto, que es lo que importa

**El informe COLECTIVO es viable con lo que hay hoy.** Centroide a 1,55 m
y ocupación con 15,5 % de error bastan para decir por dónde va el juego,
cómo se mueve el bloque y qué zonas ocupa cada equipo.

**El informe POR JUGADOR no lo es.** Cada jugador está repartido en una
mediana de **6 identidades** y el recorrido total se queda un 13 % corto,
con desviaciones individuales de −40 % a +29 %. Un entrenador que
pregunte "cuánto corrió el 7" no puede tener respuesta.

Eso ordena el producto: **lo colectivo ya se puede vender; lo individual
necesita el tracker que llevamos semanas persiguiendo.**

---

# VÍA 1: ¿etiquetar el equipo por OBSERVACIÓN? (20-ago-2026)

`scripts/etiqueta_por_observacion.py`.

| estrategia | centroide | anchura | acierto PURAS | acierto CONTAM. |
|---|---|---|---|---|
| **SISTEMA REAL (referencia)** | **1,55 m** | 0,93 m | **99,7 %** | 83,8 % |
| identidad, solo color | 8,70 m | 35,84 m | 82,3 % | 83,8 % |
| **observación** | 8,57 m | **25,69 m** | **88,5 %** | **90,8 %** |
| ventana 1,0 s | 8,84 m | 29,56 m | 87,6 % | 90,8 % |
| ventana 2,0 s | 8,82 m | 29,56 m | 88,8 % | **91,1 %** |
| ventana 4,0 s | 8,92 m | 33,82 m | 89,1 % | 91,1 % |

## Lo primero: el color solo no compite

Todas las variantes de color puro dan **8,5-8,9 m de centroide frente a
1,55 m del sistema**. La diferencia no es la estrategia de etiquetado:
son las **reglas posicionales** —portero, staff, árbitro, `solo_cercanos`—
que el sistema aplica encima. Aportan muchísimo más que cualquier
refinamiento del voto.

Por eso la comparación válida es **entre las filas de color**, que
comparten esa carencia.

## Y ahí sí: por observación gana en las dos columnas

Frente a "identidad, solo color":

| | por identidad | por observación | |
|---|---|---|---|
| acierto en identidades **contaminadas** | 83,8 % | **90,8 %** | +7,0 |
| acierto en identidades **puras** | 82,3 % | **88,5 %** | +6,2 |
| anchura del bloque | 35,84 m | **25,69 m** | −10,1 |

**No hay pérdida.** La expectativa era ganar en las contaminadas y pagar
en las puras por perder el voto mayoritario; medido, **gana en ambas**.

El motivo probable: agregar sobre TODA la vida de la identidad mete
observaciones lejanas, donde el color es malo, en la media que decide la
etiqueta. El voto no es tan robusto como parecía cuando lo que promedia
está sesgado.

## El desglose por profundidad: la respuesta es MIXTA, y al revés

| estrategia | 10-20 m | 20-30 m | 30+ m |
|---|---|---|---|
| SISTEMA REAL | **100,0 %** | **98,6 %** | 84,1 % |
| observación | 92,0 % | 85,0 % | **91,7 %** |

**Por observación pierde cerca (−8 y −13,6 puntos) y gana en el fondo
(+7,6).** Es lo contrario de lo que se esperaba: el fondo, donde el color
da 0,000 separando equipos, resulta ser donde etiquetar por observación
compensa.

La explicación es coherente con todo lo demás: el sistema decide la
etiqueta con `solo_cercanos` —las observaciones próximas, donde el color
funciona— y la **propaga** a las lejanas. Cuando la identidad está
contaminada, propaga la etiqueta equivocada, y el 95 % de la
contaminación está justo en el fondo.

## Recomendación: híbrido por profundidad, no cambio global

Mantener la agregación por identidad con `solo_cercanos`, que acierta el
100 % cerca, y **permitir que las observaciones del fondo se etiqueten
solas cuando la identidad es sospechosa**. Es la misma forma que ha
funcionado antes: añadir donde falta, no sustituir lo que gana.

No adoptado: falta medirlo con las reglas posicionales puestas, que es
donde vive el 1,55 m. Esta tabla dice que la idea tiene fundamento, no
que esté lista.

---

# EL HÍBRIDO POR PROFUNDIDAD, con las reglas puestas (20-ago-2026)

`scripts/hibrido_profundidad.py`. Identidad cerca, observación en el
fondo **solo si la identidad es sospechosa**, y solo re-etiquetando lo
que decidió el COLOR: si a un portero lo fijó la regla de área o a un
árbitro el catálogo, el color no lo pisa.

| variante | centroide | anchura | ocupación | 10-20 m | 20-30 m | 30+ m |
|---|---|---|---|---|---|---|
| **SISTEMA (referencia)** | 1,55 m | 0,93 m | **15,5 %** | 100,0 % | 98,6 % | 84,1 % |
| dispersión > 0,5 | 1,51 m | 0,95 m | 15,7 % | 100,0 % | 98,6 % | 89,8 % |
| **dispersión > 0,7** | **1,34 m** | 0,91 m | 15,7 % | 100,0 % | 98,6 % | 87,9 % |
| dispersión > 0,9 | 1,55 m | 0,93 m | 15,5 % | 100,0 % | 98,6 % | 84,1 % |
| proximidad > 10 % | 1,51 m | 0,95 m | 15,7 % | 100,0 % | 98,6 % | **91,7 %** |
| **proximidad > 30 %** | 1,41 m | **0,86 m** | 15,7 % | 100,0 % | 98,6 % | 91,2 % |
| proximidad > 50 % | 1,64 m | 0,89 m | 15,5 % | 100,0 % | 98,6 % | 85,5 % |

## Cumple el criterio: mejora el fondo sin tocar lo de cerca

**Ninguna variante degrada el 100 % de cerca ni el 98,6 % de 20-30 m.**
La restricción a la banda lejana funciona: lo que ya acertaba, se queda
como estaba.

Dos puntos de operación, según qué se quiera:

- **dispersión > 0,7**: el mejor **centroide (1,34 m, −0,21)**, fondo
  +3,8 puntos.
- **proximidad > 30 %**: la mejor **anchura (0,86 m)** y el mejor
  equilibrio: fondo +7,1 puntos, centroide 1,41 m.

## Dos avisos honestos

1. **La ocupación empeora 0,2 puntos** (15,5 → 15,7 %) en todas las
   variantes que actúan. Es pequeño, pero es sistemático y no se puede
   llamar "sin degradar nada". El intercambio es favorable —21 cm de
   centroide por 0,2 puntos de ocupación— pero hay que decirlo.
2. **El tramo es de 30 s y 14 jugadores.** La diferencia entre 1,34 y
   1,41 m no es distinguible con esta muestra, y que dispersión 0,7 bata
   a 0,5 y a 0,9 puede ser ruido. Lo que sí es sólido es la dirección: el
   fondo mejora entre 4 y 8 puntos y lo de cerca no se toca.

## Nada adoptado

Falta medirlo en Villaviciosa, que es la otra pata. Y con dos puntos de
operación tan próximos, elegir entre ellos con 30 segundos de vídeo sería
elegir ruido.

## La idea simple (propagación acotada) NO sustituye al híbrido

`alcance`: propagar la etiqueta solo mientras la identidad no se aleje N
metros de donde se decidió. Rango derivado de la distribución real de
`y_obs − y_decision` (p75 = 1,6 m, p90 = 3,3 m; el primer intento usó
5-20 m y no disparaba en absoluto — cuatro filas idénticas).

| variante | centroide | 10-20 m | 20-30 m | 30+ m |
|---|---|---|---|---|
| SISTEMA | 1,55 m | **100,0 %** | 98,6 % | 84,1 % |
| alcance 1 m | 1,56 m | **95,5 %** ⚠ | 98,6 % | 88,6 % |
| alcance 2 m | 1,61 m | **95,5 %** ⚠ | 98,6 % | 87,0 % |
| alcance 3 m | 1,53 m | 100,0 % | 98,6 % | 85,8 % |
| alcance 5 m | 1,55 m | 100,0 % | 98,6 % | 83,9 % |

**No cumple el criterio.** A 1-2 m degrada lo de cerca (100 % → 95,5 %);
a 3-5 m respeta lo de cerca pero apenas toca el fondo (+1,7 puntos frente
a los +7,1 de la puerta por proximidad).

La hipótesis era buena —si `solo_cercanos` ya elige bien, el problema
sería el alcance— pero medida no se sostiene: **acotar la propagación por
distancia no distingue entre identidades sanas y contaminadas**, y acaba
cortando la propagación buena junto con la mala. El híbrido gana porque
condiciona a que la identidad sea *sospechosa*, no solo a que esté lejos.

## PENDIENTE: Villaviciosa necesita adaptar el arnés

Al lanzarlo sobre Villaviciosa salen números imposibles —centroide 13,75
m y 1,1 % de acierto en la franja cercana— así que **no se reportan**. El
arnés está escrito para el F7: campo de 62×40 m frente a 100×64, franjas
de profundidad distintas, y `processor_v4.yaml` ni siquiera declara
`config_equipos`.

Adaptarlo es trabajo, no un parámetro. Hasta entonces, **el híbrido está
medido en UNA sola pata** y no se adopta.

---

# ⚠ EL EJE ERA EL EQUIVOCADO: se corrige y el híbrido se cae (21-ago-2026)

## El fallo

Todas las "franjas de profundidad" del benjamín estaban medidas sobre el
eje **y**, que en ese campo es la **anchura**. Su config lo dice
explícitamente (`profundidad: eje: x`, cámara detrás de la portería) y yo
usaba el default de Villaviciosa.

Comprobado con los datos, no con el config:

| pata | corr(x, alto) | corr(y, alto) | lectura |
|---|---|---|---|
| Villaviciosa | +0,07 | **−0,51** | profundidad = **y**, clara |
| benjamín | +0,13 | +0,15 | **ninguna sirve** |

En el benjamín **la profundidad no es un eje**: con la cámara detrás de la
portería la distancia es RADIAL, y por eso ninguna coordenada correlaciona
con el tamaño aparente.

## La solución de raíz: TAMAÑO APARENTE de la caja

Se sustituye "franja de profundidad" por **franja de tamaño aparente en
píxeles**, con los cortes en los terciles de la distribución real. Es lo
que de verdad determina con qué resolución se ve a un jugador, es
**agnóstico a la cámara**, y vale para las dos patas y para el siguiente
cliente sin configurar nada.

## Y con la medida correcta, el híbrido NO aporta

| variante | centroide | anchura | ocupación | pequeñas | medias | grandes |
|---|---|---|---|---|---|---|
| **SISTEMA** | **1,55 m** | 0,93 m | **15,5 %** | 93,3 % | 87,8 % | 93,6 % |
| dispersión > 0,7 | 1,55 m | 0,93 m | 15,5 % | 92,5 % | 87,8 % | 93,6 % |
| proximidad > 30 % | 1,58 m | 0,89 m | 15,5 % | 93,3 % | 87,8 % | 93,6 % |
| alcance 1-5 m | 1,66-1,75 m | — | 15,8 % | 90,3 % | 88,9 % | 92,8 % |

**Ninguna variante mejora.** La mejora que se reportó (1,55 → 1,34 m) era
un **artefacto de dirigir la re-etiquetación con el eje equivocado**: se
estaba re-etiquetando la banda lateral, no los jugadores mal resueltos.

Y hay un dato que tumba la premisa entera: **el peor acierto está en la
franja MEDIA (87,8 %), no en las cajas pequeñas (93,3 %)**. Si el
clasificador no falla especialmente donde hay poca resolución, dirigir la
re-etiquetación por tamaño no puede funcionar.

## Lo que sí sobrevive

Las conclusiones medidas con **pureza, quimeras, IDF1 y cobertura** no
dependen del eje y siguen en pie: la puerta con embedding (quimeras 4→3,
mismo equipo 2→1), la partición (+6 puntos reales), el v4 con su config,
y el diagnóstico de que la contaminación nace por proximidad en metros.

Lo que se cae es todo lo que se apoyaba en franjas de profundidad del
benjamín — que ahora hay que releer como "franjas de anchura".
