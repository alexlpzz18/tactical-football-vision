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
