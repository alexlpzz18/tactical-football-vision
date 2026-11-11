#!/usr/bin/env python
"""GPU de Colab desde la terminal: lanzar, vigilar y apagar. docs/gpu_colab.md.

Comandos:
    python scripts/gpu_colab.py saldo                 # unidades de cómputo y máquinas encendidas
    python scripts/gpu_colab.py lanzar alevinb        # detección de las dos partes en GPU
    python scripts/gpu_colab.py seguimiento alevinb   # tracking en el Mac sobre esos cachés
    python scripts/gpu_colab.py parar                 # apaga TODAS las máquinas tfv-*

`lanzar` se deja corriendo (tarda horas). Para que el Mac no se duerma mientras vigila:
    caffeinate -i python scripts/gpu_colab.py lanzar alevinb

Si se corta, se repite el mismo comando: lo completo se salta y lo empezado se reanuda.
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))

from src.cloud.colab_cli import ColabCLI  # noqa: E402
from src.cloud.trabajo_gpu import Orquestador, Parte, Trabajo  # noqa: E402

CONFIG = R / "configs/gpu_colab.yaml"
logger = logging.getLogger("gpu_colab")


def trabajos() -> dict[str, Trabajo]:
    """Los trabajos conocidos. Uno nuevo = una entrada aquí, nada más."""
    destino = R / "data/tracking_alevinb"  # gitignored: los cachés no se commitean
    return {
        "alevinb": Trabajo(
            nombre="alevinb",
            partes=[
                Parte("alevinb_p1", R / "data/raw/alevinb_p1.mp4"),
                Parte("alevinb_p2", R / "data/raw/alevinb_p2.mp4"),
            ],
            script="scripts/colab_alevinb.py",
            args=["--imagen", "original"],  # decisión de Alex, 5-nov
            modelo=R / "models/weights/best_v4pre.pt",
            destino=destino,
            # frames PROCESADOS por parte (45.550 y 45.700 originales, 1 de cada 3)
            frames_por_parte={"alevinb_p1": 15184, "alevinb_p2": 15234},
        )
    }


def cli_desde_config(cfg: dict) -> ColabCLI:
    return ColabCLI(cfg["cli"]["ruta"], cfg["cli"]["auth"])


def cmd_saldo(cfg: dict) -> None:
    cli = cli_desde_config(cfg)
    s = cli.saldo()
    print(f"Saldo: {s.unidades:.1f} CU · gasto ahora: {s.tarifa_hora:.2f} CU/h · "
          f"máquinas encendidas: {s.asignaciones}")  # fmt: skip
    if s.asignaciones:
        print(cli.sesiones())


def cmd_lanzar(cfg: dict, nombre: str, mantener: bool) -> None:
    trabajo = trabajos()[nombre]
    orq = Orquestador(cli_desde_config(cfg), cfg, trabajo, R)
    informe = {}
    try:
        informe = orq.lanzar(mantener=mantener)
    finally:
        informe = informe or orq.informe
        informe["fin"] = datetime.now().isoformat(timespec="seconds")
        ruta = trabajo.destino / f"informe_gpu_{datetime.now():%Y%m%d_%H%M}.json"
        trabajo.destino.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(informe, indent=1, ensure_ascii=False))
        logger.info("Informe: %s", ruta)


def cmd_seguimiento(nombre: str) -> None:
    t = trabajos()[nombre]
    subprocess.run(
        [sys.executable, str(R / t.script), *t.args, "--fase", "seguimiento",
         "--salida", str(t.destino), "--videos", ",".join(str(p.video) for p in t.partes),
         "--nombres", ",".join(p.nombre for p in t.partes)],
        check=True,
    )  # fmt: skip


def cmd_parar(cfg: dict) -> None:
    cli = cli_desde_config(cfg)
    prefijo = cfg["maquina"]["prefijo_sesion"] + "-"
    nombres = sorted(
        set(re.findall(rf"\b({re.escape(prefijo)}[\w-]+)", cli.sesiones()))
    )
    for n in nombres:
        cli.parar(n)
        print(f"apagada {n}")
    if not nombres:
        print("No hay máquinas tfv-* encendidas")
    cmd_saldo(cfg)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("saldo")
    p = sub.add_parser("lanzar")
    p.add_argument("trabajo", choices=sorted(trabajos()))
    p.add_argument("--mantener", action="store_true", help="no apagar al terminar")
    p = sub.add_parser("seguimiento")
    p.add_argument("trabajo", choices=sorted(trabajos()))
    sub.add_parser("parar")
    a = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = yaml.safe_load(open(CONFIG))
    if a.cmd == "saldo":
        cmd_saldo(cfg)
    elif a.cmd == "lanzar":
        cmd_lanzar(cfg, a.trabajo, a.mantener)
    elif a.cmd == "seguimiento":
        cmd_seguimiento(a.trabajo)
    else:
        cmd_parar(cfg)


if __name__ == "__main__":
    main()
