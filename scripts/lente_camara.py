#!/usr/bin/env python
"""Lente y pose de la cámara F11 con el campo como patrón plano. Criterios en `docs/lente_f11.md`.

NO es producción: nada del pipeline lo importa. La idea: el campo es un patrón plano de medidas
conocidas, así que con clics sobre el fotograma ORIGINAL (sin corregir) se ajustan a la vez la lente
y la posición de la cámara. Después no se corrige la imagen: solo se convierte cada PIE a metros.

Dos tipos de clic:
- **cruce**: una marca de metros conocidos (dos ecuaciones);
- **punto de línea**: está sobre una línea recta conocida pero no se sabe a qué metro (dos
  ecuaciones y una incógnita más: su posición a lo largo de la línea). Las líneas miden la lente:
  en el original se ven curvas y en el campo son rectas.

Uso:
    python scripts/lente_camara.py ajustar --clics clics.json --salida outputs/lente_f11
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
ANCHO_IMG, ALTO_IMG = 2560, 1064
LARGO, ANCHO = 100.0, 64.0
# corrección ACTUAL de producción (configs/processor.yaml, processor._build_camera_matrix)
K1_ACTUAL, K2_ACTUAL = -1.5, 0.5
H_ACTUAL = R / "data/calibracion/homografia.npy"
FRAME_ALEVIN = R / "data/calibracion_villa_cadete/frame_alevin_crudo.png"
# hasta dónde se mira la función radial: 85° desde el eje óptico
THETA_MAX = np.radians(85.0)
FOCALES_INICIALES = (600.0, 800.0, 1000.0, 1300.0, 1700.0)
ESCALA_PERDIDA_PX = (
    5.0  # a partir de aquí un residuo pesa menos (soft_l1): un clic malo no manda
)
CENTRO_MAX_PX = 150.0


def n_coefs(tipo: str) -> int:
    return {"ojo_pez": 4, "racional": 6}[tipo]


def radial(tipo: str, coefs: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Radio en la imagen (normalizado por la focal) del rayo a `theta` del eje óptico.

    - `ojo_pez` (cv2.fisheye): θ·(1 + k1θ² + k2θ⁴ + k3θ⁶ + k4θ⁸).
    - `racional` (cv2.projectPoints, sin tangencial), con r = tan θ:
      r·(1 + k1r² + k2r⁴ + k3r⁶) / (1 + k4r² + k5r⁴ + k6r⁶).
    """
    if tipo == "ojo_pez":
        t2 = theta * theta
        k1, k2, k3, k4 = coefs
        return theta * (1 + t2 * (k1 + t2 * (k2 + t2 * (k3 + t2 * k4))))
    r = np.tan(theta)
    r2 = r * r
    k1, k2, k3, k4, k5, k6 = coefs
    arriba = 1 + r2 * (k1 + r2 * (k2 + r2 * k3))
    abajo = 1 + r2 * (k4 + r2 * (k5 + r2 * k6))
    return r * arriba / abajo


