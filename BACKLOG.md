# BACKLOG autónomo (12-ago-2026)

Reglas: rama por tarea, medir contra el banco, tests, documentar en
`docs/experimentos_tracking.md`. Nada se adopta como default sin OK de
Alex — se deja "provisional en la rama" con la tabla delante. **Excepción
vigente**: si algo mejora TODAS las métricas sin degradar ninguna, se
adopta y se marca como tal.

| # | tarea | estado |
|---|---|---|
| 1 | Fix v2 + auditoría de consumidores + test e2e | ✅ **HECHO** (`e84a521`) |
| 2 | Rematar piloto del balón | ⛔ **PENDIENTE-ALEX** |
| 3 | Muestra estética | ✅ **HECHO** (`ec65347`), 1 min en vez de 3 |
| 4 | Pizarra táctica interactiva v1 | ⬜ pendiente |
| 5 | Informe v2 para F7 pulido | ⬜ pendiente |
| 6 | Preparar el v4 final (dataset 840 + W&B) | ⬜ pendiente |
| 7 | Robustez: TODOs, validaciones, sed frágil | ⬜ pendiente |
| 8 | Barrido COMBINADO de la asociación | 🔄 en curso |
| 9 | Barrido de suavizado × interpolación | ⬜ pendiente |
| 10 | Barrido del fit del clasificador | ⬜ pendiente |
| 11 | Repetir 8 y 10 con cachés v2color | ⛔ **PENDIENTE-ALEX** |

## Detalle de los bloqueos

### 2 — Piloto del balón: PENDIENTE-ALEX

**Qué falta**: los cachés. `data/tracking_benja/` solo tiene el tramo de
1 minuto; los `*piloto5min` y `cache_balon_piloto.pkl` nunca se llegaron
a generar (la sesión de Colab murió con el bug del salto, ya arreglado en
`39acfbe`).

**Qué necesito de ti**: correr los pasos 3-5 de
`docs/sesion_colab_completa.md` y bajarme:

- `data/tracking_benja/cache_balon_piloto.pkl`
- `data/tracking_benja/cache_detecciones_benja_piloto5min.pkl`
- `data/tracking_benja/cache_colores_benja_piloto5min.pkl`

Con eso, sin GPU, salen el CSV conjunto, el vídeo con cajas, el replay y
los números (% con balón, % en fase aérea, contactos).

### 11 — Barridos con v2color: PENDIENTE-ALEX

**Qué falta**: los cachés v2 (paso 6 de la guía). El fix ya está, así que
la generación debería correr limpia.

**Preparado para que sea un comando**: los scripts de barrido aceptan
`--config` y `--config-tracking`, así que en cuanto estén los cachés se
disparan apuntando a `configs/evaluation_v4pre_v2color.yaml`.

## 3 — Nota sobre la muestra estética

Se entregó con **1 minuto** (5:00–5:59 del vídeo), no 3, por el mismo
motivo que el punto 2: no hay cachés de 5 min. Cuando lleguen, regenerar
es un comando.
