"""Modelo PARAMETRIZABLE de campo: geometría, marcas y puntos de calibración.

Hasta ahora el sistema daba por supuesto un campo de F11 de 100×64 con las
marcas del reglamento grande, hardcodeadas en las herramientas de
calibración. Este módulo saca esa geometría a un modelo con datos, para
que un campo nuevo (otro tamaño, otra modalidad) sea una configuración y
no un cambio de código.

Convención de ejes (la misma de todo el repo):
    x = de portería a portería (0 = línea de fondo izquierda, largo = derecha)
    y = de banda a banda       (0 = una banda, ancho = la otra)

Qué es REGLAMENTO y qué es MEDIDA:
- Las marcas interiores (área, penalti, círculo, portería) están fijadas
  por el reglamento de la modalidad y NO dependen del tamaño del campo.
  Son las que permiten auditar la escala (scripts/auditar_escala.py).
- El largo y el ancho SÍ varían de campo a campo y suelen ser una
  estimación hasta que se miden. Por eso van en config.

⚠️ `src/campo.py` sigue siendo la fuente de verdad de las dimensiones que
usa el pipeline de producción (Villaviciosa, F11 100×64). Este módulo NO
las cambia: describe modelos de campo para calibrar y auditar.
"""

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

# Punto de calibración: (nombre, (x_m, y_m))
PuntoCampo = tuple[str, tuple[float, float]]


@dataclass(frozen=True)
class MarcasReglamentarias:
    """Medidas interiores fijadas por el reglamento de la modalidad.

    No dependen del tamaño del campo: son las referencias con las que se
    audita si nuestro espacio métrico está bien escalado.
    """

    area_ancho: float  # ancho TOTAL del área grande (perpendicular al eje x)
    area_profundidad: float  # cuánto entra el área desde la línea de fondo
    penalti: float  # distancia del punto de penalti a la línea de fondo
    circulo_radio: float  # radio del círculo central
    porteria_ancho: float  # distancia entre postes


# Reglamento F11 (IFAB): área 40.32 x 16.5, penalti a 11, círculo r=9.15,
# portería de 7.32 m.
MARCAS_F11 = MarcasReglamentarias(
    area_ancho=40.32,
    area_profundidad=16.5,
    penalti=11.0,
    circulo_radio=9.15,
    porteria_ancho=7.32,
)

# Reglamento F7 (Federación de Fútbol de Madrid): área 26 x 12, penalti a
# 9, círculo r=6, portería de 6 m.
MARCAS_F7 = MarcasReglamentarias(
    area_ancho=26.0,
    area_profundidad=12.0,
    penalti=9.0,
    circulo_radio=6.0,
    porteria_ancho=6.0,
)