@dataclass
class Camara:
    """Cámara con lente radial sobre el plano del campo (Z = 0)."""

    tipo: str
    f: float
    cx: float
    cy: float
    coefs: np.ndarray
    rvec: np.ndarray
    tvec: np.ndarray

    def _R(self) -> np.ndarray:
        return cv2.Rodrigues(np.asarray(self.rvec, float))[0]

    def proyectar(self, xy: np.ndarray) -> np.ndarray:
        """Metros del campo → píxel del fotograma ORIGINAL. NaN si queda detrás de la cámara."""
        xy = np.atleast_2d(np.asarray(xy, float))
        P = np.column_stack([xy, np.zeros(len(xy))])
        C = P @ self._R().T + np.asarray(self.tvec, float)
        h = np.hypot(C[:, 0], C[:, 1])
        theta = np.arctan2(h, C[:, 2])
        rd = radial(self.tipo, self.coefs, np.clip(theta, 0, THETA_MAX))
        with np.errstate(invalid="ignore", divide="ignore"):
            esc = np.where(h > 1e-12, rd / h, 1.0)
        px = np.column_stack(
            [self.cx + self.f * C[:, 0] * esc, self.cy + self.f * C[:, 1] * esc]
        )
        px[theta >= THETA_MAX] = np.nan
        return px

    def tabla_inversa(self) -> tuple[np.ndarray, np.ndarray]:
        """(radio en imagen, θ) hasta el primer pliegue de la función radial."""
        th = np.linspace(0.0, THETA_MAX, 4000)
        rd = radial(self.tipo, self.coefs, th)
        d = np.diff(rd)
        fin = int(np.argmax(d <= 0)) if (d <= 0).any() else len(d)
        return rd[: fin + 1], th[: fin + 1]

    def radio_alcanzable_px(self) -> float:
        return float(self.tabla_inversa()[0][-1] * self.f)

    def es_monotona(self, ancho=ANCHO_IMG, alto=ALTO_IMG) -> bool:
        """¿Llega sin doblarse a la esquina más lejana del fotograma? (el fallo de la actual)"""
        esquinas = np.array([[0, 0], [ancho, 0], [0, alto], [ancho, alto]], float)
        r = np.hypot(esquinas[:, 0] - self.cx, esquinas[:, 1] - self.cy).max()
        return self.radio_alcanzable_px() >= r

    def pixel_a_metros(self, px: np.ndarray) -> np.ndarray:
        """Píxel del original → metros, cortando el rayo con el plano. NaN si no corta o dobla."""
        px = np.atleast_2d(np.asarray(px, float))
        rd_tab, th_tab = self.tabla_inversa()
        dx, dy = (px[:, 0] - self.cx) / self.f, (px[:, 1] - self.cy) / self.f
        rd = np.hypot(dx, dy)
        theta = np.interp(rd, rd_tab, th_tab, right=np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            esc = np.where(rd > 1e-12, np.sin(theta) / rd, 1.0)
        rayo = np.column_stack([dx * esc, dy * esc, np.cos(theta)])
        Rm = self._R()
        d = rayo @ Rm  # = Rm.T @ rayo por filas
        origen = -Rm.T @ np.asarray(self.tvec, float)
        with np.errstate(invalid="ignore", divide="ignore"):
            s = -origen[2] / d[:, 2]
        out = origen[:2] + s[:, None] * d[:, :2]
        out[~(s > 0)] = np.nan
        return out


# ── el campo con largo y ancho posiblemente distintos de 100 × 64 ────────────────────────────────


def ajustar_medidas(xy: np.ndarray, largo: float, ancho: float) -> np.ndarray:
    """Las marcas a sus metros si el campo mide largo × ancho (áreas y círculo, a reglamento)."""
    xy = np.array(xy, float, ndmin=2)
    x, y = xy[:, 0].copy(), xy[:, 1].copy()
    x = np.where(x > LARGO * 0.75, x + (largo - LARGO), x)
    x = np.where((x > LARGO * 0.25) & (x <= LARGO * 0.75), x + (largo - LARGO) / 2, x)
    y = np.where(
        y >= ANCHO - 1e-9, ancho, np.where(y <= 1e-9, 0.0, y + (ancho - ANCHO) / 2)
    )
    return np.column_stack([x, y])


# ── datos de los clics ───────────────────────────────────────────────────────────────────────────


@dataclass
class Clics:
    cruces_px: np.ndarray  # (N, 2)
    cruces_m: np.ndarray  # (N, 2)
    nombres: list
    lineas_px: np.ndarray  # (M, 2)
    lineas_a: np.ndarray  # (M, 2): extremo a de la línea de cada punto, en metros
    lineas_b: np.ndarray  # (M, 2)
    lineas_nombre: list

    @classmethod
    def desde_json(cls, ruta) -> "Clics":
        d = json.load(open(ruta))
        c = d["cruces"]
        px, a, b, nom = [], [], [], []
        for ln in d.get("lineas", []):
            for p in ln["puntos"]:
                px.append(p)
                a.append(ln["a"])
                b.append(ln["b"])
                nom.append(ln["nombre"])
        return cls(
            np.array([x["pixel"] for x in c], float).reshape(-1, 2),
            np.array([x["metros"] for x in c], float).reshape(-1, 2),
            [x["nombre"] for x in c],
            np.array(px, float).reshape(-1, 2),
            np.array(a, float).reshape(-1, 2),
            np.array(b, float).reshape(-1, 2),
            nom,
        )

    def sin_cruce(self, i: int) -> "Clics":
        q = np.arange(len(self.nombres)) != i
        return Clics(
            self.cruces_px[q],
            self.cruces_m[q],
            [n for n, k in zip(self.nombres, q) if k],
            self.lineas_px,
            self.lineas_a,
            self.lineas_b,
            self.lineas_nombre,
        )


# ── ajuste ───────────────────────────────────────────────────────────────────────────────────────


def _inicial(tipo: str, clics: Clics, f0: float) -> Camara:
    """Pose inicial: se quita una lente equidistante de los clics y se resuelve PnP."""
    c0 = np.array([ANCHO_IMG / 2, ALTO_IMG / 2])
    d = (clics.cruces_px - c0) / f0
    rd = np.hypot(d[:, 0], d[:, 1])
    th = np.clip(rd, 0, 1.45)
    esc = np.where(rd > 1e-9, np.tan(th) / np.maximum(rd, 1e-9), 1.0)
    und = d * esc[:, None]
    P = np.column_stack([clics.cruces_m, np.zeros(len(und))])
    ok, rvec, tvec = cv2.solvePnP(
        P.astype(np.float64),
        und.astype(np.float64),
        np.eye(3),
        None,
        flags=cv2.SOLVEPNP_SQPNP if len(und) >= 4 else cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        raise RuntimeError("solvePnP no converge con estos clics")
    coefs = np.zeros(n_coefs(tipo))
    return Camara(tipo, f0, c0[0], c0[1], coefs, rvec.ravel(), tvec.ravel())


def _a_vector(cam: Camara, s: np.ndarray, medidas) -> np.ndarray:
    base = [cam.rvec, cam.tvec, [cam.f, cam.cx, cam.cy], cam.coefs, s]
    if medidas is not None:
        base.append(medidas)
    return np.concatenate(base)


def _de_vector(v: np.ndarray, tipo: str, n_s: int, libres: bool):
    fin_coefs = 9 + n_coefs(tipo)
    fin_s = fin_coefs + n_s
    cam = Camara(tipo, v[6], v[7], v[8], v[9:fin_coefs], v[:3], v[3:6])
    s = v[fin_coefs:fin_s]
    medidas = v[fin_s:] if libres else None
    return cam, s, medidas


def _residuos(v, tipo, clics: Clics, libres: bool) -> np.ndarray:
    n_s = len(clics.lineas_px)
    cam, s, med = _de_vector(v, tipo, n_s, libres)
    m = clics.cruces_m
    a, b = clics.lineas_a, clics.lineas_b
    if libres:
        m = ajustar_medidas(m, med[0], med[1])
        if n_s:
            a, b = ajustar_medidas(a, med[0], med[1]), ajustar_medidas(
                b, med[0], med[1]
            )
    partes = [(cam.proyectar(m) - clics.cruces_px).ravel()]
    if n_s:
        partes.append(
            (cam.proyectar(a + s[:, None] * (b - a)) - clics.lineas_px).ravel()
        )
    r = np.concatenate(partes)
    return np.where(np.isfinite(r), r, 1e4)


def _s_iniciales(cam: Camara, clics: Clics) -> np.ndarray:
    """Posición de cada punto de línea a lo largo de su línea, según la cámara inicial."""
    if not len(clics.lineas_px):
        return np.zeros(0)
    xy = cam.pixel_a_metros(clics.lineas_px)
    a, b = clics.lineas_a, clics.lineas_b
    ab = b - a
    s = ((xy - a) * ab).sum(1) / (ab * ab).sum(1)
    return np.clip(np.nan_to_num(s, nan=0.5), -0.2, 1.2)


def ajustar(
    tipo: str,
    clics: Clics,
    medidas_libres: bool = False,
    inicial: Camara | None = None,
    s0=None,
) -> tuple[Camara, dict]:
    """Ajuste por mínimos cuadrados robustos. Con `inicial`, una sola arrancada desde ahí."""
    n_s = len(clics.lineas_px)
    arranques = (
        [inicial]
        if inicial is not None
        else [_inicial(tipo, clics, f) for f in FOCALES_INICIALES]
    )
    mejor = None
    for cam0 in arranques:
        s = s0 if s0 is not None else _s_iniciales(cam0, clics)
        medidas = np.array([LARGO, ANCHO]) if medidas_libres else None
        v0 = _a_vector(cam0, s, medidas)
        lo, hi = np.full(len(v0), -np.inf), np.full(len(v0), np.inf)
        lo[6], hi[6] = 200.0, 4000.0
        lo[7], hi[7] = ANCHO_IMG / 2 - CENTRO_MAX_PX, ANCHO_IMG / 2 + CENTRO_MAX_PX
        lo[8], hi[8] = ALTO_IMG / 2 - CENTRO_MAX_PX, ALTO_IMG / 2 + CENTRO_MAX_PX
        v0 = np.clip(v0, lo + 1e-6, hi - 1e-6)
        sol = least_squares(
            _residuos,
            v0,
            bounds=(lo, hi),
            args=(tipo, clics, medidas_libres),
            loss="soft_l1",
            f_scale=ESCALA_PERDIDA_PX,
            x_scale="jac",
            max_nfev=400,
        )
        if mejor is None or sol.cost < mejor.cost:
            mejor = sol
    cam, s, med = _de_vector(mejor.x, tipo, n_s, medidas_libres)
    r = _residuos(mejor.x, tipo, clics, medidas_libres).reshape(-1, 2)
    e = np.hypot(r[:, 0], r[:, 1])
    info = {
        "residuo_px_mediana": round(float(np.median(e)), 2),
        "residuo_px_p90": round(float(np.percentile(e, 90)), 2),
        "residuo_px_max": round(float(e.max()), 2),
        "focal_px": round(float(cam.f), 1),
        "centro_px": [round(float(cam.cx), 1), round(float(cam.cy), 1)],
        "coefs": [round(float(c), 5) for c in cam.coefs],
        "monotona": bool(cam.es_monotona()),
        "radio_alcanzable_px": round(cam.radio_alcanzable_px(), 1),
        "_s": s,
    }
    if med is not None:
        info["medidas_estimadas_m"] = [round(float(med[0]), 2), round(float(med[1]), 2)]
    return cam, info


def validacion_cruzada(tipo: str, clics: Clics, cam: Camara, s0: np.ndarray) -> dict:
    """Deja fuera cada cruce, ajusta con el resto (líneas dentro) y lo predice EN METROS."""
    filas = []
    for i, nombre in enumerate(clics.nombres):
        c_i, _ = ajustar(tipo, clics.sin_cruce(i), inicial=cam, s0=s0)
        pred = c_i.pixel_a_metros(clics.cruces_px[[i]])[0]
        e_m = float(np.hypot(*(pred - clics.cruces_m[i])))
        e_px = float(
            np.hypot(*(c_i.proyectar(clics.cruces_m[[i]])[0] - clics.cruces_px[i]))
        )
        filas.append(
            {"nombre": nombre, "error_m": round(e_m, 3), "error_px": round(e_px, 2)}
        )
    e = np.array([f["error_m"] for f in filas], float)
    return {
        "filas": filas,
        "mediana_m": round(float(np.nanmedian(e)), 3),
        "p90_m": round(float(np.nanpercentile(e, 90)), 3),
        "no_predichos": int(np.isnan(e).sum()),
    }


# ── la calibración ACTUAL, para comparar ─────────────────────────────────────────────────────────


def corregida_a_original(px: np.ndarray) -> np.ndarray:
    """Píxel de la imagen corregida → píxel del original (el polinomio de `cv2.undistort`)."""
    px = np.atleast_2d(np.asarray(px, float))
    f, c = float(ANCHO_IMG), np.array([ANCHO_IMG / 2, ALTO_IMG / 2])
    d = (px - c) / f
    r2 = (d * d).sum(1)
    return c + f * d * (1 + K1_ACTUAL * r2 + K2_ACTUAL * r2 * r2)[:, None]


def original_a_corregida(px: np.ndarray) -> np.ndarray:
    """Píxel del original → corregida. NaN más allá del pliegue (~840 px del centro)."""
    px = np.atleast_2d(np.asarray(px, float))
    f, c = float(ANCHO_IMG), np.array([ANCHO_IMG / 2, ALTO_IMG / 2])
    r = np.linspace(0, 1.0, 20000)
    rd = r * (1 + K1_ACTUAL * r * r + K2_ACTUAL * r**4)
    fin = int(np.argmax(np.diff(rd) <= 0))
    d = (px - c) / f
    rho = np.hypot(d[:, 0], d[:, 1])
    ru = np.interp(rho, rd[: fin + 1], r[: fin + 1], right=np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        esc = np.where(rho > 1e-12, ru / rho, 1.0)
    return c + f * d * esc[:, None]


def actual_pixel_a_metros(
    px_original: np.ndarray, H: np.ndarray | None = None
) -> np.ndarray:
    """La calibración de producción: original → corregida → homografía → metros."""
    H = np.load(H_ACTUAL) if H is None else H
    und = original_a_corregida(px_original)
    p = np.column_stack([und, np.ones(len(und))]) @ H.T
    with np.errstate(invalid="ignore", divide="ignore"):
        return p[:, :2] / p[:, 2:3]


# ── dibujo ───────────────────────────────────────────────────────────────────────────────────────


def lineas_del_campo(largo=LARGO, ancho=ANCHO) -> list[np.ndarray]:
    """Polilíneas densas del campo F11 en metros (para que se vean curvas en el original)."""
    cy = ancho / 2
    seg = [
        ((0, 0), (largo, 0)),
        ((largo, 0), (largo, ancho)),
        ((largo, ancho), (0, ancho)),
        ((0, ancho), (0, 0)),
        ((largo / 2, 0), (largo / 2, ancho)),
    ]
    for x0, x1 in ((0, 16.5), (largo, largo - 16.5)):
        seg += [
            ((x0, cy - 20.16), (x1, cy - 20.16)),
            ((x1, cy - 20.16), (x1, cy + 20.16)),
            ((x1, cy + 20.16), (x0, cy + 20.16)),
        ]
    out = [np.linspace(a, b, 200) for a, b in seg]
    t = np.linspace(0, 2 * np.pi, 200)
    out.append(np.column_stack([largo / 2 + 9.15 * np.cos(t), cy + 9.15 * np.sin(t)]))
    return out


def dibujar_campo(
    cam: Camara, img: np.ndarray, clics: Clics | None = None
) -> np.ndarray:
    out = img.copy()
    for ln in lineas_del_campo():
        px = cam.proyectar(ln)
        for a, b in zip(px[:-1], px[1:]):
            if np.isfinite(a).all() and np.isfinite(b).all():
                cv2.line(
                    out,
                    tuple(int(v) for v in a),
                    tuple(int(v) for v in b),
                    (0, 255, 255),
                    1,
                )
    if clics is not None:
        for p in clics.cruces_px:
            cv2.circle(out, tuple(int(v) for v in p), 5, (0, 0, 255), 2)
        for p in clics.lineas_px:
            cv2.circle(out, tuple(int(v) for v in p), 3, (255, 0, 255), 1)
    return out


def ajustar_y_comparar(ruta_clics: Path, salida: Path) -> dict:
    """Ajusta los dos modelos, los valida y elige (docs/lente_f11.md, punto 2)."""
    salida.mkdir(parents=True, exist_ok=True)
    clics = Clics.desde_json(ruta_clics)
    res = {
        "cruces": len(clics.nombres),
        "puntos_de_linea": len(clics.lineas_px),
        "modelos": {},
    }
    cams = {}
    for tipo in ("ojo_pez", "racional"):
        cam, info = ajustar(tipo, clics)
        s = info.pop("_s")
        info["validacion"] = validacion_cruzada(tipo, clics, cam, s)
        res["modelos"][tipo] = info
        cams[tipo] = cam
        np.savez(
            salida / f"camara_{tipo}.npz",
            tipo=tipo, f=cam.f, cx=cam.cx, cy=cam.cy, coefs=cam.coefs, rvec=cam.rvec, tvec=cam.tvec,
        )  # fmt: skip
        libre, inf_l = ajustar(tipo, clics, medidas_libres=True, inicial=cam, s0=s)
        inf_l.pop("_s")
        info["con_medidas_libres"] = {
            "medidas_estimadas_m": inf_l["medidas_estimadas_m"],
            "residuo_px_mediana": inf_l["residuo_px_mediana"],
        }
        if FRAME_ALEVIN.exists():
            cv2.imwrite(
                str(salida / f"campo_{tipo}.jpg"),
                dibujar_campo(cam, cv2.imread(str(FRAME_ALEVIN)), clics),
            )
    validos = {t: m for t, m in res["modelos"].items() if m["monotona"]}
    res["elegido"] = None
    if validos:
        orden = sorted(validos, key=lambda t: validos[t]["validacion"]["mediana_m"])
        elegido = orden[0]
        if len(orden) == 2 and elegido == "racional":
            a = validos["racional"]["validacion"]["mediana_m"]
            b = validos["ojo_pez"]["validacion"]["mediana_m"]
            if b - a < 0.05 * b:
                elegido = (
                    "ojo_pez"  # con < 5 % de diferencia gana el de menos parámetros
                )
        res["elegido"] = elegido
    # la calibración actual, en los mismos cruces
    actual = actual_pixel_a_metros(clics.cruces_px)
    e = np.hypot(*(actual - clics.cruces_m).T)
    res["actual"] = {
        "filas": [
            {"nombre": n, "error_m": None if np.isnan(x) else round(float(x), 3)}
            for n, x in zip(clics.nombres, e)
        ],
        "mediana_m_de_los_representables": round(float(np.nanmedian(e)), 3),
        "no_representables": int(np.isnan(e).sum()),
    }
    json.dump(res, open(salida / "ajuste.json", "w"), indent=1, ensure_ascii=False)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("accion", choices=["ajustar"])
    ap.add_argument("--clics", type=Path, required=True)
    ap.add_argument("--salida", type=Path, default=R / "outputs/lente_f11")
    a = ap.parse_args()
    print(
        json.dumps(ajustar_y_comparar(a.clics, a.salida), indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
