# Diagnóstico 23-oct (d): velocidades de la pista, emisión cruzada, regla de portero y clip

Rama `fix-23oct-d`, sale de `fix-23oct-c`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque, solo con pytest en código 0. Producción solo cambia tras flag (apagado = idéntico a
`main`). Todo se mide sobre la **variante 2 («añade»)** del 23-oct (c), la que se quedó más cerca.
Su pista es la misma que la de la variante 1: las dos variantes solo difieren en qué hacen después.

Relojes: frame / 29,97 = tiempo del **archivo**; el reproductor de Alex va **+1:33**.

---

## Bloque 1 — los pasos de la pista a más de 9 m/s

Ayer: el 1,03 % de los pasos de la pista supera 9 m/s, y el criterio era ≤ 1 %. **El criterio de
ayer no se cambia**; aquí solo se explica de dónde sale ese 1,03 %.

**Paso** = dos frames CONSECUTIVOS de la pista, aunque haya un hueco entre ellos (la misma definición
que `metricas_pista`). Velocidad = distancia en metros / Δt.

Cada paso de más de 9 m/s se clasifica por:
- **zona**: metros por píxel en el pie (la homografía local; < 0,1 cerca, 0,1-0,2 medio, > 0,2 fondo);
- **magnitud**: 9-12, 12-20, 20-40 y > 40 m/s;
- **hueco**: Δt de un frame procesado (≤ 0,15 s) o más (la pista saltó frames o pasó por «no visible»);
- **¿cambia la detección elegida de persona?**: las dos detecciones pertenecen a identidades
  DISTINTAS del tracker (la identidad sale del CSV, con la caja cruda más cercana, como el proxy de
  siempre);
- **¿cae el chaleco?**: alguna de las dos detecciones tiene log LR ≤ 0;
- **¿caja fundida?**: alguna de las dos cajas solapa otra caja del frame con IoU > 0,1 (la definición
  de cruce del 23-oct b).

**Control: los jugadores al mismo muestreo.**
- Para cada persona del GT del benjamín (14 tracks, frames 9750-10635), en CADA frame procesado de la
  ventana: su posición del GT interpolada linealmente entre las anotaciones (cada 15 frames).
- La pista del jugador es la detección casada 1-a-1 a ≤ 1 m de esa posición (Hungarian, el protocolo
  de siempre).
- Su fracción de pasos > 9 m/s se calcula con la MISMA definición de paso.
- Se compara con la fracción de la pista del árbitro en la misma ventana y en el partido entero.

**Lectura fijada antes (de Alex):**
- Los jugadores dan **≥ 0,7×** la fracción del árbitro: el criterio no era específico (el temblor
  de las detecciones también lo dispara), y el fallo del 1,03 % **no cuenta**.
- Dan **menos de 0,7×**: son saltos reales de la pista. Se añade una **penalización de continuidad**
  tras un parámetro (por defecto 0 = la pista idéntica a hoy), y se mide con los criterios de AYER,
  sin cambiarlos.

¿Qué podría estar inventando?
- El casado a ≤ 1 m del GT RECORTA los saltos de los jugadores: una detección que salta más de ~2 m
  ya no se casa. Esto sesga el control hacia ABAJO, es decir, a favor de «saltos reales». Se dice
  cuánto pesa repitiendo el control a ≤ 2 m.
- La ventana del GT es de 30 s del minuto 5: el árbitro se compara también en esa ventana.

## Bloque 2 — emisión con mitades cruzadas

La ventana del GT se parte en dos por el frame 10192: H1 = 9750-10191 y H2 = 10192-10635. Se hacen
dos modelos de emisión, con la misma verdad del 23-oct (a) y los mismos bins:
- uno estimado solo con H1 y evaluado en H2;
- otro estimado solo con H2 y evaluado en H1.

Para cada uno, la variante 2 sobre la parte entera:
- **cobertura** y **B > 7**, en el partido entero;
- **centroide** (`foto_de_estado`), SOLO en la mitad que el modelo no vio.

La referencia es el modelo de la ventana entera (el de ayer), medido sobre la misma mitad.

**Criterio**:
- el centroide no cambia más de **0,03 m**;
- cobertura y B > 7 no cambian más de **1 punto**.

Si cambian, se dice cuánto y en qué dirección.

¿Qué podría estar inventando? Con ~35 filas de árbitro por mitad, el suavizado de Laplace pesa más.
Un modelo «estable» podría serlo porque la pista la manda el movimiento y no la emisión. Se informa
también el log LR de cada bin de los tres modelos.

## Bloque 3 — la regla de portero (solo medición, no se implementa nada)

**(a) La fila de más en los frames con B > 7.**
- 30 frames con B > 7 de la variante 2, repartidos por el partido: 30 tramos iguales de tiempo, y un
  frame al azar (semilla 1) de cada tramo que tenga alguno.
- Panel por frame: el vídeo con todas las cajas (etiqueta e identidad) y, al lado, la pizarra de ese
  frame.
- Clasificación a ojo de la fila de más:
  - **portero con rol equivocado**, con dos subtipos: (a1) el portero verde de B etiquetado como
    jugador de B; (a2) el portero de A etiquetado B;
  - árbitro;
  - fantasma o balón;
  - duplicado;
  - jugador de A etiquetado B;
  - otro.

**(b) ¿Quién se lleva `portero_A` / `portero_B`, y cuál es el portero real?**
- Proxy del **portero real** por frame: la detección más profunda dentro de su área (área F7 del
  modelo: x 0-12 y 50-62, y 7-33):
  - para B, la de mayor x con x ≥ 50;
  - para A, la de menor x con x ≤ 12.
  - Es POSICIÓN DEL INSTANTE, no de la identidad: la regla de producción decide sobre el conjunto de
    fragmentos de una identidad, así que el proxy no es la misma medida.
