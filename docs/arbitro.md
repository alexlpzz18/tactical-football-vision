# El árbitro: los cinco criterios fallan, y no compensa perseguirlo

> ✅ **Verificado el 27-ago-2026**: el recuadro verde es el color que el
> VÍDEO da a una caja sin etiqueta; no existe en la pizarra. El vídeo
> nunca tuvo el bug del renderizador (`docs/pizarra_colapsaba.md`), así
> que esta observación se mantiene.


*26-ago-2026. Reproducir: `python scripts/arbitro_criterios.py`.*

⚠️ **El GT del benjamín NO anota al árbitro** (14 tracks: 12 jugadores y 2
porteros). Solo el de Villaviciosa lo tiene (track 22). Así que la
medición contra verdad de posición solo se puede hacer en una pata.

## Los tres criterios de Alex, medidos: los tres fallan

| criterio | puesto del árbitro | él | el mejor jugador |
|---|---|---|---|
| dispersión longitudinal (max−min de x) | **14º de 23** | 20,9 m | 32,7 m |
| desviación típica de x | **18º de 23** | 4,6 m | 7,5 m |
| mediana cerca del centro | **11º de 23** | 11,3 m | 0,2 m |
| entre los dos porteros | empatado | 100 % | **20 de 22 jugadores también al 100 %** |

El árbitro **se mueve MENOS** que la mayoría de los jugadores, no más. Y
"entre los dos porteros" no discrimina nada: los porteros definen un
intervalo que ocupa casi todo el campo, así que todo el mundo está
dentro.

## Y dos señales alternativas mías, también fallan

| señal | puesto del árbitro |
|---|---|
| ¿de qué bloque es? \|d(centroide A) − d(centroide B)\| / suma | 7º de 23 |
| distancia al vecino más cercano (estar solo) | 11º de 23 |

Los jugadores salen MÁS equidistantes de los dos bloques que el árbitro, y
los que están más solos son los porteros.

## Por qué fallan: la ventana

Los tres criterios de Alex hablan de un **partido entero** —"recorre el
campo de área a área"— y la ventana medida son **50 segundos**. En 50 s el
árbitro no cruza el campo: sigue al balón, que se queda en una zona,
mientras un lateral sí hace una carrera larga. Puede que los criterios
sean ciertos en 90 minutos; con lo que hay no se puede saber, y no se
adopta lo que no se puede medir.

## Pero, sobre todo: no compensa

Coste de contar al árbitro como un jugador más, medido sobre el GT de
Villaviciosa metiéndolo en cada equipo:

| | centroide | anchura |
|---|---|---|
| árbitro colado en el equipo A (12 jugadores) | **0,41 m** | **0,00 m** |
| árbitro colado en el equipo B (10 jugadores) | **0,61 m** | **0,00 m** |
| *para comparar: error del sistema hoy* | *3,55 m* | *3,81 m* |
| *para comparar: suelo de ruido de esa pata* | *0,83 m* | *1,25 m* |

**El daño está POR DEBAJO del suelo de ruido de la pata**, y es una
séptima parte del error actual. Perseguir al árbitro no paga.

### Y explica por qué el entrenador sí pagaba

El entrenador (regla del staff lento) valía 0,68 m de media de centroide
y **0,57 m de anchura**; el árbitro vale 0,41-0,61 m y **cero** de
anchura. La diferencia no es que uno sea más "no jugador" que el otro:

> **Lo que rompe el bloque es estar en el BORDE, no ser un no-jugador.**

Un entrenador en la banda estira el rectángulo; un árbitro en medio del
juego se mezcla con la nube de jugadores y apenas mueve la media. Es la
misma lección que la descomposición del centroide: la basura costaba el
61 % del error de anchura porque estaba en los extremos.

## Estado

Línea **cerrada por ahora**, con dos salidas si alguna vez interesa:

1. **Un tramo más largo con GT.** Los criterios de dispersión necesitan
   minutos, no segundos. Habría que anotar al árbitro en un tramo de
   varios minutos — y en el benjamín, anotarlo por primera vez.
2. **El catálogo de equipaciones**, que es lo único que ha funcionado: en
   el benjamín caza al árbitro a nivel de identidad (583 observaciones,
   verde flúor → 'otro'). En Villaviciosa no lo caza, y su color está a
   0,60-0,94 de los prototipos, solapando el 50 % con los jugadores.

