#!/usr/bin/env python
"""Elige el backbone de apariencia con el criterio de docs/benchmark_embeddings.md.

El criterio se fijó ANTES de ver un solo número, y este script lo aplica
tal cual. Resumen de por qué es así:

- **TPR @ FPR 1 % sobre parejas de MISMO EQUIPO**, no AUC. Fragmentar es
  recuperable, mezclar no: un falso positivo aquí ES una quimera. El AUC
  promediaría sobre puntos de operación que nunca usaríamos.
- **Doble estratificación**: tamaño de recorte (nuestros jugadores miden
  13-40 px y la media la sostienen los cercanos) × separación temporal
  (las quimeras nacen al RECUPERAR un track, no en el cruce instantáneo).
- **El histograma HSV es una columna más.** Si nadie lo bate, la línea de
  la apariencia queda muerta y hay que decirlo.

Solo se mide en Villaviciosa: es la única pata con GT posicional, que es
lo que permite saber si dos recortes son la misma persona. El mini-GT del
benjamín es de equipo, no de identidad.

Uso:
    python scripts/benchmark_embeddings.py
"""

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.tracking.cache_io import cargar_cache  # noqa: E402

logger = logging.getLogger("benchmark")

BINS_TAMANO = [("<20 px", 0, 20), ("20-30 px", 20, 30), (">30 px", 30, 1e9)]
BINS_TIEMPO = [("<1 s", 0.0, 1.0), ("2-5 s", 2.0, 5.0), (">5 s", 5.0, 1e9)]
# La casilla que decide, escrita en el criterio antes de medir.
CASILLA = ("<20 px", "2-5 s")
FPR_OBJETIVO = 0.01
MAX_PAREJAS = 60_000
SEMILLA = 0


def cargar_gt(cfg):
    gt = gt_a_por_frame(
        parsear_cvat(cfg["rutas"]["ground_truth"]),
        np.load(cfg["rutas"]["homografia"]),
        frame_offset=cfg["alineacion"]["frame_offset"],
        paso_gt=cfg["alineacion"]["paso_gt"],
    )
    return gt


def etiquetar(claves, cache, gt, umbral):
    """persona y equipo del GT para cada recorte; None si no casa."""
    pos = {}
    for e in cache:
        for i, d in enumerate(e["dets"]):
            pos[(e["frame_idx"], i)] = (d[0], d[1])
    personas, equipos = [], []
    for clave in claves:
        p = pos.get(tuple(clave))
        g = gt.get(clave[0]) if p is not None else None
        mejor, dmin, eq = None, umbral, None
        if g:
            for o in g:
                dist = float(np.linalg.norm(np.asarray(o.pos) - np.asarray(p)))
                if dist < dmin:
                    mejor, dmin, eq = o.obj_id, dist, o.team
        personas.append(mejor)
        equipos.append(str(eq))
    return np.array(personas, dtype=object), np.array(equipos, dtype=object)


