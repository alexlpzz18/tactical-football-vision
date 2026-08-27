# BACKLOG autónomo (12-ago-2026)

Reglas: rama por tarea, medir contra el banco, tests, documentar en
`docs/experimentos_tracking.md`. Nada se adopta como default sin OK de
Alex — se deja "provisional en la rama" con la tabla delante. **Excepción
vigente**: si algo mejora TODAS las métricas sin degradar ninguna, se
adopta y se marca como tal.

| # | tarea | estado |
|---|---|---|
| 1 | Fix v2 + auditoría de consumidores + test e2e | ✅ **HECHO** (`e84a521`) |
| 2 | Rematar piloto del balón | ✅ **HECHO** (`c0518d8`) |
| 3 | Muestra estética | ✅ **HECHO** (`ec65347`), 1 min en vez de 3 |
| 4 | Pizarra táctica interactiva v1 | ⬜ pendiente |
| 5 | Informe v2 para F7 pulido | ✅ **HECHO** — muestra del benja generada |
| 6 | Preparar el v4 final (dataset 840 + W&B) | ✅ **HECHO** — dos celdas listas |
| 7 | Robustez: TODOs, validaciones, sed frágil | ⬜ pendiente |
| 8 | Barrido COMBINADO de la asociación | 🔄 en curso |
| 9 | Barrido de suavizado × interpolación | ✅ **HECHO** — dos presets, ninguno adoptado |
| 10 | Barrido del fit del clasificador | ✅ **HECHO** — radio 45 adoptado |
| 11 | Repetir 8 y 10 con cachés v2color | ⚠️ **PARCIAL** — benja OK (empate), Villaviciosa con detector equivocado |

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

## 12. Apariencia en la ASOCIACIÓN (abierta 17-ago-2026)
Diseño en `docs/apariencia_en_asociacion.md`. Es donde viven las 5-8
quimeras que resisten al detector nuevo y al barrido del fit.
- [ ] Paso 0 — DIAGNÓSTICO: ¿las 8 quimeras de Villaviciosa nacen en
      frames con solape de cajas? Si la mayoría no nace ahí, toda la
      hipótesis es falsa y no hay que construir nada encima.
- [ ] Camino A — veto de color SOLO en el instante de cruce (no global:
      cortar con señales ruidosas en todos los frames ya salió mal tres
      veces).
- [ ] Camino B — asociación propia con coste mixto IoU+color, solo si A
      confirma la hipótesis.
Criterio: quimeras 8 → menos SIN degradar cobertura 0,598, IDF1 0,484 ni
concurrencia 23.

## 13. La animación tiene que respetar lo que la cámara TAPA (idea de Alex, 27-ago-2026)

Si sabemos que la cámara tapa una zona —por ejemplo la esquina inferior
izquierda— y un jugador aparece de repente ahí, no ha aparecido de la
nada: **viene de ahí**. La ficha del replay debería entrar desde la zona
tapada en vez de materializarse en el sitio, que es lo que hoy se lee
como un fallo del sistema.

Es la misma familia de ideas que ya pagó dos veces en este proyecto: el
valor está en el CONOCIMIENTO DEL DOMINIO —dónde está la cámara, qué
tapa, por dónde se entra al campo— y no en el modelo.

Lo que haría falta, en orden:
- [ ] Declarar las zonas ciegas en el config del campo (son una propiedad
      de la CÁMARA de ese partido, como `espejar`).
- [ ] Comprobar la premisa antes de construir: ¿las apariciones súbitas
      se concentran de verdad en esas zonas? Si aparecen por todo el
      campo, la explicación es otra (fallo de asociación) y taparla con
      una animación la escondería.
- [ ] Solo entonces, la entrada/salida animada desde el borde de la zona.

⚠️ El riesgo conocido: una animación que rellena lo que no se vio es una
posición INVENTADA. Tiene que distinguirse de una medida (el replay ya
tiene el desvanecido por antigüedad para eso) o el replay pasa de mostrar
lo que el sistema ve a mostrar lo que suponemos.
