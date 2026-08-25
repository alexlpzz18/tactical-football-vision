# PARTE 1: limpiar la basura del campo

*25-ago-2026. Reproducir: `python scripts/reglas_fisicas.py`
(bloques A/B/C/E/D/R; `--solo D` para la tabla de producto).*

Medido antes: sacar del bloque a quien no es una persona real vale
**0,68 m de media de centroide y el 61 % del error de anchura**, el doble
que arreglar los cruces de equipo (`docs/cruce_de_equipos.md`).

## El resultado

| variante | mediana | media | p90 | anchura | ocupación |
|---|---|---|---|---|---|
| antes | 1,55 m | 2,40 m | 5,97 m | 0,93 m | 6,7 % |
| **staff lento (ADOPTADO)** | **1,27 m** | **1,78 m** | **4,17 m** | **0,43 m** | **5,5 %** |
| + filtro físico "gratis" | 1,31 m | 1,63 m | 3,79 m | 0,52 m | 4,3 % |
| *oráculo (equipo perfecto y sin basura)* | *1,47 m* | *1,55 m* | *3,52 m* | *0,33 m* | — |

Con una sola regla, **la anchura mejora un 54 %** y el p90 del centroide
un 30 %. Y ya está por debajo del oráculo en la mediana.

## 1. El entrenador: la tolerancia sola NO puede

El barrido de `tolerancia_m` se estrella contra un muro:

| tolerancia | ids staff | obs de las 14 sacadas | obs basura | ¿saca al entrenador? |
|---|---|---|---|---|
| 0,0 - 0,2 m | 34 | **16** | 236 | SÍ |
| 0,5 - 1,0 m | 31 | 0 | 210 | no |
| **2,0 m (antes)** | 30 | 0 | 210 | no |

Y mirando quién está en la frontera:

| identidad | mediana | fuera | obs | ¿es de las 14? |
|---|---|---|---|---|
| **id 55 (entrenador)** | (31,0, −0,2) | **0,23 m** | 169 | no |
| **id 46 (jugador real)** | (27,5, 40,2) | **0,22 m** | 86 | **sí** |

**Un centímetro.** Ninguna tolerancia los separa mirando solo la posición.
Bajarla a 0 m saca al entrenador y cuesta 16 observaciones de un jugador
real. Negativo limpio: **esta vía, sola, no existe.**

⚠️ De paso, un bug del barrido: `staff._distancia_fuera` está acotada con
`max(0, ...)`, así que una tolerancia negativa no significa "dentro por
ese margen" — la comparación `0 > −1` es cierta para todo el mundo y
marcaba las 75 identidades como staff. Lo cazaron dos filas idénticas y
absurdas. El barrido usa ahora una distancia CON SIGNO.

## 2. La velocidad sola tampoco: el más lento es EL PORTERO

Velocidad media de las identidades que son personas del GT:

```
0,60 · 2,06 · 2,35 · 2,59 · 2,61 · 3,07 · 3,50 · 3,51 · 3,55 · 3,84 ·
4,15 · 4,16 · 4,23 · 4,29 · 4,74 · 5,03 · 5,47 · 6,07 · 6,39 · 6,47 ·
6,52 · 7,05  m/s
```

La primera es **el portero (0,60 m/s)**, más lento que el entrenador
(0,67). Una regla de "se mueve poco" a secas se lo lleva por delante —
que es exactamente el error que ya destrozó el doble pase.

## 3. Las dos JUNTAS sí: fuera de la línea Y lento

Porque el portero está **dentro** y el entrenador **fuera**. Es la
doctrina de siempre: no aplicar un criterio ruidoso a todo el mundo, solo
decidir mejor donde ya hay riesgo. La velocidad solo se mira en quien ya
está fuera de las líneas.

| tolerancia | velocidad | ids | obs de las 14 | obs basura | ¿entrenador? |
|---|---|---|---|---|---|
| 0,0 m | < 1,5 m/s | 11 | **0** | 61 | **SÍ** |
| 0,5 m | < 1,5 m/s | 10 | 0 | 36 | no |
| 2,0 m | sin condición *(antes)* | 28 | 0 | 202 | no |

Se adopta como **unión** con la regla de siempre, no como sustituta.

**El umbral está en una MESETA**: 1,0 · 1,5 · 2,0 · 2,5 m/s dan
resultados IDÉNTICOS. No es un filo. El hueco real va del portero (0,60)
al jugador de campo más lento (2,06); 1,5 cae en medio.

**Villaviciosa: cifras idénticas a antes.** Allí no hay a quién coger
—su GT anota a 23 personas, incluido el árbitro, y solo quedan 41
detecciones sin casar— pero tampoco rompe nada. Cumple el criterio de
adopción de Alex: mejora todas las métricas de una pata sin degradar
ninguna de la otra.

