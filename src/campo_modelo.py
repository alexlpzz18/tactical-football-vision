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
    # Área pequeña: existe en F11, no en el F7 de Madrid (None = no dibujar)
    area_pequena_ancho: float | None = None
    area_pequena_profundidad: float | None = None


# Reglamento F11 (IFAB): área 40.32 x 16.5, penalti a 11, círculo r=9.15,
# portería de 7.32 m.
MARCAS_F11 = MarcasReglamentarias(
    area_ancho=40.32,
    area_profundidad=16.5,
    penalti=11.0,
    circulo_radio=9.15,
    porteria_ancho=7.32,
    area_pequena_ancho=18.32,
    area_pequena_profundidad=5.5,
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

    def geometria_dibujo(self) -> dict:
        """Todo lo que hace falta para PINTAR el campo, en primitivas.

        Sale del modelo, no de constantes: así el replay y el informe
        dibujan el campo del partido que están mostrando (un círculo de
        9,15 m sobre un campo de F7 delata que algo no cuadra) y el mismo
        código sirve para las dos modalidades.

        El diccionario es serializable a JSON tal cual, porque el replay
        lo embebe en su HTML y lo dibuja en canvas.

        Returns:
            {
              "largo", "ancho",
              "lineas":   [[[x1,y1],[x2,y2]], ...]   segmentos rectos
              "circulos": [{"cx","cy","r"}]          círculo central
              "puntos":   [[x,y], ...]               centro y penaltis
              "arcos":    [{"cx","cy","r","desde","hasta"}]  frontal del área
              "porterias":[{"x","y","ancho","alto"}] rectángulos de portería
            }
        """
        import numpy as np

        largo, ancho = self.largo, self.ancho
        m = self.marcas
        cy = ancho / 2

        lineas = [[list(p1), list(p2)] for p1, p2 in self.lineas()]
        puntos = [[largo / 2, cy]]
        arcos = []
        porterias = []
        profundidad_porteria = min(2.0, largo * 0.03)

        for x0, direccion in ((0.0, 1), (largo, -1)):
            # Área pequeña (si la modalidad la tiene)
            if m.area_pequena_ancho and m.area_pequena_profundidad:
                mitad = m.area_pequena_ancho / 2
                x1 = x0 + direccion * m.area_pequena_profundidad
                lineas.extend(
                    [
                        [[x0, cy - mitad], [x1, cy - mitad]],
                        [[x1, cy - mitad], [x1, cy + mitad]],
                        [[x1, cy + mitad], [x0, cy + mitad]],
                    ]
                )
            # Punto de penalti
            x_pen = x0 + direccion * m.penalti
            puntos.append([x_pen, cy])
            # Frontal del área: el trozo del círculo del penalti que sobresale
            if m.penalti + m.circulo_radio > m.area_profundidad:
                dentro = (m.area_profundidad - m.penalti) / m.circulo_radio
                media_apertura = float(np.arccos(max(-1.0, min(1.0, dentro))))
                centro_angulo = 0.0 if direccion == 1 else float(np.pi)
                arcos.append(
                    {
                        "cx": x_pen,
                        "cy": cy,
                        "r": m.circulo_radio,
                        "desde": centro_angulo - media_apertura,
                        "hasta": centro_angulo + media_apertura,
                    }
                )
            # Portería (hacia fuera del campo)
            mitad_porteria = m.porteria_ancho / 2
            porterias.append(
                {
                    "x": min(x0, x0 - direccion * profundidad_porteria),
                    "y": cy - mitad_porteria,
                    "ancho": profundidad_porteria,
                    "alto": m.porteria_ancho,
                }
            )

        return {
            "largo": largo,
            "ancho": ancho,
            "lineas": lineas,
            "circulos": [{"cx": largo / 2, "cy": cy, "r": m.circulo_radio}],
            "puntos": puntos,
            "arcos": arcos,
            "porterias": porterias,
        }

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

    def areas_porteria(
        self, margen: float = 0.0
    ) -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
        """Rectángulos de las dos áreas de penalti, DERIVADOS del modelo.

        Los usa la regla de porteros: una identidad cuya posición mediana
        cae dentro de un área es el portero de ese lado. Antes estos
        números estaban a mano en el YAML (16,5 / 88,5 / 20-55 del F11),
        que en un campo de 62 m no significan nada.

        Args:
            margen: metros de holgura alrededor del área. Un portero sale a
                achicar, y la mediana de su posición puede quedar algo
                fuera del área dibujada.

        Returns:
            {"bajo": ((x_min, x_max), (y_min, y_max)), "alto": (...)},
            donde "bajo" es el área del lado x pequeño.
        """
        m = self.marcas
        cy = self.ancho / 2
        media_area = m.area_ancho / 2
        rango_y = (cy - media_area - margen, cy + media_area + margen)
        return {
            "bajo": ((-margen, m.area_profundidad + margen), rango_y),
            "alto": (
                (self.largo - m.area_profundidad - margen, self.largo + margen),
                rango_y,
            ),
        }


@dataclass(frozen=True)
class EjeProfundidad:
    """De qué eje del campo se aleja la cámara.

    No es un detalle: casi todo el sistema trata la PROFUNDIDAD de forma
    especial (el color solo es señal de cerca, el error de localización
    crece con la distancia, los umbrales de asociación dependen de ella).
    Con la cámara en la banda —Villaviciosa— la profundidad es el eje
    ANCHO; con la cámara detrás de una portería —benjamines— es el eje
    LARGO. Dar por supuesto el eje equivocado hace que "quedarse con los
    recortes cercanos" seleccione por una coordenada que no tiene nada
    que ver con la distancia, y el clasificador de color colapsa (es el
    mismo fallo que tumbó el fit en producción en julio).

    Attributes:
        eje: 'x' (largo) o 'y' (ancho).
        creciente: True si alejarse de la cámara aumenta la coordenada.
    """

    eje: str = "y"
    creciente: bool = True

    def de(self, pos, modelo: "ModeloCampo") -> float:
        """Distancia (m) del punto a la cámara, medida sobre su eje."""
        valor = float(pos[0] if self.eje == "x" else pos[1])
        if self.creciente:
            return valor
        limite = modelo.largo if self.eje == "x" else modelo.ancho
        return limite - valor

    @classmethod
    def desde_dict(cls, d: dict | None) -> "EjeProfundidad":
        if not d:
            return cls()
        eje = d.get("eje", "y")
        if eje not in ("x", "y"):
            raise ValueError(f"eje de profundidad inválido: {eje!r} (usa 'x' o 'y')")
        return cls(eje=eje, creciente=bool(d.get("creciente", True)))


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