Lo siguiente del tercer grupo es el **staff**, que además ya tiene media
regla hecha y cuyo daño sí está medido y es grande.

---

# El enfoque correcto era DESCARTAR, no identificar

*26-ago-2026, corrección de Alex. Reproducir: `python scripts/censo_otros.py`.*

No hay que encontrar al árbitro entre 23 candidatos: hay que contar y
descartar. Dentro del campo hay tres grupos, y en "otros" deberían quedar
tres personas —los dos porteros, ya identificados con 8 de 8, y el
árbitro—. Mismo principio que la exclusividad un-portero-por-área.

## El censo: el embudo funciona mucho mejor de lo que temíamos

| filtro | benjamín | Villaviciosa |
|---|---|---|
| todas las identidades | 67 | 79 |
| ni A ni B | 30 | 8 |
| + dentro del campo (geométrico) | 4 | 4 |
| + quitando los porteros | **2** | **2** |
| + quitando el staff | 2 | 2 |
| + con ≥25 observaciones | **2** | **2** |

El filtro geométrico es el que hace el trabajo pesado: en el benjamín
tira 26 de 30 (público, árboles proyectados a 176 m, entrenadores). No
quedan quince: quedan **dos**, en las dos patas.

## Quiénes son las dos, y el error de lectura que casi cometo

| pata | id | obs | **casadas con el GT** | mediana | qué es |
|---|---|---|---|---|---|
| benjamín | 28 | 493 | **1** | (31,0 · 24,0) | *"jugador"* → **es el ÁRBITRO** |
| benjamín | 1 | 204 | **0** | (24,3 · 22,2) | no es del GT |
| Villaviciosa | 67 | 136 | 27 | (66,3 · 33,8) | **árbitro** |
| Villaviciosa | 40 | 110 | 22 | (49,2 · 28,9) | jugador |

⚠️ La identidad 28 del benjamín salía etiquetada "jugador" y **eso se
apoyaba en UNA sola observación casada de 493**. Con 493 observaciones en
el centro exacto del campo, verde flúor (H=62, S=248), es el árbitro —
coincide con la descripción que ya estaba en el config. Lo delató añadir
la columna de observaciones casadas: **un dueño mayoritario sobre 1 voto
no es un hecho.**

## Y la vía sale gratis, con un parámetro que ya existía y estaba apagado

La segunda identidad de Villaviciosa (id 40, 110 obs, centro del campo) es
literalmente **el bug que ya estaba anotado** en `arbitro.py`: un jugador
que el catálogo roba porque su color se aparta del prototipo de su equipo.
El arreglo estaba escrito y en off: `arbitro.margen_equipo`.

| margen | benjamín: quedan | Villaviciosa: quedan |
|---|---|---|
| 0,00 | 2 | 2 |
| 0,50-0,60 | 2 | **1 (el árbitro)** |
| **0,65-0,75** | **1 (el árbitro)** | **1 (el árbitro)** |
| 0,80-0,90 | **0** (se pierde) | 1 (el árbitro) |

**Con `margen_equipo` entre 0,65 y 0,75, en las dos patas queda
exactamente el árbitro.** Villaviciosa tiene meseta ancha (0,50-0,90); el
benjamín, una ventana estrecha de tres puntos con acantilado en 0,80. El
centro común es **0,70**.

Coste en producto:

| pata | margen | mediana | media | p90 | anchura | ocupación |
|---|---|---|---|---|---|---|
| benjamín | 0,00 | 1,30 m | 1,64 m | 3,25 m | 0,64 m | 4,0 % |
| benjamín | **0,70** | 1,30 m | 1,64 m | 3,25 m | 0,64 m | 4,0 % |
| Villaviciosa | 0,00 | 3,55 m | 3,87 m | 6,42 m | 3,81 m | 9,0 % |
| Villaviciosa | **0,70** | 3,65 m | 3,95 m | 6,53 m | 3,81 m | 9,5 % |

Idéntico en el benjamín; en Villaviciosa se mueve 0,10 m, **muy por
debajo de su suelo de ruido (0,83 m)**, así que no es interpretable como
degradación — pero tampoco mejora. Por el criterio de adopción no entra
solo: es decisión de Alex.