## 4. El modelo físico: correcto, y casi inútil

La homografía da la escala del suelo en cada píxel. Con el **jacobiano**,
`alto_px × escala_lateral` es la altura REAL del objeto, y la distancia
y la focal se cancelan (ver `src/tracking/plausibilidad_fisica.py`).

**El modelo es bueno, y viaja:**

| | mediana implícita | deriva de punta a punta |
|---|---|---|
| benjamín (niños de 8-9 años) | **1,50 m** | 12 % |
| Villaviciosa (adultos) | **1,63 m** | 19 % |

Distingue solo a niños de adultos, sin calibrar nada. Y las detecciones
que no son personas dan alturas implícitas absurdas: p99 de **17,86 m**.

**Pero para el producto no vale casi nada:**

| regla (encima del staff lento) | dets quitadas | efecto |
|---|---|---|
| alto máximo 1,75 | 114 | **ninguno** |
| ancho mínimo 0,10 | 6 | **ninguno** |
| ancho máximo 1,00 | 157 | **ninguno** |
| alto mínimo 0,30 | 157 | mejora media/p90/ocupación, **empeora mediana y anchura** |
| solo el filtro, sin staff lento | 320 | 1,55 → 1,50 m |

Tres de las cuatro reglas quitan detecciones y **no cambian nada**:
las que quitan ya estaban fuera del bloque. Y las 6 líneas del campo que
vio Alex mueren solo con umbrales que empiezan a costar personas reales.

**No se adopta.** Queda implementado y en off (`alto_min_frac` etc. a 0).

### Cuáles son fiables y cuáles arriesgan (pregunta 3 de Alex)

| regla | ¿fiable? | por qué |
|---|---|---|
| altura implícita **máxima** | **sí, gratis** | 0 personas perdidas hasta 1,75×; mata el fondo lejano absurdo |
| anchura implícita **máxima** | **sí, gratis** | idem |
| anchura implícita **mínima** | **hasta 0,10×** | a 0,15× ya cuesta personas; las líneas viven justo en el borde |
| altura implícita **mínima** | **hasta 0,30×** | a 0,40× cuesta 2 personas, a 0,55× cuesta 7 |
| relación de aspecto | **no** | p1 de las personas 0,27 y mediana 0,39: la banda es estrechísima, y a 0,25 ya cuesta 2 personas |
| coherencia tamaño↔posición | **es la misma cosa** | la altura implícita YA es esa coherencia, expresada en metros |

El patrón: **los máximos son gratis y los mínimos son caros**, porque una
persona parcialmente ocluida o cortada por el borde produce una caja
pequeña legítima, mientras que nada legítimo produce una caja enorme.

## 5. EL CONTROL QUE CAMBIA CÓMO SE LEE TODO: el suelo de ruido

En Villaviciosa, quitar **5 detecciones de 28.000** movía el centroide de
3,55 a 4,13 m. O el filtro es milagrosamente dañino, o el pipeline es
caótico. Se midió quitando detecciones **al azar**, 5 semillas:

| pata | quitadas | mediana | media | p90 | anchura |
|---|---|---|---|---|---|
| benjamín | 5 al azar | **sin cambio** | sin cambio | sin cambio | sin cambio |
| benjamín | 100 al azar | 1,55-1,96 | 2,25-2,54 | 4,18-5,95 | 0,93-2,68 |
| **Villaviciosa** | **5 al azar** | **3,55-4,38** | 3,87-4,85 | **6,42-8,87** | 3,81-5,06 |
| Villaviciosa | 100 al azar | 3,31-4,57 | 3,80-5,29 | 6,32-10,68 | 3,92-6,25 |

**En Villaviciosa el suelo de ruido es de 0,83 m en la mediana y 2,45 m
en el p90 para una perturbación de CINCO detecciones.** Quitar una
detección cambia una asociación, que cambia una identidad, que cambia una
etiqueta de equipo. Consecuencias:

1. La "degradación" del filtro físico en Villaviciosa **está dentro del
   ruido** y no significa nada.
2. **Ninguna comparación de Villaviciosa por debajo de ~1 m de centroide
   es interpretable**, y hay que releer con eso en la mano todo lo medido
   allí.
3. La regla adoptada **no quita ni una detección** —solo cambia
   etiquetas— así que no está sujeta a ese ruido. Por eso su resultado sí
   es sólido, y por eso las cifras de Villaviciosa salen idénticas dígito
   a dígito en vez de "parecidas".

El benjamín es estable (cero cambio con 5 detecciones al azar), así que
sus mediciones sí se pueden leer con más finura.
