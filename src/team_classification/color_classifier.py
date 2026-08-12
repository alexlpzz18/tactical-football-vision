"""Clasificador de equipos de 2 fases por color (migración del validado en Colab).

Diseño (briefing 2.3, validado en frames sueltos):

1. Feature de color por recorte (`_color_torso`): banda del pecho (12-45 %
   del alto, 15-85 % del ancho) + máscara anti-verde en HSV (H 35-85,
   S≥40, V≥40 se descartan: es césped) + histograma HS 16×16 normalizado
   → vector de 256 floats. Es la MISMA feature del caché de colores que
   genera Colab, así que el clasificador puede entrenarse aquí con esas
   features sin tocar imágenes.

2. `fit`: KMeans k=8 generoso sobre todas las features → fusión jerárquica
   (linkage average sobre los centros) con umbral AUTO (barrido 0.5-1.3
   maximizando equilibrio-top2 × separación-del-3º) → los 2 meta-grupos
   más grandes POR TAMAÑO (nº de muestras) = equipos A y B; el resto =
   "otro" (árbitro, porteros, ruido) → prototipos = media de las features
   de cada grupo.

3. `predict_color(feat)`: distancia euclídea a los prototipos → 'A' / 'B'
   / 'otro'.

Nota de alcance: el color agregado POR IDENTIDAD (media de muchos recortes)
sí clasifica equipos; como discriminador de identidad individual tracklet a
tracklet quedó medido como no-útil (ver docs/experimentos_tracking.md).
"""

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)


@dataclass
class ParametrosClasificadorColor:
    """Parámetros del clasificador (valores validados como defaults)."""

    # Banda del pecho dentro del recorte del jugador (fracciones del alto/ancho)
    torso_alto: tuple[float, float] = (0.12, 0.45)
    torso_ancho: tuple[float, float] = (0.15, 0.85)
    # Máscara anti-verde HSV: los píxeles dentro de estos rangos se descartan
    verde_h: tuple[int, int] = (35, 85)
    verde_s_min: int = 40
    verde_v_min: int = 40
    # Histograma HS
    bins_h: int = 16
    bins_s: int = 16
    # Clustering
    k_clusters: int = 8
    # Barrido del umbral de fusión jerárquica
    umbral_min: float = 0.5
    umbral_max: float = 1.3
    umbral_paso: float = 0.05
    semilla: int = 0

    @classmethod
    def desde_dict(cls, d: dict) -> "ParametrosClasificadorColor":
        d = dict(d)
        for clave in ("torso_alto", "torso_ancho", "verde_h"):
            if clave in d:
                d[clave] = tuple(d[clave])
        return cls(**d)


@dataclass
class _Prototipos:
    """Prototipos aprendidos en fit: feature media de A, B y 'otro'."""

    a: np.ndarray
    b: np.ndarray
    otro: np.ndarray | None = None
    etiquetas: list[str] = field(default_factory=lambda: ["A", "B", "otro"])


