# La foto completa: las dos patas, antes y ahora (28-ago-2026)

Encargo de Alex. Todo contra el GT de CVAT de cada pata, con el pipeline
de PRODUCCIÓN y **el mismo arnés en las cuatro filas** —
`scripts/foto_de_estado.py`, con `--antes` reconstruyendo el estado
anterior a esta semana desde config (portero por área, catálogo por
identidad, staff sin distancia con signo).

⚠️ **Estos números NO son comparables con los de `docs/resumen_semana.md`**
(1,30 → 0,97 m, etc.): aquellos salieron de otro banco, sin etiqueta por
observación y con casado a la fila más cercana en vez de 1-a-1. Es la
razón de tener una tabla con un solo arnés.

| pata | centroide | anchura | ocupación | A ok | B ok | ambos | equipo mal |
|---|---|---|---|---|---|---|---|
| **benjamín, antes** | 1,18 m | 0,39 m | 6,6 % | 62 % | 13 % | 8 % | 1,2 % |
| **benjamín, AHORA** | **0,86 m** | 0,39 m | **4,1 %** | 62 % | **45 %** | **25 %** | 1,2 % |
| **Villaviciosa, antes** | 4,37 m | 4,81 m | 16,7 % | 17 % | 9 % | 0 % | 23,6 % |
| **Villaviciosa, AHORA** | 4,37 m | 4,81 m | 16,7 % | 17 % | 9 % | 0 % | 23,6 % |

**Villaviciosa es idéntica columna por columna.** No es que le lleguen la
mitad de las mejoras del mes: no le llega **ninguna**.

Y la distancia entre patas es de otro orden: **1,2 % de equipo equivocado
en el benjamín contra 23,6 % en Villaviciosa**, veinte veces.

## ¿Y si se activa `por_observacion` en Villaviciosa? Medido

| variante | centroide | anchura | ocupación | A ok | equipo mal |
|---|---|---|---|---|---|
| apagado (hoy) | 4,37 m | 4,81 m | 16,7 % | 17 % | 23,6 % |
| solo la ventana A/B | **4,67 m** | 5,18 m | 18,2 % | 14 % | 22,3 % |
| ventana + catálogo | 4,10 m | 5,63 m | 18,0 % | 15 % | 21,1 % |
| solo catálogo | **3,89 m** | 4,96 m | **15,9 %** | 18 % | 22,3 % |

La ventana A/B sola **empeora** el centroide (4,37 → 4,67), que confirma
el negativo ya registrado: allí el recorte suelto es ruido y lo que salva
es promediar.

## ⚠️ Y el "solo catálogo" es un ESPEJISMO: el control lo tumba

Parecía la mejor Villaviciosa de la historia (3,89 m, el centroide por
debajo de 4 por primera vez). Se comprobó **qué saca de los equipos**, y
de las 90 observaciones que caen en frames del GT:

| | |
|---|---|
| jugador del equipo B | 39 |
| jugador del equipo A | 36 |
| portero_B | 7 |
| sin casar con el GT | 8 |
| **árbitro** | **0** |

**Cero árbitros.** La mejora del centroide sale de **quitar jugadores**,
que aprieta el bloque artificialmente. Es el fracaso canónico de los tres
intentos anteriores de tercer grupo por color, con otra cara.

> **El catálogo arbitral por observación NO viaja al F11.** En el
> benjamín caza al árbitro (recuento de B 13 % → 43 %, un jugador
> sacrificado de 814); en Villaviciosa saca 82 jugadores y ningún
> árbitro.

La causa es la misma que ya está medida para `por_observacion`: allí los
recortes están lejos y son ruido, así que la media de una ventana corta
se pasea por los arquetipos arbitrales. **Donde el recorte es señal,
decidir por recorte gana; donde es ruido, lo que salva es promediar.**

`agregacion.por_observacion.solo_catalogo` queda implementado y **apagado**:
separa dos cosas que estaban acopladas en el código y sirve para volver a
medirlo el día que el F11 tenga recortes mejores.
