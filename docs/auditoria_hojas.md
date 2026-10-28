# Auditoría de las hojas de revisión: ¿la caja dibujada es la detección de la fila? (28-oct-2026)

Rama `auditar-hojas`, sale de `main`. Disparada por el 28-oct (f): la hoja `equipo_por_obs_20min`
enseñó la caja de OTRA identidad en 11 de 120 filas, y 10 de los 12 «errores» eran de la
herramienta. Criterios escritos y commiteados ANTES de contar nada. Commit solo con pytest en 0.

## Cómo elige la caja cada hoja (leído en el código, antes de mirar datos)

| hoja (marcada por Alex) | generador | cómo se elige la caja | ¿hay que auditar fila a fila? |
|---|---|---|---|
| `azar` (91 marcas, `revision.csv`) | `hoja_revision_equipos.py` | dibuja TODAS las detecciones del frame, cada una con su identidad (`capt["obs"]`, la asignación del tracker) | **no**: la caja es la detección por construcción; la marca se refiere a una caja numerada |
| `arbitro_viterbi` (revisada a ojo por carpeta, 23-oct) | `diag23c_viterbi.hojas` | la detección de la PISTA del árbitro en ese frame, pasada al caché crudo por igualdad de caja (`k_crudo`) | sí, pero solo para comprobar que la igualdad de caja es exacta (distancia L1 = 0) |
| `viterbi_a_otro` (revisada a ojo, 23-oct) | `diag23c_viterbi.hojas` → `diag22e_invariantes.con_caja` | **la detección cruda MÁS CERCANA a la posición del CSV** (suavizada) | **sí** |
| `equipo_por_obs_20min` (120 marcas) | `diag26b.hoja` → `con_caja` | ídem, la más cercana | sí: ya medido en el 28-oct (f), 11/120 |
| GT de equipo de 30 s, CVAT (`annotations.xml`) | `etiquetar_tracking_gt.py` → `gt_tracking_a_cvat.py` | **ninguna**: Alex hace clic en los pies sobre el FOTOGRAMA ENTERO; la caja se sintetiza alrededor de su clic | **no**: el sistema no condiciona la respuesta |
| mini-GT de equipos de agosto (`gt_equipos_benja.csv`, 236 recortes) | `etiquetar_equipos_gt.construir_identidades` | **la detección MÁS CERCANA a la posición del CSV** (≤ 2 m) | **sí** |

## Qué se mide

**Discrepancia** = la caja dibujada NO es la detección de la identidad de la fila en ese frame.

- **Exacta** (`viterbi_a_otro`, `equipo_por_obs_20min`, `arbitro_viterbi`):
  - la detección de la fila sale de las identidades de la captura de `main`
    (`outputs/diagnostico_26oct_b/captura_main.pkl`);
  - para `viterbi_a_otro` vale porque su CSV (`viterbi_benja_v1_sustituye.csv`) tiene las posiciones
    IDÉNTICAS a las de esa captura en las 180.479 filas. El tracking es el mismo; solo cambian
    etiquetas;
  - del caché filtrado se pasa al crudo por igualdad de caja (IoU > 0,99);
  - discrepancia si la caja dibujada tiene **IoU < 0,5** con la de la fila, o si la identidad no
    tiene detección en ese frame.
- **Por proxy** (el mini-GT de agosto, cuyas identidades ya no se pueden reconstruir: el tracker ha
  cambiado desde entonces):
  - se reconstruyen las muestras con la MISMA función (`construir_identidades`, determinista) sobre
    el CSV y el caché de entonces (`posiciones_benja.csv`, `cache_detecciones_benja.pkl`);
  - una muestra es **dudosa** si la detección más cercana está a > 0,05 m de la posición del CSV (no
    es la misma proyección) **y** hay OTRA detección a ≤ 2 m;
  - **control del proxy**: aplicado a `equipo_por_obs_20min`, donde la verdad se conoce, tiene que
    marcar como dudosas **las 11 discrepancias conocidas**. Si no las marca todas, el proxy no vale
    y el mini-GT queda **sin auditar**, dicho así.

