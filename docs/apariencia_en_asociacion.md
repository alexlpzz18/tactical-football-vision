# La apariencia en la ASOCIACIÓN, no solo en el cosido

Diseño abierto el 17-ago-2026, después de que el v4 cerrara la vía de la
detección. **No implementado**: esto es el plan, no el resultado.

## El hallazgo que obliga a esto

El v4 (mAP50 0,944 frente a 0,900) mejoró todo lo medible en Villaviciosa
—cobertura 0,559→0,598, IDF1 0,453→0,484, tasa de IDSW 0,123→0,100,
concurrencia 25→23— **y subió las quimeras de 5 a 8**.

No es una anomalía, es la consecuencia. El v4 fragmenta menos (115→83
identidades con más cobertura), o sea produce identidades más largas, y
una identidad larga tiene más ocasiones de contener a dos personas. Mejor
detección compra continuidad, y la continuidad es lo que convierte un
cruce mal resuelto en una quimera con recorrido.

El id 4 del benjamín lo enseña sin promedios: esa identidad del v4pre la
cubren **cinco** identidades del v4, cuando la mediana es 1. El v4 parte
la quimera pero no la resuelve: la reparte.

**Conclusión: la quimera de cruce no es un problema de detección.** Se ha
descartado empíricamente. Tampoco es del clasificador (los tres casos con
nombre resistieron el barrido del fit). Queda la ASOCIACIÓN: el instante
en que dos cajas se solapan y ByteTrack decide con IoU en píxeles, que es
justo la magnitud que deja de distinguir cuando dos cajas se superponen.

Es el mismo diagnóstico por el que BoT-SORT añade ReID a SORT: el coste
de emparejamiento no puede ser solo geométrico si la geometría es
ambigua. Nosotros ya tenemos la apariencia —la firma de color por
identidad— pero la usamos **después**, en el cosido, cuando el daño ya
está hecho. Ahí no puede deshacer una mezcla: solo puede unir trozos.

## El obstáculo real de implementación

`sv.ByteTrack.update_with_detections()` es una caja cerrada: recibe cajas
y confianzas y devuelve ids. **No hay dónde inyectar un coste de
apariencia** sin reescribir la asociación. Eso deja tres caminos, en
orden creciente de coste y de riesgo.

### Camino A — veto de apariencia SOLO en el instante de cruce

El más barato y el que mejor respeta lo aprendido. No se toca ByteTrack:
se detectan los frames donde dos cajas se solapan por encima de un umbral
—que es el único sitio donde nacen las quimeras— y solo ahí se comprueba
si la identidad que continúa mantiene su firma de color o la cambia de
golpe. Si la cambia, se corta la identidad en ese punto exacto y se deja
que el cosido por pureza decida después.

Lo que lo hace defendible es que **no es un corte global**. La lección
más cara del proyecto es que cortar identidades con señales ruidosas por
observación destruye identidades buenas: pasó con la velocidad, con el
post-proceso completo y con el color, tres negativos seguidos. Aquí la
señal se consulta en el 1 % de los frames donde hay riesgo, no en todos.

### Camino B — asociación propia con coste mixto

Reimplementar la etapa: coste = α·(1−IoU) + (1−α)·distancia_de_color, con
matching húngaro, como BoT-SORT. Es lo correcto a largo plazo y lo que
permitiría además asociar en METROS en vez de en píxeles, que es la
ventaja diferencial declarada del proyecto. Pero es reescribir la pieza
que hoy es lo mejor medido que tenemos, y hay que estar dispuesto a
perder un tiempo largo antes de recuperar el nivel actual.

### Camino C — cambiar de librería

`trackers.ByteTrackTracker` (el sucesor que reclama `supervision`) o una
implementación con ReID. **Ojo**: `boxmot` está vetado en CLAUDE.md
porque rompió el entorno. Antes de instalar nada, comprobar que no sube
numpy por encima de 2.1.

## Recomendación

**Empezar por A.** Es medible en una tarde, no arriesga lo que funciona,
y sobre todo **contesta la pregunta que hace falta contestar antes de
invertir en B**: ¿las 8 quimeras nacen de verdad en solapes de cajas? Si
al mirar los frames de cruce resulta que la mayoría no nace ahí, B estaría
construido sobre una hipótesis falsa.

