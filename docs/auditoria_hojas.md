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
