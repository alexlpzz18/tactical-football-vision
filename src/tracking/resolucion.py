"""Resolución métrica del campo: cuántos metros vale un píxel en cada zona.

Por qué existe (diagnóstico del benjamín, 08-ago-2026): el corte por
velocidad hizo 138 cortes en un tramo de un minuto, frente a un puñado en
Villaviciosa. No es que los niños teletransporten: es que los umbrales
estaban en m/s fijos y la resolución del encuadre NO es uniforme.

Con la cámara detrás de la portería, un píxel vale 0,02 m junto al área
cercana y 0,44 m en el fondo — un factor 21. Como el detector tiene un
jitter de un par de píxeles en la caja, esa misma vibración se traduce en
velocidades aparentes muy distintas según dónde esté el jugador:

    v_ruido = jitter_px · (metros por píxel) / dt

Con dt = 0,12 s y 2 px de jitter: 0,35 m/s cerca y 7,4 m/s en el fondo.
Un umbral fijo de 8,5 m/s es holgado cerca y se dispara en el fondo con
ruido puro — de ahí los cortes. La solución no es subir el umbral (eso
cegaría la zona buena) sino hacerlo LOCAL: umbral físico + margen de
ruido de esa zona.

El mismo razonamiento vale para la distancia de consolidación (dos fichas
del mismo jugador se separan tanto más cuanto peor es la resolución) y
para cuánto conviene interpolar (rellenar donde un píxel vale medio metro
inventa más metros).
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ResolucionCampo:
    """Metros por píxel en cada punto del campo, según la homografía.

    Se precalcula sobre una rejilla y se consulta por celda: se llama una
    vez por observación y por par de identidades, así que hacer la
    proyección punto a punto sería innecesariamente caro.
    """

    def __init__(
        self,
        homografia: np.ndarray,
        largo: float,
        ancho: float,
        paso_m: float = 2.0,
    ):
        self.largo = largo
        self.ancho = ancho
        self.paso = paso_m
        self._nx = max(int(largo / paso_m) + 1, 2)
        self._ny = max(int(ancho / paso_m) + 1, 2)
        self._rejilla = self._calcular(homografia)
        finitos = self._rejilla[np.isfinite(self._rejilla)]
        self.mpp_min = float(finitos.min()) if len(finitos) else 1.0
        self.mpp_max = float(finitos.max()) if len(finitos) else 1.0
        logger.info(
            "Resolución del campo: %.3f m/píxel en la mejor zona, %.3f en la "
            "peor (factor %.0f×)",
            self.mpp_min,
            self.mpp_max,
            self.mpp_max / max(self.mpp_min, 1e-9),
        )

    def _calcular(self, homografia: np.ndarray) -> np.ndarray:
        """Rejilla de metros/píxel proyectando ±1 píxel en cada celda."""
        H_inv = np.linalg.inv(homografia)
        xs = np.linspace(0, self.largo, self._nx)
        ys = np.linspace(0, self.ancho, self._ny)
        rejilla = np.full((self._ny, self._nx), np.nan)
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                pix = H_inv @ np.array([x, y, 1.0])
                if abs(pix[2]) < 1e-12:
                    continue
                pix = pix / pix[2]
                # Un píxel en cada eje de imagen → cuántos metros
                vecinos = np.array(
                    [[[pix[0] + 1.0, pix[1]]], [[pix[0], pix[1] + 1.0]]],
                    dtype=np.float64,
                )
                metros = cv2.perspectiveTransform(vecinos, homografia).reshape(2, 2)
                d = np.linalg.norm(metros - np.array([x, y]), axis=1)
                rejilla[j, i] = float(np.max(d))
        # Rellenar celdas degeneradas (detrás del horizonte) con el peor valor
        if np.isnan(rejilla).any():
            peor = np.nanmax(rejilla) if np.isfinite(np.nanmax(rejilla)) else 1.0
            rejilla = np.nan_to_num(rejilla, nan=peor)
        return rejilla

    def metros_por_pixel(self, pos) -> float:
        """Metros que vale un píxel en la posición (x, y) en metros."""
        i = int(round(float(pos[0]) / self.paso))
        j = int(round(float(pos[1]) / self.paso))
        i = min(max(i, 0), self._nx - 1)
        j = min(max(j, 0), self._ny - 1)
        return float(self._rejilla[j, i])

    def velocidad_ruido(self, pos, jitter_px: float, dt: float) -> float:
        """Velocidad aparente (m/s) que produce el jitter de la caja aquí."""
        if dt <= 0:
            return 0.0
        return jitter_px * self.metros_por_pixel(pos) / dt

    def factor(self, pos) -> float:
        """Cuántas veces peor es la resolución aquí que en la mejor zona."""
        return self.metros_por_pixel(pos) / max(self.mpp_min, 1e-9)

    def tabla(self, n: int = 6) -> list[tuple[float, float]]:
        """[(x, metros/píxel)] a lo largo del eje largo, para el log."""
        cy = self.ancho / 2
        return [
            (float(x), self.metros_por_pixel((x, cy)))
            for x in np.linspace(self.largo * 0.05, self.largo * 0.95, n)
        ]


def desde_config(cfg_tracking: dict, ruta_homografia, largo: float, ancho: float):
    """Construye la ResolucionCampo si la config la pide (None si no).

    Se activa con `escalado_resolucion.activo: true` en tracking.yaml. Sin
    ella, todo el sistema usa los umbrales fijos de siempre — el F11 no
    cambia de comportamiento.
    """
    cfg = cfg_tracking.get("escalado_resolucion", {})
    if not cfg.get("activo", False):
        return None
    homografia = np.load(ruta_homografia)
    return ResolucionCampo(homografia, largo, ancho, cfg.get("paso_rejilla_m", 2.0))
