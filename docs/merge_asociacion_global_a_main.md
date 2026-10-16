# Merge de `experimento/asociacion-global` a `main` — PREPARADO, SIN FUSIONAR (16-oct-2026)

Nada se fusiona sin el OK de Alex. Este documento es lo que hay que revisar antes.

## Estado

- La rama local y `origin/experimento/asociacion-global` coinciden (0 commits de diferencia), igual
  que `main` y `origin/main`.
- **163 commits** de la rama no están en `main`; **0** de `main` faltan en la rama. La rama sale del
  último merge (`229e7f7`, 20-ago) y solo lo adelanta: **no puede haber conflictos**.
- **Ensayo** (`git merge --no-commit --no-ff` sobre `origin/main`, en un worktree temporal, luego
  `--merge --abort`): **entra limpio**, 0 conflictos, 264 ficheros. **El árbol fusionado es idéntico
  al de la rama**, que es el mismo sobre el que la suite pasa entera (694 tests).

## Qué entra (264 ficheros: 225 nuevos, 39 modificados)

`scripts/` 95 · `docs/` 75 · `tests/` 54 · `src/` 22 · `configs/` 15 · `CLAUDE.md`, `BACKLOG.md`,
`.gitignore`.

**Datos y ficheros grandes: ninguno.**
- En el diff no hay `.pkl`, `.pt`, `.mp4`, `.npy`, `.zip`, `.csv`, `.json` ni imágenes, ni rutas bajo
  `data/`, `outputs/` o `models/`. El mayor fichero es `docs/experimentos_tracking.md` (150 KB).
- **En el historial** (que también entra): ningún blob pasa de 1 MB, y ningún commit tocó rutas de
  datos. ⚠️ Sí entran en el historial **507 KB de HTML/JS de la landing y de unas previsualizaciones
  3D** (`landing_page/`, `.preview-3d/`). Se añadieron y se borraron dentro de la propia rama
  (`af0a476` → `1734de8` y `0b993ab`, 21-22 ago), así que no están en el árbol final. No son datos.
  Reescribir el historial de una rama ya publicada sería peor que dejarlos.

## Qué DEFAULTS cambian (lo que cambia la salida de producción)

Comparando los YAML como datos (clave a clave) y los defaults del código:

**Benjamín y Villaviciosa** (`team_classification*.yaml` y código):
| qué | antes (`main`) | ahora |
|---|---|---|
| fit de color, `n_init` del KMeans | 10 (en el código) | **50** |
| regla de porteros | por ÁREA | **`ultimo_hombre`** por conjunto de fragmentos (0,55 / 0,50 / presencia 0,50 / duplicados a 2 m) |
| árbitro | — | **`uno_solo: true`** (también es el default del código), `margen_equipo: 0.0`, `devolver_por_color: false` |
| staff | — | **staff lento** (`tolerancia_lento_m −1,5`, `vel_max_lento 2,75`, `min_obs_lento 25`) |

**Solo benjamín**:
| qué | antes | ahora |
|---|---|---|
| `tracking_benja.yaml` | — | **plausibilidad física** (`ancho_min_frac 0,15`) |
| `team_classification_benja.yaml` | — | **etiqueta por observación** (ventana 1,5 s, `catalogo_arbitral`, `forzar_ab`) |
| config de producción | — | **`processor_benja_parte_entera.yaml`** (nuevo): `bytetrack`, 1 de cada 3, checkpoint cada 500 |

**Villaviciosa**: `tracking.yaml` y `processor.yaml` NO cambian. Sí cambia `team_classification.yaml`
(la tabla de arriba). `tracking_v4.yaml` gana la plausibilidad física, pero no es el config de
producción de Villaviciosa.

**Balón** (`ParametrosBalon`, defaults del código):
- `dist_max_jugadores` baja de 25 a 10 m;
- relleno de huecos con FUTURO (recta entre anclas, ≤ 1,2 s, ≤ 12 m/s, x ≥ 20 m);
- selector por continuidad (Viterbi) activo;
- balón de staff fuera del campo quitado;
- vuelos readmitidos (≤ 2,5 s);
- filtro de marcas estáticas, en `src/balon/carga.py`.

