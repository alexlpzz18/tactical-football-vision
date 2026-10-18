#!/usr/bin/env python
"""Cuántas identidades 'se teletransportan' (cambio de identidad) en los 20 min.

1. Identidades del perfil de producción (bytetrack) sobre el caché entero,
   posiciones SIN suavizar (las del Tracklet, proyección directa de la caja).
2. Salto en un paso: > SALTO_M en <= DT_PASO s entre observaciones consecutivas.
3. PERSISTENTE (cambio de persona) si la mediana del segundo siguiente está a
   > SALTO_M de la del segundo anterior. Si no, es temblor o un error suelto.
4. Firma de caja FUNDIDA: la caja del salto mide >= 1,25x la mediana de alto de
   esa identidad en ±2 s.
5. Aparte, los saltos imposibles tras un HUECO (re-entrada, 0,35-2,5 s).

Resultados y su verificación a ojo: docs/cambio_de_identidad_por_caja_fundida.md

Uso:
    python scripts/cambios_de_identidad.py [carpeta_de_salida]
"""

import pickle
import sys

from pathlib import Path

import numpy as np
import yaml

R = str(Path(__file__).resolve().parent.parent) + "/"
S = sys.argv[1] if len(sys.argv) > 1 else "outputs/cambios_de_identidad"
Path(S).mkdir(parents=True, exist_ok=True)
sys.path.insert(0, R)

from src.team_classification.pipeline_equipos import cargar_config_equipos  # noqa: E402
from src.team_classification.pipeline_equipos import entrenar_clasificador  # noqa: E402
from src.tracking.cache_io import cargar_cache  # noqa
from src.tracking.filtro_confianza import filtrar_por_confianza  # noqa
from src.tracking.perfiles import correr_perfil  # noqa

SALTO_M, DT_PASO, VENTANA_S, FACTOR_FUNDIDA = 3.0, 0.35, 1.0, 1.25

cfg = yaml.safe_load(open(R + "configs/processor_benja_parte_entera.yaml"))
cfg_tr = yaml.safe_load(open(R + cfg["config_tracking"]))
datos = cargar_cache(R + cfg["rutas"]["cache"])
with open(R + cfg["rutas"]["cache_colores"], "rb") as fh:
    colores = pickle.load(fh)
cache, colores = filtrar_por_confianza(
    datos["cache"], colores, float(cfg_tr.get("confianza_min", 0) or 0)
)
cfg_eq = cargar_config_equipos(R + cfg["config_equipos"])
clf = entrenar_clasificador(colores, cfg_eq, cache)
ids = correr_perfil(
    cache,
    datos["fps"],
    datos["sample"],
    cfg_tr,
    perfil="bytetrack",
    colores=colores,
    clasificador=clf,
    cfg_equipos=cfg_eq,
)
dets = {e["frame_idx"]: e["dets"] for e in cache}
pickle.dump(ids, open(f"{S}/identidades_p1.pkl", "wb"))
print(f"identidades: {len(ids)}")

eventos, reentradas, saltos_un_paso = [], [], 0
for k, ident in enumerate(ids, start=1):
    obs = sorted(
        (t, np.asarray(p, float), par)
        for tr in ident
        for t, p, par in zip(tr.ts, tr.pos, tr.det_idxs)
    )
    ts = np.array([o[0] for o in obs])
    ps = np.array([o[1] for o in obs])
    alto = np.array(
        [dets[o[2][0]][o[2][1]][5] - dets[o[2][0]][o[2][1]][3] for o in obs]
    )
    for i in range(1, len(obs)):
        dt = ts[i] - ts[i - 1]
        salto = float(np.linalg.norm(ps[i] - ps[i - 1]))
        if dt <= DT_PASO and salto > SALTO_M:
            saltos_un_paso += 1
            pre = ps[(ts >= ts[i - 1] - VENTANA_S) & (ts <= ts[i - 1])]
            post = ps[(ts >= ts[i]) & (ts <= ts[i] + VENTANA_S)]
            if len(pre) < 3 or len(post) < 3:
                continue
            d = float(np.linalg.norm(np.median(post, 0) - np.median(pre, 0)))
            ref = alto[(np.abs(ts - ts[i]) <= 2.0) & (np.arange(len(ts)) != i)]
            fundida = bool(len(ref) and alto[i] >= FACTOR_FUNDIDA * np.median(ref))
            eventos.append(
                dict(
                    id=k,
                    t=float(ts[i]),
                    frame=obs[i][2][0],
                    salto=salto,
                    persiste=d > SALTO_M,
                    d_medianas=d,
                    fundida=fundida,
                    x=float(np.median(pre, 0)[0]),
                    y=float(np.median(pre, 0)[1]),
                    n_obs=len(obs),
                )
            )
        elif DT_PASO < dt <= 2.5 and salto > 8.0 * dt + 2.0:
            reentradas.append(dict(id=k, t=float(ts[i]), dt=float(dt), salto=salto))

pickle.dump(
    {"eventos": eventos, "reentradas": reentradas},
    open(f"{S}/punto4_eventos.pkl", "wb"),
)
# Solo DENTRO del campo (con 1 m de margen en la banda): fuera hay público y
# árboles proyectados a decenas de metros, cuyo "salto" no es de nadie.
dentro = [e for e in eventos if 0 <= e["x"] <= 62 and -1 <= e["y"] <= 41]
pers = [e for e in dentro if e["persiste"]]
print(
    f"saltos de >{SALTO_M} m en un paso: {saltos_un_paso} · con ventanas medibles: "
    f"{len(eventos)} · dentro del campo: {len(dentro)}"
)
# ⚠️ "Persistente" NO es "cambio de persona": verificado a ojo sobre 12, la
# mitad larga de los que no tienen caja fundida son el pie de la caja
# desplazándose en el fondo (docs/cambio_de_identidad_por_caja_fundida.md).
print(
    f"  PERSISTENTES dentro del campo (CANDIDATOS a cambio de persona, verificar a ojo): "
    f"{len(pers)} = {len(pers) / 20:.1f}/min · identidades distintas: "
    f"{len({e['id'] for e in pers})} de {len(ids)}"
)
print(
    f"  de ellos con caja FUNDIDA (>= {FACTOR_FUNDIDA}x de alto, la firma más fiable): "
    f"{sum(e['fundida'] for e in pers)} · sin esa firma: {sum(not e['fundida'] for e in pers)}"
)
print(f"  NO persistentes dentro (temblor / error suelto): {len(dentro) - len(pers)}")
xs = np.array([e["x"] for e in pers])
for a, b in ((0, 20), (20, 40), (40, 62.01)):
    print(
        f"  persistentes con x en {a:.0f}-{b:.0f} m: {int(((xs >= a) & (xs < b)).sum())}"
    )
print(f"re-entradas imposibles tras un hueco (0,35-2,5 s): {len(reentradas)}")
