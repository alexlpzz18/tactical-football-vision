#!/usr/bin/env python
"""¿Con los interruptores apagados, esta rama da EXACTAMENTE lo mismo que `main`?
(docs/plan_literatura.md)

Corre el `desde_cache` de producción con los configs de `main` (los YAML del worktree de main) dos
veces: con el código de `main` y con el de esta rama. Los dos leen los mismos cachés de `data/` y
escriben en carpetas nuevas de `outputs/`. Compara los CSV byte a byte (SHA-256).

Uso:
    python scripts/identidad_con_main.py --main /ruta/al/worktree_de_main \\
        --configs configs/processor_benja.yaml configs/processor.yaml
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent

HIJO = r"""
import sys, yaml, logging
from pathlib import Path
codigo, datos, config, salida = map(Path, sys.argv[1:5])
sys.path.insert(0, str(codigo))
logging.basicConfig(level=logging.ERROR)
from src.tracking_data.processor import procesar_desde_cache
cfg = yaml.safe_load(open(config))
cfg["modo"] = "desde_cache"
base_cfg = config.parent.parent  # raíz del worktree de main (los configs relativos son de allí)
# Los configs que el processor carga POR DEFECTO (sin clave en el YAML) se resuelven relativos a
# la carpeta del código: hay que fijarlos a los de main, o cada lado leería los suyos (pasó el
# 19-nov con el config de equipos de Villaviciosa).
defectos = {
    "config_tracking": "configs/tracking.yaml",
    "config_equipos": "configs/team_classification.yaml",
}
for k, defecto in defectos.items():
    v = cfg.get(k, defecto)
    cfg[k] = v if Path(v).is_absolute() else str(base_cfg / v)
for k, v in list(cfg["rutas"].items()):
    if isinstance(v, str) and v.startswith("data/"):
        cfg["rutas"][k] = str(datos / v)
cfg["rutas"]["salida_csv"] = str(salida / "posiciones.csv")
cfg["rutas"]["salida_meta"] = str(salida / "meta.json")
salida.mkdir(parents=True, exist_ok=True)
procesar_desde_cache(cfg)
"""


def sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--main", type=Path, required=True, help="worktree de main")
    ap.add_argument("--configs", nargs="+", required=True, help="relativos a la raíz")
    ap.add_argument(
        "--salida", type=Path, default=R / "outputs/literatura/identidad_con_main"
    )
    a = ap.parse_args()
    resultado = {}
    for config in a.configs:
        nombre = Path(config).stem
        csvs = {}
        for lado, codigo in (("main", a.main), ("rama", R)):
            sal = a.salida / nombre / lado
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    HIJO,
                    str(codigo),
                    str(R),
                    str(a.main / config),
                    str(sal),
                ],
                check=True,
                cwd=str(codigo),
            )
            csvs[lado] = sal / "posiciones.csv"
        iguales = sha(csvs["main"]) == sha(csvs["rama"])
        resultado[nombre] = {
            "identico_byte_a_byte": iguales,
            "sha_main": sha(csvs["main"])[:16],
            "sha_rama": sha(csvs["rama"])[:16],
        }
        print(nombre, resultado[nombre], flush=True)
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "resultado.json").write_text(json.dumps(resultado, indent=1))
    if not all(r["identico_byte_a_byte"] for r in resultado.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
