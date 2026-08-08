#!/usr/bin/env python
"""Auditoría de escala: ¿son reales las medidas que asumimos del campo?

Idea (validada con el F11 de Villaviciosa, 08-ago-2026): las marcas
INTERIORES del campo —área, penalti, círculo, portería— están fijadas por
el reglamento y no dependen de lo grande que sea el campo. El largo y el
ancho, en cambio, suelen ser una estimación. Proyectando los clics de
calibración con la homografía y midiendo esas marcas se sabe si el
espacio métrico está bien escalado, y en qué eje falla.

Qué reporta:
  1. Cada marca reglamentaria medida vs su valor de reglamento.
  2. El error agregado por EJE (longitudinal vs transversal): un error
     solo en uno de los dos apunta a que la dimensión de ese eje está mal;
     un error que cambia con la posición en la imagen apunta a distorsión
     de lente y NO se arregla cambiando las medidas.
  3. Si el error supera el umbral, un barrido de (largo, ancho) con
     validación cruzada: se ajusta con el marco del campo y se miden las
     marcas, para derivar las medidas reales sin circularidad.
  4. La resolución métrica por profundidad: cuántos metros vale un píxel
     de error a cada distancia (crítico con cámara baja tras portería).

Uso:
    python scripts/auditar_escala.py                          # F11 actual
    python scripts/auditar_escala.py --config configs/campo_benja.yaml
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campo_modelo import cargar_modelo  # noqa: E402

PUNTOS_F11 = "data/calibracion/puntos_marcados.json"


def _dist(d: dict, a: str, b: str) -> float | None:
    """Distancia en metros entre dos puntos medidos (None si falta alguno)."""
    if a not in d or b not in d:
        return None
    return float(np.linalg.norm(d[a] - d[b]))


def marcas_medidas(d: dict, modelo) -> list[tuple[str, float, float, str]]:
    """[(nombre, medido, reglamento, eje)] de las marcas disponibles."""
    m = modelo.marcas
    candidatas = [
        # (nombre, valor medido, valor de reglamento, eje que audita)
        (
            "diámetro círculo (vertical)",
            _dist(d, "circulo_top", "circulo_bottom"),
            2 * m.circulo_radio,
            "transversal",
        ),
        (
            "diámetro círculo (horizontal)",
            _dist(d, "circulo_left", "circulo_right"),
            2 * m.circulo_radio,
            "longitudinal",
        ),
        (
            "ancho área izquierda",
            _dist(d, "box_left_top", "box_left_bottom"),
            m.area_ancho,
            "transversal",
        ),
        (
            "ancho área derecha",
            _dist(d, "box_right_top", "box_right_bottom"),
            m.area_ancho,
            "transversal",
        ),
        (
            "ancho área izq (línea fondo)",
            _dist(d, "box_left_top_line", "box_left_bottom_line"),
            m.area_ancho,
            "transversal",
        ),
        (
            "ancho área der (línea fondo)",
            _dist(d, "box_right_top_line", "box_right_bottom_line"),
            m.area_ancho,
            "transversal",
        ),
        (
            "profundidad área izq",
            _dist(d, "box_left_top", "box_left_top_line"),
            m.area_profundidad,
            "longitudinal",
        ),
        (
            "profundidad área der",
            _dist(d, "box_right_top", "box_right_top_line"),
            m.area_profundidad,
            "longitudinal",
        ),
        (
            "portería izquierda",
            _dist(d, "goal_left_top", "goal_left_bottom"),
            m.porteria_ancho,
            "transversal",
        ),
        (
            "portería derecha",
            _dist(d, "goal_right_top", "goal_right_bottom"),
            m.porteria_ancho,
            "transversal",
        ),
    ]
    # Marcas absolutas respecto al origen (necesitan que el eje esté anclado)
    if "penalty_left" in d:
        candidatas.append(
            (
                "penalti izq → fondo",
                float(d["penalty_left"][0]),
                m.penalti,
                "longitudinal",
            )
        )
    if "box_left_top" in d:
        candidatas.append(
            (
                "área izq → fondo",
                float(d["box_left_top"][0]),
                m.area_profundidad,
                "longitudinal",
            )
        )
    return [(n, v, e, eje) for n, v, e, eje in candidatas if v is not None]


def medir_campo(d: dict, modelo) -> dict:
    """Largo y ancho MEDIDOS con la homografía (los que se asumieron no)."""
    medidas = {}
    ancho = _dist(d, "halfway_top", "halfway_bottom")
    if ancho is not None:
        medidas["ancho (banda a banda)"] = ancho
    for arriba, abajo, etiqueta in (
        ("corner_top_left", "corner_bottom_left", "ancho (línea de fondo izq)"),
        ("corner_top_right", "corner_bottom_right", "ancho (línea de fondo der)"),
    ):
        v = _dist(d, arriba, abajo)
        if v is not None:
            medidas[etiqueta] = v
    for izq, der, etiqueta in (
        ("corner_top_left", "corner_top_right", "largo (banda superior)"),
        ("corner_bottom_left", "corner_bottom_right", "largo (banda inferior)"),
        ("penalty_left", "penalty_right", "largo (penalti a penalti + 2·penalti)"),
    ):
        v = _dist(d, izq, der)
        if v is None:
            continue
        if etiqueta.startswith("largo (penalti"):
            v += 2 * modelo.marcas.penalti
        medidas[etiqueta] = v
    return medidas


def barrido_dimensiones(puntos: list[dict], modelo, marco: list[str]) -> None:
    """Deriva (largo, ancho) por validación cruzada: ajusta con el marco del
    campo y mide las marcas reglamentarias, que NO entran en el ajuste."""
    disponibles = {p["nombre"] for p in puntos}
    marco = [n for n in marco if n in disponibles]
    if len(marco) < 4:
        print("\n(no hay puntos suficientes del marco del campo para el barrido)")
        return
    pix_marco = np.array(
        [p["pixel"] for p in puntos if p["nombre"] in marco], dtype=np.float64
    )
    nombres_marco = [p["nombre"] for p in puntos if p["nombre"] in marco]
    pix_todos = np.array([p["pixel"] for p in puntos], dtype=np.float64)
    nombres_todos = [p["nombre"] for p in puntos]

    print("\n=== 3. BARRIDO DE DIMENSIONES (validación cruzada) ===")
    print(f"  se ajusta con {len(marco)} puntos del marco y se miden las marcas")
    mejor = None
    for largo in np.arange(
        modelo.largo * 0.80, modelo.largo * 1.25, modelo.largo * 0.01
    ):
        for ancho in np.arange(
            modelo.ancho * 0.80, modelo.ancho * 1.25, modelo.ancho * 0.01
        ):
            cand = modelo.con_dimensiones(float(largo), float(ancho))
            objetivo = dict(cand.puntos_clicables())
            met = np.array([objetivo[n] for n in nombres_marco], dtype=np.float64)
            H_m2p, _ = cv2.findHomography(met, pix_marco, method=0)
            if H_m2p is None:
                continue
            H_p2m = np.linalg.inv(H_m2p)
            medidos = cv2.perspectiveTransform(
                pix_todos.reshape(-1, 1, 2), H_p2m
            ).reshape(-1, 2)
            d = dict(zip(nombres_todos, medidos))
            marcas = marcas_medidas(d, cand)
            if not marcas:
                continue
            err = float(np.mean([abs(v - e) / e for _n, v, e, _x in marcas])) * 100
            if mejor is None or err < mejor[0]:
                mejor = (err, float(largo), float(ancho))
    if mejor is None:
        print("  (el barrido no encontró ninguna solución)")
        return
    err, largo, ancho = mejor
    print(
        f"  óptimo: largo {largo:.1f} m, ancho {ancho:.1f} m "
        f"→ error medio de las marcas {err:.1f}%"
    )
    print(
        f"  asumido: largo {modelo.largo:.1f} m, ancho {modelo.ancho:.1f} m "
        f"({100*(largo-modelo.largo)/modelo.largo:+.1f}% / "
        f"{100*(ancho-modelo.ancho)/modelo.ancho:+.1f}%)"
    )
    print("\n  ⚠️ Antes de adoptar estas medidas, comprobar que son físicamente")
    print("  plausibles y que no dejan jugadores fuera del campo: con clics")
    print("  concentrados en una franja de la imagen el ajuste se va lejos")
    print("  (pasó con el F11: derivaba 119 m de largo).")


def resolucion_por_profundidad(H: np.ndarray, modelo, n: int = 6) -> None:
    """Cuántos metros vale 1 píxel de error a cada distancia de la cámara.

    Con cámara baja detrás de portería el eje largo se aleja del objetivo y
    la compresión crece con el cuadrado de la distancia: es física de la
    proyección, no un fallo del sistema.
    """
    print("\n=== 4. RESOLUCIÓN MÉTRICA POR PROFUNDIDAD ===")
    print("  (metros de error por cada píxel de error en la caja)")
    H_inv = np.linalg.inv(H)
    cy = modelo.ancho / 2
    print(f"  {'x (m)':>8} {'m/píxel en x':>14} {'m/píxel en y':>14}")
    for x in np.linspace(modelo.largo * 0.05, modelo.largo * 0.95, n):
        punto = np.array([x, cy, 1.0])
        pix = H_inv @ punto
        pix = pix / pix[2]
        # Derivada numérica: 1 píxel en cada eje → cuántos metros
        deltas = []
        for dpix in ([1.0, 0.0], [0.0, 1.0]):
            p2 = np.array([pix[0] + dpix[0], pix[1] + dpix[1], 1.0])
            m2 = H @ p2
            m2 = m2 / m2[2]
            deltas.append(float(np.linalg.norm(m2[:2] - np.array([x, cy]))))
        print(f"  {x:>8.1f} {deltas[0]:>14.3f} {deltas[1]:>14.3f}")
    print("\n  Un crecimiento fuerte con x es ESPERADO con cámara baja tras")
    print("  portería (el factor va con el cuadrado de la distancia). Sirve")
    print("  para calibrar los umbrales por profundidad de ESTE campo, no")
    print("  para descartar la calibración.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campo", default="f11", help="f11 (defecto) o f7")
    parser.add_argument("--config", default=None, help="YAML del campo y rutas")
    parser.add_argument("--puntos", default=None)
    parser.add_argument(
        "--umbral-pct",
        type=float,
        default=3.0,
        help="Error a partir del cual se lanza el barrido de dimensiones",
    )
    args = parser.parse_args()

    modelo = cargar_modelo(
        nombre=None if args.config else args.campo, config=args.config
    )
    rutas = {}
    if args.config:
        with open(args.config) as f:
            rutas = yaml.safe_load(f).get("rutas", {})
    ruta_puntos = args.puntos or rutas.get("puntos", PUNTOS_F11)

    with open(ruta_puntos) as f:
        puntos = json.load(f)

    src = np.array([p["pixel"] for p in puntos], dtype=np.float32)
    dst = np.array([p["metros"] for p in puntos], dtype=np.float32)
    H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)

    medidos = cv2.perspectiveTransform(
        src.astype(np.float64).reshape(-1, 1, 2), H
    ).reshape(-1, 2)
    d = dict(zip([p["nombre"] for p in puntos], medidos))

    ancho_tabla = 74
    print("=" * ancho_tabla)
    print(
        f"AUDITORÍA DE ESCALA — campo '{modelo.nombre}' "
        f"({modelo.largo:.1f} x {modelo.ancho:.1f} m asumidos)"
    )
    print("=" * ancho_tabla)
    print(f"Puntos de calibración: {len(puntos)} ({ruta_puntos})")

    print("\n=== 1. MARCAS REGLAMENTARIAS MEDIDAS ===")
    marcas = marcas_medidas(d, modelo)
    if not marcas:
        print("  (no hay pares de puntos suficientes; marca más puntos)")
        return
    print(f"  {'marca':<32} {'medido':>8} {'reglam.':>8} {'error':>8}  eje")
    for nombre, medido, esperado, eje in marcas:
        print(
            f"  {nombre:<32} {medido:>8.2f} {esperado:>8.2f} "
            f"{100*(medido-esperado)/esperado:>7.1f}%  {eje}"
        )

    print("\n=== 2. ERROR POR EJE ===")
    peor = 0.0
    for eje in ("longitudinal", "transversal"):
        errs = [abs(v - e) / e * 100 for _n, v, e, x in marcas if x == eje]
        if not errs:
            continue
        peor = max(peor, float(np.mean(errs)))
        print(
            f"  {eje:<14} error medio {np.mean(errs):>5.1f}%  "
            f"(máximo {max(errs):.1f}%, {len(errs)} marcas)"
        )
    print("\n  Lectura: si un eje falla y el otro no, la dimensión de ese eje")
    print("  está mal. Si el error cambia con la posición en la imagen (centro")
    print("  bien, periferia mal), es distorsión de lente y cambiar las")
    print("  medidas del campo NO lo arregla.")

    medidas = medir_campo(d, modelo)
    if medidas:
        print("\n  Dimensiones MEDIDAS con esta homografía:")
        for nombre, valor in medidas.items():
            referencia = modelo.ancho if "ancho" in nombre else modelo.largo
            print(
                f"    {nombre:<38} {valor:>7.1f} m  "
                f"({100*(valor-referencia)/referencia:+.1f}% vs asumido)"
            )

    if peor > args.umbral_pct:
        print(f"\n  ⚠️ El error ({peor:.1f}%) supera el umbral ({args.umbral_pct}%).")
        barrido_dimensiones(
            puntos,
            modelo,
            marco=[
                "halfway_top",
                "halfway_bottom",
                "center",
                "corner_top_left",
                "corner_bottom_left",
                "corner_top_right",
                "corner_bottom_right",
            ],
        )
    else:
        print(
            f"\n  ✓ El error está por debajo del umbral ({args.umbral_pct}%): "
            "las medidas asumidas se sostienen."
        )

    resolucion_por_profundidad(H, modelo)
    print("\n" + "=" * ancho_tabla)


if __name__ == "__main__":
    main()
