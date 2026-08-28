"""Tests de la selección de frames del detector de balón.

Todos salen de un bug real que costó una sesión de GPU: el script
procesaba 0 frames, escribía un caché vacío, imprimía "✓ Caché de balón"
y reventaba con una división por cero. La causa era que `cap.set` daba el
salto por bueno y dejaba el lector inservible — en Colab, con un vídeo
que en local se lee sin problema.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from detectar_balon import iter_frames  # noqa: E402


class CapFalso:
    """VideoCapture de mentira, con el fallo de Colab reproducible."""

    def __init__(self, n_frames=200, muere_tras_saltar=False):
        self.n = n_frames
        self.pos = 0
        self.muere = muere_tras_saltar
        self.roto = False

    def set(self, _prop, valor):
        self.pos = int(valor)
        # El fallo: el seek se da por bueno y el lector queda inservible.
        # Rebobinar a 0 lo revive, que es justo la salida de emergencia.
        self.roto = self.muere and valor > 0
        return True

    def get(self, _prop):
        return float(self.pos)

    def grab(self):
        if self.pos >= self.n:
            return False
        self.pos += 1
        return True

    def read(self):
        if self.roto or self.pos >= self.n:
            return False, None
        f = f"frame{self.pos}"
        self.pos += 1
        return True, f


def test_lee_el_tramo_pedido_con_su_muestreo():
    frames = list(iter_frames(CapFalso(200), 100, 120, 2))
    assert [i for i, _f in frames] == [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]


def test_se_recupera_si_el_salto_deja_el_lector_muerto():
    """EL bug. Sin la salida de emergencia, esto devuelve 0 frames — que
    es exactamente lo que pasó en Colab."""
    cap = CapFalso(200, muere_tras_saltar=True)
    frames = list(iter_frames(cap, 100, 110, 2, total=200))
    assert len(frames) == 5, "debe rebobinar y decodificar, no rendirse"
    assert frames[0][0] == 100


def test_sin_recuperacion_posible_falla_con_diagnostico():
    """Un vídeo truncado no puede dar frames: hay que decirlo, no
    devolver una lista vacía que el llamante interpretará como 'no hay
    balón en ningún sitio'."""
    cap = CapFalso(50)  # el tramo pedido cae fuera
    with pytest.raises(SystemExit, match="no se puede leer el frame"):
        list(iter_frames(cap, 100, 120, 2, total=50))


def test_el_muestreo_impar_no_pierde_el_primer_frame():
    """frame_ini impar con sample par: el primero que cuadra es el
    siguiente, no ninguno."""
    frames = list(iter_frames(CapFalso(200), 101, 110, 2))
    assert [i for i, _f in frames] == [102, 104, 106, 108]


# ── Checkpoint del detector de balón (28-ago-2026) ───────────────────
#
# Este script dio dos sustos: procesar 0 frames en silencio y un
# "✓ Caché de balón" sobre un archivo vacío. Quedaba el peor: el volcado
# estaba solo al final, así que una caída en el minuto 35 de 40 lo perdía
# todo. Sobre la parte entera son 17.983 frames de GPU.


def _firma():
    return {
        "video": "v.mp4",
        "modelo": "m.pt",
        "confianza": 0.35,
        "imgsz": 1280,
        "sample_every": 2,
        "sahi": {},
        "k1": 0.0,
        "k2": 0.0,
        "tramo": {},
    }


def _guardar(ruta, firma, completo, n=10):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from detectar_balon import _volcar

    _volcar(
        ruta,
        {
            "cache": [
                {"frame_idx": i * 2, "t": i * 0.066, "dets": []} for i in range(n)
            ],
            "fps": 29.97,
            "sample": 2,
            "wh": (1920, 1080),
            "modelo": "m.pt",
            "confianza": 0.35,
            "completo": completo,
            "firma": firma,
        },
    )


def test_el_balon_reanuda_un_checkpoint_compatible(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from detectar_balon import _reanudar_balon

    ruta = tmp_path / "b.pkl"
    _guardar(ruta, _firma(), completo=False)
    assert len(_reanudar_balon(ruta, _firma()) or []) == 10


def test_el_balon_NO_reanuda_con_otra_confianza(tmp_path):
    """La confianza cambia qué se detecta: mezclarlas sería un caché falso."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from detectar_balon import _reanudar_balon

    ruta = tmp_path / "b.pkl"
    _guardar(ruta, _firma(), completo=False)
    otra = {**_firma(), "confianza": 0.50}
    assert _reanudar_balon(ruta, otra) is None


def test_el_balon_NO_reanuda_un_cache_completo(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from detectar_balon import _reanudar_balon

    ruta = tmp_path / "b.pkl"
    _guardar(ruta, _firma(), completo=True)
    assert _reanudar_balon(ruta, _firma()) is None


def test_un_volcado_de_balon_fallido_no_pierde_el_cache_bueno(tmp_path):
    import pickle
    import sys
    from pathlib import Path

    import pytest as _pytest

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from detectar_balon import _volcar

    ruta = tmp_path / "b.pkl"
    _guardar(ruta, _firma(), completo=False, n=7)
    with _pytest.raises(Exception):
        _volcar(ruta, lambda x: x)  # no serializable
    assert list(tmp_path.glob("*.tmp")) == [], "quedó un temporal colgado"
    with open(ruta, "rb") as f:
        assert len(pickle.load(f)["cache"]) == 7


def test_el_balon_RELEE_el_fichero_antes_del_visto_bueno():
    """Contar lo enviado al disco no prueba que esté en el disco."""
    from pathlib import Path

    codigo = (
        Path(__file__).resolve().parent.parent / "scripts" / "detectar_balon.py"
    ).read_text()
    assert "releido = pickle.load(f)" in codigo
    assert "salió INCOMPLETO" in codigo
