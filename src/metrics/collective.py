"""
Cálculo de métricas colectivas a partir de la tabla de posiciones.
No dependen de IDs estables ni de la separación de equipos:
trabajan sobre el conjunto de posiciones detectadas.
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

FIELD_LENGTH = 100.0
FIELD_WIDTH = 64.0


def compute_collective_metrics(
    csv_path: str,
    output_json: str = None,
    field_length: float = FIELD_LENGTH,
    field_width: float = FIELD_WIDTH,
    grid_nx: int = 16,
    grid_ny: int = 10,
):
    """
    Lee el CSV de posiciones y calcula métricas colectivas.

    Returns:
        dict con resumen, centroide, amplitud, profundidad, zonas y heatmap.
    """
    df = pd.read_csv(csv_path)
    if len(df) == 0:
        print("CSV vacío, no hay nada que calcular.")
        return None

    n = len(df)

    # ── Resumen general ──
    resumen = {
        "total_posiciones": int(n),
        "ids_unicos": int(df["id_jugador"].nunique()),
        "frames_con_deteccion": int(df["frame"].nunique()),
    }

    # ── Centroide: posición media de todas las detecciones ──
    centroide = {
        "x_m": round(float(df["x_m"].mean()), 2),
        "y_m": round(float(df["y_m"].mean()), 2),
    }

    # ── Amplitud (dispersión a lo ancho, eje Y) y profundidad (eje X) ──
    # Usamos 2x desviación típica como medida de "cuánto se reparte"
    amplitud = round(float(df["y_m"].std() * 2), 2)
    profundidad = round(float(df["x_m"].std() * 2), 2)

    # ── Presencia por zonas (tercios del eje X) ──
    t1 = field_length / 3
    t2 = 2 * field_length / 3
    zona_izq = int((df["x_m"] < t1).sum())
    zona_cen = int(((df["x_m"] >= t1) & (df["x_m"] < t2)).sum())
    zona_der = int((df["x_m"] >= t2).sum())
    zonas = {
        "izquierda_pct": round(100 * zona_izq / n, 1),
        "centro_pct": round(100 * zona_cen / n, 1),
        "derecha_pct": round(100 * zona_der / n, 1),
    }

    # ── Mapa de calor: rejilla de conteos sobre el campo ──
    heatmap = np.zeros((grid_ny, grid_nx), dtype=int)
    for x, y in zip(df["x_m"], df["y_m"]):
        cx = min(int(x / field_length * grid_nx), grid_nx - 1)
        cy = min(int(y / field_width * grid_ny), grid_ny - 1)
        if cx >= 0 and cy >= 0:
            heatmap[cy, cx] += 1

    metrics = {
        "resumen": resumen,
        "centroide": centroide,
        "amplitud_m": amplitud,
        "profundidad_m": profundidad,
        "zonas": zonas,
        "heatmap": {"nx": grid_nx, "ny": grid_ny, "grid": heatmap.tolist()},
    }

    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"Métricas guardadas en {output_json}")

    return metrics


if __name__ == "__main__":
    m = compute_collective_metrics(
        "data/tracking/posiciones_p1.csv",
        output_json="data/metrics/metricas_p1.json",
    )
    if m:
        print(json.dumps(m, indent=2, ensure_ascii=False))