def extraer_color_torso(
    crop: np.ndarray, params: ParametrosClasificadorColor | None = None
) -> np.ndarray:
    """Feature de color del torso de un recorte BGR de jugador.

    ÚNICA función de extracción del repo (la usan el clasificador y el
    modo full del procesador): banda del pecho + máscara anti-verde HSV +
    histograma HS 16×16 **normalizado en L2** (256 floats). Si tras la
    máscara no queda ningún píxel, devuelve ceros.

    ⚠️ NORMALIZACIÓN L2, no por suma (bug de producción del 12-jul-2026):
    el extractor validado del notebook usaba cv2.normalize, cuyo default
    es NORM_L2 (verificado forense: el 96 % de las features del caché de
    referencia tienen ||f||₂ = 1.0 exacto, el 4 % restante son ceros).
    TODOS los umbrales calibrados del sistema viven en esa escala: el
    barrido de fusión del fit (0.5-1.3), el veto de color (1.2, con
    mediana de pares legítimos 0.90 y p90 1.16) y las firmas de la
    salvaguarda. Con normalización por suma las distancias se encogen y
    la fusión jerárquica colapsa en un solo equipo (reproducido: mismas
    features en L1 → A=2548/B=44 con umbral 0.50, idéntico al fallo de
    Colab).
    """
    p = params or ParametrosClasificadorColor()
    alto, ancho = crop.shape[:2]
    y0, y1 = int(alto * p.torso_alto[0]), int(alto * p.torso_alto[1])
    x0, x1 = int(ancho * p.torso_ancho[0]), int(ancho * p.torso_ancho[1])
    banda = crop[y0:y1, x0:x1]
    if banda.size == 0:
        return np.zeros(p.bins_h * p.bins_s)

    hsv = cv2.cvtColor(banda, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    es_verde = (
        (h >= p.verde_h[0])
        & (h <= p.verde_h[1])
        & (s >= p.verde_s_min)
        & (v >= p.verde_v_min)
    )
    validos = hsv[~es_verde]
    if len(validos) == 0:
        return np.zeros(p.bins_h * p.bins_s)

    hist, _, _ = np.histogram2d(
        validos[:, 0],
        validos[:, 1],
        bins=[p.bins_h, p.bins_s],
        range=[[0, 180], [0, 256]],
    )
    hist = hist.flatten()
    norma = np.linalg.norm(hist)
    return hist / norma if norma > 0 else hist


def _solo_hs(feature):
    """El bloque HS del pecho, sea la feature v1 o v2.

    TODOS los umbrales del sistema están calibrados en la escala de la v1
    (fusión del fit 0,5-1,3, veto de color 1,2, firmas). Una feature v2 es
    más larga, así que cualquier distancia calculada sobre el vector
    entero vive en OTRA escala y esos umbrales dejan de significar lo que
    dicen — en silencio, que es lo peligroso. Recortando aquí, un caché
    v2 se comporta EXACTAMENTE como uno v1, y usar los bloques nuevos
    pasa a ser una decisión explícita en vez de un efecto colateral.
    """
    from src.team_classification.feature_v2 import parte_camiseta_hs

    return parte_camiseta_hs(np.asarray(feature))


def color_dominante(feature: np.ndarray, params=None) -> tuple[int, int, int]:
    """Color RGB representativo de una feature de torso (histograma HS).

    La feature es un histograma 2D de tono×saturación normalizado. El bin
    con más masa es el color que más veces aparece en el pecho de esos
    jugadores: convertido a RGB, es literalmente el color de la camiseta.

    Sirve para que el replay pinte a cada equipo de SU color (naranja y
    blanco, si eso es lo que llevan) en vez de un azul y un rojo fijos que
    obligan al entrenador a mirar la leyenda.

    El valor (brillo) no está en la feature —el histograma es solo H y S—
    así que se fija alto: interesa un color legible en pantalla, no
    reproducir la iluminación del campo.
    """
    p = params or ParametrosClasificadorColor()
    hist = _solo_hs(feature).astype(np.float64).reshape(p.bins_h, p.bins_s)
    if not np.isfinite(hist).any() or hist.sum() <= 0:
        return (128, 128, 128)
    bin_h, bin_s = np.unravel_index(int(np.argmax(hist)), hist.shape)
    # Centro del bin, en la escala HSV de OpenCV (H 0-179, S 0-255)
    h = (bin_h + 0.5) * 180.0 / p.bins_h
    sat = (bin_s + 0.5) * 256.0 / p.bins_s
    # Saturación mínima para que un blanco/gris no salga negro en pantalla
    hsv = np.uint8([[[h, min(sat, 255), 235]]])
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
    return (int(bgr[2]), int(bgr[1]), int(bgr[0]))


class TeamClassifierColor:
    """Clasificador de equipos por color, 100 % automático (sin etiquetas)."""

    def __init__(self, params: ParametrosClasificadorColor | None = None):
        self.params = params or ParametrosClasificadorColor()
        self._prototipos: _Prototipos | None = None

    # ------------------------------------------------------------ features
    def _color_torso(self, crop: np.ndarray) -> np.ndarray:
        """Feature de color del torso (delega en extraer_color_torso)."""
        return extraer_color_torso(crop, self.params)

    # ----------------------------------------------------------------- fit
    def fit(self, crops: list[np.ndarray]) -> None:
        """Entrena a partir de recortes BGR de jugadores (extrae features)."""
        features = np.array([self._color_torso(c) for c in crops])
        self.fit_features(features)

    def fit_features(self, features: np.ndarray) -> None:
        """Entrena a partir de features ya extraídas (p. ej. caché de Colab).

        KMeans k=8 → fusión jerárquica con umbral auto → 2 meta-grupos más
        grandes por tamaño = equipos → prototipos.
        """
        p = self.params
        features = np.array([_solo_hs(f) for f in np.asarray(features)])
        if len(features) < p.k_clusters:
            raise ValueError(
                f"Se necesitan al menos {p.k_clusters} features para entrenar "
                f"(hay {len(features)})."
            )

        kmeans = KMeans(n_clusters=p.k_clusters, n_init=10, random_state=p.semilla)
        asignacion = kmeans.fit_predict(features)

        # Fusión jerárquica de los CENTROS de los k clusters
        enlaces = linkage(kmeans.cluster_centers_, method="average")
        umbral = self._umbral_auto(enlaces, asignacion)
        meta = fcluster(enlaces, t=umbral, criterion="distance")
        if len(np.unique(meta)) < 2:
            # Salvaguarda: si el umbral fusiona todo en un grupo (features
            # muy compactas), forzamos exactamente 2 meta-grupos.
            meta = fcluster(enlaces, t=2, criterion="maxclust")

        # Tamaño de cada meta-grupo = nº de muestras de sus clusters
        tamanos = {
            g: int(np.isin(asignacion, np.where(meta == g)[0]).sum())
            for g in np.unique(meta)
        }
        orden = sorted(tamanos, key=tamanos.get, reverse=True)
        grupo_a, grupo_b = orden[0], orden[1]

        mascara_a = np.isin(asignacion, np.where(meta == grupo_a)[0])
        mascara_b = np.isin(asignacion, np.where(meta == grupo_b)[0])
        mascara_otro = ~(mascara_a | mascara_b)
        self._prototipos = _Prototipos(
            a=features[mascara_a].mean(axis=0),
            b=features[mascara_b].mean(axis=0),
            otro=features[mascara_otro].mean(axis=0) if mascara_otro.any() else None,
        )
        logger.info(
            "Clasificador entrenado: umbral fusión=%.2f, tamaños A=%d B=%d otro=%d",
            umbral,
            int(mascara_a.sum()),
            int(mascara_b.sum()),
            int(mascara_otro.sum()),
        )

    def _umbral_auto(self, enlaces: np.ndarray, asignacion: np.ndarray) -> float:
        """Elige el umbral de fusión: maximiza equilibrio-top2 × separación-del-3º.

        - equilibrio-top2 = tamaño del 2º meta-grupo / tamaño del 1º
          (1.0 = dos equipos perfectamente equilibrados).
        - separación-del-3º = 1 − tamaño del 3º / tamaño del 2º
          (1.0 = no hay tercer grupo comparable; los equipos destacan).

        Solo se consideran umbrales que dejen al menos 2 meta-grupos.
        """
        p = self.params
        mejor_umbral, mejor_puntuacion = None, -1.0
        for umbral in np.arange(p.umbral_min, p.umbral_max + 1e-9, p.umbral_paso):
            meta = fcluster(enlaces, t=umbral, criterion="distance")
            if len(np.unique(meta)) < 2:
                continue
            tamanos = sorted(
                (
                    int(np.isin(asignacion, np.where(meta == g)[0]).sum())
                    for g in np.unique(meta)
                ),
                reverse=True,
            )
            n1, n2 = tamanos[0], tamanos[1]
            n3 = tamanos[2] if len(tamanos) > 2 else 0
            equilibrio = n2 / n1 if n1 else 0.0
            separacion = 1.0 - (n3 / n2 if n2 else 1.0)
            puntuacion = equilibrio * separacion
            if puntuacion > mejor_puntuacion:
                mejor_puntuacion, mejor_umbral = puntuacion, float(umbral)
        if mejor_umbral is None:
            # Todos los umbrales fusionan en 1 grupo: usar el mínimo del barrido
            mejor_umbral = p.umbral_min
        return mejor_umbral

    def colores_equipos(self) -> dict[str, str]:
        """{'A': '#rrggbb', 'B': '#rrggbb'} de los prototipos aprendidos.

        Es el color con el que el replay pinta cada equipo. Si el
        clasificador no está entrenado, devuelve {} y quien llame usa sus
        colores por defecto.
        """
        if self._prototipos is None:
            return {}
        salida = {}
        for etiqueta, proto in (("A", self._prototipos.a), ("B", self._prototipos.b)):
            r, g, b = color_dominante(proto, self.params)
            salida[etiqueta] = f"#{r:02x}{g:02x}{b:02x}"
        logger.info("Colores de equipo derivados del clasificador: %s", salida)
        return salida

    # ------------------------------------------------------------- predict
    def predict_color(self, feat: np.ndarray, dist_max: float | None = None) -> str:
        """Clasifica una feature (p. ej. color medio de una identidad).

        `dist_max` es la distancia máxima admitida a AMBOS prototipos. Con
        solo dos cajones, un árbitro de amarillo o un entrenador en
        chándal caen forzosamente en el menos malo — en el benjamín el
        árbitro salía como equipo B en los tres frames revisados. Si la
        feature está lejos de los dos, la respuesta honesta es 'otro'.

        El umbral es RELATIVO a la separación entre los dos prototipos,
        no absoluto. Medirlo enseñó por qué hace falta: calibrado a mano
        con el caché del benjamín (jugadores p90 0,656 frente a staff p10
        0,712, casi sin solape) el valor 0,70 parecía perfecto, y llevado
        tal cual a Villaviciosa hundía la accuracy de equipos de 0,718 a
        0,482. Cada partido tiene su propia escala de color, así que un
        número en unidades de histograma no viaja. La distancia entre A y
        B sí es una escala natural del problema: "lejos de los dos"
        significa lejos COMPARADO con lo que separa a los dos equipos.

        Los porteros superan cualquier umbral razonable —visten distinto,
        que es justo el problema— pero no importa: la regla de área los
        reetiqueta después por su posición.
        """
        if self._prototipos is None:
            raise RuntimeError(
                "El clasificador no está entrenado: llama a fit primero."
            )
        feat = _solo_hs(feat)
        pr = self._prototipos
        candidatos = [("A", pr.a), ("B", pr.b)]
        if pr.otro is not None:
            candidatos.append(("otro", pr.otro))
        distancias = [np.linalg.norm(feat - proto) for _, proto in candidatos]
        mejor = int(np.argmin(distancias))
        if dist_max is not None:
            separacion = float(np.linalg.norm(pr.a - pr.b))
            if separacion > 0 and distancias[mejor] > dist_max * separacion:
                return "otro"
        return candidatos[mejor][0]
