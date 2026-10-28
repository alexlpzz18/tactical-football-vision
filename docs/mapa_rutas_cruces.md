# Mapa de rutas para los cruces (28-oct-2026)

> ⚠️ **CORRECCIÓN (28-oct f)**: la premisa de este mapa, «16,7 % de error de equipo en cruce», era un artefacto de la hoja. El error real es **1/60 en cruce** (`diagnostico_28oct_f.md`). Lo que queda en los cruces es de ASOCIACIÓN y de POSICIÓN (la ficha suavizada cae cerca de otra persona), no de etiqueta. El paso previo de (a) dio **0 cambios de identidad** en los errores reales, y excluir las filas en cruce (ruta 1) empeora el centroide a 5-7 m de p95.


Sin código nuevo y sin medir: es una lectura de lo que ya está en `docs/`. Cada cifra lleva su
fichero.

## El problema, con los números de hoy

- **Error de equipo por observación**: **16,7 %** en cruce (10 de 60) contra **3,3 %** fuera de
  cruce (2 de 60) en la hoja de 20 min. **5,5 %** reponderado al partido (`diagnostico_28oct_c.md`).
- **Para el producto**: con ese error, el p95 del instante es de 3,6 m de centroide y 2,6 m de
  anchura. Hace falta promediar **10 s** para bajar de 1 m y 1,5 m (`diagnostico_28oct_d.md`,
  `_28oct_e.md`). **La pizarra lo nota; un informe por tramos de ≥ 10 s, no.**
- **Mecanismo, lo medido**:
  - en los cruces, el detector a menudo da UNA caja. En 2 de 6 frames da las dos y el tracking
    las mezcla igual (`diagnostico_28oct_c.md`);
  - la contaminación nace con **proximidad en METROS**: vecino a < 2,5 m, 2,42× sobre la base, y
    solo el 25 % con solape de cajas. Y nace en el fondo (1,65×) (`oraculos.md`, «Dónde nace»);
  - **el 86-94 % de los cambios en cruce es entre RIVALES** (`diagnostico_22oct_g.md`, bloque A),
    pero el **28-32 %** de los cambios de persona en general es entre compañeros (`oraculos.md`);
  - en un cruce, el sistema ROMPE más que intercambia: de 24 fallos, 21 son roturas y 3 son
    intercambios limpios (20-ago, `oraculos.md`).

## 1. Probado y cerrado

| ruta | cuándo | resultado | fichero |
|---|---|---|---|
| Consistencia de VELOCIDAD en la unión del cosido (veto 7 m/s, término de coste) | jul | No baja los cambios; en el candidato los sube (807 → 914). La velocidad de un trozo corto es ruido | `experimentos_tracking.md` 3f |
| Asociación propia en metros + apariencia («camino B») | 19-ago | Pierde contra ByteTrack: 8 quimeras contra 3, IDF1 0,426 contra 0,546 | `apariencia_en_asociacion.md` |
| Nuestro tracking contra un ByteTrack estándar | 10-ago | Gana el estándar; nuestro post-proceso tapaba defectos propios | `experimentos_tracking.md` |
| Embeddings de apariencia (dinov2, resnet50, siglip) para distinguir COMPAÑEROS | 19-ago | A < 20 px, TPR 0,000; a 20-30 px, ≤ 0,18 a 2-5 s. Sin datos en la casilla que decidía | `benchmark_embeddings.md` |
| Partir trozos por punto de cambio de apariencia | 20-ago | +6 puntos de pureza reales (control al azar). Con unión perfecta, 1,68 m: el grafo no paga | `oraculos.md` 4a/4b |
| Intercambiar colas por continuidad de movimiento (diseño) | 20-ago | **No se construyó**: arreglaría 3 de 24 fallos (el 87 % son roturas) | `oraculos.md` |
| Puerta de apariencia en el CRUCE (`puerta_reentrada.mirar_cruces`) | ago | Sube las quimeras 3 → 4 en Villaviciosa | `merge_a_main.md` |
| Corte por COLOR sostenido (`corte_color`) | ago | Negativo en las 4 configuraciones; quimeras 4 → 5 | `experimentos_tracking.md` |
| Excluir ocluidos del voto por ventana | 21-sep | Empeora (1,2 → 1,8 %). El ocluido vota casi igual (91,4 % contra 93,6 %) | `baile_y_oclusion.md` |
| Suavizar el parpadeo de etiqueta | — | El parpadeo es la señal del fallo; taparlo lo esconde | CLAUDE.md |
| Guarda de CAJA FUNDIDA (salto persistente + caja fundida) | 3-oct, 2 intentos | Acierta 3/4 cortes, pero no cumple en las dos patas; el cosido une 1 de 4 | `guarda_caja_fundida.md` |
| Resolución local en el cosido | 16-oct | Fabrica quimeras: 10 de 24 uniones nuevas juntan trozos con etiquetas DISTINTAS | `resolucion_en_cosido.md` |
| Procesar 1/1 en vez de 1/3 | 16-oct | Mejora la presencia, no la asociación; ×3 de GPU | `plan_ablacion_1a1.md` |
| **B1**: término de color en el coste de ByteTrack | 22-oct | Pureza y equipo mejoran, pero fragmenta: +125 % de identidades | `diagnostico_22oct_g.md` |
| **B2**: cortar en cruces (IoU > 0,1) y reenlazar por movimiento + color | 22-23 oct | Mejora el benjamín POR FRAGMENTACIÓN (el color permutado da lo mismo); Villaviciosa peor; IDF1 0,589 → 0,566 | `_22oct_g.md`, `_23oct_a.md` |
| Cortar en cruces SIN color, reenlace generoso | 23-oct b | Reconstruye las quimeras: centroide 0,86 → 1,30 m, IDF1 0,589 → 0,546 | `diagnostico_23oct_b.md` |
| Tope de cardinalidad (MILP ≤ 7 por equipo) | 22-oct e | Por identidad pierde el voto por observación; por trozos, el árbitro peor | `diagnostico_22oct_e.md` |
| Dedupe de identidades por IoU | 23-oct d | No existe umbral (personas distintas llegan a IoU 0,156) | `diagnostico_23oct_d.md` |
| Caja fundida por el postproceso de SAHI (NMS por IoU) | 28-oct c | No confirmada: en crudo hay UNA caja, o ya hay dos | `diagnostico_28oct_c.md` |

