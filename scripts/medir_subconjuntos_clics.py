#!/usr/bin/env python
"""¿Qué 4-6 clics bastan para calibrar? Subconjuntos, regla y validadores. SOLO MEDICIÓN.

Plan: docs/plan_calibracion_semiautomatica.md. El CRITERIO se commiteó ANTES de medir.

Uso:
    python scripts/medir_subconjuntos_clics.py
"""

# ══════════════════════════ CRITERIO (fijado ANTES de medir) ══════════════════════════
CRITERIO = {
    "ks": (4, 5, 6),
    "borde_px": 30,  # R1/R2: puntos elegibles a ≥ esto del borde de la imagen
    # 1. R1 (k puntos con máxima envolvente convexa) ≤ base19 en los puntos no usados,
    #    en los DOS campos
    # 2. validador útil: AUC(buenos vs malos) ≥ esto en los DOS campos
    "auc_min": 0.80,
    "malo_factor": 2.0,  # "malo" = error ≥ factor × base19; "bueno" = error ≤ base19
    "tol_linea_px": 4.0,  # V1
    "margen_campo_m": 3.0,  # V2
    "frames_v2": 50,
}
# ═══════════════════════════════════════════════════════════════════════════════════════


def veredicto_regla(r1: dict, base19: dict) -> dict:
    """r1/base19: {campo: {k: error}} y {campo: {k: error}}. Por k: ¿cumple en todos?"""
    salida = {}
    for k in CRITERIO["ks"]:
        salida[k] = all(r1[c][k] <= base19[c][k] for c in r1)
    cumplen = [k for k, ok in salida.items() if ok]
    salida["k_minimo"] = min(cumplen) if cumplen else None
    return salida


def validador_util(aucs: dict) -> bool:
    """aucs: {campo: auc o None}. Útil si llega al mínimo en TODOS los campos."""
    return all(a is not None and a >= CRITERIO["auc_min"] for a in aucs.values())


if __name__ == "__main__":
    raise SystemExit("medición aún no implementada (criterio commiteado antes)")
