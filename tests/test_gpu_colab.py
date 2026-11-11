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

from src.cloud.colab_cli import MARCA_FIN, ColabCLI, ErrorColab, Saldo, leer_saldo
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

    def __init__(self, guion, saldo=100.0, tarifa=1.5, en_drive=None):
        self.guion = list(guion)  # una respuesta de sondeo por llamada: (vivo, log)
        self.en_drive = en_drive or {}  # nombre de vídeo → bytes que hay en Drive
        self.montado = True
        self.fallos_al_parar = 0
        self.llamadas, self.remoto = [], {}
        self._saldo, self._tarifa = saldo, tarifa

    def saldo(self):
        self.llamadas.append("usage")
        return Saldo(self._saldo, self._tarifa, 0)

    def nueva(self, sesion, gpu):
        self.llamadas.append(f"new {sesion} {gpu}")

    def parar(self, sesion):
        if self.fallos_al_parar:
            self.fallos_al_parar -= 1
            raise ErrorColab("NameResolutionError")
        self.llamadas.append(f"stop {sesion}")

    def subir(self, sesion, local, remoto):
        self.llamadas.append(f"upload {remoto}")
        self.remoto[remoto] = Path(local).read_bytes()

    def montar_drive(self, sesion):
        self.llamadas.append("drivemount")

    def sha_remoto(self, sesion, remoto):
        return hashlib.sha256(self.remoto[remoto]).hexdigest()

    def subir_grande(self, sesion, local, remoto):
        self.subir(sesion, local, remoto)

    def bajar_grande(self, sesion, remoto, local):
        self.bajar(sesion, remoto, local)

    def bajar(self, sesion, remoto, local):
        self.llamadas.append(f"download {remoto}")
        datos = self.remoto.get(remoto) or pickle.dumps({"completo": True, "cache": []})
        self.remoto[remoto] = datos
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(datos)

    def python(self, sesion, codigo, limite_s=120):
        if "print('RC=' + rc)" in codigo:  # `_esperar`: lo lanzado terminó bien
            return "RC=0\n"
        if "MONTADO=" in codigo:
            return f"MONTADO={self.montado}\n"
        if "echo COPIADO" in codigo:  # copiar de Drive al disco de la máquina
            nombre = codigo.split("/")[-1].split(" ")[0].strip("'")
            nombre = next((n for n in self.en_drive if n in codigo), None)
            if nombre is None:
                return "NO_ESTA\n"
            destino = codigo.split(" cp ")[1].split(" ")[1].strip("'")
            self.remoto[destino] = self.en_drive[nombre]
            self.llamadas.append(f"drive {nombre}")
            return "COPIADO\n"
        if "sha256sum" in codigo:
            ruta = codigo.split("sha256sum ")[1].split("'")[0].split('"')[0].strip()
            return hashlib.sha256(self.remoto[ruta]).hexdigest() + "  x\n"
        if "latido" in codigo and "json.dumps" in codigo:
            vivo, log, *ck = self.guion.pop(0)
            n, mt = ck if ck else (0, 0.0)
            if isinstance(vivo, Exception):
                raise vivo
            if "✓ deteccion" in log:  # el procesador termina: su caché queda completo
                for ruta in [r for r in self.remoto if r.startswith("/s/cache_")]:
                    self.remoto[ruta] = pickle.dumps({"completo": True, "cache": []})
            import json

            return (
                json.dumps({"vivo": vivo, "log": log, "n": n, "mt": mt, "inicio": 0.0})
                + "\n"
            )
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
        return subprocess.CompletedProcess(cmd, 0, MARCA_FIN, "")

    ColabCLI("/bin/colab", "oauth2", falso, dormir=lambda s: None).python(
        "tfv-x", "print(1)"
    )
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


# ── la CLI real, con un `ejecutar` falso ─────────────────────────────
def test_exec_que_lanza_se_detecta_aunque_la_cli_salga_con_0():
    """`colab exec` sale con 0 aunque el código lance (medido): manda la marca de fin."""

    def falso(cmd, input=None, **kw):
        # la traza de un error: el código no llega a imprimir la marca
        return subprocess.CompletedProcess(cmd, 0, "AssertionError: x\n", "")

    with pytest.raises(ErrorColab, match="no terminó bien"):
        ColabCLI("/bin/colab", "oauth2", falso, dormir=lambda s: None).python(
            "tfv-x", "assert False"
        )


