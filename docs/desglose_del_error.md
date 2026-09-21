# ¿De qué está hecho el error del centroide y del recuento? (21-sep-2026)

Rama `experimento/asociacion-global`. `scripts/desglose_del_error.py`,
`src/evaluation/desglose_error.py` (15 tests en `tests/test_desglose_error.py`).

Alex: *«si ni el portero ni el árbitro explican el ruido grande del recuento y
el centroide, ¿QUÉ lo explica? Quiero un desglose del error total en el partido
entero: cuánto es identidad, cuánto encuadre, cuánto localización, cuánto lo que
queda sin nombre.»*

## Respuesta corta

Del **1,45 m** de error medio de centroide (GT, 30 s, equipo por equipo):

| trozo | qué es | metros | % |
|---|---|---|---|
| **MIS** | personas del GT a las que NINGUNA fila cubre (a ≤ 5 m) | **0,60** | **41 %** |
| **EXT** | filas A/B que no son nadie del GT (el árbitro sobre todo) | 0,36 | 25 % |
| **DES** | una fila **mal colocada** 2–5 m (cuenta como un faltante + un sobrante) | 0,24 | 17 % |
| **LOC** | localización de las filas bien casadas | 0,16 | 11 % |
| **LAB** | **equipo equivocado** (la «identidad» de la que hablábamos) | **0,08** | **6 %** |

(reparto de Shapley, radio 2 m; la suma es exactamente el error del sistema.)

**La etiqueta de equipo, que es lo que llevamos semanas persiguiendo, pesa el
6 %.** El 83 % del error es **QUIÉN ESTÁ en el bloque** (faltan, sobran o están
mal puestos), no cómo se les colorea. Y con la lista de presentes perfecta y las
posiciones del sistema (LAB+EXT+MIS+DES) el centroide baja de 1,45 a **0,25 m**:
localización, lo que queda, es pequeña. Encaja con `docs/oraculos.md` (asociación
perfecta = 0,42 m), pero **corrige su lectura**: «asociación» no era el color del
equipo sino *quién cuenta como presente*.

Y la sorpresa que Alex pedía ver: **el recuento neto casi no falla** (7 − n_sistema
= +0,13 por equipo y frame) porque **faltan 0,76 y sobran 0,84**: dos flujos
brutos del mismo tamaño que se compensan en el recuento y **no** en el centroide.
Por eso el recuento parece «casi bien» y el centroide sale a 1,45 m.

## Método

Escalera de oráculos sobre la salida FINAL (`posiciones_benja_p1_v3.csv`,
`es_real=1`), contra el GT del benjamín. Cinco palancas, cada una una versión
perfecta de un trozo:

- **LOC**: las filas casadas con una persona del GT se mueven a su posición.
- **LAB**: esas filas pasan a llevar su equipo verdadero.
- **EXT**: se quitan las filas A/B sin persona en el GT.
- **MIS**: se añaden las personas del GT que ninguna fila cubre.
- **DES**: una persona sin fila y una fila A/B sin persona a ≤ 5 m son **la misma**
  (una fila mal colocada): se quita la fila y se pone la persona en su sitio.
  Sin esta palanca, EXT y MIS cargaban con lo que era un solo fallo.

Con las cinco aplicadas el conjunto ES el GT y el error es 0 (comprobado en test
y en el partido). Como las palancas se estorban entre sí —quitar un fantasma sin devolver al que
falta desplaza el bloque, y en la primera versión con 4 palancas EXT solo
*empeoraba* el centroide, 1,45 → 1,58 m—, el efecto de una sola no es el suyo. Se
reparte con **valores de Shapley** (el promedio de la mejora de cada palanca sobre los 120
órdenes posibles).

**Control (¿lo que mido es lo que creo?)**: con el protocolo de
`comparar_escalas.py` salen 723 casadas de 814 y **9 equipos equivocados = 1,2 %**,
igual que lo documentado. La media de centroide 1,45 m (mediana 0,86, p90 3,37)
reproduce lo conocido (1,43 / 0,97 / 3,39 con v2).