Ese diagnóstico es el primer paso aunque se acabe eligiendo B.

## Cómo se mide

La métrica objetivo es **quimeras en Villaviciosa: 8 → menos**, con la
condición explícita de no degradar cobertura (0,598), IDF1 (0,484) ni
concurrencia (23, con GT 22). Un corte que baje quimeras hundiendo la
cobertura es el error de siempre, ya cometido tres veces.

Segunda pata: los tres casos con nombre del benjamín (id 4, id 32,
id 19→4), que han resistido al barrido del fit **y** al detector nuevo. Si
la hipótesis de la asociación es correcta, son los primeros que deberían
caer.

## Lo que hay que arreglar antes de medir nada aquí

El mini-GT de equipos del benjamín está indexado por **ids del v4pre**, y
los ids no sobreviven a un cambio de detector: 27 de sus 30 identidades
caen a más de 5 m de donde estaba esa id con el v4 (mediana 38 m).
`medir_v4.py` ya traslada las etiquetas por solape espacio-temporal, pero
es un parche con pérdida: solo 35 de las 84 identidades del v4 encuentran
equivalente, y varias identidades nuevas caen sobre una misma vieja (el
id 4, cinco).

Cualquier GT que vaya a sobrevivir a estos cambios tiene que estar
indexado por **posición y tiempo**, no por id del sistema.

---

# CAMINO B: el coste mixto en METROS (19-ago-2026)

`src/tracking/coste_asociacion.py`. Implementado el término geométrico
como pidió Alex: **distancia física con radio derivado de la física**, no
un umbral abstracto.

    radio(Δt, y) = v_max · Δt  +  k · σ(y)

- `v_max · Δt` crece **solo con el hueco**: cuanto más tiempo lleva
  perdido un jugador, más lejos puede estar legítimamente.
- `σ(y)` es la incertidumbre de la proyección, medida: **±0,11 m cerca,
  ±1,85 m en el fondo**. Sin ella el radio del fondo sería tan estrecho
  como el de cerca y vetaría emparejamientos correctos.

## El peso NO es constante, y se deriva en vez de elegirse

Un α fijo seguiría fiándose de la geometría en el fondo, donde no informa.
La solución no es inventar un α por zona sino **pesar cada evidencia por
su precisión**, que es lo estándar al combinar dos medidas:

    σ_geo(Δt, y)² = σ(y)² + (v_incert · Δt)²
    α = (1/σ_geo²) / (1/σ_geo² + 1/σ_app²)

α baja **solo** en los dos casos en que debe: lejos y tras un hueco
largo. Ninguna regla ad hoc.

| y (m) | Δt | σ(y) | radio | **α** |
|---|---|---|---|---|
| 0 | 0,12 s | 0,11 | 1,1 m | **0,96** |
| 0 | 1,0 s | 0,11 | 7,2 m | 0,31 |
| 20 | 0,12 s | 0,63 | 2,1 m | 0,70 |
| 40 | 0,12 s | 1,15 | 3,1 m | 0,42 |
| 65 | 0,12 s | 1,80 | 4,4 m | **0,23** |
| 65 | 3,0 s | 1,80 | 24,6 m | 0,04 |

En continuidad y cerca manda la geometría (0,96). En el fondo tras un
hueco, la apariencia (α = 0,04). **Y eso encaja con lo medido**: allí la
geometría es mala Y el color da 0,000 separando equipos, así que la
apariencia es lo único que queda — y el peso llega solo a esa conclusión.

## Dos decisiones de diseño que conviene no perder

**El veto por radio va ANTES de mirar la apariencia.** Por muy parecido
que sea el aspecto, un jugador no puede estar donde no ha podido llegar.
La apariencia desempata dentro de lo posible; no autoriza lo imposible.
Si se mezclara en un único coste sin veto, un embedding muy parecido
podría comprar un salto de 40 m — que es justo la quimera que queremos
matar.

**Una sola constante libre**: `sigma_apariencia`, la incertidumbre
equivalente de la apariencia en metros (cuántos metros de error
posicional "valen" lo que la distancia de coseno). Todo lo demás sale de
física o de medidas ya hechas. Es lo único que hay que calibrar contra el
banco.

## Lo que falta

