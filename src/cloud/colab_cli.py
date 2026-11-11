"""Envoltorio fino de la Colab CLI oficial (`google-colab-cli`, comando `colab`).

Por qué un envoltorio y no llamar a `colab` a pelo desde cada script:
- un solo sitio donde se construyen los comandos, con la sesión SIEMPRE explícita (`-s`): sin ella
  la CLI usa «la última», y un trabajo podría acabar escribiendo en la máquina de otro;
- los errores de la CLI se convierten en una excepción con el comando y su salida, en vez de
  perderse en un código de salida que nadie mira;
- los tests sustituyen `ejecutar` por un falso y comprueban la LÓGICA (que siempre se apaga la
  máquina, que no se gasta por encima del presupuesto) sin gastar ni una unidad de cómputo.

docs/gpu_colab.md.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MARCA_FIN = "__TFV_FIN_OK__"  # ver ColabCLI.python
TROZO_MB = 40  # el servidor rechaza una subida de 100 MB y acepta 50 (medido el 11-nov)
PARALELO = 4
PAUSA_ENTRE_EXEC_S = 3  # deja que el cliente del exec anterior termine de cerrarse


class ErrorColab(RuntimeError):
    """La CLI devolvió un código distinto de 0. Lleva el comando y lo que imprimió."""


class SinRespuesta(ErrorColab):
    """La llamada no terminó en su tiempo máximo (la CLI se quedó colgada)."""


@dataclass(frozen=True)
class Saldo:
    """Lo que dice `colab usage`."""

    unidades: float  # saldo de unidades de cómputo (CU)
    tarifa_hora: float  # CU por hora que se están gastando AHORA (0 sin máquinas)
    asignaciones: int  # máquinas encendidas en la cuenta


def leer_saldo(texto: str) -> Saldo:
    """Interpreta la salida de `colab usage`.

    Formato (CLI 0.8): «Current balance: 98.5 compute units», «Usage rate: 1.76/hr» y «Active
    assignments: 1». Si cambia el formato se lanza: un saldo mal leído es peor que ninguno, porque
    el presupuesto se decide con él.
    """
    saldo = re.search(r"balance:\s*([\d.,]+)", texto, re.IGNORECASE)
    tarifa = re.search(r"rate:\s*([\d.,]+)", texto, re.IGNORECASE)
    activas = re.search(r"assignments:\s*(\d+)", texto, re.IGNORECASE)
    if not saldo:
        raise ErrorColab(f"No se entiende la salida de `colab usage`:\n{texto}")

    def num(m):
        return float(m.group(1).replace(",", "")) if m else 0.0

    return Saldo(num(saldo), num(tarifa), int(activas.group(1)) if activas else 0)


class ColabCLI:
    """Una llamada por método; cada una autentica, hace una cosa y sale (así funciona la CLI)."""

    def __init__(
        self,
        ruta: str | Path,
        auth: str = "oauth2",
        ejecutar: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self.ruta = str(Path(ruta).expanduser())
        self.auth = auth
        self._ejecutar = ejecutar
        self._dormir = dormir
        # una sola conexión al kernel a la vez (ver `python`)
        self._kernel = threading.Lock()

    # ── base ──────────────────────────────────────────────────────────
    def _cmd(
        self, *args: str, entrada: str | None = None, timeout: float | None = None
    ) -> str:
        cmd = [self.ruta, "--auth", self.auth, *args]
        logger.debug("colab %s", " ".join(args))
        try:
            r = self._ejecutar(
                cmd, input=entrada, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as err:
            # una llamada colgada no puede dejar la máquina encendida esperando para siempre
            raise SinRespuesta(
                f"`colab {' '.join(args)}` no respondió en {timeout} s"
            ) from err
        if r.returncode != 0:
            raise ErrorColab(
                f"`colab {' '.join(args)}` salió con {r.returncode}:\n"
                f"{(r.stdout or '')[-2000:]}\n{(r.stderr or '')[-2000:]}"
            )
        return r.stdout or ""

    # ── cuenta y sesiones ─────────────────────────────────────────────
    def saldo(self) -> Saldo:
        return leer_saldo(self._cmd("usage"))

    def sesiones(self) -> str:
        return self._cmd("sessions")

    def nueva(self, sesion: str, gpu: str | None) -> str:
        args = ["new", "-s", sesion]
        if gpu:
            args += ["--gpu", gpu]
        return self._cmd(*args, timeout=900)

    def estado(self, sesion: str) -> str:
        return self._cmd("status", "-s", sesion, timeout=120)

    def parar(self, sesion: str) -> str:
        return self._cmd("stop", "-s", sesion, timeout=300)

    def montar_drive(self, sesion: str, ruta: str = "/content/drive") -> None:
        """Monta el Drive de Alex en la máquina. INTERACTIVO, y una vez por máquina.

        La CLI abre en el navegador del Mac la página de permiso de Google y espera un Enter en la
        terminal (medido el 11-nov). Por eso NO se captura la salida: se hereda la terminal desde
        la que se lanzó, para que Alex vea el aviso y pueda responder.
        """
        cmd = [self.ruta, "--auth", self.auth, "drivemount", "-s", sesion, ruta]
        r = self._ejecutar(cmd, timeout=900)
        if r.returncode != 0:
            raise ErrorColab(f"`colab drivemount` salió con {r.returncode}")

    # ── ejecución y ficheros ──────────────────────────────────────────
    def python(
        self, sesion: str, codigo: str, limite_s: int = 120, reintentos: int = 3
    ) -> str:
        """Ejecuta `codigo` en el kernel de la máquina y devuelve lo que imprime.

        Tres cosas medidas el 11-nov, que no dice la documentación de la CLI:

        1. `colab exec` sale con 0 AUNQUE EL CÓDIGO LANCE (con un `assert False`). Por eso se añade
           una marca al final: si no aparece en la salida, el código no llegó al final y se lanza.
        2. DOS `colab exec` A LA VEZ se bloquean los dos (4,5 min con la L4 parada, kernel IDLE).
           El candado las pone en fila.
        3. UNO DETRÁS DE OTRO TAMBIÉN PUEDE COLGARSE: el cliente del exec anterior aún se está
           cerrando, el nuevo da «Kernel startup timeout», reintenta, se conecta y NUNCA envía el
           código (colab.log; 7 min con el kernel IDLE). Por eso: una pausa entre llamadas, un
           tiempo máximo corto y reintento si no responde.

        De ahí la regla: TODO lo que se ejecuta así es CORTO (segundos) y se puede repetir sin
        daño. Lo largo (instalar, detectar) se lanza en segundo plano en la máquina y se consulta.
        """
        for intento in range(1, reintentos + 1):
            with self._kernel:
                try:
                    salida = self._cmd(
                        "exec", "-s", sesion, "--timeout", str(limite_s),
                        entrada=f"{codigo}\nprint({MARCA_FIN!r})\n",
                        timeout=limite_s + 30,
                    )  # fmt: skip
                    break
                except SinRespuesta:
                    if intento == reintentos:
                        raise
                    logger.warning(
                        "colab exec sin respuesta (intento %d/%d): se repite",
                        intento,
                        reintentos,
                    )
                finally:
                    self._dormir(PAUSA_ENTRE_EXEC_S)
        if MARCA_FIN not in salida:
            raise ErrorColab(f"El código remoto no terminó bien:\n{salida[-3000:]}")
        return salida.replace(MARCA_FIN, "").rstrip() + "\n"

    def subir(self, sesion: str, local: str | Path, remoto: str) -> str:
        """Un fichero de hasta ~50 MB (más, el servidor responde 400). Para más: `subir_grande`."""
        return self._cmd("upload", "-s", sesion, str(local), remoto, timeout=1800)

    def bajar(self, sesion: str, remoto: str, local: str | Path) -> str:
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        return self._cmd("download", "-s", sesion, remoto, str(local), timeout=1800)

    def sha_remoto(self, sesion: str, remoto: str) -> str:
        out = self.python(
            sesion,
            "import hashlib\nh = hashlib.sha256()\n"
            f"with open({remoto!r}, 'rb') as f:\n"
            "    for b in iter(lambda: f.read(1 << 24), b''):\n        h.update(b)\n"
            "print(h.hexdigest())\n",
        )
        return out.split()[-1]

    def subir_grande(
        self, sesion: str, local: str | Path, remoto: str,
        trozo_mb: int = TROZO_MB, paralelo: int = PARALELO,
    ) -> None:  # fmt: skip
        """Sube cualquier tamaño: en trozos, varios a la vez, y comprueba la huella del total.

        Medido el 11-nov: 50 MB suben y 100 MB no (400). Un trozo suelto va a ~1,9 MB/s y cuatro
        a la vez a ~6 MB/s, así que un vídeo de 956 MB tarda ~3 min en vez de ~8.
        """
        local = Path(local)
        dir_r = f"{remoto}.trozos"
        self.python(sesion, f"import os\nos.makedirs({dir_r!r}, exist_ok=True)\n")
        with tempfile.TemporaryDirectory() as tmp:
            trozos = trocear(local, Path(tmp), trozo_mb * 1_000_000)
            with ThreadPoolExecutor(paralelo) as ex:
                list(
                    ex.map(lambda t: self.subir(sesion, t, f"{dir_r}/{t.name}"), trozos)
                )
        nombres = [t.name for t in trozos]
        self.python(
            sesion,
            "import os, shutil\n"
            f"with open({remoto!r}, 'wb') as out:\n"
            f"    for n in {nombres!r}:\n"
            f"        with open(os.path.join({dir_r!r}, n), 'rb') as f:\n"
            "            shutil.copyfileobj(f, out, 1 << 24)\n"
            f"shutil.rmtree({dir_r!r})\n",
        )
        if self.sha_remoto(sesion, remoto) != sha256(local):
            raise ErrorColab(f"{local.name}: la huella no coincide tras subirlo")

    def bajar_grande(
        self, sesion: str, remoto: str, local: str | Path,
        trozo_mb: int = TROZO_MB, paralelo: int = PARALELO,
    ) -> None:  # fmt: skip
        """Lo mismo al revés: se trocea en la máquina, se bajan los trozos y se une en el Mac.

        ⚠️ La huella se calcula sobre los MISMOS bytes que se trocean, en la misma llamada: el
        fichero remoto puede cambiar mientras se descarga (un checkpoint nuevo del detector) y
        comparar con el fichero de después daba «la huella no coincide» sobre una descarga buena
        (11-nov: así se apagó la detección de jugadores a mitad). El checkpoint se escribe con
        `os.replace`, así que el fichero abierto aquí es una foto fija aunque cambie el nombre.
        """
        local = Path(local)
        dir_r = f"{remoto}.trozos"
        out = self.python(
            sesion,
            "import hashlib, os, shutil\n"
            f"shutil.rmtree({dir_r!r}, ignore_errors=True); os.makedirs({dir_r!r})\n"
            "n = 0; h = hashlib.sha256()\n"
            f"with open({remoto!r}, 'rb') as f:\n"
            f"    while b := f.read({trozo_mb * 1_000_000}):\n"
            f"        open(os.path.join({dir_r!r}, f'{{n:05d}}'), 'wb').write(b); n += 1\n"
            "        h.update(b)\n"
            "print(n, h.hexdigest())\n",
        )
        n_txt, sha_foto = out.split()[-2:]
        n = int(n_txt)
        local.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local.parent) as tmp:
            nombres = [f"{i:05d}" for i in range(n)]
            with ThreadPoolExecutor(paralelo) as ex:
                list(ex.map(
                    lambda nm: self.bajar(sesion, f"{dir_r}/{nm}", Path(tmp) / nm), nombres
                ))  # fmt: skip
            with open(local, "wb") as salida:
                for nm in nombres:
                    with open(Path(tmp) / nm, "rb") as f:
                        shutil.copyfileobj(f, salida, 1 << 24)
        self.python(sesion, f"import shutil\nshutil.rmtree({dir_r!r})\n")
        if sha_foto != sha256(local):
            raise ErrorColab(f"{local.name}: la huella no coincide tras bajarlo")


def sha256(ruta: Path, bloque: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while b := f.read(bloque):
            h.update(b)
    return h.hexdigest()


def trocear(ruta: Path, carpeta: Path, tamano: int) -> list[Path]:
    """Parte un fichero en trozos de `tamano` bytes, con nombres que ordenan bien (00000…)."""
    trozos = []
    with open(ruta, "rb") as f:
        while b := f.read(tamano):
            t = carpeta / f"{len(trozos):05d}"
            t.write_bytes(b)
            trozos.append(t)
    return trozos
