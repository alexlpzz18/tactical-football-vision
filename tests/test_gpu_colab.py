"""Guardas del orquestador de GPU (src/cloud/trabajo_gpu.py), sin gastar ni una unidad de cómputo.

Lo que se protege es lo que cuesta dinero si falla:
- la máquina se APAGA siempre, también cuando algo revienta a mitad o se para por presupuesto;
- no se enciende nada si el commit no está en GitHub o si faltan entradas;
- la proyección de coste usa el ritmo real y para ANTES de pasarse del tope;
- el interruptor de hombre muerto de la máquina solo actúa sin trabajo Y sin Mac.
"""

import hashlib
import importlib.util
import pickle
import subprocess
from pathlib import Path

import pytest

from src.cloud.colab_cli import ColabCLI, ErrorColab, Saldo, leer_saldo
from src.cloud.trabajo_gpu import (
    Orquestador,
    Parte,
    Trabajo,
    TrabajoAbortado,
    leer_progreso,
    proyectar_cu,
)

R = Path(__file__).resolve().parent.parent

CFG = {
    "maquina": {"gpu": "T4", "prefijo_sesion": "tfv"},
    "repo": {"url": "https://example.invalid/repo.git", "requisitos": "req.txt"},
    "presupuesto": {"max_cu": 40, "reserva_cu": 10},
    "vigilancia": {
        "sondeo_s": 120,
        "respaldo_cada_s": 10**9,
        "sin_progreso_s": 1500,
        "huerfana_tras_s": 3600,
    },
    "rutas_remotas": {"repo": "/r", "datos": "/d", "salida": "/s"},
}


def _log(hechos, total=1000, ms=500):
    return f"INFO {hechos}/{total} frames ({100 * hechos // total} %) · {ms} ms/frame · ok\n"


class FalsaCLI:
    """Imita la CLI: guarda lo que «está» en la máquina y responde a los sondeos con un guion."""

    def __init__(self, guion, saldo=100.0, tarifa=1.5):
        self.guion = list(guion)  # una respuesta de sondeo por llamada: (vivo, log)
        self.llamadas, self.remoto = [], {}
        self._saldo, self._tarifa = saldo, tarifa

    def saldo(self):
        self.llamadas.append("usage")
        return Saldo(self._saldo, self._tarifa, 0)

    def nueva(self, sesion, gpu):
        self.llamadas.append(f"new {sesion} {gpu}")

    def parar(self, sesion):
        self.llamadas.append(f"stop {sesion}")

    def subir(self, sesion, local, remoto):
        self.llamadas.append(f"upload {remoto}")
        self.remoto[remoto] = Path(local).read_bytes()

    def bajar(self, sesion, remoto, local):
        self.llamadas.append(f"download {remoto}")
        datos = self.remoto.get(remoto) or pickle.dumps({"completo": True, "cache": []})
        self.remoto[remoto] = datos
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(datos)

    def python(self, sesion, codigo, inactividad_s=600):
        if "sha256sum" in codigo:
            ruta = codigo.split("sha256sum ")[1].split("'")[0].split('"')[0].strip()
            return hashlib.sha256(self.remoto[ruta]).hexdigest() + "  x\n"
        if "latido" in codigo and "json.dumps" in codigo:
            vivo, log = self.guion.pop(0)
            if isinstance(vivo, Exception):
                raise vivo
            if "✓ deteccion" in log:  # el procesador termina: su caché queda completo
                for ruta in [r for r in self.remoto if r.startswith("/s/cache_")]:
                    self.remoto[ruta] = pickle.dumps({"completo": True, "cache": []})
            import json

            return json.dumps({"vivo": vivo, "log": log}) + "\n"
        return ""


def _git_ok(cmd, **kw):
    salida = {"rev-parse": "abc123\n", "fetch": "", "branch": "  origin/rama\n"}
    clave = next(k for k in salida if k in cmd)
    return subprocess.CompletedProcess(cmd, 0, salida[clave], "")