### Escalera (error que QUEDA)

| arreglado | centroide media | mediana | p90 | anchura | profundidad |
|---|---|---|---|---|---|
| sistema | 1,45 | 0,86 | 3,37 | 1,27 | 1,78 |
| solo LAB | 1,40 | 0,86 | 3,35 | 1,24 | 1,79 |
| solo LOC | 1,35 | 1,00 | 3,22 | 1,02 | 1,06 |
| solo EXT | 1,26 | 0,48 | 3,13 | 1,09 | 1,65 |
| solo MIS | 0,93 | 0,62 | 1,80 | 1,11 | 1,38 |
| solo DES | 1,23 | 0,73 | 2,65 | 1,09 | 1,72 |
| **LAB+EXT+MIS+DES** (lista de presentes perfecta) | **0,25** | 0,22 | 0,50 | 0,32 | 0,96 |
| todo | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |

Reparto por métrica (Shapley, media): anchura LOC 22 % · EXT 30 % · MIS 29 % ·
DES 15 %; profundidad LOC 47 % · MIS 33 % · EXT 11 % · DES 10 %. **En anchura y
sobre todo en profundidad la localización pesa más** (la profundidad es el eje
largo del campo, donde un píxel vale más).

## ¿Aguanta? (tres comprobaciones)

1. **Barrido del radio de casado** (el criterio es un parámetro, no una verdad):

   | radio | LOC | LAB | EXT | MIS | DES |
   |---|---|---|---|---|---|
   | 1,5 m | 0,10 | 0,09 | 0,36 | 0,60 | 0,31 |
   | 2,0 m | 0,16 | 0,08 | 0,36 | 0,60 | 0,24 |
   | 3,0 m | 0,21 | 0,15 | 0,36 | 0,60 | 0,14 |
   | 4,0 m | 0,24 | 0,17 | 0,37 | 0,58 | 0,09 |
   | 5,0 m | 0,29 | 0,24 | 0,38 | 0,54 | 0,00 |

   Los puntos son distintos y **MIS (0,54-0,60) y EXT (0,36-0,38) no se mueven**:
   lo único que cambia con el radio es cuánto de DES se llama LOC o LAB. Con radios
   grandes LAB sube (0,24 a 5 m) porque se casa con el vecino del otro equipo: es
   el artefacto de siempre, no identidad.
   ⚠️ La **mediana** de Shapley NO es estable con el radio (EXT 0,03 → 0,62 en el
   desglose de 4 palancas): no se usa; la media y el p90 sí aguantan.

2. **Tercios de la ventana** (20 frames cada uno):

   | tercio | sistema | LOC | LAB | EXT | MIS | DES |
   |---|---|---|---|---|---|---|
   | 1 | 0,75 | 0,11 | 0,00 | 0,37 | 0,24 | 0,03 |
   | 2 | 1,15 | 0,19 | 0,08 | 0,33 | 0,47 | 0,08 |
   | 3 | 2,46 | 0,19 | 0,17 | 0,39 | 1,09 | 0,62 |

   **El error triplica de un tercio a otro** y todo el crecimiento es MIS y DES
   (gente que falta o sale desplazada). EXT (0,33-0,39) y LOC (0,11-0,19) son un
   suelo casi constante. O sea: **el ruido no es estacionario, es EPISÓDICO**: hay
   segundos en que se pierde gente y segundos en que no.

3. **Mutación**: 11 mutaciones del código (LAB sin reetiquetar, pesos de Shapley
   uniformes, radio ignorado, casado no 1-a-1, DES sin quitar la fila…): **10
   atrapadas** por los tests y 1 escapó por ser un **mutante equivalente** (una
   condición redundante en EXT), que se quitó del código.

## Lo que hay dentro de cada trozo (medido, 60 frames, radio 2 m)

**Faltantes: 91 personas sin fila** (11,2 % de las 814).

