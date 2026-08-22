# Banco de métricas de PRODUCTO (20-ago-2026)

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
