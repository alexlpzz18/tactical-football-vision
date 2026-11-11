#!/usr/bin/env python
"""Interruptor de hombre muerto que corre EN LA MÁQUINA de Colab. docs/gpu_colab.md.

El Mac vigila el trabajo y apaga la máquina al terminar. Pero si el Mac se duerme, pierde la red o
se cierra la terminal, la máquina se quedaría encendida gastando unidades de cómputo hasta que
Colab la recogiera por inactividad. Este proceso lo evita:

- cada vez que el Mac pregunta cómo va, toca el fichero `--latido`;
- si el trabajo YA NO CORRE (terminó o murió) y el latido lleva más de `--tras-s` segundos sin
  tocarse, la máquina se libera sola.

Mientras el trabajo corra, nunca se apaga: si el Mac falta pero la detección avanza, el gasto es
útil, y el resultado queda en la máquina hasta que el Mac vuelva a por él. Lo que se pierde al
liberarla es lo que no se haya descargado: por eso el Mac trae el checkpoint cada media hora.

Uso (lo lanza scripts/gpu_colab.py, no se usa a mano):
    python scripts/vigia_colab.py --pid-fichero /content/salida/trabajo.pid \\
        --latido /content/salida/latido --tras-s 3600
"""

import argparse
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger("vigia_colab")
COMPROBAR_CADA_S = 60


def corre(pid: int) -> bool:
    """¿Sigue vivo el proceso? (señal 0: no hace nada, solo pregunta)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # un proceso hijo terminado queda «zombi» hasta que alguien lo recoge: cuenta como muerto
    try:
        estado = Path(f"/proc/{pid}/stat").read_text().split()[2]
        return estado != "Z"
    except OSError:
        return True


def huerfana(trabajo_vivo: bool, edad_latido_s: float, tras_s: float) -> bool:
    """La decisión, aparte para poder probarla: solo sin trabajo Y sin Mac."""
    return (not trabajo_vivo) and edad_latido_s > tras_s


def liberar_maquina() -> None:
    """Libera la máquina de Colab desde dentro (API del propio runtime de Colab)."""
    from google.colab import runtime  # solo existe dentro de Colab

    runtime.unassign()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid-fichero", type=Path, required=True)
    ap.add_argument("--latido", type=Path, required=True)
    ap.add_argument("--tras-s", type=float, default=3600)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s vigia %(message)s")
    a.latido.touch()
    while True:
        time.sleep(COMPROBAR_CADA_S)
        try:
            pid = int(a.pid_fichero.read_text().strip())
        except (OSError, ValueError):
            pid = -1
        vivo = pid > 0 and corre(pid)
        edad = time.time() - a.latido.stat().st_mtime if a.latido.exists() else 1e9
        if huerfana(vivo, edad, a.tras_s):
            logger.warning(
                "Trabajo terminado y sin noticias del Mac desde hace %.0f s: "
                "se libera la máquina",
                edad,
            )
            liberar_maquina()
            return


if __name__ == "__main__":
    main()
