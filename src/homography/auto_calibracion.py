"""Calibración AUTOMÁTICA del campo a partir de las líneas pintadas (SOLO MEDICIÓN).

Plan y criterio: docs/plan_calibracion_automatica.md. Este módulo NO lo importa el
pipeline: la homografía de producción sigue siendo la de los clics manuales.

Idea en tres pasos:

1. **Píxeles de línea**: dentro del césped, lo claro, estrecho y poco saturado.
2. **Alinear el modelo ENTERO** (no segmentos sueltos): se muestrea el modelo F7 en puntos,
   se proyecta con una homografía candidata y se cuenta cuántos caen sobre una línea.
   Así el círculo no puede "casar" con un arco de área sin que el resto deje de cuadrar.
3. **Inicialización con una cámara física** (posición, punto al que mira, giro y focal),
   barriendo cámaras plausibles alrededor del campo. Luego se refina con Nelder-Mead y al
   final se ajusta la homografía completa (ICP contra el esqueleto de las líneas).

Convenciones: H_m2px lleva metros → píxeles; su inversa es la del pipeline (píxel →
metros). Ejes del campo: x de portería a portería, y de banda a banda, z hacia arriba.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.optimize import minimize

# ───────────────────────────── 1. píxeles de línea ─────────────────────────────

# Césped ARTIFICIAL del benjamín: tono ~54, saturación ~86 (medido en un frame de
# desarrollo, no en el de calibración). La ladera de hierba natural de detrás es más
# amarilla (tono 22-38): con el rango de line_detector (35-85) entraba y llenaba la
# máscara de "líneas" que eran vallas y matorrales.
VERDE_BAJO, VERDE_ALTO = np.array([45, 45, 40]), np.array([75, 200, 210])


def mascara_campo(img: np.ndarray) -> np.ndarray:
    """La mayor región de césped, con sus agujeros (líneas, jugadores) rellenos.

    Se rellena el CONTORNO EXTERIOR y no la envolvente convexa: la envolvente cruzaba la
    grada y la ladera, y metía sus bordes como si fueran líneas.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    verde = cv2.inRange(hsv, VERDE_BAJO, VERDE_ALTO)
    verde = cv2.morphologyEx(verde, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    verde = cv2.morphologyEx(verde, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contornos, _ = cv2.findContours(verde, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    salida = np.zeros(img.shape[:2], np.uint8)
    if contornos:
        cv2.drawContours(salida, [max(contornos, key=cv2.contourArea)], -1, 255, -1)
        # se encoge un poco: el borde del césped no es línea (la banda sí está dentro)
        salida = cv2.erode(salida, np.ones((7, 7), np.uint8))
    return salida


def mascara_lineas(
    img: np.ndarray,
    campo: np.ndarray,
    kernel_tophat: int = 15,
    umbral_tophat: int = 25,
    sat_max: int = 70,
    largo_min_px: int = 40,
) -> np.ndarray:
    """Píxeles de línea: más claros que su entorno (top-hat), poco saturados, en el césped.

    Las componentes cortas (diagonal de su caja < `largo_min_px`) se descartan: casi
    todas son jugadores, el balón o reflejos. Las líneas y los arcos son largos.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_tophat, kernel_tophat))
    tophat = cv2.morphologyEx(v, cv2.MORPH_TOPHAT, k)
    m = ((tophat > umbral_tophat) & (hsv[:, :, 1] < sat_max) & (campo > 0)).astype(
        np.uint8
    )
    n, et, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    diag = np.hypot(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    # Una línea es larga y FINA: poca área para el tamaño de su caja. Un jugador de
    # blanco es un bulto (área/diag² ~0,2-0,4). Lo muy largo se queda siempre: es una
    # línea aunque lleve un jugador pegado.
    finura = stats[:, cv2.CC_STAT_AREA] / np.maximum(diag, 1) ** 2
    buenas = np.zeros(n, bool)
    buenas[1:] = (diag[1:] >= largo_min_px) & ((finura[1:] < 0.08) | (diag[1:] > 300))
    return (buenas[et]).astype(np.uint8) * 255


def adelgazar(mascara: np.ndarray, iter_max: int = 20) -> np.ndarray:
    """Esqueleto de una máscara binaria (Zhang-Suen, vectorizado con numpy).

    El ICP necesita el CENTRO de la línea: con la máscara gruesa, el píxel más cercano
    está en el borde y sesga el ajuste medio ancho de línea hacia la cámara.
    """
    img = (mascara > 0).astype(np.uint8)
    for _ in range(iter_max):
        cambio = False
        for paso in (0, 1):
            p = np.pad(img, 1)
            n = [
                p[:-2, 1:-1],
                p[:-2, 2:],
                p[1:-1, 2:],
                p[2:, 2:],
                p[2:, 1:-1],
                p[2:, :-2],
                p[1:-1, :-2],
                p[:-2, :-2],
            ]  # fmt: skip  (P2..P9 en sentido horario desde arriba)
            b = sum(n)
            a = sum(((n[i] == 0) & (n[(i + 1) % 8] == 1)) for i in range(8))
            if paso == 0:
                c1, c2 = n[0] * n[2] * n[4], n[2] * n[4] * n[6]
            else:
                c1, c2 = n[0] * n[2] * n[6], n[0] * n[4] * n[6]
            borrar = (img == 1) & (b >= 2) & (b <= 6) & (a == 1) & (c1 == 0) & (c2 == 0)
            if borrar.any():
                img[borrar] = 0
                cambio = True
        if not cambio:
            break
    return img * 255


# ───────────────────────────── 2. modelo del campo ─────────────────────────────


def puntos_modelo(
    largo: float,
    ancho: float,
    area_ancho: float = 26.0,
    area_prof: float = 12.0,
    radio_circulo: float = 6.0,
    paso_m: float = 0.25,
) -> np.ndarray:
    """Puntos (N×2, metros) sobre las líneas del modelo F7: bandas, fondos, medio campo,
    círculo central y las dos áreas. Las marcas que el reglamento no fija (semicírculos,
    áreas pequeñas) NO se modelan a propósito: el coste va del modelo a la imagen, así que
    una línea de más en la imagen no castiga."""
    segs = [
        ((0, 0), (largo, 0)),
        ((0, ancho), (largo, ancho)),
        ((0, 0), (0, ancho)),
        ((largo, 0), (largo, ancho)),
        ((largo / 2, 0), (largo / 2, ancho)),
    ]
    y0, y1 = (ancho - area_ancho) / 2, (ancho + area_ancho) / 2
    for xf, xa in ((0.0, area_prof), (largo, largo - area_prof)):
        segs += [((xf, y0), (xa, y0)), ((xf, y1), (xa, y1)), ((xa, y0), (xa, y1))]
    pts = []
    for (ax, ay), (bx, by) in segs:
        n = max(2, int(np.hypot(bx - ax, by - ay) / paso_m))
        t = np.linspace(0, 1, n)
        pts.append(np.c_[ax + t * (bx - ax), ay + t * (by - ay)])
    ang = np.linspace(
        0, 2 * np.pi, int(2 * np.pi * radio_circulo / paso_m), endpoint=False
    )
    pts.append(
        np.c_[
            largo / 2 + radio_circulo * np.cos(ang),
            ancho / 2 + radio_circulo * np.sin(ang),
        ]
    )
    return np.vstack(pts)


# ───────────────────────────── 3. cámara física y coste ─────────────────────────────


def camara_a_homografia(params, w: int, h: int) -> np.ndarray | None:
    """params = (cx, cy, cz, tx, ty, giro, f): cámara en (cx,cy,cz) mirando al punto del
    suelo (tx,ty), con giro alrededor del eje óptico y focal f (px). Devuelve H_m2px."""
    cx, cy, cz, tx, ty, giro, f = params
    if cz <= 0.3 or f <= 100:
        return None
    c = np.array([cx, cy, cz])
    adelante = np.array([tx, ty, 0.0]) - c
    nrm = np.linalg.norm(adelante)
    if nrm < 1e-6:
        return None
    adelante /= nrm
    derecha = np.cross(adelante, [0.0, 0.0, 1.0])
    if np.linalg.norm(derecha) < 1e-6:
        return None
    derecha /= np.linalg.norm(derecha)
    abajo = np.cross(adelante, derecha)
    cg, sg = np.cos(giro), np.sin(giro)
    derecha, abajo = cg * derecha + sg * abajo, -sg * derecha + cg * abajo
    R = np.vstack([derecha, abajo, adelante])
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1.0]])
    H = K @ np.c_[R[:, 0], R[:, 1], -R @ c]
    return H / H[2, 2] if abs(H[2, 2]) > 1e-12 else None


def proyectar(H: np.ndarray, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(píxeles N×2, delante N bool): solo valen los puntos por DELANTE de la cámara."""
    p = np.c_[pts, np.ones(len(pts))] @ H.T
    delante = p[:, 2] > 1e-9
    with np.errstate(divide="ignore", invalid="ignore"):
        px = p[:, :2] / p[:, 2:3]
    return px, delante


@dataclass
class Imagen:
    """Lo que el coste necesita de un frame, precalculado una vez."""

    dt: np.ndarray  # distancia (px) al esqueleto de línea más cercano
    campo: np.ndarray  # máscara del césped
    w: int
    h: int
    vecino: (
        np.ndarray
    )  # (h, w, 2): coordenadas (x, y) del píxel de esqueleto más cercano
    esqueleto: (
        np.ndarray
    )  # (M, 2) píxeles de esqueleto (submuestreados) para el coste inverso


def preparar(img: np.ndarray, lineas: np.ndarray | None = None) -> Imagen:
    campo = mascara_campo(img)
    if lineas is None:
        lineas = mascara_lineas(img, campo)
    return preparar_desde_lineas(lineas, campo)


def preparar_desde_lineas(lineas: np.ndarray, campo: np.ndarray) -> Imagen:
    esq = adelgazar(lineas)
    dt, et = cv2.distanceTransformWithLabels(
        (esq == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )
    ys, xs = np.nonzero(esq)
    # las etiquetas de DIST_LABEL_PIXEL numeran los píxeles cero en orden de barrido
    tabla = np.zeros((et.max() + 1, 2), np.float32)
    orden = np.lexsort((xs, ys))
    tabla[1 : len(xs) + 1] = np.c_[xs[orden], ys[orden]]  # noqa: E203
    h, w = lineas.shape
    esq_pts = np.c_[xs, ys][:: max(1, len(xs) // 3000)].astype(np.float32)
    return Imagen(dt=dt, campo=campo, w=w, h=h, vecino=tabla[et], esqueleto=esq_pts)


def evaluar(H, im: Imagen, pts: np.ndarray, tau: float) -> tuple[float, float, int]:
    """(coste en [0,1], S, puntos visibles).

    Coste: media sobre TODOS los puntos del modelo de min(d, τ)/τ, contando 1 los que no
    se ven o caen fuera del césped. Es "cuánto modelo NO cae sobre una línea".
    S (confianza): de los puntos visibles, fracción a ≤ τ px de una línea.
    """
    if H is None:
        return 1.0, 0.0, 0
    px, delante = proyectar(H, pts)
    x, y = px[:, 0], px[:, 1]
    vis = (
        delante
        & np.isfinite(x)
        & (x >= 0)
        & (x <= im.w - 1.5)
        & (y >= 0)
        & (y <= im.h - 1.5)
    )
    c = np.ones(len(pts))
    # REDONDEAR, no truncar: truncar sesga medio píxel y el ICP lo acumula en cada vuelta
    # (medido: 7 px de deriva partiendo de la solución exacta en una escena sintética)
    xi, yi = np.rint(x[vis]).astype(int), np.rint(y[vis]).astype(int)
    en_campo = im.campo[yi, xi] > 0
    d = im.dt[yi, xi]
    cv = np.where(en_campo, np.minimum(d, tau) / tau, 1.0)
    c[vis] = cv
    n_vis = int(en_campo.sum())
    s = float(((d <= tau) & en_campo).sum() / n_vis) if n_vis else 0.0
    return float(c.mean()), s, n_vis


def coste_inverso(H, im: Imagen, largo: float, ancho: float, tau: float) -> float:
    """Fracción de los píxeles de línea detectados que NO explica el modelo (a > τ px de
    una línea del modelo proyectada). Se calcula a media resolución, que basta para esto.

    Sin este término, un campo ENCOGIDO dentro del encuadre ganaba a la solución correcta:
    la correcta paga por la línea de fondo cercana, que está fuera de plano, y la encogida
    no paga nada. Las líneas largas de la imagen que el campo encogido deja sin explicar lo
    delatan. (Las marcas que no están en el modelo pagan igual en todas las soluciones.)
    """
    if H is None or len(im.esqueleto) == 0:
        return 1.0
    esc = 0.5
    lienzo = np.zeros((int(im.h * esc), int(im.w * esc)), np.uint8)
    for seg in _polilineas_modelo(largo, ancho):
        px, delante = proyectar(H, seg)
        if not delante.all() or not np.isfinite(px).all() or np.abs(px).max() > 1e5:
            continue
        cv2.polylines(lienzo, [(px * esc).astype(np.int32)], False, 255, 1)
    dt = cv2.distanceTransform((lienzo == 0).astype(np.uint8), cv2.DIST_L2, 3) / esc
    q = (im.esqueleto * esc).astype(int)
    return float((dt[q[:, 1], q[:, 0]] > tau).mean())


def _polilineas_modelo(largo, ancho, area_ancho=26.0, area_prof=12.0, radio=6.0):
    y0, y1 = (ancho - area_ancho) / 2, (ancho + area_ancho) / 2
    lineas = [
        [(0, 0), (largo, 0)], [(0, ancho), (largo, ancho)], [(0, 0), (0, ancho)],
        [(largo, 0), (largo, ancho)], [(largo / 2, 0), (largo / 2, ancho)],
        [(0, y0), (area_prof, y0), (area_prof, y1), (0, y1)],
        [(largo, y0), (largo - area_prof, y0), (largo - area_prof, y1), (largo, y1)],
    ]  # fmt: skip
    salida = []
    for ln in lineas:
        ln = np.array(ln, float)
        fino = [ln[0]]
        for a, b in zip(ln[:-1], ln[1:]):  # densificar: la perspectiva curva nada, pero
            fino.extend(a + (b - a) * t for t in np.linspace(0, 1, 20)[1:])  # recorta
        salida.append(np.array(fino))
    ang = np.linspace(0, 2 * np.pi, 72)
    salida.append(
        np.c_[largo / 2 + radio * np.cos(ang), ancho / 2 + radio * np.sin(ang)]
    )
    return salida


# Cámaras físicamente plausibles durante la búsqueda (fuera de aquí, coste máximo)
ALTURA_M = (1.5, 25.0)
FOCAL_PX = (500.0, 4000.0)


def _coste_total(q, im, pts, largo, ancho, tau):
    if not (ALTURA_M[0] <= q[2] <= ALTURA_M[1] and FOCAL_PX[0] <= q[6] <= FOCAL_PX[1]):
        return 2.0
    H = camara_a_homografia(q, im.w, im.h)
    return evaluar(H, im, pts, tau)[0] + coste_inverso(H, im, largo, ancho, tau)


# ───────────────────────────── 4. búsqueda y refinado ─────────────────────────────


def rejilla_camaras(largo: float, ancho: float):
    """Cámaras plausibles: detrás de cada portería y en cada banda, a varias distancias,
    alturas y focales, mirando a una rejilla de puntos del suelo.

    ⚠️ Los puntos a los que mira llegan MÁS ALLÁ del campo. Una cámara baja que encuadra el
    campo entero tiene el centro de la imagen en el horizonte, así que su eje óptico corta
    el suelo muy lejos (la cámara del benjamín: a ~140 m). La primera versión solo miraba
    a puntos del campo, y todas sus cámaras salían demasiado picadas: el ajuste caía en un
    mínimo con el campo encogido. Corregido en el frame de desarrollo, antes de medir.
    """
    lejos = (0.3, 0.5, 0.7, 1.5, 3.0)  # fracción del campo hacia donde mira la cámara
    for dist in (2.0, 6.0, 12.0, 20.0):
        for altura in (2.5, 5.0, 9.0, 15.0):
            for lado in range(4):
                for frac in (0.25, 0.5, 0.75):
                    for prof in lejos:
                        for lat in (0.3, 0.5, 0.7):
                            # (cámara, punto al que mira), en el sistema del lado
                            if lado == 0:
                                c, t = (-dist, frac * ancho), (
                                    prof * largo,
                                    lat * ancho,
                                )
                            elif lado == 1:
                                c = (largo + dist, frac * ancho)
                                t = (largo - prof * largo, lat * ancho)
                            elif lado == 2:
                                c, t = (frac * largo, -dist), (
                                    lat * largo,
                                    prof * ancho,
                                )
                            else:
                                c = (frac * largo, ancho + dist)
                                t = (lat * largo, ancho - prof * ancho)
                            for f in (900.0, 1400.0, 2100.0, 3200.0):
                                yield (c[0], c[1], altura, t[0], t[1], 0.0, f)


@dataclass
class Resultado:
    H_m2px: np.ndarray | None
    S: float
    coste: float
    params: tuple | None


def calibrar(
    im: Imagen,
    largo: float,
    ancho: float,
    n_semillas: int = 12,
    tau_final: float = 4.0,
    icp_iter: int = 15,
    busqueda: str = "amplia",
) -> Resultado:
    """Estima H_m2px. Devuelve también S (confianza) con τ = `tau_final`.

    `busqueda`:
    - "estrecha" (INTENTO 1): las 1000 mejores semillas por el coste directo, reordenadas con
      el coste en los dos sentidos; se refinan las 12 mejores. Midió 684 px en los clics: las
      12 mejores eran variaciones de la MISMA solución equivocada.
    - "amplia" (INTENTO 2): TODA la rejilla ordenada con el coste en los dos sentidos, y se
      refina la mejor semilla de cada (lado, distancia, altura): semillas DIVERSAS, para que
      el valle de la solución buena tenga alguna.
    """
    pts = puntos_modelo(largo, ancho)
    sub = pts[
        ::4
    ]  # rejilla gruesa: un punto de cada cuatro basta para ordenar semillas
    cand = []
    for p in rejilla_camaras(largo, ancho):
        coste, _s, nv = evaluar(camara_a_homografia(p, im.w, im.h), im, sub, 25.0)
        if nv >= 20:
            cand.append((coste, p))
    if busqueda == "estrecha":
        cand.sort(key=lambda z: z[0])
        cand = sorted(
            cand[:1000],
            key=lambda z: _coste_total(np.array(z[1]), im, sub, largo, ancho, 25.0),
        )
        semillas = [p for _c, p in cand[:n_semillas]]
    else:
        por_grupo: dict = {}
        for _c, p in cand:
            total = _coste_total(np.array(p), im, sub, largo, ancho, 25.0)
            lado = (
                round(p[0], 0) if p[0] < 0 or p[0] > largo else "x",
                p[1] < 0 or p[1] > ancho,
            )
            grupo = (
                lado,
                round(p[2], 1),
                round(np.hypot(p[0] - p[3], p[1] - p[4]) / 20),
            )
            if grupo not in por_grupo or total < por_grupo[grupo][0]:
                por_grupo[grupo] = (total, p)
        semillas = [p for _t, p in sorted(por_grupo.values(), key=lambda z: z[0])[:30]]
    mejor = (9.0, None)
    for p0 in semillas:
        p = np.array(p0, float)
        for tau in (25.0, 10.0):
            p = minimize(
                _coste_total,
                p,
                args=(im, sub, largo, ancho, tau),
                method="Nelder-Mead",
                options={"maxiter": 500, "xatol": 1e-3},
            ).x
        c = _coste_total(p, im, pts, largo, ancho, 10.0)
        if c < mejor[0]:
            mejor = (c, p)
    if mejor[1] is None:
        return Resultado(None, 0.0, 1.0, None)
    H = camara_a_homografia(mejor[1], im.w, im.h)
    H = refinar_icp(H, im, pts, iteraciones=icp_iter)
    H = canonica(H, largo, ancho)
    coste, S, _ = evaluar(H, im, pts, tau_final)
    return Resultado(H, S, coste, tuple(mejor[1]))


def refinar_icp(H, im: Imagen, pts: np.ndarray, iteraciones: int = 15) -> np.ndarray:
    """Ajuste fino de los 8 grados de libertad: cada punto visible del modelo con su píxel
    de esqueleto más cercano, mínimos cuadrados, iterado con tolerancia decreciente."""
    for k in range(iteraciones):
        tau = max(3.0, 12.0 * (1 - k / iteraciones))
        px, delante = proyectar(H, pts)
        x, y = px[:, 0], px[:, 1]
        vis = (
            delante
            & np.isfinite(x)
            & (x >= 0)
            & (x < im.w - 1)
            & (y >= 0)
            & (y < im.h - 1)
        )
        idx = np.nonzero(vis)[0]
        xi, yi = np.rint(x[idx]).astype(int), np.rint(y[idx]).astype(int)
        ok = (im.campo[yi, xi] > 0) & (im.dt[yi, xi] <= tau)
        if ok.sum() < 30:
            break
        src = pts[idx[ok]].astype(np.float32)
        dst = im.vecino[yi[ok], xi[ok]].astype(np.float32)
        Hn, _ = cv2.findHomography(src, dst, 0)
        if Hn is None:
            break
        H = Hn / Hn[2, 2]
    return H


def canonica(H, largo: float, ancho: float) -> np.ndarray:
    """El F7 es simétrico a 180°: (x, y) y (largo−x, ancho−y) dan la misma imagen. Por
    CONVENIO, x = 0 es la portería más cercana a la cámara (la que proyecta más abajo en la
    imagen). No mira la H manual: es una regla fija."""
    rot = np.array([[-1, 0, largo], [0, -1, ancho], [0, 0, 1.0]])
    a = proyectar(H, np.array([[0.0, ancho / 2]]))[0][0, 1]
    b = proyectar(H, np.array([[largo, ancho / 2]]))[0][0, 1]
    return H @ rot if b > a else H