def test_exec_bueno_devuelve_la_salida_sin_la_marca():
    def falso(cmd, input=None, **kw):
        marca = input.strip().splitlines()[-1].split("(")[1].rstrip(")").strip("'")
        return subprocess.CompletedProcess(cmd, 0, f"hola\n{marca}\n", "")

    out = ColabCLI("/bin/colab", "oauth2", falso, dormir=lambda s: None).python(
        "tfv-x", "print('hola')"
    )
    assert out == "hola\n"


def test_trocear_y_unir_reconstruye_el_fichero(tmp_path):
    from src.cloud.colab_cli import trocear

    f = tmp_path / "v.mp4"
    f.write_bytes(bytes(range(256)) * 1000)  # 256.000 bytes
    (tmp_path / "t").mkdir()
    trozos = trocear(f, tmp_path / "t", 100_000)
    assert [t.stat().st_size for t in trozos] == [100_000, 100_000, 56_000]
    assert b"".join(t.read_bytes() for t in sorted(trozos)) == f.read_bytes()


def test_dos_exec_a_la_vez_van_en_fila():
    """Dos `colab exec` simultáneos se bloquean en la máquina (medido): tienen que ir en fila."""
    import threading
    import time as _t

    dentro, solapes = [0], []
    cerrojo = threading.Lock()

    def falso(cmd, input=None, **kw):
        with cerrojo:
            dentro[0] += 1
            solapes.append(dentro[0])
        _t.sleep(0.05)
        with cerrojo:
            dentro[0] -= 1
        return subprocess.CompletedProcess(cmd, 0, MARCA_FIN, "")

    cli = ColabCLI("/bin/colab", "oauth2", falso, dormir=lambda s: None)
    hilos = [
        threading.Thread(target=cli.python, args=("tfv-x", "print(1)"))
        for _ in range(4)
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert max(solapes) == 1


def test_exec_colgado_se_corta_por_tiempo():
    def falso(cmd, timeout=None, **kw):
        raise subprocess.TimeoutExpired(cmd, timeout)

    with pytest.raises(ErrorColab, match="no respondió"):
        ColabCLI("/bin/colab", "oauth2", falso, dormir=lambda s: None).python(
            "tfv-x", "print(1)", 60
        )


def test_exec_colgado_se_reintenta_y_sigue():
    """Un exec que se cuelga sin enviar el código (medido en colab.log) se repite."""
    llamadas = []

    def falso(cmd, timeout=None, **kw):
        llamadas.append(cmd)
        if len(llamadas) == 1:
            raise subprocess.TimeoutExpired(cmd, timeout)
        return subprocess.CompletedProcess(cmd, 0, f"ok\n{MARCA_FIN}\n", "")

    cli = ColabCLI("/bin/colab", "oauth2", falso, dormir=lambda s: None)
    assert cli.python("tfv-x", "print('ok')") == "ok\n"
    assert len(llamadas) == 2


def test_exec_que_falla_de_verdad_no_se_reintenta():
    """Un error del CÓDIGO no se arregla repitiéndolo: solo se repite lo que no respondió."""
    llamadas = []

    def falso(cmd, **kw):
        llamadas.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "Traceback ...\n", "")

    cli = ColabCLI("/bin/colab", "oauth2", falso, dormir=lambda s: None)
    with pytest.raises(ErrorColab):
        cli.python("tfv-x", "assert False")
    assert len(llamadas) == 1


def test_sin_red_a_github_vale_el_ultimo_push(tmp_path):
    def git_sin_red(cmd, **kw):
        if "fetch" in cmd:
            return subprocess.CompletedProcess(
                cmd, 128, "", "ssh: connect to host github.com"
            )
        return _git_ok(cmd)

    t = _trabajo(tmp_path)
    cli = FalsaCLI([])
    assert _orq(cli, tmp_path, t, git=git_sin_red).comprobar_antes() == "abc123"


# ── vídeo desde Drive ────────────────────────────────────────────────
def _cfg_drive():
    import copy

    cfg = copy.deepcopy(CFG)
    cfg["video"] = {"origen": "drive", "carpeta_drive": "/content/drive/MyDrive/v"}
    return cfg


def _orq_drive(cli, tmp_path, t):
    reloj = iter(range(0, 10**9, 60))
    return Orquestador(
        cli, _cfg_drive(), t, tmp_path, dormir=lambda s: None,
        reloj=lambda: next(reloj), git=_git_ok,
    )  # fmt: skip


