# Cero cruces de equipo: la métrica, el techo y qué es viable

*25-ago-2026. Encargo de Alex tras mirar los 5 frames de
`mirar_recortes_sueltos.py`: dos bugs concretos y una propuesta de fondo.*

Reproducir:
```
python scripts/fugas_en_el_campo.py     # los dos bugs
python scripts/cruce_de_equipos.py      # la métrica, el techo, el doble pase
```

## La métrica nueva

Para el replay COLECTIVO una quimera entre compañeros es invisible: el
bloque sigue teniendo a los mismos niños en los mismos sitios. Lo que
rompe el centroide es que un jugador salga en el equipo contrario. La
métrica pasa a ser:

| sobre el sistema de hoy | valor |
|---|---|
| observaciones con el **equipo equivocado** | **59 de 729 = 8,1 %** |
| identidades que **mezclan los dos equipos** | **5** |
| *(aparte, no cuenta como fallo)* identidades que mezclan compañeros | 6 |

Y la descomposición que decide si la propuesta tiene sentido: **58 de las
59 observaciones mal etiquetadas vienen de esas 5 identidades que cruzan
equipos**. Solo 1 viene de una identidad pura mal etiquetada. O sea: el
problema es la ASOCIACIÓN, no el clasificador. La premisa de Alex era
correcta.

## El techo del veto de color

De los 25 saltos de persona dentro de una identidad:

| tipo de salto | n | ¿lo ve el color por observación? |
|---|---|---|
| entre equipos **distintos** | 13 (52 %) | **10 = 77 %** |
| entre compañeros del mismo equipo | 12 (48 %) | 0 (visten igual: no puede) |

**Coste**: entre dos observaciones seguidas de LA MISMA persona el color
dice cosas distintas en **21 de 679 = 3,1 %**. Un veto aplicado en todos
los frames haría ~21 cortes buenos para cazar 10 malos — ratio 2:1 en
contra. Fragmentar es recuperable y mezclar no, así que no lo invalida,
pero manda dónde ponerse la puerta.

## Pero el premio es pequeño, y no está donde parecía

Oráculo: misma asociación, etiqueta de equipo PERFECTA regalada.

| variante | mediana | media | p90 | anchura |
|---|---|---|---|---|
| sistema de hoy | 1,55 m | 2,40 m | 5,97 m | 0,93 m |
| + equipo perfecto | 1,47 m | 2,05 m | 4,57 m | 0,86 m |
| + **sin basura** (solo las 14 personas) | 1,55 m | 1,72 m | 3,54 m | **0,36 m** |
| + equipo perfecto **Y** sin basura | 1,47 m | **1,55 m** | 3,52 m | **0,33 m** |

⚠️ La mediana es mala resumidora: el daño está concentrado en pocos
frames. Con la mediana sola, "equipo perfecto" parece valer 0,08 m; en la
media vale 0,35 m y en el p90, **1,40 m** — y el p90 es lo que se ve en
un replay, los instantes en los que el bloque pega un salto.

**Lo que domina no son los cruces de equipo: es la BASURA.** Sacar del
bloque a quien no es ninguna de las 14 personas vale **0,68 m de media**
y, sobre todo, **se lleva el 61 % del error de anchura (0,93 → 0,36 m)**.
Un entrenador o el árbitro metidos en el bloque estiran el rectángulo
muchísimo más de lo que lo desplazan.

Y el 1,47 m de centroide que queda con equipo perfecto Y sin basura no es
identidad, ni equipo, ni basura: es **error de localización** — dónde cae
el pie proyectado.

## La simulación del doble pase (medida, no adoptada)

Partir el caché por el color de cada observación y correr el pipeline
entero una vez por equipo. No toca ByteTrack ni una línea.

| variante | obs con equipo mal | ids que cruzan | ids |
|---|---|---|---|
| sistema de hoy | 59 (8,1 %) | 5 | 84 |
| **doble pase** | **31 (4,2 %)** | 5 | 105 |
| doble pase + exclusiones de hoy | 30 (4,1 %) | 5 | 58 |

**Funciona en lo que promete**: parte por la mitad las observaciones con
el equipo equivocado. Pero en el producto:

| | centroide | anchura | ocupación |
|---|---|---|---|
| sistema de hoy | **1,55 m** | 0,93 m | 6,7 % |
| doble pase | 3,17 m | 1,05 m | 10,0 % |

### Por qué se dispara, y el error de lectura que casi cuento

Primero acusé a las reglas posicionales de romperse al fragmentarse las
identidades. **Falso**: regalarle al doble pase las exclusiones de hoy no
arregló nada (3,23 m). Después acusé a los porteros. También falso por sí
solo. La comparación honesta —los dos lados sin porteros y sin
no-jugadores— da:

| variante | centroide |
|---|---|
| sistema de hoy | 1,46 m |
| doble pase | 1,60 m |

O sea: **empate técnico**. Los 3,17 m eran un artefacto de comparar un
bloque con porteros contra otro con los porteros destrozados.

El mecanismo real, mirando un frame concreto (10440, equipo B): el doble
pase mete en el bloque a dos fantasmas —uno en (7,0, 20,5), dentro del
área cercana, y otro en (30,9, −0,3), en la banda—. **La equipación del
portero es distinta a propósito, así que su color es poco fiable; partir
el caché por color lo TROCEA entre los dos pases**, y el trozo que cae en
el pase equivocado se convierte en un jugador fantasma dentro del área,
que es el peor sitio posible para un centroide.

## Veredicto sobre las dos opciones que planteaba Alex

**(i) Doble pase.** Viable técnicamente —el pipeline ya está compuesto en
`src/tracking/perfiles.py` y `asociar_con_bytetrack` toma el caché como
argumento, así que son ~30 líneas— pero con una trampa que hay que
respetar: los índices de detección son POSICIONES dentro de la lista del
frame, así que partir el caché los desplaza y hay que remapearlos o cada
caja queda emparejada con el color de otra persona **sin fallar** (el
mismo bug que documenta `src/tracking/filtro_confianza.py`). Riesgo
principal: **destroza a los porteros**, y no paga en el producto.

**(ii) Post-proceso que parta donde el color cambia de forma sostenida.**
Menos riesgo estructural: no toca la asociación, corta después, y es
exactamente la doctrina que ya ha funcionado tres veces (actuar solo
donde hay riesgo). Con el ratio medido (21 cortes buenos por 10 malos
cazados), "de forma sostenida" no es un adorno: un veto por frame corta
demasiado. Y la puerta de re-entrada ya es esa pieza — solo habría que
darle una segunda condición.

## Lo que dicen los números que hay que hacer antes

Sacar del bloque a los que no juegan vale **el doble** que arreglar los
cruces de equipo, y es más barato. Ver `docs/fugas_en_el_campo.md`.