**El patrón de los cierres**:
- cortar y reenlazar falla por un lado o por el otro. Con una puerta estrecha, fragmenta (B2). Con
  una puerta generosa, rehace las quimeras (sin color);
- y cualquier señal POR TROZO CORTO (velocidad, color de un recorte) es ruido a 15-40 px.

## 2. No probado, ordenado por plausibilidad y coste

| # | ruta | plausibilidad | coste | por qué en este puesto |
|---|---|---|---|---|
| 1 | **Producto: la pizarra «sabe» que hay cruce** — en los tramos de proximidad a < 2,5 m, pintar la etiqueta como incierta en vez de inventarla; el informe, por tramos de ≥ 10 s | **alta** (para el producto) | **bajo** (render, sin tocar el tracking) | Es el plan B de agosto («admitir identidad desconocida»), y ahora hay números: el agregado de ≥ 10 s ya cumple. No arregla el tracking, arregla lo que ve el entrenador |
| 2 | **(a) Revincular tras el cruce: movimiento antes Y después + «una continuación mantiene el equipo»** | **media** | **medio** (CPU, `desde_cache`; se apoya en `corte_en_cruces.py`) | Es la única ruta que ataca la causa con una señal que no es por recorte. Ver la comparación con B1/B2 abajo y su paso 0 |
| 3 | **Puerta de proximidad en METROS + apariencia como sentencia** | media-baja | medio | Medida solo como techo, con unión perfecta: 1,57 m contra 1,81 (17 % del margen). Nunca en producción. Pariente de (a): (a) le da la sentencia al movimiento + equipo y esta, a la apariencia |
| 4 | **(b) Otro seguimiento con apariencia** (BoT-SORT, StrongSORT o Deep OC-SORT) como etapa de asociación | **baja** | **alto** | Ver abajo |
| 5 | NMS INTERNO de YOLO (IoU 0,7 por tesela) como origen de la caja única | baja | bajo (CPU, frames sueltos) | Lo dejó abierto el 28-oct (c). En 3 de 6 frames la caja única ya está en crudo, así que podría estar ahí, pero la palanca de detección ya se cerró |

### (a) Revincular tras el cruce: en qué se diferencia de B1 y B2

| | B1 | B2 | cortar sin color | **(a)** |
|---|---|---|---|---|
| dónde actúa | en CADA frame, dentro de ByteTrack | después, en los cruces | después, en los cruces | después, en los cruces |
| qué define el cruce | — | IoU de cajas > 0,1 (PÍXELES) | IoU > 0,1 | **proximidad en METROS** (< 2,5 m), la señal 2,42× |
| movimiento | — | solo hacia DELANTE, a velocidad constante, ≤ 1,5 m, hueco 1 s | hacia delante, puerta generosa (1,5 m + 3 m/s × hueco, ≤ 2,5 s) | **en los dos sentidos**: se extrapola el que entra hacia delante y el que sale hacia atrás, y se casan en el centro del cruce, a la cadencia nativa (0,1 s) |
| color | distancia HS continua al modelo de la pista, recorte a recorte | puerta continua d/sep sobre los frames limpios | ninguno | **ninguna distancia de color**: una RESTRICCIÓN discreta, el EQUIPO de cada trozo, votado por observación SOLO en sus frames fuera del cruce |
| qué decide | coste mezclado | húngaro con puerta | húngaro con puerta | húngaro con el movimiento como coste y el equipo como veto duro (A no continúa a B) |