**Criterio (el de Alex)**:
- discrepancias en **< 2 % de las filas** → las conclusiones previas de esa hoja valen;
- si no, se recalcula con la caja correcta (la marca contra la etiqueta del DUEÑO de la caja que vio
  Alex, como en el 28-oct f) y se listan las filas que habría que volver a marcar: las que se le
  enseñaron con una caja de otra persona.

¿Qué podría estar inventando?
- Las revisiones a ojo (`arbitro_viterbi`, `viterbi_a_otro`) no tienen CSV de marcas: Alex dijo
  «todos perfectos menos 23_7-08.6.jpg». Una discrepancia ahí cambia QUÉ revisó, no un número.
- En el mini-GT, el proxy solo dice «dudosa», no «mal»: una muestra dudosa puede ser correcta.

## El arreglo del generador

- `hoja_otro_v3.escribir_hoja` (lo usan todas las hojas de recortes) recibe `k`. El fallo está en
  quien se la calcula: `con_caja` (la más cercana).
- Se añade una función que da la detección de la FILA a partir de la asignación del tracker
  (identidad → (frame, detección del caché filtrado) → índice en el crudo por igualdad de caja), y
  `diag26b.hoja` y `diag23c_viterbi.hojas` la usan en vez de `con_caja`.
  - `con_caja` se queda para los proxies que la usan como medida (`diag22b`, `diag22e`), con un
    aviso en su docstring.
- **Test**: un caso sintético de cruce donde la posición suavizada cae más cerca de la detección
  del OTRO. Con el método antiguo el test falla; con el nuevo, la caja es la de la fila.
- **CLAUDE.md**: una línea sobre el control del instrumento en las hojas.
- No toca código de producción (`src/`): solo generadores de hojas en `scripts/`.

## Oráculo con la tasa corregida

- Inyección de **1,7 %** (en cruce y fuera), filas sueltas y rachas, 200 semillas, la ventana de 30 s
  del GT (la misma de 28-oct d/e/f).
- p95 del centroide y de la anchura en el **instante** (0,5 s) y en ventanas de **1 s**.
- Sin umbral nuevo: se informa contra el de Alex (≤ 1 m / ≤ 1,5 m).

---

# Resultados

`python scripts/auditar_hojas.py` → `outputs/auditoria_hojas/auditoria.json`.

**Comprobación previa**: el tracking de la pasada del viterbi es el de la captura de `main`. Las
180.479 filas tienen la misma posición, así que la comprobación de `viterbi_a_otro` es exacta.

| hoja | cómo elige la caja | filas | discrepancias | ¿valen las conclusiones? (< 2 %) |
|---|---|---|---|---|
| `azar` | todas las detecciones con su identidad | 91 marcas | 0 por construcción | **sí** |
| `arbitro_viterbi` | la detección de la pista | 60 | **0** (las 60 cajas son detecciones exactas; coinciden además con la pista de `main`) | **sí** |
| `viterbi_a_otro` | la más cercana a la posición | 60 | **1 (1,7 %)** | **sí** |
| `equipo_por_obs_20min` | la más cercana a la posición | 120 | **11 (9,2 %)** | **no** → recalculado |
| GT de 30 s (CVAT) | ninguna: clics de Alex sobre el fotograma entero | — | 0 por construcción | **sí** |
| mini-GT de agosto | la más cercana a la posición (≤ 2 m) | 236 | **sin auditar**: el proxy no pasa su control | ver abajo |

**`viterbi_a_otro`**: la única discrepancia es **23_7-08.6.jpg** (7:08,6 / 8:41,6). Es justo la
imagen de la que Alex dijo «son dos jugadores, el árbitro está a unos metros a la derecha». La hoja
le enseñó la caja de la identidad 161 en vez de la de la fila (309). Su único «fallo» en esa hoja
era de la herramienta. Las otras 59 están bien elegidas, y Alex las dio por buenas.

