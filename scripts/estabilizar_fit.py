#!/usr/bin/env python
"""Estabilizar el fit del color, que es el canal de ruido de Villaviciosa.

Medido en `docs/suelo_de_ruido.md`: quitando 5 detecciones al azar de
10.040, la cobertura de Villaviciosa se mueve 0,047 y la accuracy de
equipos 0,085, y **congelando el fit el ruido desaparece**. Aquí se
intenta arreglar el fit.

## Los tres candidatos que apunté quedan REFUTADOS por el mecanismo

Escribí que el problema era el `argmax` sobre la rejilla de umbrales, y
propuse promediar la meseta, interpolar el máximo o promediar los
prototipos empatados. Mirando la curva de puntuación de cerca, las tres
atacan algo que no pasa:

| umbral | sin perturbar (n1, n2, n3) | con 5 dets menos |
|---|---|---|
| 0,75 | 0,7379 (1259, 1080, 151) | 0,7348 (1233, 1081, 175) |
| **0,90** | **0,9023 (1259, 1231, 95)** | **0,7003 (1408, 1081, 95)** |
| 0,95-1,05 | 0,9023 (igual) | 0,7003 (igual) |

La puntuación es una FUNCIÓN ESCALÓN y la meseta 0,90-1,05 es idéntica en
los dos casos, así que elegir su centro, interpolar o promediar sobre
ella da exactamente lo mismo. Lo que cambia es **la partición dentro del
escalón**: al quitar UNA feature de 2.658, los centros del KMeans se
mueven, cambia el orden de fusión del árbol jerárquico y un cluster de
~150 muestras se pasa de bando (1231 → 1081). El umbral solo es el
mensajero.

Se miden igualmente los tres —para no fiarse de un razonamiento— y otros
que sí atacan el mecanismo:

- **meseta / promedio_meseta**: los propuestos. Se espera que no cambien
  nada, y si cambian algo es que el razonamiento de arriba está mal.
- **bagging**: K fits sobre submuestras y promedio de los prototipos,
  alineando A/B entre fits. Ataca directamente la varianza del KMeans.
- **dos_medias**: se salta el barrido de umbral y el criterio de "los dos
  meta-grupos más grandes". Agrupa los k centros del KMeans en DOS con
  2-medias ponderado por masa. No hay decisión discreta que saltar.
- **n_init**: subir los reinicios del KMeans, por si la varianza es del
  propio KMeans y no de la muestra.

Criterio doble de Alex, y hay que cumplir LOS DOS:
1. que la dispersión bajo perturbación caiga a la del fit congelado
   (cobertura 0,001 · equipos 0,003),
2. que las métricas SIN perturbar no empeoren.

Uso:
    python scripts/estabilizar_fit.py
    python scripts/estabilizar_fit.py --semillas 6 --solo actual,bagging
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.cluster import KMeans

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")

from medir_migracion_bytetrack import Banco, medir  # noqa: E402
from src.team_classification.color_classifier import (  # noqa: E402
    ParametrosClasificadorColor,
    TeamClassifierColor,
    _Prototipos,
    _solo_hs,
)
from src.team_classification.pipeline_equipos import (  # noqa: E402
    _profundidad_configurada,
    clasificar_identidades,
)
from src.tracking.interpolacion import (  # noqa: E402
    identidades_a_trayectorias,
    interpolar_trayectorias,
)
from src.tracking.perfiles import correr_perfil  # noqa: E402
from suelo_de_ruido import quitar_al_azar  # noqa: E402

logger = logging.getLogger("fit")

METRICAS = [
    ("cobertura", "cobertura", "{:.3f}"),
    ("acc", "equipos", "{:.3f}"),
    ("idf1", "IDF1", "{:.3f}"),
    ("quimeras", "quim", "{:.0f}"),
    ("nids", "nIds", "{:.0f}"),
]


def features_cercanas(cache, colores, cfg_eq):
    """Las features con las que se entrena, igual que `entrenar_clasificador`."""
    modelo, prof = _profundidad_configurada(cfg_eq)
    cfg_fit = cfg_eq.get("entrenamiento", {})
    if not cfg_fit.get("solo_cercanos", True):
        return np.array([_solo_hs(f) for f in colores.values()])
    umbral = cfg_fit.get("umbral_profundidad_m", cfg_fit.get("umbral_my", 34.0))
    prof_por = {
        (e["frame_idx"], i): prof.de((d[0], d[1]), modelo)
        for e in cache
        for i, d in enumerate(e["dets"])
    }
    cercanas = [
        _solo_hs(f)
        for k, f in colores.items()
        if prof_por.get(k, float("inf")) < umbral
    ]
    minimo = cfg_fit.get("min_features", 300)
    if len(cercanas) >= minimo:
        return np.array(cercanas)
    return np.array([_solo_hs(f) for f in colores.values()])


def _arbol(features, p, n_init=10, semilla=None):
    km = KMeans(
        n_clusters=p.k_clusters,
        n_init=n_init,
        random_state=p.semilla if semilla is None else semilla,
    )
    asign = km.fit_predict(features)
    return km, asign, linkage(km.cluster_centers_, method="average")


def _puntuacion(enlaces, asign, u):
    meta = fcluster(enlaces, t=u, criterion="distance")
    if len(np.unique(meta)) < 2:
        return None, meta
    tam = sorted(
        (int(np.isin(asign, np.where(meta == g)[0]).sum()) for g in np.unique(meta)),
        reverse=True,
    )
    n1, n2 = tam[0], tam[1]
    n3 = tam[2] if len(tam) > 2 else 0
    equilibrio = n2 / n1 if n1 else 0.0
    separacion = 1.0 - (n3 / n2 if n2 else 1.0)
    return equilibrio * separacion, meta


def _prototipos_de(features, asign, meta):
    tam = {
        g: int(np.isin(asign, np.where(meta == g)[0]).sum()) for g in np.unique(meta)
    }
    orden = sorted(tam, key=tam.get, reverse=True)
    if len(orden) < 2:
        return None
    ma = np.isin(asign, np.where(meta == orden[0])[0])
    mb = np.isin(asign, np.where(meta == orden[1])[0])
    mo = ~(ma | mb)
    return _Prototipos(
        a=features[ma].mean(axis=0),
        b=features[mb].mean(axis=0),
        otro=features[mo].mean(axis=0) if mo.any() else None,
    )


def _alinear(proto, ref):
    """Deja (a, b) en el mismo orden que la referencia."""
    if ref is None:
        return proto
    directo = np.linalg.norm(proto.a - ref.a) + np.linalg.norm(proto.b - ref.b)
    cruzado = np.linalg.norm(proto.a - ref.b) + np.linalg.norm(proto.b - ref.a)
    if cruzado < directo:
        return _Prototipos(a=proto.b, b=proto.a, otro=proto.otro)
    return proto


# ─────────────────────────── estrategias ───────────────────────────────


def fit_actual(features, p, **kw):
    _km, asign, enl = _arbol(features, p)
    mejor_u, mejor_s = None, -1.0
    for u in np.arange(p.umbral_min, p.umbral_max + 1e-9, p.umbral_paso):
        s, _ = _puntuacion(enl, asign, u)
        if s is not None and s > mejor_s:
            mejor_s, mejor_u = s, float(u)
    if mejor_u is None:
        mejor_u = p.umbral_min
    _s, meta = _puntuacion(enl, asign, mejor_u)
    return _prototipos_de(features, asign, meta)


def fit_meseta(features, p, **kw):
    """Centro de la MESETA de umbrales empatados con el máximo."""
    _km, asign, enl = _arbol(features, p)
    us = list(np.arange(p.umbral_min, p.umbral_max + 1e-9, p.umbral_paso))
    puntos = [(float(u), _puntuacion(enl, asign, u)[0]) for u in us]
    validos = [(u, s) for u, s in puntos if s is not None]
    if not validos:
        return fit_actual(features, p)
    mejor = max(s for _u, s in validos)
    meseta = [u for u, s in validos if s >= mejor - 1e-9]
    centro = float(np.median(meseta))
    _s, meta = _puntuacion(enl, asign, centro)
    return _prototipos_de(features, asign, meta)


def fit_promedio_meseta(features, p, **kw):
    """Promedio de los PROTOTIPOS de todos los umbrales empatados."""
    _km, asign, enl = _arbol(features, p)
    us = list(np.arange(p.umbral_min, p.umbral_max + 1e-9, p.umbral_paso))
    puntos = [(float(u), _puntuacion(enl, asign, u)) for u in us]
    validos = [(u, s) for u, (s, _m) in puntos if s is not None]
    if not validos:
        return fit_actual(features, p)
    mejor = max(s for _u, s in validos)
    protos, ref = [], None
    for u, (s, meta) in puntos:
        if s is None or s < mejor - 1e-9:
            continue
        pr = _prototipos_de(features, asign, meta)
        if pr is None:
            continue
        pr = _alinear(pr, ref)
        ref = ref or pr
        protos.append(pr)
    if not protos:
        return fit_actual(features, p)
    return _Prototipos(
        a=np.mean([x.a for x in protos], axis=0),
        b=np.mean([x.b for x in protos], axis=0),
        otro=(
            np.mean([x.otro for x in protos if x.otro is not None], axis=0)
            if any(x.otro is not None for x in protos)
            else None
        ),
    )


def fit_bagging(features, p, n_bolsas=9, fraccion=0.8, **kw):
    """K fits sobre submuestras y promedio de los prototipos alineados.

    Ataca la varianza directamente: si un cluster se pasa de bando en una
    submuestra pero no en las otras ocho, el promedio apenas se mueve.
    """
    rnd = np.random.RandomState(p.semilla)
    protos, ref = [], None
    n = max(int(len(features) * fraccion), p.k_clusters * 2)
    for _i in range(n_bolsas):
        idx = rnd.choice(len(features), size=n, replace=False)
        sub = features[idx]
        pr = fit_actual(sub, p)
        if pr is None:
            continue
        pr = _alinear(pr, ref)
        if ref is None:
            ref = pr
        protos.append(pr)
    if not protos:
        return fit_actual(features, p)
    con_otro = [x.otro for x in protos if x.otro is not None]
    return _Prototipos(
        a=np.mean([x.a for x in protos], axis=0),
        b=np.mean([x.b for x in protos], axis=0),
        otro=np.mean(con_otro, axis=0) if con_otro else None,
    )


def fit_dos_medias(features, p, **kw):
    """Sin barrido de umbral: 2-medias sobre los k centros, ponderado por masa.

    Quita la decisión discreta de raíz. Los dos equipos son los dos
    grupos de centros más separados, no "los dos meta-grupos más grandes
    al umbral que gane un barrido".
    """
    km, asign, _enl = _arbol(features, p)
    masas = np.array([int((asign == c).sum()) for c in range(p.k_clusters)])
    km2 = KMeans(n_clusters=2, n_init=20, random_state=p.semilla)
    etiqueta = km2.fit_predict(km.cluster_centers_, sample_weight=masas)
    ma = np.isin(asign, np.where(etiqueta == 0)[0])
    mb = ~ma
    if ma.sum() < mb.sum():
        ma, mb = mb, ma
    return _Prototipos(
        a=features[ma].mean(axis=0), b=features[mb].mean(axis=0), otro=None
    )


def fit_ninit(features, p, n_init=50, **kw):
    """El actual pero con más reinicios del KMeans."""
    _km, asign, enl = _arbol(features, p, n_init=n_init)
    mejor_u, mejor_s = None, -1.0
    for u in np.arange(p.umbral_min, p.umbral_max + 1e-9, p.umbral_paso):
        s, _ = _puntuacion(enl, asign, u)
        if s is not None and s > mejor_s:
            mejor_s, mejor_u = s, float(u)
    _s, meta = _puntuacion(enl, asign, mejor_u or p.umbral_min)
    return _prototipos_de(features, asign, meta)


ESTRATEGIAS = {
    "actual": fit_actual,
    "meseta": fit_meseta,
    "promedio_meseta": fit_promedio_meseta,
    "bagging": fit_bagging,
    "dos_medias": fit_dos_medias,
    "ninit50": fit_ninit,
}


# ──────────────────────────── medición ─────────────────────────────────


def evaluar(banco, cache, colores, estrategia):
    p = (
        ParametrosClasificadorColor.desde_dict(banco.cfg_equipos["clasificador_color"])
        if "clasificador_color" in banco.cfg_equipos
        else ParametrosClasificadorColor()
    )
    features = features_cercanas(cache, colores, banco.cfg_equipos)
    clf = TeamClassifierColor(p)
    clf._prototipos = ESTRATEGIAS[estrategia](features, p)
    identidades = correr_perfil(
        cache,
        banco.datos["fps"],
        banco.datos["sample"],
        banco.cfg_tracking,
        perfil="bytetrack",
        colores=colores,
        clasificador=clf,
        cfg_equipos=banco.cfg_equipos,
    )
    equipos = clasificar_identidades(identidades, colores, clf, banco.cfg_equipos)
    tray = interpolar_trayectorias(
        identidades_a_trayectorias(identidades), banco.frames_ts, max_hueco=6.0
    )
    return medir(
        "x", tray, equipos, banco.gt, banco.comunes, banco.tiempos, banco.umbral
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="configs/evaluation_v4.yaml")
    p.add_argument("--config-tracking", default="configs/tracking_v4.yaml")
    p.add_argument("--semillas", type=int, default=6)
    p.add_argument("--quitar", type=int, default=5)
    p.add_argument("--solo", default=",".join(ESTRATEGIAS))
    args = p.parse_args()
    logging.basicConfig(level=logging.CRITICAL)

    banco = Banco(args.config, args.config_tracking)
    cache0 = banco.datos["cache"]
    perturbados = [
        quitar_al_azar(cache0, banco.colores, args.quitar, s)
        for s in range(1, args.semillas + 1)
    ]
    print(
        f"\n{args.config} · quitando {args.quitar} detecciones al azar · "
        f"{args.semillas} semillas"
    )
    cab = f"  {'estrategia':<18}{'':<3}"
    for _c, etiq, _f in METRICAS:
        cab += f"{etiq:>15}"
    print("\n" + cab)
    print("  " + "-" * (len(cab) - 2))
    for nombre in args.solo.split(","):
        base = evaluar(banco, cache0, banco.colores, nombre)
        linea = f"  {nombre:<18}{'base':<3}"
        for clave, _e, fmt in METRICAS:
            linea += f"{fmt.format(float(base[clave])):>15}"
        print(linea)
        res = [evaluar(banco, c, col, nombre) for c, col in perturbados]
        linea = f"  {'':<18}{'±':<3}"
        for clave, _e, fmt in METRICAS:
            v = np.array([float(r[clave]) for r in res])
            linea += (
                f"{fmt.format(v.min()):>15}"
                if v.min() == v.max()
                else f"{fmt.format(v.min()) + '-' + fmt.format(v.max()):>15}"
            )
        print(linea)
        print()


if __name__ == "__main__":
    main()
