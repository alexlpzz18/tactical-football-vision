#!/usr/bin/env python
"""¿Qué pasa si la resolución local llega DE VERDAD al cosido por pureza? SOLO MEDICIÓN.

Plan y razones: docs/plan_resolucion_en_cosido.md. El CRITERIO de abajo se fijó y se
commiteó ANTES de correr ninguna variante.

El hallazgo (16-oct-2026): `perfiles._perfil_bytetrack` lee `cfg_tracking["_resolucion"]`
y nadie escribe esa clave, así que en producción el cosido corre con `resolucion=None`:
sin los márgenes locales de `cosido_pureza._coste` y sin leer `jitter_px`.

Cada variante corre la cadena de producción COMPLETA (`procesar_desde_cache`). La
resolución se inyecta envolviendo, solo durante la corrida, `perfiles.coser_por_pureza`
(y, en el segundo intento, `cosido_pureza._coste`). **Ningún fichero de producción
cambia.** Guarda: la rama `base` tiene que dar EXACTAMENTE el CSV de una corrida sin
parches, o el script se para.

Los cachés viven en el checkout principal (gitignored). `--datos` es la raíz donde está
`data/`; las rutas `data/...` de los configs se reescriben contra ella.

Uso:
    python scripts/medir_resolucion_en_cosido.py --datos /ruta/al/checkout  # intento 1
    python scripts/medir_resolucion_en_cosido.py --datos ... --intento 2  # si el plan lo pide
"""

import argparse
import json
import logging
import math
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R / "scripts"))
warnings.filterwarnings("ignore")

from comparar_escalas import casar as casar_banco  # noqa: E402
from medir_guarda_caja_fundida import metricas_gt  # noqa: E402
import src.tracking.cosido_pureza as cosido_pureza  # noqa: E402
import src.tracking.perfiles as perfiles  # noqa: E402
from src.evaluation.desglose_error import (  # noqa: E402
    EQUIPOS,
    casar_frame,
    cuenta_de_recuento,
    equipo_de_etiqueta,
)
from src.evaluation.gt_parser import gt_a_por_frame, parsear_cvat  # noqa: E402
from src.evaluation.modelo import Observacion  # noqa: E402
from src.evaluation.trackeval_runner import evaluar_con_trackeval  # noqa: E402
from src.tracking.resolucion import ResolucionCampo, desde_config  # noqa: E402
from src.tracking_data.processor import procesar_desde_cache  # noqa: E402

