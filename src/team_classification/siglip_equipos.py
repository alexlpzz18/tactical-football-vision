"""Equipos con SigLIP, elegido POR PARTIDO con la consistencia física.

Plan y medidas: docs/plan_siglip_por_partido.md.

Interruptor `siglip.activo` del YAML de equipos (apagado por defecto). Con él:

1. Se leen las etiquetas 0/1 de SigLIP por detección (UMAP 3D + K-means de 2 sobre el embedding del
   torso; las produce `scripts/lit_siglip_etiquetar.py` a partir de la celda de GPU). Van indexadas
   por el caché de detecciones CRUDO; aquí se alinean con el caché que usa el tracking por
   igualdad de caja (el processor puede filtrar detecciones y renumerarlas).
2. El selector compara, en parejas de ventanas de 1,5 s de tramos aislados de la MISMA identidad
   con un cambio de profundidad ≥ 6 m, la kappa de la partición HS y la de SigLIP («una persona no
   cambia de equipo»). Si SigLIP gana por `margen_kappa` con al menos `min_parejas` parejas, se usa
   SigLIP; si no, todo sigue como hoy.
3. Con SigLIP, los nombres 0/1 se pasan a A/B por mayoría de acuerdo con el clasificador HS (para
   que los colores y las reglas de porteros sigan hablando de los mismos equipos), y el voto por
   ventana decide con la mayoría de SigLIP de la ventana en vez de con el color medio.

Medido (intento 2): el selector elige HS en el benjamín y SigLIP en el alevín B; en el alevín B el
mini-GT a ojo pasa de 79,7 a 89,9 %. La adopción en `main` depende de la hoja de 300 recortes.
"""

import logging
from types import SimpleNamespace

import numpy as np

logger = logging.getLogger(__name__)


def alinear_por_caja(etiquetas_crudas: dict, cache_crudo: list, cache: list) -> dict:
    """{(frame, j del caché del tracking): etiqueta}, desde claves del caché crudo, por caja."""
    crudo = {e["frame_idx"]: e["dets"] for e in cache_crudo}
    salida = {}
    for e in cache:
        f = e["frame_idx"]
        cajas = np.array([d[2:6] for d in crudo.get(f, [])], dtype=float).reshape(-1, 4)
        if not len(cajas):
            continue
        for j, det in enumerate(e["dets"]):
            dif = np.abs(cajas - np.asarray(det[2:6], dtype=float)).sum(axis=1)
            k = int(np.argmin(dif))
            if dif[k] < 1e-3 and (f, k) in etiquetas_crudas:
                salida[(f, j)] = int(etiquetas_crudas[(f, k)])
    return salida


def elegir(
    identidades,
    colores: dict,
    etiquetas: dict,
    cache: list,
    dentro,
    profundidad_de,
    cfg: dict,
) -> dict:
    """Informe del selector: kappas, parejas y si se usa SigLIP."""
    from sklearn.cluster import KMeans

    from src.team_classification.color_classifier import (
        ParametrosClasificadorColor,
        _feature_trabajo,
    )
    from src.team_classification.seleccion_feature import (
        _kappa,
        parejas,
        ventanas_aisladas,
    )

    claves = [k for k in colores if k in etiquetas]
    conjunta = {
        k: np.append(np.asarray(colores[k], float), float(etiquetas[k])) for k in claves
    }
    ids = [
        [
            SimpleNamespace(
                ts=[t for tr in ident for t in tr.ts],
                det_idxs=[tuple(p) for tr in ident for p in tr.det_idxs],
            )
        ]
        for ident in identidades
    ]
    medias, aisladas = ventanas_aisladas(
        ids,
        conjunta,
        cache,
        dentro,
        profundidad_de,
        aislamiento_m=float(cfg.get("aislamiento_m", 2.0)),
        ventana_s=float(cfg.get("ventana_s", 1.5)),
        hueco_max_s=float(cfg.get("hueco_max_s", 0.5)),
    )
    pares = parejas(
        aisladas,
        max_dt_s=float(cfg.get("max_dt_s", 6.0)),
        min_dprof_m=float(cfg.get("min_dprof_m", 6.0)),
    )
    informe = {"parejas": len(pares), "usa_siglip": False}
    if len(pares) < int(cfg.get("min_parejas", 100)) or len(medias) < 10:
        return informe
    params = ParametrosClasificadorColor()
    X = np.array([_feature_trabajo(m[:-1], params) for m in medias])
    km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(X)
    et_hs = km.predict(
        np.array([_feature_trabajo(v[3][:-1], params) for v in aisladas])
    )
    et_sig = np.array([int(v[3][-1] >= 0.5) for v in aisladas])
    i, j = np.array(pares).T
    informe["kappa_hs"] = round(float(_kappa(et_hs[i], et_hs[j])), 3)
    informe["kappa_siglip"] = round(float(_kappa(et_sig[i], et_sig[j])), 3)
    informe["usa_siglip"] = bool(
        informe["kappa_siglip"]
        >= informe["kappa_hs"] + float(cfg.get("margen_kappa", 0.05))
    )
    return informe


def nombrar(etiquetas: dict, colores: dict, clasificador, muestra: int = 5000) -> dict:
    """{clave: 'A'/'B'}: el grupo de SigLIP que más coincide con la A del HS se llama A."""
    claves = [k for k in etiquetas if k in colores]
    if claves:
        rng = np.random.default_rng(0)
        sel = [
            claves[i] for i in rng.choice(len(claves), min(muestra, len(claves)), False)
        ]
        hs = np.array(
            [clasificador.predict_color(colores[k], solo_equipos=True) for k in sel]
        )
        sg = np.array([etiquetas[k] for k in sel])
        acuerdo_0_es_A = float(np.mean((sg == 0) == (hs == "A")))
    else:
        acuerdo_0_es_A = 1.0
    cero = "A" if acuerdo_0_es_A >= 0.5 else "B"
    uno = "B" if cero == "A" else "A"
    return {k: (cero if v == 0 else uno) for k, v in etiquetas.items()}
