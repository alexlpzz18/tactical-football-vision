#!/usr/bin/env python
"""Mide la calibración AUTOMÁTICA del campo contra la manual (benjamín). SOLO MEDICIÓN.

Plan: docs/plan_calibracion_automatica.md. El CRITERIO de abajo se commiteó ANTES de
implementar el método y de ver ningún número.

Uso:
    python scripts/medir_calibracion_automatica.py
"""

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
CRITERIO = {
    # a) 19 clics: mediana px con H auto ≤ factor × mediana px con H manual
    "a_factor_vs_manual": 1.5,
    # b) pies del GT: mediana |auto − manual| en metros
    "b_pies_m_max": 1.0,
    # c) dispersión entre frames (px) ≤ error de (a) con la H auto; y aceptados ≥ esto
    "c_frames": 20,
    "c_aceptados_min": 16,
    # confianza: fracción de puntos visibles del modelo a ≤ tol px de una línea
    "s_tol_px": 4.0,
    "s_min": 0.5,
    # d) controles: 10 máscaras aleatorias + la real volteada, TODOS rechazados (S < s_min)
    "d_aleatorias": 10,
}
# ═══════════════════════════════════════════════════════════════════════════════════════


def veredicto(r: dict, crit: dict = CRITERIO) -> dict:
    """r: {'a_auto_px', 'a_manual_px', 's_frame', 'b_pies_m', 'c_dispersion_px',
    'c_aceptados', 'd_scores': [...]}. Devuelve {punto: bool, 'viable': bool}."""
    v = {
        "a_reproyeccion": r["s_frame"] >= crit["s_min"]
        and r["a_auto_px"] <= crit["a_factor_vs_manual"] * r["a_manual_px"],
        "b_pies": r["b_pies_m"] <= crit["b_pies_m_max"],
        "c_dispersion": r["c_dispersion_px"] <= r["a_auto_px"],
        "c_aceptados": r["c_aceptados"] >= crit["c_aceptados_min"],
        "d_control": bool(r["d_scores"])
        and all(s < crit["s_min"] for s in r["d_scores"]),
    }
    v["viable"] = all(v.values())
    return v


if __name__ == "__main__":
    raise SystemExit("método aún no implementado (criterio commiteado antes)")