**Lo que cambia de verdad**:
1. **La señal de equipo no es el color de un recorte, sino la etiqueta ya decidida**, que fuera del
   cruce falla el 3,3 % (28-oct c).
   - B1 y B2 metían el color crudo (0,884 contra 0,936: solapados), justo donde es peor.
   - El veto también ataca el fallo medido del cosido con resolución: 10 de 24 uniones juntaban
     trozos con etiquetas distintas.
2. **Corta donde nace la contaminación** (metros), no donde se solapan las cajas (25 % de los
   casos).
3. **El movimiento hacia atrás** no lo usó nadie. Con la extrapolación solo hacia delante, en el GT
   a 0,5 s, la geometría acertaba el 65 % (`oraculos.md`, «Los cruces»).

**Por qué NO es seguro, dicho antes**:
- **Es de la familia «cortar y reenlazar», que ya lleva dos intentos cerrados** (B2 y sin color).
  Por la regla, solo se abre como plan NUEVO, y su argumento tiene que ser el veto de equipo: es lo
  que permite una puerta de movimiento generosa (no fragmenta) sin rehacer las quimeras A↔B.
- **No ve los cruces entre compañeros** (28-32 % de los cambios de persona): ahí solo queda el
  movimiento, que es lo que ya falló en «sin color».
- **Ni al árbitro**: no tiene etiqueta de equipo fiable.
- **La velocidad de un trozo corto es ruido** (3f). Hay que estimarla con varias observaciones
  antes del cruce, y con 0,1 s de cadencia y el temblor del fondo (1 px ≈ 0,42 m), puede no dar.
- **Paso 0 obligatorio, barato y sin GPU, antes de escribir el módulo** («comprobar la premisa»).
  - El error de equipo de hoy es POR OBSERVACIÓN (ventana de 1,5 s). Revincular solo lo arregla si
    los 10 errores en cruce de la hoja vienen de una ventana que vota a través de un cambio de
    persona, y no de un recorte mezclado (la caja fundida da un color que no es de nadie).
  - En los 10 casos marcados por Alex: ¿la identidad cambia de persona dentro de su ventana de
    1,5 s?
  - Si la mayoría son recortes mezclados, (a) no mueve el 16,7 % y baja a la altura de la ruta 3.

### (b) Otro seguimiento con apariencia

- **Lo que ya dicen los datos**:
  - la apariencia no separa compañeros a este tamaño: TPR 0,000 a < 20 px y ≤ 0,18 a 20-30 px, con
    tres backbones;
  - nuestra propia asociación con apariencia (camino B) perdió contra ByteTrack;
  - la única apariencia que ha pagado es siglip en la RE-ENTRADA: quimeras 4 → 3 e IDF1 +0,011 en
    el perfil v4. No en el cruce, donde la puerta de apariencia empeoró (3 → 4).
- **Dónde sí podría ayudar**: los cruces entre RIVALES (86-94 % de los cambios en cruce), donde la
  equipación sí difiere. Pero para eso basta con la etiqueta de equipo, que es lo que usa (a), sin
  un embedding.
- **Restricciones del proyecto**:
  - NO usar boxmot (rompió el entorno y es AGPL);
  - comprobar la licencia de cualquier otra librería antes de instalarla;
  - **NO sustituir el tracking en metros** por uno en píxeles: la librería solo podría ser la
    etapa de asociación, como hoy ByteTrack;
  - el detector no corre en el Mac, así que los embeddings irían a Colab, y su coste a escala de
    partido sigue sin medir (`merge_a_main.md`).
- **Veredicto**: baja plausibilidad y el coste más alto. Solo tendría sentido si (a) falla por los
  cruces entre rivales y no por los de compañeros, cosa que su paso 0 y su resultado dirían.

## Recomendación

1. **Ya**: la ruta 1 (producto). Barata, y los números de esta semana dicen que el informe
   agregado aguanta.
2. **Después, el paso 0 de (a)**: una tabla de los 10 errores en cruce, «cambio de persona en la
   ventana» contra «recorte mezclado». Decide si (a) merece un plan.
3. (b), solo si (a) se construye y falla en los cruces entre rivales.
