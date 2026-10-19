#!/usr/bin/env python
"""Árbitro por observación con TONO y BRILLO sobre el torso — CRITERIO, SIN MEDIR TODAVÍA.

Plan: `docs/plan_arbitro_tono_brillo.md`. Aquí solo hay el criterio fijado y las funciones que
derivan los umbrales y dan el veredicto, con tests. Se mide cuando Alex haya rellenado
`outputs/hoja_equipos/revision.csv` (validación SOLO contra sus marcas de la ventana `azar`).
"""

import numpy as np

# ── Fijado ANTES de medir ─────────────────────────────────────────────────────
CRITERIO = {
    "centro_torso_filas": (0.20, 0.45),
    "centro_torso_columnas": (0.35, 0.65),
    "minutos_excluidos_de_calibracion": [16, 17],  # la ventana `azar` (16:04-17:04)
    "h_banda_percentiles_chaleco": (5, 95),
    "s_min_percentil_chaleco": 5,
    "v_min_percentil_cesped": 99,
    "v_min_percentil_portero_b": 95,
    "frac_percentil_cesped": 99,
    "frac_percentil_portero_b": 99,
    "aviso_si_v_min_supera_percentil_chaleco": 25,
    "margen_area_portero_b_m": 2.0,
    # adopción, contra las marcas de Alex en `azar`
    "max_falsos_positivos": 1,
    "min_recuperacion": 0.80,
    "min_cajas_arbitro_verdad": 20,
    "n_lista": 20,
}


def derivar_umbrales(chaleco, cesped, portero_b, frac_cesped, frac_portero_b) -> dict:
    """Umbrales de PERCENTILES de cada clase.

    chaleco, cesped, portero_b: píxeles HSV (N×3) de la calibración (sin los minutos de `azar`).
    frac_*: fracción «chaleco» por caja en cajas vacías de césped y en cajas del portero de B,
    calculada con los umbrales de píxel ya derivados (segunda pasada).
    """
    c = CRITERIO
    h0, h1 = np.percentile(chaleco[:, 0], c["h_banda_percentiles_chaleco"])
    s_min = float(np.percentile(chaleco[:, 1], c["s_min_percentil_chaleco"]))
    v_min = float(
        max(
            np.percentile(cesped[:, 2], c["v_min_percentil_cesped"]),
            np.percentile(portero_b[:, 2], c["v_min_percentil_portero_b"]),
        )
    )
    perdida_v = float((chaleco[:, 2] < v_min).mean())
    out = {
        "h": (float(h0), float(h1)),
        "s_min": s_min,
        "v_min": v_min,
        "chaleco_bajo_v_min": perdida_v,
        "aviso_v": perdida_v > c["aviso_si_v_min_supera_percentil_chaleco"] / 100,
    }
    if frac_cesped is not None and frac_portero_b is not None:
        out["frac_min"] = float(
            max(
                np.percentile(frac_cesped, c["frac_percentil_cesped"]),
                np.percentile(frac_portero_b, c["frac_percentil_portero_b"]),
            )
        )
    return out


def es_pixel_chaleco(hsv: np.ndarray, u: dict) -> np.ndarray:
    return (
        (hsv[:, 0] >= u["h"][0])
        & (hsv[:, 0] <= u["h"][1])
        & (hsv[:, 1] >= u["s_min"])
        & (hsv[:, 2] >= u["v_min"])
    )


def veredicto(
    n_arbitro_verdad: int, recuperadas: int, falsos_positivos: int, jugador_en_top: bool
):
    c = CRITERIO
    if n_arbitro_verdad < c["min_cajas_arbitro_verdad"]:
        return "NO CONCLUYENTE (pocas cajas de árbitro en la verdad)"
    if jugador_en_top:
        return "NO SE ADOPTA (un jugador real entre las 20 de más fracción, por encima del umbral)"
    if falsos_positivos > c["max_falsos_positivos"]:
        return "NO SE ADOPTA (demasiados jugadores o porteros convertidos en árbitro)"
    if recuperadas / n_arbitro_verdad < c["min_recuperacion"]:
        return "NO SE ADOPTA (recupera menos del 80 % del árbitro)"
    return "PASA EL CRITERIO (no va a producción sin el OK de Alex)"