| causa | n |
|---|---|
| DES: su fila existe pero está a 2-5 m | 46 |
| no detectada (ninguna detección cruda a ≤ 5 m) | 25 |
| detección propia a <2 m, pero el tracking/filtros no la sacan | 8 |
| detección fundida con un vecino (cruce) | 5 |
| detección propia; solo hay fila RELLENADA (es_real=0) | 4 |
| detección libre a 2-5 m | 3 |

Los verdaderamente ausentes son **45** (0,38 por equipo y frame). No se concentran
en una persona (12 personas distintas; la máxima, el 27 % de sus frames) y son más
frecuentes en los extremos (15 % y 17 % en x 0-20 y 40-62 m contra 7 % en el
centro). La mayoría (25) **no tiene detección cruda alguna**: el detector no las ve
o no están en imagen.

**Sobrantes: 101 filas A/B sin persona.**

| causa | n |
|---|---|
| DES: una persona sin fila a ≤ 5 m | 46 |
| identidad que nunca casa con nadie, **con firma de árbitro** | 28 |
| identidad que nunca casa, sin firma: **4 son también el árbitro** (id 292, cuando su firma cae bajo el umbral) y 4 están en la línea de banda (y ≈ 0) | 8 |
| identidad de un jugador real, sin pareja | 19 |

El árbitro (id 292: 32 filas) es **más de la mitad de los sobrantes de
verdad** (32 de 55) — coherente con `docs/peso_arbitro_y_portero.md`: pesa, pero son
≈ 0,2 m de 1,45 (por proporción de filas, aproximado), no el ruido grande. **Casi no hay duplicados**: solo 2 de los 55
sobrantes están a < 1,5 m de otra fila del mismo equipo.

**DES: 46 filas mal colocadas.** 38 son del mismo equipo. El desplazamiento es
casi todo en **profundidad** (|dx| mediana 2,7 m, |dy| 0,6 m) y el 85 % **hacia la
cámara**. **Premisa comprobada y refutada: NO es el retardo del suavizado de
0,5 s.** Si lo fuera, la fila iría *contra* la velocidad del jugador (signo
opuesto); coincide en el 43 % (azar, 50 %), la pendiente error-vs-velocidad sobre
las 692 casadas con velocidad es 0,00 s, y el error de las casadas casi no depende
de la velocidad (0,47-0,69 m por tramos). Queda **sin nombre**. Pista: el 25 % de las filas libres está a >1,2 m
de toda detección cruda pese a `es_real=1` (entre las casadas, p90 0,7 m y p99 1,8 m); ese detalle
recuerda a las «alas» del balón (`docs/balon_sin_alas.md`) y no está medido.

## Encuadre (estimación, no medida)

En el GT hay **18 de 120 pares (frame, equipo) con menos de 7 personas visibles**
(0,22 por par: el «encuadre» del recuento contra 7). Para el centroide no es un
fallo del sistema contra el GT (el GT solo tiene a los visibles), pero sí lo es
contra el equipo REAL de 7: ocultar 1 jugador al azar mueve el centroide **1,74 m** y
ocultar 2, **2,77 m**. Con la distribución observada, el efecto esperado es
**≈ 0,33 m** ⚠️ ESTIMACIÓN: supone ocultos al azar, y los reales son de borde
(moverían más). No se puede medir sin un GT que diga quién está fuera de imagen.

## El partido entero: lo medido, lo estimado y lo que NO se puede

El GT es el 2,5 % de la pasada y cae en un minuto **bueno**: el 5 (recuento medio
6,69). El desglose anterior es **de ese minuto**.

**MEDIDO sin GT en los 20 minutos** (`outputs/desglose_error_por_minuto.csv`):

| | media | mín. — máx. entre minutos |
|---|---|---|
| jugadores por equipo y frame (`n_medio`) | 6,30 | 4,83 (min 3) — 7,25 (min 12) |
| recuento exactamente 7 | 35 % | 15 % — 68 % |
| recuento < 7 | 47 % | 18 % — 79 % |
| detecciones crudas EN CAMPO por frame | 13,5 | 11,3 — 14,5 |
| filas A/B por frame | 12,6 | 9,7 — 14,5 |
| filas de árbitro dentro de un equipo (proxy de masa) | 0,17 | 0,00 — 0,33 |