def _git_sin_subir(cmd, **kw):
    r = _git_ok(cmd)
    return r if "branch" not in cmd else subprocess.CompletedProcess(cmd, 0, "", "")


def _trabajo(tmp_path, n_partes=1):
    partes = []
    for i in range(1, n_partes + 1):
        v = tmp_path / f"p{i}.mp4"
        v.write_bytes(b"video" * 10 + bytes([i]))
        partes.append(Parte(f"x_p{i}", v))
    raiz = tmp_path
    (raiz / "models").mkdir(exist_ok=True)
    modelo = raiz / "models/best.pt"
    modelo.write_bytes(b"pesos")
    return Trabajo(
        "x", partes, "scripts/s.py", ["--imagen", "original"], modelo, tmp_path / "out",
        {p.nombre: 1000 for p in partes},
    )  # fmt: skip


def _orq(cli, tmp_path, trabajo, git=_git_ok):
    reloj = iter(range(0, 10**9, 60))
    return Orquestador(
        cli, CFG, trabajo, tmp_path, dormir=lambda s: None,
        reloj=lambda: next(reloj), git=git,
    )  # fmt: skip


# ── piezas puras ─────────────────────────────────────────────────────
def test_leer_saldo():
    s = leer_saldo(
        "Current balance: 1,234.5 compute units\nUsage rate: 1.76/hr\n"
        "Active assignments: 2\n"
    )
    assert s == Saldo(1234.5, 1.76, 2)


def test_leer_saldo_formato_desconocido_lanza():
    with pytest.raises(ErrorColab):
        leer_saldo("algo nuevo que no entendemos")


def test_progreso_es_la_ultima_linea():
    p = leer_progreso(_log(500) + "ruido\n" + _log(1000, ms=420))
    assert (p.hechos, p.total, p.ms_por_frame) == (1000, 1000, 420)
    assert leer_progreso("sin checkpoint todavía") is None


def test_proyeccion():
    # 7.200 frames a 500 ms = 1 h; a 2 CU/h son 2 CU
    assert proyectar_cu(7200, 500, 2.0) == pytest.approx(2.0)


def test_la_cli_pone_auth_y_sesion_explicitas():
    vistos = []

    def falso(cmd, **kw):
        vistos.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ColabCLI("/bin/colab", "oauth2", falso).python("tfv-x", "print(1)")
    assert vistos[0][:4] == ["/bin/colab", "--auth", "oauth2", "exec"]
    assert vistos[0][4:6] == ["-s", "tfv-x"]


# ── el ciclo ─────────────────────────────────────────────────────────
def test_camino_feliz_apaga_y_deja_el_cache(tmp_path):
    t = _trabajo(tmp_path)
    cli = FalsaCLI(
        [(True, _log(500)), (True, _log(1000) + "✓ deteccion x_p1: 3 min\n")]
    )
    informe = _orq(cli, tmp_path, t).lanzar()
    assert cli.llamadas[-1] == "stop tfv-x"
    assert (t.destino / "cache_x_p1.pkl").exists()
    assert "x_p1" in informe["partes"]
    # el vídeo y el modelo se subieron
    assert "upload /d/x_p1.mp4" in cli.llamadas
    assert any(c.startswith("upload /r/models/best.pt") for c in cli.llamadas)


def test_si_revienta_a_mitad_se_apaga_igual(tmp_path):
    t = _trabajo(tmp_path)
    cli = FalsaCLI([(True, _log(500)), (False, _log(500) + "Traceback: CUDA OOM\n")])
    with pytest.raises(TrabajoAbortado, match="murió"):
        _orq(cli, tmp_path, t).lanzar()
    assert cli.llamadas[-1] == "stop tfv-x"


def test_tres_sondeos_fallidos_seguidos_apagan(tmp_path):
    t = _trabajo(tmp_path)
    err = ErrorColab("red")
    cli = FalsaCLI([(err, ""), (err, ""), (err, "")])
    with pytest.raises(ErrorColab):
        _orq(cli, tmp_path, t).lanzar()
    assert cli.llamadas[-1] == "stop tfv-x"