logger = logging.getLogger("resolucion_en_cosido")

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
# Ramas. La CANDIDATA es la única que se juzga; las demás explican de dónde sale el efecto.
#   base           producción tal cual (el cosido recibe resolucion=None)
#   candidata      intento 1: la resolución que YA construye el processor (desde_config,
#                  mismos argumentos), con el jitter_px del YAML. Es "arreglar el cableado".
#   solo_espacial  ablación: solo el margen de distancia (margen_v = 0)
#   solo_velocidad ablación: solo el margen del veto de velocidad (margen_m = 0)
#   intento2       SOLO si el intento 1 falla y el diagnóstico señala al veto de velocidad:
#                  el margen de velocidad con el ruido de un desplazamiento medido a lo
#                  largo del HUECO (jitter·m/px / hueco), no de un frame (jitter·m/px / dt).
#   villa_forzada  informativa, nunca adoptable: Villaviciosa con escalado FORZADO (su
#                  tracking.yaml no lo pide y su jitter no está medido; se usa el 3,5 px).
RAMAS_INTENTO = {1: ["candidata", "solo_espacial", "solo_velocidad"], 2: ["intento2"]}
CANDIDATA = {1: "candidata", 2: "intento2"}
CRITERIO = {
    # ── NO EMPEORAR, en el benjamín (la pata donde actúa) ──
    "equipo_equivocado_tol_pp": 0.0,  # % equipo equivocado ≤ base
    "quimeras_tol": 0,  # quimeras (def. del banco) ≤ base
    "centroide_tol_m": 0.01,  # ≤ base + 1 cm (resolución de lectura)
    "anchura_tol_m": 0.01,
    "faltan_tol": 0.01,  # por equipo y frame, ≤ base + 0,01
    "sobran_tol": 0.01,
    "trackeval_tol": 0.005,  # DetA, AssA, IDF1 ≥ base − 0,005
    # ¿QUÉ INVENTA? (20 min, sin GT): uniones NUEVAS que cambian de etiqueta a través
    # de la unión. Falla si el límite INFERIOR del IC 95 % (Wilson) de su tasa supera
    # la tasa de las uniones que ya hacía la base.
    "z_wilson": 1.96,
    "ventana_etiqueta_s": 2.0,
    # ── MEJORAR (al menos una), en el benjamín ──
    "mejora_ids_por_persona": 0.05,  # identidades por persona baja ≥ esto
    "mejora_trackeval": 0.005,  # o AssA o IDF1 sube ≥ esto
    # Con menos uniones cambiadas que esto DENTRO de la ventana del GT, la parte
    # "MEJORAR" contra el GT es NO CONCLUYENTE (el GT es el 2,5 % de la parte).
    "min_uniones_cambiadas_ventana": 5,
    # ── Villaviciosa ──
    # Su tracking.yaml no activa escalado_resolucion → desde_config da None → la
    # candidata tiene que dar el CSV IDÉNTICO. Si no, se le aplican los puntos de arriba.
    "villa_identico": True,
    # Lado de la caja para TrackEval y radio del casado: los del banco.
    "lado_caja_trackeval": 2.0,
    "radio_m": 2.0,
}
# ═══════════════════════════════════════════════════════════════════════════════════════

PATAS = {
    "benja": dict(
        config="configs/processor_benja_parte_entera.yaml",
        gt="data/annotations/gt_benja/annotations.xml",
        offset=9750,
    ),
    "villa": dict(
        config="configs/processor.yaml",
        gt="data/annotations/ground_truth_tracking/annotations.xml",
        offset=7500,
    ),
}
PASO_GT = 15


# ───────────────────────────── la resolución que se inyecta ─────────────────────────────
class ResolucionParcial:
    """Envuelve una ResolucionCampo y apaga uno de los dos márgenes del cosido.

    `cosido_pureza._coste` solo llama a `metros_por_pixel` (margen de distancia) y a
    `velocidad_ruido` (margen del veto de velocidad); aquí se puede anular cada uno.
    """

    def __init__(self, res: ResolucionCampo, espacial: bool, velocidad: bool):
        self.res, self.espacial, self.velocidad = res, espacial, velocidad

    def metros_por_pixel(self, pos) -> float:
        return self.res.metros_por_pixel(pos) if self.espacial else 0.0

    def velocidad_ruido(self, pos, jitter_px, dt) -> float:
        return self.res.velocidad_ruido(pos, jitter_px, dt) if self.velocidad else 0.0


def _coste_con_hueco(coste_original):
    """Intento 2: el margen de velocidad con el ruido medido a lo largo del HUECO.

    En `_coste`, `dt` solo se usa en `velocidad_ruido(p, jitter, dt) = jitter·m/px / dt`.
    El ruido de la caja en el salto entre el final de un fragmento y el inicio del otro
    es de un desplazamiento entre DOS cajas separadas `hueco` segundos, así que la
    velocidad aparente que produce es jitter·m/px / hueco. Pasar dt=hueco da justo eso.
    """

    def coste(i, j, extremos, velocidades, frames, firmas, params, res, jitter, dt):
        hueco = extremos[j][0] - extremos[i][1]
        return coste_original(
            i, j, extremos, velocidades, frames, firmas, params, res, jitter,
            max(hueco, dt),
        )  # fmt: skip

    return coste