**El recuento corto es upstream del tracking**: por minuto, `n_medio` correlaciona
**+0,93 con las detecciones crudas en campo** y +0,87 con las filas reales. En los
minutos peores (3, 4, 8, 13, 14: `n_medio` < 6) el detector ya ve solo 11-13 personas
en campo (contra 14,4 en los buenos) y el tracking no pierde nada: las filas
reales son 11,6 contra 11,3 detecciones. Y esos minutos son los de **cajas grandes**
(altura mediana 76-85 px contra ~49-66 px en los buenos; correlación de las
detecciones en campo con esa altura, **-0,78**): el juego está **cerca de la cámara**.
Eso apunta al **ENCUADRE** (a la hipótesis de Alex): con el juego junto a la cámara
el campo visible se estrecha y hay jugadores fuera de plano. La confianza del
detector no baja (0,86 en todos los minutos), o sea que no es el detector empeorando.
⚠️ **Es coherente con el encuadre, no lo demuestra**: una oclusión masiva junto a la
cámara produciría lo mismo. Distinguirlo exige un GT de esos minutos.

**ESTIMADO** (con supuestos): los flujos brutos faltan/sobran solo están medidos en
el minuto 5. En los minutos con recuento < 6 el neto ya no se compensa: allí
**dominan los faltantes** y el centroide tiene que ser peor que 1,45 m. No se puede
poner un número sin GT.

**NO MEDIBLE sin más GT**: cuánto de los minutos malos es encuadre y cuánto detector;
la composición de identidad (LAB) fuera del minuto 5; y los minutos 0-5, que ya eran
otro régimen (`CLAUDE.md`: solo el 15,9 % de sus frames tiene el recuento correcto).

## ¿Qué arregla? ¿Qué podría estar INVENTANDO?

- **¿Qué arregla?** Dice dónde NO hay que gastar: la etiqueta de equipo (6 %) y el
  árbitro como bulto (~0,2 m). Y dónde sí: la **presencia** (quién falta y quién
  está mal puesto: 58 % entre MIS y DES).
- **¿Qué podría estar inventando?** (1) **Shapley es una atribución, no una causalidad**:
  reparte la interacción EXT↔MIS por promedio de órdenes; con otras definiciones de
  palanca cambiaría. Se comprobó que no depende del radio (MIS/EXT estables) pero sí
  del momento (tercios). (2) **El GT es una plantilla de 40×18 px**: su «posición» no
  es un pie exacto (`docs/portero_cortado.md`), y LOC incluye ese sesgo. (3) **Un
  conjunto de presentes «perfecto» es un oráculo**: 0,25 m es el techo si arreglamos
  la presencia, no una promesa. (4) 30 s de GT en un minuto bueno no dice cómo son los
  malos (se ve en los tercios: 0,75 → 2,46).

## Qué sale de aquí

1. **Actualizar la lectura de «la asociación es el 100 % del margen»** (CLAUDE.md):
   es *cierto* que el margen está en quién cuenta como presente, pero de eso solo el
   6 % es la etiqueta de equipo. El grueso es **presencia** (faltan / sobran /
   mal puestos).
2. **El recuento exacto sigue siendo una mala métrica** (BACKLOG 24): el neto se
   compensa. Un informe debe dar el centroide con su rango, no «7 de 7».
3. **Lo más valioso ahora no es código sino GT**: dos o tres ventanas de 30 s en
   minutos MALOS (3, 8, 13 o 14), **solo de recuento** (marcar cuántos jugadores hay
   en imagen y quién falta; no hacen falta tracks ni identidades). Con eso se
   separaría encuadre de detector, que es lo que hoy no se puede medir.
4. La pista de las **filas `es_real=1` a >1 m de toda detección** (DES) merece una
   medición propia antes de tocar nada (¿el suavizado o la resolución de solapes
   generan posiciones que no son de nadie?).