**Entrenamiento del balón** (`entrenamiento_balon.yaml`): el modelo base pasa de `yolov8n` a
`yolov8s`. El bloque `reentreno` entra, pero esa vía está **cerrada** (los dos candidatos
suspendieron); es configuración de un experimento, no de producción.

**Sin efecto en la salida**: en `perfiles.py` se quitó el interruptor muerto `_resolucion`; el CSV
de las dos patas sale idéntico byte a byte.

## Qué entra APAGADO (código presente, default off)

- `agregacion.por_observacion.excluir_ocluidas` (negativo del 21-sep).
- `cota_plantilla` y `exclusion_espacial`: `activa: false`, y ahora el código SÍ lee la clave. Solo
  existen en los perfiles `candidato`/`oficial`, que no son producción.
- ⚠️ `rescate_cortos.activo: false` **NO lo lee nadie**: el perfil `candidato` filtra las identidades
  cortas siempre. Es otro interruptor que no apaga nada, dormido porque producción usa `bytetrack`.
  No se toca en este merge; queda anotado.
- `segunda_pasada` solo la usa el banco (`scripts/evaluar_tracking.py`), no producción.
- `puerta_reentrada` (apagada en el benjamín).
- En la etiqueta por observación, `solo_catalogo` y `ampliar_ventana_s`.
- `staff.vel_max_lento` vale 0 (apagado) en el código: se enciende por config.
- `plausibilidad_fisica`: apagada en el código, se enciende por config.
- `entrenamiento.desde_s` (None).

## Qué se DESCARTA (vías cerradas: entra su código de medida y su documento, nada activo)

Todas con su medición en `docs/` y su fila en la tabla de vías cerradas de `CLAUDE.md`:
- guarda de caja fundida;
- calibración automática por líneas;
- reentreno del balón con el pool;
- vídeos panorámicos de grada como segunda pata;
- regla de forma contra el balón como persona;
- procesar 1/1 en vez de 1/3;
- suavizado por tiempo (V1/V2/V3);
- resolución local en el cosido;
- excluir ocluidos del voto por ventana.

Los scripts de esos experimentos (`scripts/*`) entran porque reproducen la medida del negativo.
Ninguno lo llama producción.

## Ramas que se pueden borrar DESPUÉS del merge

Comprobado con `merge-base --is-ancestor`: todo su contenido ya está en la rama que se fusiona.

**Remotas** (`origin/…`):
- `barrido/asociacion-combinada`, `barrido/fit-clasificador`, `barrido/suavizado`;
- `feature/analisis-ia`, `feature/balon`, `feature/informe-v2`, `feature/tracking-v4pre`,
  `feature/tracking-ventana`;
- `v4/caches-y-informe`, `v4/preparacion-dataset`;
- `experimento/asociacion-global`, una vez fusionada.

**Locales**:
- `barrido/fit-clasificador`, `feature/tracking-v4pre`, `v4/preparacion-dataset`;
- `experimento/asociacion-global`, tras el merge;
- `claude/fervent-galileo-22ae0a`: es el worktree de la otra sesión; borrar cuando esa sesión esté
  cerrada.

**NO borrar: `gt/identidad-benja` (local y remota).** Tiene 6 commits propios, y 6 de sus ficheros
**nunca llegaron** a esta rama:
- `scripts/etiquetar_tracking_gt.py` (**la herramienta de clic con la que se hizo el GT**);
- `scripts/probar_pose.py` y `docs/colab_pose_y_cronometros.md`;
- `scripts/auditar_homografia.py`, `scripts/cronometrar_embeddings.py` y `scripts/podar_embeddings.py`.

Los otros 6 ficheros de esa rama ya están aquí, idénticos. Decisión pendiente de Alex: fusionarla
aparte o conservarla.
