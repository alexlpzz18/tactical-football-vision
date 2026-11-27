#!/usr/bin/env python
"""GPU de Colab desde la terminal: lanzar, vigilar y apagar. docs/gpu_colab.md.

Comandos:
    python scripts/gpu_colab.py saldo                 # unidades de cómputo y máquinas encendidas
    python scripts/gpu_colab.py lanzar alevinb        # detección de las dos partes en GPU
    python scripts/gpu_colab.py lanzar alevinb --gpu T4   # en T4 si la L4 da 503
    python scripts/gpu_colab.py probar --gpu T4       # ¿hay T4 hoy? enciende y apaga (~0,02 CU)
    python scripts/gpu_colab.py seguimiento alevinb   # tracking en el Mac sobre esos cachés
    python scripts/gpu_colab.py parar                 # apaga TODAS las máquinas tfv-*

`lanzar` se deja corriendo (tarda horas). Para que el Mac no se duerma mientras vigila:
    caffeinate -i python scripts/gpu_colab.py lanzar alevinb

Si se corta, se repite el mismo comando: lo completo se salta y lo empezado se reanuda.
"""

from __future__ import annotations  # `str | None` también en el Python 3.9 de los tests

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

from src.cloud.colab_cli import ColabCLI, ErrorColab  # noqa: E402
from src.cloud.trabajo_gpu import Orquestador, Parte, Trabajo  # noqa: E402

CONFIG = R / "configs/gpu_colab.yaml"
# GPU que se pueden pedir por lanzamiento. La del YAML (L4) es la de por defecto; T4 es la
# alternativa cuando Google responde 503 a la L4 (27-nov, dos veces seguidas).
GPUS = ("L4", "T4", "A100")
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
        ),
        # BALÓN: mismo vídeo, otro detector, 1 de cada 2 (docs/alevinb_balon.md)
        "alevinb_balon": Trabajo(
            nombre="alevinb_balon",
            partes=[
                Parte("alevinb_p1_balon", R / "data/raw/alevinb_p1.mp4"),
                Parte("alevinb_p2_balon", R / "data/raw/alevinb_p2.mp4"),
            ],
            script="scripts/colab_alevinb_balon.py",
            args=["--imagen", "original"],
            modelo=R / "models/weights/best_balon_v1.pt",
            destino=destino,
            frames_por_parte={"alevinb_p1_balon": 22775, "alevinb_p2_balon": 22850},
            ficheros=("cache",),  # el balón no tiene caché de colores
        ),
        # OPCIÓN 1 en el alevín B (adoptada en la rama el 27-nov): las dos partes con las
        # detecciones débiles añadidas. Nombres de parte NUEVOS (_conf010) para no pisar los cachés
        # de producción. Estimado 4-10 CU (docs/plan_opcion1_dos_etapas.md).
        "alevinb_dos_etapas": Trabajo(
            nombre="alevinb_dos_etapas",
            partes=[
                Parte("alevinb_p1_conf010", R / "data/raw/alevinb_p1.mp4"),
                Parte("alevinb_p2_conf010", R / "data/raw/alevinb_p2.mp4"),
            ],
            script="scripts/colab_alevinb.py",
            args=["--imagen", "original", "--dos-etapas"],
            modelo=R / "models/weights/best_v4pre.pt",
            destino=destino,
            frames_por_parte={"alevinb_p1_conf010": 15184, "alevinb_p2_conf010": 15234},
        ),
        # OPCIÓN 1 del embudo lejano (docs/plan_opcion1_dos_etapas.md): el alevín A, 60 s
        # (5:00-6:00), con las detecciones de 0,10-0,30 AÑADIDAS a las de producción. Unos minutos
        # de L4 (~1 CU con arranque y subida del vídeo).
        "villa_dos_etapas": Trabajo(
            nombre="villa_dos_etapas",
            partes=[Parte("villa_conf010", R / "data/raw/partido.mp4")],
            script="scripts/colab_villa_dos_etapas.py",
            args=[],
            modelo=R / "models/weights/best_v4pre.pt",
            destino=R / "data/tracking",
            frames_por_parte={"villa_conf010": 500},
        ),
        # EMBEDDINGS DINOv2 de cada detección de producción de las tres patas
        # (docs/plan_equipos_embeddings.md). DINOv2 se descarga en la máquina: no hay pesos propios.
        "embeddings_equipos": Trabajo(
            nombre="embeddings_equipos",
            partes=[
                Parte(
                    "emb_benja",
                    R / "data/raw/benja_gredos_p1_20min.mp4",
                    [
                        (
                            R / "data/tracking_benja/cache_detecciones_benja.pkl",
                            "det_emb_benja.pkl",
                        )
                    ],
                ),
                Parte(
                    "emb_villa",
                    R / "data/raw/partido.mp4",
                    [
                        (
                            R / "data/tracking/cache_detecciones_v4pre.pkl",
                            "det_emb_villa.pkl",
                        )
                    ],
                ),
                Parte(
                    "emb_alevinb_p1",
                    R / "data/raw/alevinb_p1.mp4",
                    [(destino / "cache_alevinb_p1.pkl", "det_emb_alevinb_p1.pkl")],
                ),
            ],
            script="scripts/colab_embeddings_equipos.py",
            args=[],
            modelo=None,
            destino=R / "data/embeddings_equipos",
            frames_por_parte={
                "emb_benja": 600,
                "emb_villa": 500,
                "emb_alevinb_p1": 15184,
            },
            ficheros=("cache",),
        ),
        # EMBEDDINGS SigLIP del TORSO (docs/plan_siglip_por_partido.md): la misma celda con
        # `--modelo siglip`. El benjamín, con su caché v2 (cajas idénticas a producción), que es el
        # que usa el banco.
        "siglip_equipos": Trabajo(
            nombre="siglip_equipos",
            partes=[
                Parte(
                    "sig_benja",
                    R / "data/raw/benja_gredos_p1_20min.mp4",
                    [
                        (
                            R
                            / "data/tracking_benja/cache_detecciones_benja_v2color.pkl",
                            "det_sig_benja.pkl",
                        )
                    ],
                ),
                Parte(
                    "sig_villa",
                    R / "data/raw/partido.mp4",
                    [
                        (
                            R / "data/tracking/cache_detecciones_v4pre.pkl",
                            "det_sig_villa.pkl",
                        )
                    ],
                ),
                Parte(
                    "sig_alevinb_p1",
                    R / "data/raw/alevinb_p1.mp4",
                    [(destino / "cache_alevinb_p1.pkl", "det_sig_alevinb_p1.pkl")],
                ),
            ],
            script="scripts/colab_embeddings_equipos.py",
            args=["--modelo", "siglip"],
            modelo=None,
            destino=R / "data/embeddings_equipos",
            frames_por_parte={
                "sig_benja": 600,
                "sig_villa": 500,
                "sig_alevinb_p1": 15184,
            },
            ficheros=("cache",),
        ),
    }