## Estado

- El árbitro **sale por eliminación** en las dos patas, sin necesidad de
  ninguna señal de comportamiento. Los cinco criterios medidos antes
  siguen siendo negativos, pero ya no hacen falta.
- Lo que lo hace posible no es una regla nueva: es el **filtro geométrico**
  (que ya está) más **`margen_equipo: 0.70`** (que ya estaba escrito y
  apagado).
- Sigue valiendo menos que el suelo de ruido, así que no se ha invertido
  más de lo que costaba.

---

# ⛔ Y el margen se revirtió el mismo día: la ventana se mueve con el detector

*26-ago-2026, horas después de adoptarlo.*

Alex pidió dos cosas al adoptar `margen_equipo`: elegir el centro de la
zona común (0,68 en vez de 0,70) y **una guarda por si en otro campo se
cae**. Se cayó antes: en el mismo partido, con otro caché.

| caché | margen 0,00 | margen 0,68 |
|---|---|---|
| benjamín **v3** (producción) | 18 de 309 = 5,8 % | 18 de 309 = 5,8 % |
| benjamín **v4** | 26 de 380 = 6,8 % | **85 de 380 = 22,4 %** |

*(fugas = detecciones que no son ninguna de las 14 personas y salen
etiquetadas como jugador)*

Con el caché v4, el margen 0,68 deja fuera al **árbitro** —583
observaciones en el centro del campo— y se cuela entero en el equipo B.
El valor al que el árbitro sobrevive es **0,62-0,75 con el v3 y ≤0,50 con
el v4**: no hay ningún valor común.

No es que la ventana sea estrecha: es que **se mueve con el detector**.
Mismo patrón que ya conocíamos —"los parámetros van pegados al
detector"— pero aquí la consecuencia es que el parámetro no existe.

## La lección de método: contar no basta

La guarda que se añadió (`avisar_tercer_grupo`) contaba las identidades
del tercer grupo y exigía que fuera 1. **Daba el visto bueno** en el caso
roto: quedaba 1 identidad… pero no era el árbitro, era otra persona, y el
árbitro estaba dentro del equipo B.

> Una guarda que cuenta no puede detectar un fallo de IDENTIDAD.

Se añade la que sí lo habría cazado, en `arbitro.py`: **avisar cuando el
margen veta a una identidad grande** (≥100 observaciones) que casaba un
arquetipo arbitral. Ese es el evento, y es observable sin GT.

## Estado

- `margen_equipo` vuelve a **0,0**.
- El árbitro **sigue saliendo por eliminación** en las tres patas, solo
  que acompañado de una segunda identidad. Para quedarse con una sola
  haría falta separar esas dos, y el color no puede.
- El **bug del id 40 de Villaviciosa** (jugador robado por el catálogo)
  sigue sin arreglar: era lo que el margen resolvía.
- Lo bueno: las fugas de hoy están en **5,8 % (v3) y 6,8 % (v4)**, contra
  el 13,4 % que se midió antes de esta semana. El staff lento y el
  portero por último hombre ya se llevaron la mitad.

---

# Un solo árbitro: la exclusividad (adoptada) y su limitación

*26-ago-2026. Alex, viendo el vídeo: "hay que dejar claro que dentro del
campo solo puede haber un árbitro".*

Implementada en `arbitro.py::un_solo_arbitro`, misma forma que la
exclusividad un-portero-por-área: conocimiento del reglamento, **no un
umbral**, así que no puede moverse con el detector como se movió
`margen_equipo`.

| pata | candidato | obs | distancia al prototipo | qué es |
|---|---|---|---|---|
| benjamín | **28** | **493** | **0,76** | **el árbitro** |
| benjamín | 1 | 204 | 0,60 | otro |
| Villaviciosa | **67** | **136** | **0,96** | **el árbitro** |
| Villaviciosa | 40 | 110 | 0,40 | un jugador robado |

Las dos señales hacen falta: por observaciones el margen es 2,4× y solo
1,24×; por color 1,27× y 2,4×. **Multiplicadas, 3,0× en las dos patas.**
Producto idéntico a antes en las dos.

## ⚠️ Limitación conocida: NO se abstiene