- **Control del proxy, ANTES de usarlo:**
  - en la ventana del GT, los tracks GT de los porteros (la persona con la mediana de x más extrema
    de cada lado): ¿el proxy cae a ≤ 1,5 m de ellos?
  - en los 30 paneles, con el proxy marcado: ¿es el portero (camiseta verde de B / negra de A)?
  - Si el proxy acierta menos del **80 %** en alguno de los dos, la fracción de rol correcto queda
    **NO MEDIDA** y solo vale la lectura a ojo.
- **Frames con ambos porteros visibles** = el proxy encuentra candidato en las dos áreas.
- Por lado se mide:
  - la **fracción de frames con rol correcto** (la detección del proxy lleva `portero_X`);
  - la tabla de identidades que se llevan `portero_X`, con filas y tramo;
  - los fallos por tipo:
    1. la etiqueta se la lleva OTRA detección; se cuenta si es un jugador del otro equipo según el
       voto de color de ESA observación;
    2. el portero real está **cortado por el borde inferior** (la caja toca el borde) y no lleva su
       etiqueta;
    3. nadie lleva la etiqueta en ese frame (sin corona);
    4. dos `portero_X` a la vez.
- **Propuesta** del cambio mínimo con su criterio, SIN implementar.

## Bloque 4 — el clip 10:00-10:45 del archivo (11:33-12:18 del reproductor)

- Vídeo con etiquetas y pizarra, con **hoy** y con la **variante 2**, para que Alex los compare
  (`diag23b_auditoria.py render`).
- Explicación, con los datos de la pista, de por qué en el frame **f23553** (**13:05,9** archivo /
  **14:38,9** reproductor) la variante 2 deja al árbitro en B.

---

## Resultado del bloque 1 — los pasos a más de 9 m/s

`python scripts/diag23d.py velocidades --salida outputs/diagnostico_23oct_d` (`velocidades.json`; el
detalle paso a paso, en `bloque1_pasos.json`).

Comprobación previa: la pasada de hoy y la de la variante 2 dan un CSV **idéntico byte a byte** al
de ayer (`cmp`). Se mide lo mismo que se midió.

### La lectura fijada: el criterio NO era específico

| | pasos | > 9 m/s |
|---|---|---|
| pista del árbitro, partido entero | 11.641 | **1,03 %** (120) |
| pista del árbitro, solo la ventana del GT | 289 | 0,0 % (0) |
| **jugadores del GT, mismo muestreo, casados a ≤ 1 m** | 3.074 (14 personas) | **2,28 %** |
| jugadores del GT, casados a ≤ 2 m | 3.637 | 4,81 % |

- Los jugadores dan **2,2× la fracción del árbitro**, por encima del 0,7× fijado: **el fallo del
  1,03 % no cuenta**.
- Ningún benjamín corre a más de 9 m/s. Si los jugadores casados con el GT, con su posición real
  conocida, pasan ese umbral el 2,3 % de las veces, lo que dispara el criterio es el **temblor de la
  detección**: 1 px vale hasta 0,42 m en el fondo y un paso dura 0,1 s.
- El sesgo previsto va en la dirección que refuerza la lectura: casar a 2 m (más permisivo) DUPLICA
  la fracción de los jugadores.
- **No se añade la penalización de continuidad.** El criterio de ayer no se cambia: formalmente sigue
  en ✗. Lo que cambia es lo que dice ese ✗.

### De dónde salen los 120 pasos de la pista

| | sí | no | lo que dice |
|---|---|---|---|
| cruzan un **hueco** (Δt > 0,15 s) | 54 | 66 | solo el 2,0 % de los pasos tiene hueco, pero el 22,8 % de ellos supera 9 m/s; sin hueco, el 0,58 % |
| tienen **caja fundida** (IoU > 0,1) | 74 | 46 | el 19 % de todos los pasos tiene caja fundida; con ella, el 3,3 % supera 9 m/s; sin ella, el 0,49 % |
| **cambian de identidad** del tracker | 10 | 110 | casi nunca salta a OTRA persona del tracker |
| el **chaleco cae** (log LR ≤ 0) | 2 | 118 | la pista casi nunca pisa una detección sin chaleco |

- **Por zona**: cerca 0,54 %, medio 0,82 %, fondo **1,34 %**. Crece con los metros por píxel, que es
  la firma del temblor y no la de un cambio de persona.
- **Por magnitud**: 57 en 9-12, 45 en 12-20, 17 en 20-40 y 1 > 40 m/s. Son casi todos saltos de
  1-2 m en 0,1 s: una caja fundida desplaza su pie.
- Quedan **32 pasos** (0,27 % de la pista) sin hueco y sin caja fundida.

### ¿Qué podría estar inventando este número?
- El 0,0 % del árbitro en la ventana del GT son 0 de 289 pasos. Con la tasa del partido se esperarían
  3, y ver 0 pasa un ~5 % de las veces. No es prueba de nada; por eso la comparación se hace contra
  la tasa del partido.
- El control de los jugadores no es una pista de Viterbi: casa por persona en cada frame. Puede saltar
  de detección cuando dos jugadores están a menos de 1 m, lo mismo que puede hacer la pista. Las dos
  medidas tienen el mismo tipo de ruido; por eso el control vale.
- «Caja fundida» y «fondo» no son independientes: en el fondo las cajas son pequeñas y se solapan más.
  No se ha separado una cosa de la otra.