def con_gpu(cfg: dict, gpu: str | None) -> dict:
    """Copia de la config con otra GPU para ESTE lanzamiento; sin `gpu`, la del YAML intacta."""
    if not gpu:
        return cfg
    return {**cfg, "maquina": {**cfg["maquina"], "gpu": gpu}}


def cli_desde_config(cfg: dict) -> ColabCLI:
    return ColabCLI(cfg["cli"]["ruta"], cfg["cli"]["auth"])


def cmd_saldo(cfg: dict) -> None:
    cli = cli_desde_config(cfg)
    s = cli.saldo()
    print(f"Saldo: {s.unidades:.1f} CU · gasto ahora: {s.tarifa_hora:.2f} CU/h · "
          f"máquinas encendidas: {s.asignaciones}")  # fmt: skip
    if s.asignaciones:
        print(cli.sesiones())


def filtrar_partes(trabajo: Trabajo, partes: str | None) -> Trabajo:
    if partes:
        pedidas = partes.split(",")
        desconocidas = set(pedidas) - {p.nombre for p in trabajo.partes}
        if desconocidas:
            raise SystemExit(f"Partes desconocidas: {sorted(desconocidas)}")
        trabajo.partes = [p for p in trabajo.partes if p.nombre in pedidas]
    return trabajo