def test_drive_monta_copia_y_solo_sube_lo_que_falta(tmp_path):
    t = _trabajo(tmp_path, n_partes=2)
    p1 = t.partes[0].video
    cli = FalsaCLI(
        [
            (True, _log(1000) + "✓ deteccion x_p1: 1 min\n"),
            (True, _log(1000) + "✓ deteccion x_p2: 1 min\n"),
        ],
        en_drive={p1.name: p1.read_bytes()},
    )
    _orq_drive(cli, tmp_path, t).lanzar()
    assert cli.llamadas.index("drivemount") < cli.llamadas.index(f"drive {p1.name}")
    assert "upload /d/x_p1.mp4" not in cli.llamadas  # la 1 vino de Drive
    assert "upload /d/x_p2.mp4" in cli.llamadas  # la 2 no estaba: desde el Mac
    assert cli.llamadas[-1] == "stop tfv-x"


def test_drive_con_otro_fichero_del_mismo_nombre_para(tmp_path):
    t = _trabajo(tmp_path)
    p1 = t.partes[0].video
    cli = FalsaCLI([], en_drive={p1.name: b"OTRO VIDEO"})
    with pytest.raises(TrabajoAbortado, match="NO es el mismo"):
        _orq_drive(cli, tmp_path, t).lanzar()
    assert cli.llamadas[-1] == "stop tfv-x"


def test_drive_que_no_monta_cae_a_subir_desde_el_mac(tmp_path):
    t = _trabajo(tmp_path)
    p1 = t.partes[0].video
    cli = FalsaCLI(
        [(True, _log(1000) + "✓ deteccion x_p1: 1 min\n")],
        en_drive={p1.name: p1.read_bytes()},
    )
    cli.montado = False
    _orq_drive(cli, tmp_path, t).lanzar()
    assert cli.llamadas.count("drivemount") == 2  # un reintento del permiso
    assert "upload /d/x_p1.mp4" in cli.llamadas
    assert cli.llamadas[-1] == "stop tfv-x"


def test_apagar_reintenta_si_falla_la_red(tmp_path):
    t = _trabajo(tmp_path)
    cli = FalsaCLI([(True, _log(1000) + "✓ deteccion x_p1: 1 min\n")])
    cli.fallos_al_parar = 2
    _orq(cli, tmp_path, t).lanzar()
    assert cli.llamadas[-1] == "stop tfv-x"


# ── progreso por checkpoint y enganche ───────────────────────────────
def test_progreso_por_checkpoint_sin_lineas_en_el_log(tmp_path):
    """El log remoto no tenía progreso (sin `logging`): se lee del checkpoint en disco."""
    t = _trabajo(tmp_path)
    t.frames_por_parte = {"x_p1": 10**6}
    # 500 frames en 250 s desde el arranque = 500 ms/frame; 10^6 frames ≈ 139 h > tope
    cli = FalsaCLI([(True, "sin progreso en el log\n", 500, 250.0)])
    with pytest.raises(TrabajoAbortado, match="Proyección"):
        _orq(cli, tmp_path, t).lanzar()
    assert cli.llamadas[-1] == "stop tfv-x"


def test_ritmo_entre_dos_checkpoints(tmp_path):
    t = _trabajo(tmp_path)
    orq = _orq(FalsaCLI([]), tmp_path, t)
    parte = t.partes[0]
    p1 = orq._progreso_checkpoint(parte, {"n": 500, "mt": 300.0, "inicio": 0.0})
    p2 = orq._progreso_checkpoint(parte, {"n": 1000, "mt": 500.0, "inicio": 0.0})
    assert p1.ms_por_frame == pytest.approx(600)  # 300 s / 500 desde el arranque
    assert p2.ms_por_frame == pytest.approx(400)  # 200 s / 500 entre checkpoints


def test_adjuntar_no_enciende_ni_sube_y_apaga(tmp_path):
    t = _trabajo(tmp_path)
    cli = FalsaCLI([(True, "", 500, 250.0), (True, "✓ deteccion x_p1: 9 min\n")])
    _orq(cli, tmp_path, t).adjuntar()
    assert not any(c.startswith(("new", "upload", "drivemount")) for c in cli.llamadas)
    assert (t.destino / "cache_x_p1.pkl").exists()
    assert cli.llamadas[-1] == "stop tfv-x"


def test_trabajo_sin_colores_solo_baja_el_cache(tmp_path):
    """El balón no tiene caché de colores: no se puede pedir un fichero que no existe."""
    t = _trabajo(tmp_path)
    t.ficheros = ("cache",)
    cli = FalsaCLI([(True, _log(1000) + "✓ deteccion x_p1: 1 min\n")])
    _orq(cli, tmp_path, t).lanzar()
    bajadas = [c for c in cli.llamadas if c.startswith("download")]
    assert bajadas == ["download /s/cache_x_p1.pkl"]