def test_presupuesto_se_para_antes_de_pasarse(tmp_path):
    t = _trabajo(tmp_path)
    t.frames_por_parte = {"x_p1": 10**6}
    # 10^6 frames a 500 ms ≈ 139 h · 1,5 CU/h ≈ 208 CU > tope 40
    cli = FalsaCLI([(True, _log(500, total=10**6))])
    with pytest.raises(TrabajoAbortado, match="Proyección"):
        _orq(cli, tmp_path, t).lanzar()
    assert cli.llamadas[-1] == "stop tfv-x"
    # el checkpoint queda en el Mac para reanudar
    assert (t.destino / "cache_x_p1.pkl").exists()


def test_reserva_baja_el_tope(tmp_path):
    t = _trabajo(tmp_path)
    cli = FalsaCLI([], saldo=15.0)  # 15 - reserva 10 = tope 5 CU
    orq = _orq(cli, tmp_path, t)
    orq.comprobar_antes()
    assert orq.tope_cu == pytest.approx(5.0)


def test_sin_saldo_no_se_enciende(tmp_path):
    t = _trabajo(tmp_path)
    cli = FalsaCLI([], saldo=8.0)
    with pytest.raises(TrabajoAbortado, match="reserva"):
        _orq(cli, tmp_path, t).lanzar()
    assert not any(c.startswith("new") for c in cli.llamadas)


def test_commit_sin_subir_no_se_enciende(tmp_path):
    t = _trabajo(tmp_path)
    cli = FalsaCLI([])
    with pytest.raises(TrabajoAbortado, match="GitHub"):
        _orq(cli, tmp_path, t, git=_git_sin_subir).lanzar()
    assert not any(c.startswith("new") for c in cli.llamadas)


def test_parte_completa_en_el_mac_se_salta(tmp_path):
    t = _trabajo(tmp_path, n_partes=2)
    t.destino.mkdir()
    (t.destino / "cache_x_p1.pkl").write_bytes(pickle.dumps({"completo": True}))
    cli = FalsaCLI([(True, _log(1000) + "✓ deteccion x_p2: 1 min\n")])
    _orq(cli, tmp_path, t).lanzar()
    assert "upload /d/x_p1.mp4" not in cli.llamadas
    assert "upload /d/x_p2.mp4" in cli.llamadas


def test_checkpoint_del_mac_se_sube_para_reanudar(tmp_path):
    t = _trabajo(tmp_path)
    t.destino.mkdir()
    (t.destino / "cache_x_p1.pkl").write_bytes(pickle.dumps({"completo": False}))
    (t.destino / "colores_x_p1.pkl").write_bytes(pickle.dumps({}))
    cli = FalsaCLI([(True, _log(1000) + "✓ deteccion x_p1: 1 min\n")])
    _orq(cli, tmp_path, t).lanzar()
    subidas = [c for c in cli.llamadas if c.startswith("upload /s/")]
    assert subidas == ["upload /s/colores_x_p1.pkl", "upload /s/cache_x_p1.pkl"]


def test_todo_completo_no_enciende_nada(tmp_path):
    t = _trabajo(tmp_path)
    t.destino.mkdir()
    (t.destino / "cache_x_p1.pkl").write_bytes(pickle.dumps({"completo": True}))
    cli = FalsaCLI([])
    _orq(cli, tmp_path, t).lanzar()
    assert cli.llamadas == []


# ── interruptor de hombre muerto (corre en la máquina) ───────────────
def _vigia():
    spec = importlib.util.spec_from_file_location("vigia", R / "scripts/vigia_colab.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize(
    "vivo, edad, esperado",
    [
        (True, 10**6, False),  # el trabajo corre: nunca se apaga, aunque falte el Mac
        (False, 60, False),  # terminó pero el Mac está aquí: el Mac la apagará
        (False, 3601, True),  # terminó y el Mac no da señales: se libera sola
    ],
)
def test_vigia_solo_sin_trabajo_y_sin_mac(vivo, edad, esperado):
    assert _vigia().huerfana(vivo, edad, 3600) is esperado