def cmd_lanzar(
    cfg: dict,
    nombre: str,
    mantener: bool,
    partes: str | None,
    adjuntar: bool,
    video_desde: str | None = None,
) -> None:
    trabajo = filtrar_partes(trabajos()[nombre], partes)
    if video_desde:  # p. ej. «mac» cuando nadie va a estar para dar el permiso de Drive
        cfg = {**cfg, "video": {**cfg.get("video", {}), "origen": video_desde}}
    orq = Orquestador(cli_desde_config(cfg), cfg, trabajo, R)
    informe, error = {}, None
    try:
        informe = orq.adjuntar(mantener) if adjuntar else orq.lanzar(mantener=mantener)
    except BaseException as err:
        # 27-nov: cinco informes sin la causa del fallo; ahora queda escrita
        error = f"{type(err).__name__}: {str(err)[:500]}"
        raise
    finally:
        informe = informe or orq.informe
        informe["gpu"] = cfg["maquina"]["gpu"]
        if error:
            informe["error"] = error
        informe["fin"] = datetime.now().isoformat(timespec="seconds")
        ruta = trabajo.destino / f"informe_gpu_{datetime.now():%Y%m%d_%H%M}.json"
        trabajo.destino.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(informe, indent=1, ensure_ascii=False))
        logger.info("Informe: %s", ruta)


def cmd_seguimiento(nombre: str, partes: str | None = None) -> None:
    t = filtrar_partes(trabajos()[nombre], partes)
    subprocess.run(
        [sys.executable, str(R / t.script), *t.args, "--fase", "seguimiento",
         "--salida", str(t.destino), "--videos", ",".join(str(p.video) for p in t.partes),
         "--nombres", ",".join(p.nombre for p in t.partes)],
        check=True,
    )  # fmt: skip


def cmd_probar(cfg: dict) -> None:
    """Enciende una máquina con la GPU pedida y la apaga en seguida: ¿la da Google hoy?

    Solo `new` + `nvidia-smi -L` + `stop`: no sube vídeos ni modelo. Cuesta lo que tarda en
    encender (2-3 min, unas centésimas de CU). Si Google responde 503, sale con error sin gastar.
    """
    cli = cli_desde_config(cfg)
    gpu = cfg["maquina"]["gpu"]
    sesion = f"{cfg['maquina']['prefijo_sesion']}-prueba-{gpu.lower()}"
    print(f"Pidiendo una {gpu}…")
    try:
        cli.nueva(sesion, gpu)
    except ErrorColab as err:
        raise SystemExit(f"✗ {gpu} NO disponible ahora: {str(err)[-300:]}") from err
    try:
        print(cli.python(sesion, "import subprocess\nprint(subprocess.run(['nvidia-smi', "
                         "'-L'], capture_output=True, text=True).stdout)\n"))  # fmt: skip
        print(f"✓ {gpu} disponible")
    finally:
        cli.parar(sesion)
        print(f"apagada {sesion}")


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
    p.add_argument("--partes", default=None, help="solo estas partes, por comas")
    p.add_argument("--video-desde", choices=["drive", "mac"], default=None)
    p.add_argument(
        "--max-cu",
        type=float,
        default=None,
        help="tope de CU de ESTE lanzamiento (si no, el de configs/gpu_colab.yaml)",
    )
    p.add_argument(
        "--gpu",
        choices=GPUS,
        default=None,
        help="GPU de ESTE lanzamiento (si no, la de configs/gpu_colab.yaml: L4)",
    )
    p.add_argument(
        "--adjuntar",
        action="store_true",
        help="engancharse a la máquina que YA está detectando (no enciende ni sube nada)",
    )
    p = sub.add_parser("seguimiento")
    p.add_argument("trabajo", choices=sorted(trabajos()))
    p.add_argument("--partes", default=None, help="solo estas partes, por comas")
    p = sub.add_parser("probar")
    p.add_argument("--gpu", choices=GPUS, default=None)
    sub.add_parser("parar")
    a = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = con_gpu(yaml.safe_load(open(CONFIG)), getattr(a, "gpu", None))
    if a.cmd == "saldo":
        cmd_saldo(cfg)
    elif a.cmd == "lanzar":
        if a.max_cu is not None:  # solo puede BAJAR el tope del YAML, nunca subirlo
            tope = min(float(a.max_cu), float(cfg["presupuesto"]["max_cu"]))
            cfg = {**cfg, "presupuesto": {**cfg["presupuesto"], "max_cu": tope}}
        cmd_lanzar(cfg, a.trabajo, a.mantener, a.partes, a.adjuntar, a.video_desde)
    elif a.cmd == "seguimiento":
        cmd_seguimiento(a.trabajo, a.partes)
    elif a.cmd == "probar":
        cmd_probar(cfg)
    else:
        cmd_parar(cfg)


if __name__ == "__main__":
    main()
