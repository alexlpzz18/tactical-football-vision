#!/usr/bin/env python
"""Diagnóstico 23-oct (b), bloque 1: ¿qué definición de «cruce» cubre los cambios de persona reales?

Solo medición. Criterio en `docs/diagnostico_23oct_b.md`. Sobre la salida de ByteTrack de hoy (donde
actuaría el corte), en las ventanas del GT de las dos patas.

Uso:
    python scripts/diag23b_cortes.py --salida outputs/diagnostico_23oct_b
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
UMBRALES_IOU = (0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5)
MARGEN_S, DIST_METROS = 0.5, 2.0


def _mod(nombre):
    spec = importlib.util.spec_from_file_location(nombre, R / f"scripts/{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def por_deteccion(cache):
    """{(frame, det): (IoU máx. con otra caja, distancia mínima en metros a otra detección)}."""
    from src.tracking.asociacion_bytetrack import _iou_maximo

    out = {}
    for e in cache:
        dets = e["dets"]
        if not dets:
            continue
        iou = _iou_maximo(np.array([d[2:6] for d in dets], float))
        P = np.array([d[:2] for d in dets], float)
        D = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])
        np.fill_diagonal(D, np.inf)
        dmin = D.min(axis=1) if len(dets) > 1 else np.full(len(dets), np.inf)
        for j in range(len(dets)):
            out[(e["frame_idx"], j)] = (float(iou[j]), float(dmin[j]))
    return out


def cortes_de(ident, info, en_cruce, f0, f1, t_de):
    """Instantes de corte (paso de limpia a cruce) de una identidad dentro de [f0, f1]."""
    obs = sorted(
        (int(p[0]), int(p[1])) for tr in ident for p in tr.det_idxs if f0 <= p[0] <= f1
    )
    cortes, previo = [], False
    for f, j in obs:
        c = en_cruce(info[(f, j)])
        if c and not previo:
            cortes.append(t_de[f])
        previo = c
    return cortes


def evaluar(idents, persona, gt, info, t_de, en_cruce, paso_s) -> dict:
    frames_gt = sorted(gt)
    f0, f1 = frames_gt[0], frames_gt[-1]
    cambios = []  # (identidad, t_f, t_g)
    for i, _ident in enumerate(idents):
        casadas = sorted(f for (ii, f) in persona if ii == i)
        for f, g in zip(casadas[:-1], casadas[1:]):
            if persona[(i, f)] != persona[(i, g)]:
                cambios.append((i, t_de[f], t_de[g]))
    cortes = {
        i: cortes_de(ident, info, en_cruce, f0, f1, t_de)
        for i, ident in enumerate(idents)
    }
    cubiertos = sum(
        any(tf - MARGEN_S <= t <= tg + MARGEN_S for t in cortes[i])
        for i, tf, tg in cambios
    )
    n_cortes = sum(len(v) for v in cortes.values())
    utiles = sum(
        any(tf - MARGEN_S <= t <= tg + MARGEN_S for ii, tf, tg in cambios if ii == i)
        for i, ts in cortes.items()
        for t in ts
    )
    persona_min = sum(len(gt[f]) for f in frames_gt) * paso_s / 60
    return {
        "cambios_verdaderos": len(cambios),
        "recall": round(cubiertos / max(len(cambios), 1), 3),
        "cortes": n_cortes,
        "precision": round(utiles / max(n_cortes, 1), 3),
        "cortes_por_persona_minuto": round(n_cortes / persona_min, 2),
    }


def pixeles_por_2m(cache, H) -> float:
    """Mediana de los píxeles que ocupan 2 m en las detecciones (homografía inversa)."""
    Hi = np.linalg.inv(H)

    def a_px(x, y):
        q = Hi @ np.array([x, y, 1.0])
        return q[:2] / q[2]

    d = []
    for e in cache[:: max(1, len(cache) // 300)]:
        for det in e["dets"]:
            x, y = det[0], det[1]
            d.append(
                (
                    np.linalg.norm(a_px(x + 2, y) - a_px(x, y))
                    + np.linalg.norm(a_px(x, y + 2) - a_px(x, y))
                )
                / 2
            )
    return float(np.median(d))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    dp, col = _mod("diag22f_pureza"), _mod("diag22g_color")
    res = {}
    for pata in ("benja", "villa"):
        cfg = yaml.safe_load(open(col.CONFIGS[pata]))
        captura, datos = dp.capturar(col.CONFIGS[pata], salida / f"cortes_{pata}.csv")
        gt = col.gt_de(pata)
        idents = captura["bytetrack"]
        _obs, persona = dp.casar_etapa("bytetrack", idents, None, gt)
        info = por_deteccion(datos["cache"])
        t_de = {e["frame_idx"]: e["t"] for e in datos["cache"]}
        paso_s = 15 / float(datos["fps"])
        defs = {"a_metros_2m": lambda v: v[1] < DIST_METROS}
        for t in UMBRALES_IOU:
            defs[f"iou_>{t:g}"] = lambda v, t=t: v[0] > t
        res[pata] = {
            "pixeles_por_2m_mediana": round(
                pixeles_por_2m(datos["cache"], np.load(R / cfg["rutas"]["homografia"])),
                1,
            ),
            **{
                n: evaluar(idents, persona, gt, info, t_de, f, paso_s)
                for n, f in defs.items()
            },
        }
    # (c): el mayor t de IoU con recall ≥ 80 % en las dos patas
    validos = [
        t
        for t in UMBRALES_IOU
        if all(res[p][f"iou_>{t:g}"]["recall"] >= 0.80 for p in ("benja", "villa"))
    ]
    t_c = max(validos) if validos else None
    res["c_umbral_iou_fijado"] = t_c
    cands = {"a_metros_2m": "a_metros_2m", "b_iou_>0.1": "iou_>0.1"}
    if t_c is not None:
        cands["c_iou_fijado"] = f"iou_>{t_c:g}"
    ok = {
        k: sum(res[p][v]["cortes_por_persona_minuto"] for p in ("benja", "villa"))
        for k, v in cands.items()
        if all(res[p][v]["recall"] >= 0.80 for p in ("benja", "villa"))
    }
    res["eleccion"] = (
        min(ok, key=ok.get) if ok else "NINGUNA llega a recall ≥ 80 % en las dos patas"
    )
    res["eleccion_columna"] = cands.get(res["eleccion"])
    texto = json.dumps(res, indent=1, ensure_ascii=False)
    (salida / "bloque1.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
