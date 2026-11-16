"""Suavizado en los dos sentidos (RTS) con el ruido LOCAL de la medida, estimado de los datos.

docs/registro_mision.md, H1. Por qué existe: en el F11 las fichas «vuelan» (52 saltos de > 3 m en
0,2 s por minuto). Medido: el 97 % de esos saltos mueve el pie ≤ 20 px en la imagen. Es el borde
inferior de la caja temblando 4-6 px, multiplicado por la proyección rasante: un píxel vale 0,08 m
cerca de la cámara y 0,38 m lejos. La media móvil de ventana fija trata igual todo el campo.

Dos ideas:

1. **El ruido se mide, no se supone.** Sin ruido, tres posiciones seguidas de un jugador están casi
   en línea (en 0,12 s nadie acelera más de unos centímetros). Lo que se sale de la línea
   (la segunda diferencia) es ruido de medida: su varianza es 6·σ². Se calcula por celdas del campo
   y POR EJE (lejos, el eje de profundidad tiembla mucho más que el lateral). No necesita la
   homografía ni el modelo de lente: vale para cualquier cámara.

2. **Suavizado de Rauch-Tung-Striebel (velocidad constante).** Usa pasado y futuro (el vídeo ya está
   grabado), respeta los tiempos reales entre muestras (no promedia a través de un hueco como si no
   existiera) y pesa cada medida por su ruido local: donde la medida es buena, la sigue; donde es
   mala, se fía del movimiento.

No añade ni quita puntos, y no toca identidades.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ParametrosRTS:
    # Cuánto puede acelerar un jugador (m/s²). Es la «rigidez» del modelo: más alto = sigue más a
    # la medida. Físico, no de un partido: un sprint o un frenazo fuerte son 3-5 m/s².
    aceleracion_ms2: float = 4.0
    # Rejilla del ruido local
    paso_rejilla_m: float = 4.0
    min_muestras_celda: int = 150
    # Suelo y techo del ruido de medida (m): nunca se supone una medida perfecta ni inútil
    sigma_min_m: float = 0.03
    sigma_max_m: float = 3.0
    # ROBUSTEZ. El temblor de la caja no es gaussiano: casi siempre es pequeño y de vez en cuando
    # el borde inferior salta 5-10 px (una pierna, otra persona pegada). Medido en el alevín B: σ
    # robusta de 0,07-0,12 m y, aun así, p99 de velocidad cruda de 47 m/s. Con ruido gaussiano el
    # filtro se cree esos saltos. En cada pasada, una medida que queda a más de `corte_sigmas` de
    # la trayectoria suavizada pierde peso en proporción (Huber); `pasadas_robustas` = 0 lo apaga.
    pasadas_robustas: int = 3
    corte_sigmas: float = 2.0

    @classmethod
    def desde_dict(cls, d: dict | None) -> "ParametrosRTS":
        d = d or {}
        return cls(**{c: d[c] for c in cls.__dataclass_fields__ if c in d})


class RuidoLocal:
    """σ de la medida (m) por celda del campo y por eje, estimado de las propias trayectorias."""

    def __init__(self, trayectorias, tiempo_de: dict, params: ParametrosRTS):
        self.params = params
        pos, d2 = [], []
        for tr in trayectorias:
            if len(tr) < 3:
                continue
            t = np.array([tiempo_de[f] for f, _p, _r in tr], dtype=float)
            p = np.array([q for _f, q, _r in tr], dtype=float)
            dt0, dt1 = t[1:-1] - t[:-2], t[2:] - t[1:-1]
            # solo tríos a la cadencia nativa: con huecos la segunda diferencia ya no es solo ruido
            paso = np.median(np.diff(t)) if len(t) > 1 else 0.0
            ok = (np.abs(dt0 - paso) < 0.25 * paso) & (np.abs(dt1 - paso) < 0.25 * paso)
            # La celda se elige con la MEDIA de las tres posiciones, no con la central: la media no
            # está correlada con la segunda diferencia, y con la central las celdas seleccionan el
            # ruido (σ sale un 30 % baja cuando el ruido es del tamaño de la celda).
            pos.append(((p[:-2] + p[1:-1] + p[2:]) / 3.0)[ok])
            d2.append((p[2:] - 2 * p[1:-1] + p[:-2])[ok])
        if not pos or sum(len(x) for x in pos) == 0:
            self._global = np.array([0.3, 0.3])
            self._rejilla = None
            return
        pos, d2 = np.concatenate(pos), np.concatenate(d2)
        self._global = self._sigma(d2)
        paso_m = params.paso_rejilla_m
        # Extensión ROBUSTA: una proyección cerca del horizonte cae a kilómetros, y con el mínimo y
        # el máximo la rejilla tendría millones de celdas. Lo de fuera usa la celda del borde.
        self._origen = np.percentile(pos, 0.5, axis=0)
        tope = np.percentile(pos, 99.5, axis=0)
        celdas = np.floor(
            (np.clip(pos, self._origen, tope) - self._origen) / paso_m
        ).astype(int)
        forma = celdas.max(axis=0) + 1
        rejilla = np.full((forma[0], forma[1], 2), np.nan)
        orden = np.lexsort((celdas[:, 1], celdas[:, 0]))
        celdas_o, d2_o = celdas[orden], d2[orden]
        cortes = np.flatnonzero(np.any(np.diff(celdas_o, axis=0) != 0, axis=1)) + 1
        for ini, fin in zip(np.r_[0, cortes], np.r_[cortes, len(celdas_o)]):
            if fin - ini >= params.min_muestras_celda:
                i, j = celdas_o[ini]
                rejilla[i, j] = self._sigma(d2_o[ini:fin])
        self._rejilla = self._rellenar(rejilla)
        self._paso = paso_m
        logger.info(
            "Ruido local de la medida (m): global x %.2f · y %.2f; por celda x %.2f-%.2f · "
            "y %.2f-%.2f (%d celdas medidas)",
            self._global[0],
            self._global[1],
            np.nanmin(rejilla[..., 0]) if np.isfinite(rejilla).any() else np.nan,
            np.nanmax(rejilla[..., 0]) if np.isfinite(rejilla).any() else np.nan,
            np.nanmin(rejilla[..., 1]) if np.isfinite(rejilla).any() else np.nan,
            np.nanmax(rejilla[..., 1]) if np.isfinite(rejilla).any() else np.nan,
            int(np.isfinite(rejilla[..., 0]).sum()),
        )

    def _sigma(self, d2: np.ndarray) -> np.ndarray:
        """σ robusta por eje: MAD de la segunda diferencia / √6 (var(d2) = 6·σ² si es blanco)."""
        mad = np.median(np.abs(d2 - np.median(d2, axis=0)), axis=0)
        return np.clip(
            1.4826 * mad / np.sqrt(6.0),
            self.params.sigma_min_m,
            self.params.sigma_max_m,
        )

    def _rellenar(self, rejilla: np.ndarray) -> np.ndarray:
        """Las celdas sin muestras heredan la media de sus vecinas medidas, o la global."""
        llena = rejilla.copy()
        for _ in range(max(rejilla.shape[:2])):
            huecos = np.argwhere(np.isnan(llena[..., 0]))
            if len(huecos) == 0:
                break
            nueva = llena.copy()
            for i, j in huecos:
                vec = llena[max(i - 1, 0) : i + 2, max(j - 1, 0) : j + 2]  # noqa: E203
                vec = vec.reshape(-1, 2)
                vec = vec[np.isfinite(vec[:, 0])]
                if len(vec):
                    nueva[i, j] = vec.mean(axis=0)
            if np.isnan(nueva[..., 0]).sum() == len(huecos):
                break
            llena = nueva
        llena[np.isnan(llena[..., 0])] = self._global
        return llena

    def sigma(self, pos: np.ndarray) -> np.ndarray:
        """σ (N, 2) de la medida en cada posición (N, 2)."""
        pos = np.atleast_2d(pos)
        if self._rejilla is None:
            return np.tile(self._global, (len(pos), 1))
        c = np.floor((pos - self._origen) / self._paso).astype(int)
        c[:, 0] = np.clip(c[:, 0], 0, self._rejilla.shape[0] - 1)
        c[:, 1] = np.clip(c[:, 1], 0, self._rejilla.shape[1] - 1)
        return self._rejilla[c[:, 0], c[:, 1]]


def rts_1d(t: np.ndarray, z: np.ndarray, sigma: np.ndarray, q: float) -> np.ndarray:
    """Suavizado RTS de una coordenada con modelo de velocidad constante.

    Args:
        t: tiempos (s), crecientes. z: medidas (m). sigma: ruido de cada medida (m).
        q: densidad espectral de la aceleración (m²/s³).
    """
    n = len(z)
    if n < 3:
        return z.copy()
    # Aritmética escalar a propósito: con matrices 2×2 de numpy cada paso cuesta ~50 µs y un
    # partido son millones de pasos. El estado es (p, v) y la covarianza (a, b; b, c).
    t, z, sigma = t.tolist(), z.tolist(), sigma.tolist()
    k2 = min(2, n - 1)
    p, v = z[0], (z[k2] - z[0]) / max(t[k2] - t[0], 1e-6)
    a, b, c = sigma[0] ** 2 * 4, 0.0, 25.0
    filt, pred, dts = [], [], []
    for k in range(n):
        dt = t[k] - t[k - 1] if k else 0.0
        # predicción
        pp, vp = p + dt * v, v
        ap = a + 2 * dt * b + dt * dt * c + q * dt**3 / 3
        bp = b + dt * c + q * dt * dt / 2
        cp = c + q * dt
        # corrección con la medida z[k]
        s = ap + sigma[k] ** 2
        k0, k1 = ap / s, bp / s
        inn = z[k] - pp
        p, v = pp + k0 * inn, vp + k1 * inn
        a, b, c = ap - k0 * ap, bp - k0 * bp, cp - k1 * bp
        filt.append((p, v, a, b, c))
        pred.append((pp, vp, ap, bp, cp))
        dts.append(dt)
    suave = [0.0] * n
    ps, vs = filt[-1][0], filt[-1][1]
    suave[-1] = ps
    for k in range(n - 2, -1, -1):
        p, v, a, b, c = filt[k]
        pp, vp, ap, bp, cp = pred[k + 1]
        dt = dts[k + 1]
        # C = P·Fᵀ·Pp⁻¹, con P·Fᵀ = [[a + dt·b, b], [b + dt·c, c]]
        det = ap * cp - bp * bp
        m00, m01, m10, m11 = a + dt * b, b, b + dt * c, c
        c00 = (m00 * cp - m01 * bp) / det
        c01 = (-m00 * bp + m01 * ap) / det
        c10 = (m10 * cp - m11 * bp) / det
        c11 = (-m10 * bp + m11 * ap) / det
        dp, dv = ps - pp, vs - vp
        ps, vs = p + c00 * dp + c01 * dv, v + c10 * dp + c11 * dv
        suave[k] = ps
    return np.array(suave)


def suavizar_rts(
    trayectorias: list[list[tuple]],
    tiempo_de: dict,
    params: ParametrosRTS | None = None,
) -> list[list[tuple]]:
    """Suaviza las posiciones REALES de cada trayectoria. Ni añade ni quita puntos.

    Args:
        trayectorias: [[(frame_idx, pos, es_real), ...], ...]
        tiempo_de: {frame_idx: t en segundos} (el tiempo REAL de cada frame del caché).
    """
    params = params or ParametrosRTS()
    ruido = RuidoLocal(trayectorias, tiempo_de, params)
    q = params.aceleracion_ms2**2
    resultado = []
    for tr in trayectorias:
        indices = [i for i, (_f, _p, real) in enumerate(tr) if real]
        if len(indices) < 3:
            resultado.append(tr)
            continue
        t = np.array([tiempo_de[tr[i][0]] for i in indices], dtype=float)
        p = np.array([tr[i][1] for i in indices], dtype=float)
        sig = ruido.sigma(p)
        suave = np.column_stack(
            [rts_1d(t, p[:, eje], sig[:, eje], q) for eje in (0, 1)]
        )
        for _ in range(params.pasadas_robustas):
            residuo = np.abs(p - suave)
            peso = np.maximum(1.0, residuo / (params.corte_sigmas * sig))
            suave = np.column_stack(
                [rts_1d(t, p[:, eje], sig[:, eje] * peso[:, eje], q) for eje in (0, 1)]
            )
        nueva = list(tr)
        for k, i in enumerate(indices):
            nueva[i] = (tr[i][0], suave[k], tr[i][2])
        resultado.append(nueva)
    logger.info(
        "Suavizado RTS (aceleración %.1f m/s²): %d trayectorias",
        params.aceleracion_ms2,
        len(resultado),
    )
    return resultado
