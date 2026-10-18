# El tercer grupo NO se puede definir por color. Tercer intento, tercer no.

*26-ago-2026. Reproducir: `python scripts/tercer_grupo.py` y con
`--config configs/processor_villa_v4_cache.yaml --gt
data/annotations/ground_truth_tracking/annotations.xml --offset 7500`.*

El diseño tenía dos mitades: (1) definir el tercer grupo por distancia
relativa a los dos prototipos del partido, con el umbral derivado de SU
distribución; (2) separarlo por comportamiento. **La mitad 1 se cae.**

## La medición

Distancia del color medio de cada identidad al prototipo más cercano, en
unidades de la separación entre los dos prototipos:

| pata | grupo | p5 | mediana | p95 | solape con jugadores |
|---|---|---|---|---|---|
| **benjamín** | jugadores de campo | 0,27 | 0,36 | 0,56 | — |
| | porteros | 0,71 | 0,86 | 1,00 | **0 %** |
| | no son del GT | 0,36 | 0,85 | 0,97 | 17 % |
| **Villaviciosa** | jugadores de campo | **0,19** | **0,53** | **0,80** | — |
| | porteros | 0,75 | 0,78 | 0,80 | **50 %** |
| | árbitro | 0,60 | 0,77 | 0,94 | **50 %** |

En el benjamín parece funcionar: los porteros no se solapan nada con los
jugadores. **En Villaviciosa no funciona**: la mitad del rango de los
porteros y del árbitro cae dentro del p5-p95 de los jugadores.

## El diagnóstico, que corrige el que estaba escrito

La nota que había en el config decía que la causa era el árbitro: *"el
amarillo del árbitro no está lejos de los dos prototipos"*. No es eso.

La causa está en el **otro** lado de la comparación: **los jugadores de
campo de Villaviciosa están dispersos** (0,19 a 0,80) mientras que los del
benjamín están apretados (0,27 a 0,56). No es que los no-jugadores estén
cerca del prototipo: es que la mitad de los jugadores está lejos del suyo,
porque en la mitad lejana del campo su recorte es ruido.

Y eso explica por qué ninguna forma de elegir el umbral lo arregla: **el
problema no es el umbral, es que las distribuciones se pisan**. Derivarlo
de la distribución, que era el elemento nuevo de este tercer intento, no
puede cambiar eso.

## Consecuencia para el diseño

**El tercer grupo no lleva puerta de color.** Se define por
COMPORTAMIENTO, aplicado a TODAS las identidades y no a un subconjunto
preseleccionado por color.

Y hay precedente de que funciona: la regla del portero por último hombre
**ignora el color por completo** —hasta el punto de que tiene que incluir
a las identidades que el color mandó a 'otro'— y da 8 de 8 en las dos
patas. La regla del staff lento tampoco mira el color. Las dos reglas que
han pasado el banco esta semana son posicionales.

Queda como tercer negativo de la misma idea (umbral absoluto → no viaja;
umbral relativo barrido → no aporta; umbral derivado de la distribución →
las distribuciones se pisan). Por la regla de Alex —dos intentos y se
abandona— esta vía se cierra.

## Lo que sí queda por construir

El tercer grupo como **unión de reglas de comportamiento**, cada una con
su propia abstención:

- **portero**: hecho y adoptado (`docs/portero.md`).
- **árbitro**: recorre todo el campo de área a área, está entre los dos
  porteros y no por detrás de ninguno, mayor dispersión longitudinal del
  partido, mediana cerca del centro. Más el catálogo de equipaciones, que
  sí es absoluto y sí viaja, con su regla de conflicto.
- **staff**: franja estrecha junto a la banda, siempre del mismo lado,
  recorrido lateral y no de área a área, y sobre todo PERMANENCIA. Ya hay
  media regla hecha (el staff lento).