def resolucion_de(rama: str, cfg: dict, cfg_tracking: dict):
    """La resolución que recibe el cosido en cada rama (None = producción)."""
    if rama == "base":
        return None
    if rama == "villa_forzada":
        return ResolucionCampo(
            np.load(cfg["rutas"]["homografia"]),
            cfg["campo_m"]["largo"],
            cfg["campo_m"]["ancho"],
            cfg_tracking.get("escalado_resolucion", {}).get("paso_rejilla_m", 2.0),
        )
    # Los MISMOS argumentos con los que el processor la construye para postprocesar.
    res = desde_config(
        cfg_tracking,
        cfg["rutas"]["homografia"],
        cfg["campo_m"]["largo"],
        cfg["campo_m"]["ancho"],
    )
    if res is None or rama in ("candidata", "intento2"):
        return res
    return ResolucionParcial(
        res, espacial=(rama == "solo_espacial"), velocidad=(rama == "solo_velocidad")
    )


# ───────────────────────────────── la corrida ─────────────────────────────────
def con_datos(cfg: dict, datos: Path) -> dict:
    """Copia del config con las rutas `data/...` apuntando a `datos/data/...`."""
    cfg = yaml.safe_load(yaml.safe_dump(cfg))
    for k, v in cfg["rutas"].items():
        if isinstance(v, str) and v.startswith("data/"):
            cfg["rutas"][k] = str(datos / v)
    return cfg


def correr(cfg: dict, salida_csv: Path, rama: str) -> dict:
    """Producción completa con la resolución de `rama` inyectada en el cosido.

    Devuelve el CSV, los fragmentos que ENTRAN al cosido y las identidades que SALEN
    (cuyo orden es el `id_jugador` del CSV, empezando en 1).
    """
    cfg = yaml.safe_load(yaml.safe_dump(cfg))
    cfg["modo"] = "desde_cache"
    cfg["rutas"]["salida_csv"] = str(salida_csv)
    cfg["rutas"]["salida_meta"] = str(salida_csv.with_suffix(".json"))
    cfg_tracking = yaml.safe_load(open(cfg["config_tracking"]))
    res = resolucion_de(rama, cfg, cfg_tracking)
    capt = {}
    coser0, coste0 = perfiles.coser_por_pureza, cosido_pureza._coste

    def coser(identidades, colores=None, params=None, **k):
        capt["fragmentos"] = [list(i) for i in identidades]
        capt["jitter_px"], capt["dt"] = k.get("jitter_px"), k.get("dt")
        if rama != "base":
            k["resolucion"] = res
            if rama == "villa_forzada":
                k["jitter_px"] = 3.5
        capt["finales"] = coser0(identidades, colores, params, **k)
        capt["params"] = params
        return capt["finales"]

    perfiles.coser_por_pureza = coser
    if rama == "intento2":
        cosido_pureza._coste = _coste_con_hueco(coste0)
    try:
        procesar_desde_cache(cfg)
    finally:
        perfiles.coser_por_pureza, cosido_pureza._coste = coser0, coste0
    return {"df": pd.read_csv(salida_csv), **capt}


# ─────────────────────────────── las métricas ───────────────────────────────
def metricas_banco(df: pd.DataFrame, gt_m: dict) -> dict:
    """Las del banco de la guarda (equipo, quimeras, frag., centroide, anchura) +
    faltan/sobran del desglose + DetA/AssA/IDF1 de TrackEval, todo sobre la ventana."""
    m = metricas_gt(df, gt_m)
    m.pop("_casado", None)
    por_frame = {f: g for f, g in df.groupby("frame")}
    pred, faltan, sobran, n = {}, 0, 0, 0
    for f in sorted(gt_m):
        g = por_frame.get(f, df.iloc[0:0])
        pred[f] = [
            Observacion(int(r.id_jugador), np.array([r.x_m, r.y_m]), str(r.etiqueta))
            for r in g.itertuples()
        ]
        reales = g[g.es_real == 1]
        personas = [(equipo_de_etiqueta(o.team), o.pos[0], o.pos[1]) for o in gt_m[f]]
        fc = casar_frame(
            f,
            personas,
            reales.x_m.to_numpy(),
            reales.y_m.to_numpy(),
            reales.etiqueta.to_numpy(),
            CRITERIO["radio_m"],
        )
        for eq in EQUIPOS:
            c = cuenta_de_recuento(fc, eq)
            faltan, sobran, n = faltan + c["faltan"], sobran + c["sobran"], n + 1
    with tempfile.TemporaryDirectory(prefix="trackeval_") as tmp:
        te = evaluar_con_trackeval(
            gt_m, pred, sorted(gt_m), tmp, CRITERIO["lado_caja_trackeval"]
        )
    m.update(
        faltan=faltan / n,
        sobran=sobran / n,
        DetA=float(te["DetA"]),
        AssA=float(te["AssA"]),
        IDF1=float(te["IDF1"]),
        identidades=int(df.id_jugador.nunique()),
    )
    return m