Si en el tramo no hay árbitro, corona igualmente al mejor candidato.
Verificado borrando al árbitro del caché de Villaviciosa: corona a la
identidad 39 (106 obs). **No es una regresión** —ese candidato ya estaba
fuera del cómputo por estar en 'otro'— pero al revés que la regla del
portero, que sí sabe decir "aquí no hay portero", esta no.

**Una forma barata de resolverlo, si algún día interesa** (no construida):
exigir que el coronado recorra el campo. El árbitro, aunque en 50 s no
cruce de área a área, sí se mueve con el juego; los candidatos falsos que
han aparecido son fragmentos casi estáticos o gente de un punto fijo. La
señal sería la MISMA que ya usa el staff lento —velocidad media— pero al
revés: exigir un mínimo en vez de un máximo. Está por medir: el árbitro
del benjamín va a 1,91 m/s y el de Villaviciosa a 2,68, mientras que la
identidad 39 del caso negativo habría que mirarla.

## Dos cosas que hubo que corregir midiendo

- **El orden.** Puesta ANTES de la regla de porteros, ganaba un portero
  (Villaviciosa, identidad 19 con 498 observaciones) y el árbitro de
  verdad volvía al equipo A. La guarda `avisar_tercer_grupo` lo cazó
  avisando de "TERCER GRUPO VACÍO". Va después de porteros.
- **No se devuelve el equipo por color** a los no coronados: al jugador
  robado de Villaviciosa (equipo A) el clasificador lo manda a B — es
  justo el color que engañó al catálogo, así que pedirle a ese mismo
  color que lo reasigne es circular. Devolviéndolos, el centroide
  empeoraba de 3,55 a 3,65 m. Se quedan en 'otro'.

## La puerta de distancia, RE-MEDIDA POR OBSERVACIÓN (27-ago-2026): el negativo aguanta

Alex, con razón: *"el negativo anterior puede estar midiendo otra cosa"*.
El negativo del catálogo (`agregacion_dist_max_prototipo`, apagado) se
midió **por identidad**, y desde entonces existe `etiquetar_por_observacion`.
Así que se rehizo por OBSERVACIÓN, sobre la parte entera del benjamín.

Y de entrada aparece una separación que el negativo viejo no reportaba —
distancia al prototipo más cercano, en unidades de la separación A-B:

| | p25 | mediana | p75 |
|---|---|---|---|
| tercer grupo (el árbitro) | 0,69 | **1,08** | 1,16 |
| id 12 (árbitro que sale como B) | 0,79 | **1,14** | 1,17 |
| jugadores | 0,49 | **0,61** | 0,86 |

Casi 2× en la mediana. Pero la mediana no decide una puerta: la decide el
solape de las colas, y ahí se cae.

| umbral | obs del árbitro cazadas | obs de jugador perdidas |
|---|---|---|
| 0,80 | 70,4 % | 29,1 % |
| 0,95 | 53,9 % | 21,0 % |
| **1,00** | **51,9 %** | **19,3 %** |
| 1,10 | 48,9 % | 16,6 % |

En proporción parece 2,5 a 1 a favor, pero **hay muchísimos más jugadores
que árbitro**. En números absolutos, a 1,00: se rescatan ~3.500
observaciones de árbitro y se tiran ~27.600 de jugador. **Ocho jugadores
perdidos por cada árbitro cazado.**

> El color NO separa al árbitro, ni por identidad ni por observación. La
> re-medición estaba justificada y el negativo aguanta.

## Dónde está el problema de verdad (medido en la parte entera)

El tercer grupo recoge **el 54 % de los frames** del partido. El otro
46 % del tiempo el árbitro ya está dentro de un equipo **antes** de que
la exclusividad lo vea: `un_solo_arbitro` solo reparte entre quien ya
está en 'otro'. El id 12 es uno de esos, y **no lo bloqueó
`margen_equipo`** (está en 0,0, el catálogo podía hablar): fue el
arquetipo absoluto el que no reconoció ese trozo.

Y el tercer grupo tiene la misma forma que tenía el portero: de sus 10
identidades, **7 no coexisten nunca** — es una persona partida en trozos.
La exclusividad corona a uno y deja nueve sin decidir.

Dos líneas abiertas, en este orden:

1. **Meter al árbitro en el tercer grupo** (el 46 % que se escapa). Es
   aguas arriba y es donde está el volumen.