Esto es la **función de coste**, con sus tests. Falta la etapa de
asociación que la usa (matching húngaro por frame, gestión de tracks
perdidos) y la calibración de `sigma_apariencia` contra el banco. Sin esa
calibración los valores de α de la tabla son plausibles pero no están
validados: a Δt = 1 s ya baja a 0,31 incluso cerca de la cámara, que
puede ser demasiado agresivo.

## Calibración contra el banco: el camino B PIERDE (19-ago-2026)

`scripts/calibrar_coste_mixto.py`, con siglip y las dos constantes
barridas.

| sigma_app | v_incert | nIds | cob. | conc | IDF1 | tasa | quim |
|---|---|---|---|---|---|---|---|
| 0,5 | 0,5 | 88 | 0,581 | 24 | 0,449 | 0,142 | 10 |
| 0,5 | 1,5 | 84 | 0,585 | 25 | 0,440 | 0,166 | 10 |
| 0,5 | 3,0 | 77 | 0,582 | 27 | 0,355 | 0,220 | 19 |
| 1,0 | 0,5 | 91 | 0,590 | 24 | 0,447 | 0,139 | 12 |
| 1,0 | 1,5 | 91 | 0,566 | 25 | 0,399 | 0,171 | 12 |
| 1,0 | 3,0 | 77 | 0,581 | 29 | 0,348 | 0,244 | 18 |
| **2,0** | **0,5** | 91 | 0,605 | 24 | 0,426 | 0,142 | **8** |
| 2,0 | 1,5 | 91 | 0,601 | 25 | 0,392 | 0,156 | 13 |
| 2,0 | 3,0 | 76 | 0,574 | 27 | 0,387 | 0,202 | 16 |
| **REFERENCIA** (ByteTrack + puerta) | | **64** | **0,619** | **21** | **0,546** | — | **3** |

**Ninguna combinación cumple el criterio, y ninguna se acerca.** La mejor
del barrido da 8 quimeras frente a 3, con IDF1 0,426 frente a 0,546.

## No es un problema de calibración

Las nueve combinaciones quedan entre 0,348 y 0,449 de IDF1, muy por
debajo del 0,546 de la referencia. Un óptimo escondido entre esos puntos
no explicaría una brecha así: **la diferencia es algorítmica**, y hay
razones concretas:

1. **ByteTrack asocia en DOS pasadas** —primero las detecciones de alta
   confianza, luego las dudosas contra lo que quedó sin emparejar— y esa
   es literalmente su aportación. Mi implementación hace una sola pasada.
2. **ByteTrack usa filtro de Kalman**; aquí la predicción es lineal desde
   la velocidad suavizada del tracklet, mucho más pobre tras un hueco.
3. La gestión de tracks perdidos de la librería está más trabajada que un
   simple "si lleva más de X segundos, muere".

`v_incert = 0,5` sí resulta mejor que 1,5 en todas las filas, así que la
sospecha de que 1,5 era demasiado agresivo era correcta. Pero corregirlo
no salva la brecha.

## Decisión: NO se adopta, y el diseño se replantea

El camino B, tal como estaba planteado —**sustituir** ByteTrack por una
asociación propia— pierde. La lectura honesta es que reimplementar desde
cero una pieza madura, y ganarle, es más caro de lo que parecía cuando lo
propuse; el aviso estaba escrito en el diseño original ("hay que estar
dispuesto a perder un tiempo largo antes de recuperar el nivel actual") y
se ha cumplido.

Lo que **sí** está demostrado por otra vía:

- La señal de apariencia existe y es fuerte donde hace falta (siglip
  0,200 vs 0,018 del HSV en la re-entrada de recortes pequeños).
- Metida como **puerta sobre ByteTrack**, ya baja las quimeras de 5 a 3
  sin degradar nada.

O sea: la apariencia es buena, sustituir la asociación no. El camino
productivo es **añadir apariencia a la asociación que ya funciona** —por
ejemplo, sustituyendo la firma de color de la puerta de re-entrada por el
embedding de siglip, que es exactamente donde el benchmark dice que gana
por once veces— en vez de reescribir la etapa entera.

El módulo se queda en el repo, con sus tests: la función de coste y el
radio físico son correctos y reutilizables si algún día se ataca la
asociación con más tiempo (dos pasadas, Kalman) o si aparece una
implementación con licencia compatible.
