# El suelo de ruido de Villaviciosa, y qué queda invalidado

*25-ago-2026. Reproducir: `python scripts/suelo_de_ruido.py`
(métricas del banco) y `python scripts/reglas_fisicas.py --solo R`
(métricas de producto).*

## El hallazgo

Quitando **5 detecciones de 10.040 elegidas al azar** —una perturbación
que no debería cambiar nada— las métricas de Villaviciosa se mueven así
(6 semillas, corriendo el pipeline exactamente como producción):

| métrica | sin perturbar | con 5 al azar | dispersión |
|---|---|---|---|
| cobertura | 0,636 | 0,589-0,636 | **0,047** |
| accuracy de equipos | 0,804 | 0,719-0,804 | **0,085** |
| IDF1 | 0,542 | 0,538-0,542 | 0,004 |
| quimeras | 4 | 4 | 0 |
| centroide (mediana) | 3,55 m | 3,55-4,38 m | **0,83 m** |
| centroide (p90) | 6,42 m | 6,42-8,87 m | **2,45 m** |
| anchura | 3,81 m | 3,81-5,06 m | **1,25 m** |

**El benjamín no se mueve nada** con la misma perturbación.

## El canal, aislado con un interruptor

Repitiendo lo mismo pero **congelando el fit del clasificador de color**:

| perturbación | cobertura | equipos |
|---|---|---|
| 5 al azar, fit normal | 0,589-0,636 | 0,719-0,804 |
| 5 al azar, **fit congelado** | **0,635-0,636** | **0,804-0,807** |

El ruido desaparece. **No es la asociación: es el fit del color.** Medido
además detección a detección: en la semilla que se desvía cambian de
equipo 1.411 de 9.507 detecciones y solo 55 de identidad.

### La causa raíz, localizada

`TeamClassifierColor._umbral_auto` elige el umbral de fusión jerárquica
por **argmax sobre una rejilla** (0,50 a 1,30 de 0,05 en 0,05). Es una
decisión DISCRETA, y cuando dos puntos de la rejilla van casi empatados
una detección de más hace saltar al ganador:

| pata | umbral | salta con 5 detecciones al azar |
|---|---|---|
| Villaviciosa | 0,90 → 0,75 | **2 de 10 perturbaciones** |
| benjamín | 1,10 | **0 de 10** |

Al saltar el umbral cambia la partición A/B entera, y con ella la
etiqueta de equipo de miles de detecciones a la vez. Por eso el ruido es
**bimodal**: casi todas las perturbaciones no hacen nada, y de vez en
cuando una lo vuelca.

## ⚠️ Cómo se usa esto, que NO es una barra de error

La tentación es restar: "la diferencia es 0,05 y el ruido 0,085, luego no
vale". **Está mal.** Un A/B determinista sobre el MISMO caché no tiene
ruido: si cambias `min_obs_para_otro` de 0 a 25 y la accuracy sube 0,054,
ese 0,054 es exacto.

Lo que el suelo de ruido dice es otra cosa: **que la métrica es frágil
ante cambios triviales de la entrada**, y por tanto que una diferencia
pequeña medida UNA VEZ puede no sobrevivir a otro tramo, otra pasada del
detector o un reencode.

El test correcto no es comparar contra una barra: es **repetir el A/B
sobre entradas perturbadas y mirar si el SIGNO aguanta.**

## Aplicado a las dos decisiones que están en producción

**1. `agregacion.min_obs_para_otro: 25` — SOBREVIVE.**

| perturbación | otro=0 | otro=25 | delta |
|---|---|---|---|
| ninguna | 0,750 | 0,804 | +0,054 |
| 5 al azar (s1) | 0,509 | 0,719 | **+0,211** |
| 5 al azar (s2-s5) | 0,750 | 0,804 | +0,054 |

Signo constante en las 6, y en la semilla donde el fit salta la regla
**protege**: recupera 0,21 de accuracy. Adopción confirmada.

**2. El v4 contra el v4pre en Villaviciosa — SOBREVIVE.** Cada detector
con SU caja de cambios, 6 condiciones cada uno:

| métrica | v4pre | v4 | |
|---|---|---|---|
| quimeras | 5-6 | **4-4** | rangos separados |
| cobertura | 0,555-0,567 | **0,589-0,636** | rangos separados |
| IDF1 | 0,437-0,445 | **0,538-0,542** | rangos separados |

Confirma lo que ya decía CLAUDE.md (el v4 bate al v4pre en Villaviciosa
con su propia configuración) y añade que **es robusto**. La no-adopción
del v4 sigue apoyada en la otra pata, el benjamín, que aquí no se toca.

## Qué queda EN CUARENTENA

No "invalidado" —puede que sean ciertas— sino **medido una sola vez, con
una diferencia por debajo de lo que una perturbación trivial produce, y
sin el test de supervivencia del signo**. No se pueden citar como
establecidas hasta que se repitan:

| afirmación | dónde | diferencia | suelo |
|---|---|---|---|
| radio del fit 25 vs 30 mejora equipos | `experimentos_tracking.md` | +0,026 | 0,085 |
| `dist_max` relativo 1,0 hunde la accuracy | `team_classification.yaml` | 0,718 → 0,682 | 0,085 |
| cobertura del v4 vs v4pre con la caja del v4pre | `apariencia_en_asociacion.md` | 0,559 → 0,598 | 0,047 |
| cualquier comparación de centroide de Villaviciosa | `banco_producto.md` | < 0,83 m | 0,83 m |
| cualquier comparación de anchura de Villaviciosa | `banco_producto.md` | < 1,25 m | 1,25 m |

**Lo que NO está en cuarentena** porque su diferencia es varias veces el
suelo: el fit `solo_cercanos` (cobertura 0,376 → 0,456), ByteTrack contra
el candidato (quimeras 5 vs 24), y todo lo medido en el **benjamín**,
donde el fit no salta nunca.

## Tarea abierta: estabilizar el umbral de fusión

Quitaría ruido de TODAS las mediciones de Villaviciosa de golpe. Tres
candidatos que hay que medir contra el mismo experimento de perturbación:

1. **Promediar sobre la meseta**: en vez de `argmax`, quedarse con el
   centro del tramo de umbrales cuya puntuación esté a menos de un ε del
   máximo. Es lo más parecido a lo que ya se hace con otros umbrales del
   proyecto.
2. **Interpolar** la puntuación alrededor del máximo en vez de tomar el
   punto de la rejilla.
3. **Promediar los PROTOTIPOS** de los umbrales empatados, en lugar de
   elegir uno.

El criterio de éxito es doble y hay que exigir los dos: que la dispersión
bajo perturbación caiga a la del fit congelado (0,001 en cobertura,
0,003 en equipos) **y** que las métricas sin perturbar no empeoren.