2. **Coronar al CONJUNTO**, como se hizo con el portero, con la
   restricción física de que dos trozos simultáneos no son la misma
   persona (el par 155/129 coexiste 520 frames: ahí hay un jugador).

Para (1), la forma que ya ha pagado tres veces en este proyecto son **dos
señales débiles que juntas son fuertes**: la distancia al prototipo no
vale sola —está medido arriba— pero como desempate junto al
comportamiento puede valer, porque cada impostor falla al menos una.

## El 46 % que no llega al tercer grupo: no es ninguna de las tres (27-ago-2026)

Alex, con razón: *"llevamos dos sesiones puliendo una regla que solo
alcanza a la mitad del problema"*. El tercer grupo recoge el 54 % de los
frames; el otro 46 % ya está en un equipo cuando la exclusividad lo mira.
Sus tres hipótesis eran el fit, el suavizado de 1,5 s, o el arquetipo.

**Es una cuarta, y explica las tres: en un recorte suelto el árbitro NO
existe.**

| distancia al prototipo del ÁRBITRO | p10 | mediana | p90 |
|---|---|---|---|
| observaciones del árbitro | 0,799 | **0,884** | 0,959 |
| observaciones de jugador | 0,891 | **0,936** | 0,971 |

Se solapan casi por completo. Un torso de 15-40 px del árbitro no se
distingue del de un jugador. Y sin embargo, promediando 400 recortes, dos
muestras independientes suyas distan **0,0545** entre sí y **0,59-0,65**
de los equipos: **el verde flúor solo aparece al promediar**.

Cuántos recortes hacen falta para que la media lo delate (arquetipo
disparando sobre una muestra PURA de árbitro):

| N recortes | 5 | 10 | 15 | **25** | **40** | 100 |
|---|---|---|---|---|---|---|
| dispara | 40 % | 62 % | 75 % | **85 %** | **100 %** | 100 % |

Con eso, las tres hipótesis quedan contestadas de una vez:

- **(a) el fit** no se equivoca: un recorte suelto genuinamente no dice
  "árbitro". Está haciendo lo mejor posible con lo que tiene.
- **(b) el suavizado de 1,5 s** promedia ~15 recortes, que es el 75 %.
  Está POR DEBAJO del umbral donde nace la señal. Subirlo no es la
  solución: arrastraría al vecino durante más tiempo.
- **(c) el arquetipo** es el único mecanismo que promedia bastante, y su
  alcance está limitado por lo LARGAS Y PURAS que sean las identidades
  del árbitro. Con `min_observaciones: 25` acierta el 85 %; por debajo de
  25 ni siquiera juzga.

> **El árbitro no es un problema de color: es un problema de ASOCIACIÓN
> disfrazado.** Solo es alcanzable a través de identidades largas y
> puras, así que llega gratis el día que se arregle la asociación — que
> ya es el problema número uno (CLAUDE.md, 20-ago-2026).

## Y la salida de producto tampoco sale barata

Alex propuso: *"pintar como 'otro' cualquier identidad dudosa en vez de
asignarla a un equipo"*. Medido a nivel de IDENTIDAD (≥40 recortes, que
es donde la media sí tiene señal):

| | p10 | mediana | p90 |
|---|---|---|---|
| identidades de árbitro (n=8) | 0,57 | **0,62** | 0,84 |
| identidades de jugador (n=230) | 0,27 | **0,37** | 0,68 |

| umbral | árbitros cazados | jugadores sacrificados |
|---|---|---|
| 0,50 | 100 % | 24,3 % |
| 0,60 | 75 % | 14,8 % |
| 0,70 | 37,5 % | 7,0 % |

Separa mejor que por observación, pero no lo bastante: a 0,50 son **8
árbitros a cambio de ~56 identidades de jugador** mandadas a 'otro'. Y
eso es exactamente lo que Alex dice que un entrenador no perdona — equipos
con cinco jugadores en vez de siete. **No hay punto de operación bueno.**

## Veredicto

Línea cerrada. No hay causa barata: el arreglo pasa por la asociación, y
el árbitro colado cuesta 0,41-0,61 m de centroide y CERO de anchura, por
debajo del suelo de ruido. Vuelve solo cuando la asociación mejore.