def _clave(fragmento) -> tuple:
    """Identificador estable de un fragmento: su primera observación (frame, det)."""
    primero = min(fragmento, key=lambda tr: tr.ts[0])
    return tuple(primero.det_idxs[0])


def uniones(corrida: dict, res_diag: ResolucionCampo | None) -> pd.DataFrame:
    """Una fila por UNIÓN del cosido: dos fragmentos consecutivos de una identidad final.

    Los fragmentos que entran al cosido son los mismos en todas las ramas (lo de antes
    es determinista), así que una unión se identifica por el par de claves.
    """
    df, fragmentos, finales = corrida["df"], corrida["fragmentos"], corrida["finales"]
    final_de = {}
    for n, ident in enumerate(finales, start=1):
        for tr in ident:
            final_de[tuple(tr.det_idxs[0])] = n
    reales = df[df.es_real == 1]
    por_id = {k: g for k, g in reales.groupby("id_jugador")}
    params, jitter = corrida["params"], corrida["jitter_px"] or 0.0
    w = CRITERIO["ventana_etiqueta_s"]
    grupos: dict[int, list] = {}
    for frag in fragmentos:
        primero = min(frag, key=lambda tr: tr.ts[0])
        n = final_de.get(tuple(primero.det_idxs[0]))
        grupos.setdefault(n, []).append(frag)

    def mayoritaria(idj, ini, fin):
        g = por_id.get(idj)
        if g is None:
            return None
        s = g[(g.tiempo_s >= ini) & (g.tiempo_s <= fin)].etiqueta
        return s.value_counts().index[0] if len(s) else None

    filas = []
    for n, frags in grupos.items():
        frags = sorted(frags, key=lambda fr: cosido_pureza._extremos(fr)[0])
        for a, b in zip(frags, frags[1:]):
            _ti, t_fin, _pi, p_fin = cosido_pureza._extremos(a)
            t_ini, _tf, p_ini, _pf = cosido_pureza._extremos(b)
            hueco = float(t_ini - t_fin)
            dist = float(np.linalg.norm(np.asarray(p_ini) - np.asarray(p_fin)))
            mpp = res_diag.metros_por_pixel(p_fin) if res_diag is not None else 0.0
            v = dist / hueco if hueco > 0 else float("inf")
            ultimo_a = max(a, key=lambda tr: tr.ts[-1])
            primero_b = min(b, key=lambda tr: tr.ts[0])
            filas.append(
                {
                    "clave_a": _clave(a),
                    "clave_b": _clave(b),
                    "id_final": n,
                    "frame_fin_a": int(ultimo_a.det_idxs[-1][0]),
                    "frame_ini_b": int(primero_b.det_idxs[0][0]),
                    "t": float(t_fin),
                    "x": float(p_fin[0]),
                    "y": float(p_fin[1]),
                    "m_por_px": mpp,
                    "hueco_s": hueco,
                    "dist_m": dist,
                    "v_salto": v,
                    # ¿imposible AUN contando bien el ruido? (ruido de un desplazamiento
                    # entre dos cajas separadas `hueco` s: jitter·m/px / hueco)
                    "imposible": bool(
                        params is not None
                        and v > params.v_max_salto + jitter * mpp / max(hueco, 1e-9)
                    ),
                    "etiqueta_antes": mayoritaria(n, t_fin - w, t_fin),
                    "etiqueta_despues": mayoritaria(n, t_ini, t_ini + w),
                }
            )
    t = pd.DataFrame(filas)
    if not t.empty:
        t["cambia_etiqueta"] = t.etiqueta_antes.notna() & (
            t.etiqueta_antes != t.etiqueta_despues
        )
        t["con_etiqueta"] = t.etiqueta_antes.notna() & t.etiqueta_despues.notna()
    return t