def muestrear(indices_por_grupo, rng, positivas, frames, fps, n_max):
    """Parejas (i, j) positivas (misma persona) o negativas (distinta)."""
    grupos = list(indices_por_grupo.values())
    parejas = []
    if positivas:
        for idx in grupos:
            if len(idx) < 2:
                continue
            n = min(len(idx) * 4, n_max // max(1, len(grupos)))
            a = rng.choice(idx, size=n)
            b = rng.choice(idx, size=n)
            parejas.append(np.stack([a, b], axis=1))
    else:
        for k, idx_a in enumerate(grupos):
            for idx_b in grupos[k + 1 :]:  # noqa: E203
                if not len(idx_a) or not len(idx_b):
                    continue
                n = min(2000, n_max // max(1, len(grupos) ** 2))
                if n < 1:
                    continue
                parejas.append(
                    np.stack([rng.choice(idx_a, n), rng.choice(idx_b, n)], axis=1)
                )
    if not parejas:
        return np.zeros((0, 2), dtype=int)
    P = np.concatenate(parejas)
    P = P[P[:, 0] != P[:, 1]]
    return P


def distancias(vectores, parejas, coseno=True):
    a, b = vectores[parejas[:, 0]], vectores[parejas[:, 1]]
    if coseno:
        na = np.linalg.norm(a, axis=1) + 1e-9
        nb = np.linalg.norm(b, axis=1) + 1e-9
        return 1.0 - (a * b).sum(axis=1) / (na * nb)
    return np.linalg.norm(a - b, axis=1)


def tpr_a_fpr(d_pos, d_neg, fpr=FPR_OBJETIVO):
    """TPR cuando el umbral deja pasar solo `fpr` de los negativos."""
    if len(d_pos) < 10 or len(d_neg) < 10:
        return float("nan"), float("nan")
    umbral = float(np.quantile(d_neg, fpr))
    return float((d_pos <= umbral).mean()), umbral


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--emb", default="data/tracking", help="carpeta de emb_villa_*.pkl")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import yaml

    from src.evaluation.asociacion import UmbralProfundidad

    cfg = yaml.safe_load(open(args.config))
    datos = cargar_cache(cfg["rutas"]["cache"])
    gt = cargar_gt(cfg)
    umbral_gt = UmbralProfundidad.desde_dict(cfg["asociacion"]["umbral_profundidad"])

    candidatos = {}
    for f in sorted(Path(args.emb).glob("emb_villa_*.pkl")):
        with open(f, "rb") as fh:
            candidatos[f.stem.split("emb_villa_")[1]] = pickle.load(fh)

    # Línea de control: el histograma HSV que usamos hoy
    from src.team_classification.feature_v2 import parte_camiseta_hs

    with open(cfg["rutas"]["cache_colores"], "rb") as fh:
        colores = pickle.load(fh)

    ref = next(iter(candidatos.values()))
    claves = [tuple(c) for c in ref["claves"]]
    alturas = np.asarray(ref["alturas_px"])
    frames = np.array([c[0] for c in claves])
    fps = float(ref["fps"])

    hsv = np.stack(
        [
            parte_camiseta_hs(colores[c]) if c in colores else np.zeros(256)
            for c in claves
        ]
    )
    candidatos["HSV (control)"] = {"embeddings": hsv, "coseno": False}

    personas, equipos = etiquetar(claves, datos["cache"], gt, umbral_gt.base)
    validos = np.array([p is not None for p in personas])
    logger.info(
        "%d recortes, %d casados con el GT (%d personas)",
        len(claves),
        int(validos.sum()),
        len(set(personas[validos])),
    )

    rng = np.random.default_rng(SEMILLA)
    filas = []
    for nombre, datos_c in candidatos.items():
        V = np.asarray(datos_c["embeddings"], dtype=np.float32)
        coseno = datos_c.get("coseno", True)
        fila = {"nombre": nombre, "dims": V.shape[1]}

        for etiq_t, t_min, t_max in BINS_TAMANO:
            en_bin = validos & (alturas >= t_min) & (alturas < t_max)
            # Negativos: distinta persona, MISMO equipo, dentro del bin
            por_equipo = {}
            for i in np.flatnonzero(en_bin):
                por_equipo.setdefault(equipos[i], {}).setdefault(
                    personas[i], []
                ).append(i)
            d_neg_mismo, d_neg_otro = [], []
            for eq, por_persona in por_equipo.items():
                grupos = {k: np.array(v) for k, v in por_persona.items()}
                P = muestrear(grupos, rng, False, frames, fps, MAX_PAREJAS)
                if len(P):
                    d_neg_mismo.append(distancias(V, P, coseno))
            # distinto equipo
            equipos_lista = list(por_equipo)
            for k, ea in enumerate(equipos_lista):
                for eb in equipos_lista[k + 1 :]:  # noqa: E203
                    ia = np.concatenate([np.array(v) for v in por_equipo[ea].values()])
                    ib = np.concatenate([np.array(v) for v in por_equipo[eb].values()])
                    n = min(4000, len(ia), len(ib))
                    if n < 10:
                        continue
                    P = np.stack([rng.choice(ia, n), rng.choice(ib, n)], axis=1)
                    d_neg_otro.append(distancias(V, P, coseno))
            neg_mismo = np.concatenate(d_neg_mismo) if d_neg_mismo else np.zeros(0)
            neg_otro = np.concatenate(d_neg_otro) if d_neg_otro else np.zeros(0)

            # Positivos por separación temporal
            grupos_p = {}
            for i in np.flatnonzero(en_bin):
                grupos_p.setdefault(personas[i], []).append(i)
            grupos_p = {k: np.array(v) for k, v in grupos_p.items()}
            P = muestrear(grupos_p, rng, True, frames, fps, MAX_PAREJAS)
            if len(P):
                dt = np.abs(frames[P[:, 0]] - frames[P[:, 1]]) / fps
                d_pos_todas = distancias(V, P, coseno)
            for etiq_s, s_min, s_max in BINS_TIEMPO:
                if not len(P):
                    fila[(etiq_t, etiq_s)] = float("nan")
                    continue
                sel = (dt >= s_min) & (dt < s_max)
                tpr, _u = tpr_a_fpr(d_pos_todas[sel], neg_mismo)
                fila[(etiq_t, etiq_s)] = tpr
            fila[(etiq_t, "distinto equipo")] = tpr_a_fpr(
                d_pos_todas[(dt >= 2.0) & (dt < 5.0)] if len(P) else np.zeros(0),
                neg_otro,
            )[0]
            fila[(etiq_t, "n_neg")] = len(neg_mismo)
        filas.append(fila)

    # ── Tabla ──
    print("\n" + "=" * 78)
    print("TPR @ FPR=1 % sobre parejas de DISTINTA PERSONA del MISMO EQUIPO")
    print("(de cada 100 reencuentros reales, cuántos reconoce sin mezclar compañeros)")
    print("=" * 78)
    for etiq_t, _a, _b in BINS_TAMANO:
        print(f"\n── recortes {etiq_t} ──")
        cab = (
            f"{'backbone':<16}{'dims':>6}"
            + "".join(f"{s:>10}" for s, _x, _y in BINS_TIEMPO)
            + f"{'dist.equipo':>13}"
        )
        print(cab)
        print("-" * len(cab))
        for f in filas:
            vals = "".join(
                (
                    f"{f[(etiq_t, s)]:>10.3f}"
                    if f[(etiq_t, s)] == f[(etiq_t, s)]
                    else f"{'—':>10}"
                )
                for s, _x, _y in BINS_TIEMPO
            )
            de = f[(etiq_t, "distinto equipo")]
            print(
                f"{f['nombre']:<16}{f['dims']:>6}{vals}"
                + (f"{de:>13.3f}" if de == de else f"{'—':>13}")
            )

    # ── Regla de decisión, tal cual estaba escrita ──
    et, es = CASILLA
    print("\n" + "=" * 78)
    print(f"CASILLA QUE DECIDE: recortes {et} × reencuentro {es}")
    print("=" * 78)
    puntuacion = {f["nombre"]: f[(et, es)] for f in filas}
    base = puntuacion.get("HSV (control)", float("nan"))
    for nombre, v in sorted(
        puntuacion.items(), key=lambda kv: -(kv[1] if kv[1] == kv[1] else -1)
    ):
        marca = "  ← control" if nombre.startswith("HSV") else ""
        print(f"  {nombre:<16} {v:.3f}" if v == v else f"  {nombre:<16}   —", end="")
        print(marca)
    ganan = {
        k: v
        for k, v in puntuacion.items()
        if not k.startswith("HSV") and v == v and base == base and v > base
    }
    print()
    if not ganan:
        print("→ NINGÚN backbone bate al HSV en la casilla difícil.")
        print("  Según el criterio escrito: a 13-40 px NO hay señal de apariencia")
        print("  que extraer, y la línea de partir quimeras por apariencia queda")
        print("  MUERTA. Es un resultado negativo válido.")
    else:
        mejor = max(ganan, key=ganan.get)
        cercanos = [k for k, v in ganan.items() if ganan[mejor] - v < 0.03]
        if len(cercanos) > 1:
            dims = {f["nombre"]: f["dims"] for f in filas}
            mejor = min(cercanos, key=lambda k: dims[k])
            print(f"→ EMPATE TÉCNICO (<3 puntos) entre {', '.join(cercanos)}.")
            print(f"  Gana el más barato: {mejor} ({dims[mejor]} dims).")
        else:
            print(f"→ GANA {mejor}: {ganan[mejor]:.3f} vs {base:.3f} del HSV.")


if __name__ == "__main__":
    main()
