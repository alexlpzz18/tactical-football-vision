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

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class ErrorColab(RuntimeError):
    """La CLI devolvió un código distinto de 0. Lleva el comando y lo que imprimió."""


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
    ):
        self.ruta = str(Path(ruta).expanduser())
        self.auth = auth
        self._ejecutar = ejecutar

    # ── base ──────────────────────────────────────────────────────────
    def _cmd(
        self, *args: str, entrada: str | None = None, timeout: float | None = None
    ) -> str:
        cmd = [self.ruta, "--auth", self.auth, *args]
        logger.debug("colab %s", " ".join(args))
        r = self._ejecutar(
            cmd, input=entrada, capture_output=True, text=True, timeout=timeout
        )
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

    # ── ejecución y ficheros ──────────────────────────────────────────
    def python(self, sesion: str, codigo: str, inactividad_s: int = 600) -> str:
        """Ejecuta `codigo` en el kernel de la máquina y devuelve lo que imprime.

        `inactividad_s` es el `--timeout` de la CLI: falla tras ese tiempo SIN salida, no tras ese
        tiempo en total. Para trabajos largos no se usa esto: se lanzan en segundo plano.
        """
        return self._cmd(
            "exec", "-s", sesion, "--timeout", str(inactividad_s), entrada=codigo
        )

    def subir(self, sesion: str, local: str | Path, remoto: str) -> str:
        return self._cmd("upload", "-s", sesion, str(local), remoto, timeout=7200)

    def bajar(self, sesion: str, remoto: str, local: str | Path) -> str:
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        return self._cmd("download", "-s", sesion, remoto, str(local), timeout=7200)