@dataclass(frozen=True)
class ModeloCampo:
    """Un campo concreto: sus dimensiones + las marcas de su reglamento."""

    nombre: str
    largo: float
    ancho: float
    marcas: MarcasReglamentarias

    # ─────────────────────────── geometría ───────────────────────────

    @property
    def centro(self) -> tuple[float, float]:
        return (self.largo / 2, self.ancho / 2)

    def puntos_clicables(self) -> list[PuntoCampo]:
        """Puntos de calibración DERIVADOS del modelo, en orden de clic.

        El orden va de lo más fiable y visible a lo más difícil: primero el
        centro y el círculo, luego medio campo y penaltis, después las
        áreas y por último las esquinas y postes (a menudo tapados o en el
        borde del encuadre). En la herramienta se puede saltar cualquiera.
        """
        largo, ancho = self.largo, self.ancho
        m = self.marcas
        cy = ancho / 2
        media_area = m.area_ancho / 2
        media_porteria = m.porteria_ancho / 2
        x_area_izq = m.area_profundidad
        x_area_der = largo - m.area_profundidad

        puntos: list[PuntoCampo] = [
            # Centro y círculo central (4 puntos: cortes con medio campo y
            # con el eje largo)
            ("center", (largo / 2, cy)),
            ("circulo_top", (largo / 2, cy + m.circulo_radio)),
            ("circulo_bottom", (largo / 2, cy - m.circulo_radio)),
            ("circulo_left", (largo / 2 - m.circulo_radio, cy)),
            ("circulo_right", (largo / 2 + m.circulo_radio, cy)),
            # Medio campo contra las bandas
            ("halfway_top", (largo / 2, ancho)),
            ("halfway_bottom", (largo / 2, 0.0)),
            # Puntos de penalti
            ("penalty_left", (m.penalti, cy)),
            ("penalty_right", (largo - m.penalti, cy)),
            # Esquinas INTERIORES del área (donde el área "dobla")
            ("box_left_top", (x_area_izq, cy + media_area)),
            ("box_left_bottom", (x_area_izq, cy - media_area)),
            ("box_right_top", (x_area_der, cy + media_area)),
            ("box_right_bottom", (x_area_der, cy - media_area)),
            # Cortes del área con la línea de FONDO
            ("box_left_top_line", (0.0, cy + media_area)),
            ("box_left_bottom_line", (0.0, cy - media_area)),
            ("box_right_top_line", (largo, cy + media_area)),
            ("box_right_bottom_line", (largo, cy - media_area)),
            # Postes de portería (muy visibles con la cámara tras portería)
            ("goal_left_top", (0.0, cy + media_porteria)),
            ("goal_left_bottom", (0.0, cy - media_porteria)),
            ("goal_right_top", (largo, cy + media_porteria)),
            ("goal_right_bottom", (largo, cy - media_porteria)),
            # Esquinas del campo
            ("corner_top_left", (0.0, ancho)),
            ("corner_bottom_left", (0.0, 0.0)),
            ("corner_top_right", (largo, ancho)),
            ("corner_bottom_right", (largo, 0.0)),
        ]
        return puntos

    def lineas(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Segmentos de las líneas del campo, para la validación visual."""
        largo, ancho = self.largo, self.ancho
        m = self.marcas
        cy = ancho / 2
        media_area = m.area_ancho / 2
        y_lo, y_hi = cy - media_area, cy + media_area
        x_izq, x_der = m.area_profundidad, largo - m.area_profundidad
        return [
            # Perímetro
            ((0.0, 0.0), (largo, 0.0)),
            ((largo, 0.0), (largo, ancho)),
            ((largo, ancho), (0.0, ancho)),
            ((0.0, ancho), (0.0, 0.0)),
            # Medio campo
            ((largo / 2, 0.0), (largo / 2, ancho)),
            # Área izquierda
            ((0.0, y_lo), (x_izq, y_lo)),
            ((x_izq, y_lo), (x_izq, y_hi)),
            ((x_izq, y_hi), (0.0, y_hi)),
            # Área derecha
            ((largo, y_lo), (x_der, y_lo)),
            ((x_der, y_lo), (x_der, y_hi)),
            ((x_der, y_hi), (largo, y_hi)),
        ]

    def circulo(self, n_puntos: int = 40) -> list[tuple[float, float]]:
        """Polilínea del círculo central, para la validación visual."""
        import numpy as np

        cx, cy = self.centro
        r = self.marcas.circulo_radio
        return [
            (cx + r * float(np.cos(a)), cy + r * float(np.sin(a)))
            for a in np.linspace(0, 2 * np.pi, n_puntos)
        ]

    def con_dimensiones(self, largo: float, ancho: float) -> "ModeloCampo":
        """Copia del modelo con otras medidas (las marcas no cambian)."""
        return replace(self, largo=largo, ancho=ancho)


# ─────────────────────────── modelos predefinidos ───────────────────────────

# F11 de Villaviciosa: el modelo con el que está calibrada la homografía en
# producción. NO cambiar sin recalibrar (ver src/campo.py).
MODELO_F11 = ModeloCampo(nombre="f11", largo=100.0, ancho=64.0, marcas=MARCAS_F11)

# F7 (benjamines): 62x40 es la ESTIMACIÓN de partida, pendiente de derivar
# de las marcas reglamentarias con scripts/auditar_escala.py.
MODELO_F7 = ModeloCampo(nombre="f7", largo=62.0, ancho=40.0, marcas=MARCAS_F7)

MODELOS = {"f11": MODELO_F11, "f7": MODELO_F7}


def cargar_modelo(
    nombre: str | None = None, config: str | Path | None = None
) -> ModeloCampo:
    """Devuelve un modelo por nombre ('f11'/'f7') o desde un YAML.

    El YAML permite ajustar las medidas de un campo concreto sin tocar
    código:

        campo:
          nombre: benjamines
          tipo: f7          # de qué reglamento son las marcas
          largo: 62.0
          ancho: 40.0
          marcas:           # opcional: solo si el campo es atípico
            area_ancho: 26.0
    """
    if config is not None:
        with open(config) as f:
            cfg = yaml.safe_load(f)["campo"]
        base = MODELOS[cfg.get("tipo", "f7")]
        marcas = base.marcas
        if "marcas" in cfg:
            marcas = replace(marcas, **cfg["marcas"])
        return ModeloCampo(
            nombre=cfg.get("nombre", base.nombre),
            largo=float(cfg["largo"]),
            ancho=float(cfg["ancho"]),
            marcas=marcas,
        )
    if nombre is None:
        raise ValueError("Indica un modelo por nombre o un config YAML.")
    if nombre not in MODELOS:
        raise ValueError(f"Modelo desconocido: {nombre!r} (usa {sorted(MODELOS)})")
    return MODELOS[nombre]