**`equipo_por_obs_20min`**: ya recalculado en el 28-oct (f) con la caja correcta (la etiqueta del
DUEÑO de la caja que vio Alex): **2 de 120 = 1,7 % [0,5; 5,9]**. **No hace falta volver a marcar
nada para el recuento.** Si se quiere la marca de la persona de la FILA (y no de la que se enseñó),
habría que volver a marcar estas 11 con la caja nueva (archivo / reproductor):
- 11_1-43.5 (1:43,5 / 3:16,5)
- 12_2-00.2 (2:00,2 / 3:33,2)
- 14_2-07.0 (2:07,0 / 3:40,0)
- 31_5-12.3 (5:12,3 / 6:45,3)
- 36_6-07.2 (6:07,2 / 7:40,2)
- 42_6-51.4 (6:51,4 / 8:24,4)
- 57_9-13.5 (9:13,5 / 10:46,5)
- 89_14-46.5 (14:46,5 / 16:19,5)
- 99_16-20.7 (16:20,7 / 17:53,7)
- 104_17-30.3 (17:30,3 / 19:03,3)
- 105_17-34.1 (17:34,1 / 19:07,1)

**Mini-GT de agosto**: el proxy NO pasa su control.
- Sobre `equipo_por_obs_20min` marca 49 dudosas y solo 6 de las 11 discrepancias conocidas.
- Aplicado al mini-GT da 62 de 236 dudosas (26 %), pero con un proxy que falla su control ese
  número no dice nada.
- **Queda sin auditar**, y las identidades de entonces ya no se pueden reconstruir.
- Pesa poco: está indexado por id de un detector anterior y ya estaba declarado caducado
  (CLAUDE.md, «Un GT indexado por id del sistema caduca»; `diagnostico_26oct_b.md`). Ninguna cifra
  de hoy sale de él: el 1,2 % y el banco salen del GT de CVAT, que no tiene este problema.

## El arreglo

- `scripts/hoja_otro_v3.py`: `deteccion_de_la_fila` y `con_caja_de_la_fila`. Dan la detección de
  la identidad de la fila en su frame, pasada del caché filtrado al crudo por igualdad exacta de
  caja. Una fila interpolada (sin detección) no se dibuja.
- `diag26b.hoja` (`equipo_por_obs_20min`) y `diag23c_viterbi.hojas` (`viterbi_a_otro`) la usan en
  vez de `con_caja`. `diag23c` captura ahora las identidades para poder hacerlo.
- `con_caja` se queda para los proxies que la usan como MEDIDA, con un aviso en su docstring.
- **Test** `tests/test_caja_de_la_fila.py`: un cruce sintético donde la posición suavizada está a
  0,2 m del rival, y un caché filtrado que desplaza los índices.
  - Con el método nuevo, la caja es la de la fila.
  - Un test de control comprueba que el antiguo dibuja al otro.
  - **Mutación verificada**: con `con_caja_de_la_fila` devolviendo «la más cercana», 2 de los 3
    tests fallan (el fichero cambió; restaurado).
- **CLAUDE.md**: la línea del control del instrumento en las hojas.
- No se toca `src/`.

## Oráculo con la tasa corregida (1,7 %)

p95 en m (centroide / anchura), 200 semillas, ventana de 30 s del GT:

| | instante (0,5 s) | 1 s |
|---|---|---|
| filas sueltas | 2,38 / 0,34 | 1,78 / 1,20 |
| rachas | 2,36 / 0,41 | 1,81 / 1,19 |
| media (rachas) | 0,40 / 0,15 | 0,38 / 0,15 |

- **La anchura cumple ya en el instante** (≤ 1,5 m).
- **El centroide no cumple ni en el instante ni a 1 s.** Con 1,7 % hay ~0,23 filas invertidas por
  frame: en ~1 de cada 5 instantes, un jugador mal etiquetado mueve el centroide ~1,5-2,5 m, y el p95
  cae ahí.
- Con el 28-oct (f), el centroide cumple a partir de **3 s** (0,95 m).
- Control de la inyección por rachas: se invirtió el 1,53 % de las filas de cruce (esperado 1,7 %;
  con 49 episodios, dentro del ruido). La clave del JSON dice «control ~16,7 %» porque viene del
  28-oct (e); aquí el objetivo es 1,7 %.