def wilson(k: int, n: int, z: float = CRITERIO["z_wilson"]) -> tuple[float, float]:
    """IC del 95 % de una proporción k/n (Wilson). (0, 1) si n = 0."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centro - medio, centro + medio


def comparar_uniones(u_base: pd.DataFrame, u_rama: pd.DataFrame, ventana) -> dict:
    """Uniones nuevas / perdidas respecto a la base, y su tasa de cambio de etiqueta."""
    par = lambda t: set(zip(t.clave_a, t.clave_b)) if len(t) else set()  # noqa: E731
    pb, pr = par(u_base), par(u_rama)
    nuevas = (
        u_rama[[p in pr - pb for p in zip(u_rama.clave_a, u_rama.clave_b)]]
        if len(u_rama)
        else u_rama
    )
    perdidas = pb - pr

    def tasa(t):
        c = t[t.con_etiqueta] if len(t) else t
        return int(c.cambia_etiqueta.sum()) if len(c) else 0, len(c)

    k_b, n_b = tasa(u_base)
    k_n, n_n = tasa(nuevas)
    en_ventana = (
        int(
            (
                nuevas.frame_fin_a.between(*ventana)
                | nuevas.frame_ini_b.between(*ventana)
            ).sum()
        )
        if len(nuevas)
        else 0
    )
    perd_vent = sum(
        1
        for _, f in u_base.iterrows()
        if (f.clave_a, f.clave_b) in perdidas
        and (ventana[0] <= f.frame_fin_a <= ventana[1]
             or ventana[0] <= f.frame_ini_b <= ventana[1])
    )  # fmt: skip
    return {
        "uniones_base": len(u_base),
        "uniones_rama": len(u_rama),
        "nuevas": len(nuevas),
        "perdidas": len(perdidas),
        "cambiadas_en_ventana": en_ventana + perd_vent,
        "tasa_etiqueta_base": k_b / n_b if n_b else None,
        "n_etiqueta_base": n_b,
        "tasa_etiqueta_nuevas": k_n / n_n if n_n else None,
        "n_etiqueta_nuevas": n_n,
        "ic_nuevas": wilson(k_n, n_n),
        "nuevas_imposibles": int(nuevas.imposible.sum()) if len(nuevas) else 0,
        "nuevas_por_zona": (
            nuevas.groupby(pd.cut(nuevas.x, [0, 15, 30, 45, 70]), observed=True)
            .size()
            .to_dict()
            if len(nuevas)
            else {}
        ),
        "v_salto_nuevas_p50_p90": (
            [float(nuevas.v_salto.median()), float(nuevas.v_salto.quantile(0.9))]
            if len(nuevas)
            else None
        ),
        "_nuevas": nuevas,
    }


# ───────────────────────────── el veredicto (puro) ─────────────────────────────
def no_empeora(b: dict, v: dict, crit: dict = CRITERIO) -> dict:
    return {
        "equipo_equivocado": v["equipo_mal_pct"]
        <= b["equipo_mal_pct"] + crit["equipo_equivocado_tol_pp"],
        "quimeras": v["quimeras"] <= b["quimeras"] + crit["quimeras_tol"],
        "centroide": v["centroide_m"] <= b["centroide_m"] + crit["centroide_tol_m"],
        "anchura": v["anchura_m"] <= b["anchura_m"] + crit["anchura_tol_m"],
        "faltan": v["faltan"] <= b["faltan"] + crit["faltan_tol"],
        "sobran": v["sobran"] <= b["sobran"] + crit["sobran_tol"],
        "DetA": v["DetA"] >= b["DetA"] - crit["trackeval_tol"],
        "AssA": v["AssA"] >= b["AssA"] - crit["trackeval_tol"],
        "IDF1": v["IDF1"] >= b["IDF1"] - crit["trackeval_tol"],
    }


def veredicto(
    benja_base: dict,
    benja_rama: dict,
    uniones_cmp: dict,
    villa_identico: bool,
    villa_base: dict | None = None,
    villa_rama: dict | None = None,
    crit: dict = CRITERIO,
) -> dict:
    """Aplica el criterio. `pasa`: True / False / None (no concluyente)."""
    puntos = {f"benja_{k}": ok for k, ok in no_empeora(benja_base, benja_rama).items()}
    tasa_b = uniones_cmp["tasa_etiqueta_base"]
    puntos["benja_no_inventa"] = (
        uniones_cmp["n_etiqueta_nuevas"] == 0
        or tasa_b is None
        or uniones_cmp["ic_nuevas"][0] <= tasa_b
    )
    mejora = (
        benja_base["fragmentacion"] - benja_rama["fragmentacion"]
        >= crit["mejora_ids_por_persona"]
        or benja_rama["AssA"] - benja_base["AssA"] >= crit["mejora_trackeval"]
        or benja_rama["IDF1"] - benja_base["IDF1"] >= crit["mejora_trackeval"]
    )
    concluyente = (
        uniones_cmp["cambiadas_en_ventana"] >= crit["min_uniones_cambiadas_ventana"]
    )
    puntos["benja_mejora"] = mejora if concluyente else None
    if villa_identico:
        puntos["villa_identico"] = True
    else:
        puntos["villa_identico"] = False
        for k, ok in no_empeora(villa_base, villa_rama).items():
            puntos[f"villa_{k}"] = ok
    if any(ok is False for ok in puntos.values()):
        pasa = False
    elif any(ok is None for ok in puntos.values()):
        pasa = None
    else:
        pasa = True
    return {"puntos": puntos, "concluyente": concluyente, "pasa": pasa}


# ──────────────────────────────────── main ────────────────────────────────────
def _fmt(m: dict) -> str:
    return (
        f"equipo_mal {m['equipo_mal_pct']:.2f}% ({m['equipo_mal']}) · quim "
        f"{m['quimeras']}/{m['con10']} · ids/persona {m['fragmentacion']:.3f} · "
        f"centroide {m['centroide_m']:.3f} · anchura {m['anchura_m']:.3f} · faltan "
        f"{m['faltan']:.3f} · sobran {m['sobran']:.3f} · DetA {m['DetA']:.3f} · AssA "
        f"{m['AssA']:.3f} · IDF1 {m['IDF1']:.3f} · identidades {m['identidades']}"
    )


def _sin_privados(d):
    if isinstance(d, dict):
        return {
            str(k): _sin_privados(v) for k, v in d.items() if not str(k).startswith("_")
        }
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--datos", type=Path, default=R, help="raíz donde está data/")
    ap.add_argument("--intento", type=int, default=1, choices=(1, 2))
    ap.add_argument("--salida", default="outputs/resolucion_en_cosido")
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    sal = R / args.salida
    sal.mkdir(parents=True, exist_ok=True)
    ramas = RAMAS_INTENTO[args.intento]
    res = {}
    for pata, d in PATAS.items():
        cfg = con_datos(yaml.safe_load(open(R / d["config"])), args.datos)
        H = np.load(cfg["rutas"]["homografia"])
        gt_m = gt_a_por_frame(
            parsear_cvat(str(args.datos / d["gt"])), H, d["offset"], PASO_GT
        )
        ventana = (min(gt_m), max(gt_m))
        print(
            f"\n════ {pata}: GT frames {ventana}, {len(gt_m)} frames ════", flush=True
        )

        # guarda: base con el parche = producción sin parche, byte a byte
        limpio = sal / f"{pata}_sin_parche.csv"
        c2 = yaml.safe_load(yaml.safe_dump(cfg))
        c2["modo"] = "desde_cache"
        c2["rutas"]["salida_csv"] = str(limpio)
        c2["rutas"]["salida_meta"] = str(limpio.with_suffix(".json"))
        procesar_desde_cache(c2)
        base = correr(cfg, sal / f"{pata}_base.csv", "base")
        if not pd.read_csv(limpio).equals(base["df"]):
            sys.exit(
                "✗ la rama base NO reproduce producción: el arnés cambia algo. PARA."
            )
        # control del casado: el equipo equivocado de aquí = el de comparar_escalas
        mb = metricas_banco(base["df"], gt_m)
        pares = casar_banco(
            base["df"][base["df"].es_real == 1], gt_m, CRITERIO["radio_m"]
        )
        mal = sum(1 for g, s in pares if s in EQUIPOS and s != g)
        mal = min(mal, sum(1 for g, s in pares if s in EQUIPOS and s == g))
        assert mal == mb["equipo_mal"], (mal, mb["equipo_mal"])
        print(
            f"✓ base = producción; casado = el del banco\n  base           {_fmt(mb)}"
        )
        print(
            f"  (el cosido recibió jitter_px={base['jitter_px']} dt={base['dt']:.4f})"
        )
        cfg_tr = yaml.safe_load(open(cfg["config_tracking"]))
        res_diag = desde_config(
            cfg_tr, cfg["rutas"]["homografia"], cfg["campo_m"]["largo"],
            cfg["campo_m"]["ancho"],
        ) or ResolucionCampo(H, cfg["campo_m"]["largo"], cfg["campo_m"]["ancho"], 2.0)  # fmt: skip
        u_base = uniones(base, res_diag)
        res[pata] = {"base": mb, "ramas": {}}
        ramas_pata = ramas + (
            ["villa_forzada"] if pata == "villa" and args.intento == 1 else []
        )
        for rama in ramas_pata:
            cr = correr(cfg, sal / f"{pata}_{rama}.csv", rama)
            m = metricas_banco(cr["df"], gt_m)
            identico = cr["df"].equals(base["df"])
            u = uniones(cr, res_diag)
            cmp = comparar_uniones(u_base, u, ventana)
            cmp.pop("_nuevas").to_csv(
                sal / f"{pata}_{rama}_uniones_nuevas.csv", index=False
            )
            m.update(csv_identico_a_base=identico, uniones=cmp)
            res[pata]["ramas"][rama] = m
            print(f"  {rama:<14} {_fmt(m)} · CSV idéntico a base: {identico}")
            print(
                f"  {'':<14} uniones {cmp['uniones_base']} → {cmp['uniones_rama']} (nuevas "
                f"{cmp['nuevas']}, perdidas {cmp['perdidas']}, cambiadas en ventana "
                f"{cmp['cambiadas_en_ventana']}) · cambio de etiqueta: base "
                f"{cmp['tasa_etiqueta_base']} (n={cmp['n_etiqueta_base']}), nuevas "
                f"{cmp['tasa_etiqueta_nuevas']} (n={cmp['n_etiqueta_nuevas']}, IC "
                f"{cmp['ic_nuevas'][0]:.3f}-{cmp['ic_nuevas'][1]:.3f}) · imposibles "
                f"{cmp['nuevas_imposibles']} · por zona x {cmp['nuevas_por_zona']} · "
                f"v_salto p50/p90 {cmp['v_salto_nuevas_p50_p90']}",
                flush=True,
            )

    cand = CANDIDATA[args.intento]
    vb, vr = res["villa"]["base"], res["villa"]["ramas"][cand]
    v = veredicto(
        res["benja"]["base"],
        res["benja"]["ramas"][cand],
        res["benja"]["ramas"][cand]["uniones"],
        vr["csv_identico_a_base"],
        vb,
        vr,
    )
    print(f"\nVEREDICTO {cand}: {v}")
    json.dump(
        _sin_privados({"criterio": CRITERIO, "intento": args.intento,
                       "resultados": res, "veredicto": v}),
        open(sal / f"resultados_intento{args.intento}.json", "w"),
        indent=1,
        default=str,
    )  # fmt: skip
    print(f"(todo en {sal}/resultados_intento{args.intento}.json)")


if __name__ == "__main__":
    main()
