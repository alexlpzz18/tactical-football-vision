"""Orquestador de un trabajo de GPU en Colab, vigilado desde el Mac. docs/gpu_colab.md.

Un trabajo = detectar varias partes de un partido. El ciclo, y por qué cada paso:

1. **Antes de encender nada** (gratis): el commit del Mac está subido a GitHub (la máquina
   clona ESE commit: lo que corre en la GPU es lo que hay en el historial), los vídeos y el modelo
   existen, y el saldo de unidades de cómputo (CU) da para el trabajo dejando la reserva.
2. **Se enciende la GPU** y se prepara: clon del repo en el commit exacto, dependencias, modelo.
3. **Por cada parte**: se sube el vídeo (con huella sha256 comprobada en los dos lados) y se
   lanza la detección EN SEGUNDO PLANO en la máquina. La subida del vídeo siguiente se solapa con la
   detección del anterior: la GPU no espera a la red más que en la primera parte.
4. **Vigilancia**: cada `sondeo_s`, el Mac lee el progreso (el log del procesador da frames y
   ms/frame), toca el latido del interruptor de hombre muerto y, cada `respaldo_cada_s`, se trae el
   checkpoint. Tras el primer checkpoint se PROYECTA el coste total; si pasa el presupuesto, se
   para.
5. **Al terminar cada parte** se descargan los cachés y se comprueba que están completos.
6. **Siempre** se apaga la máquina al final (`finally`), haya ido bien o mal.

Si algo se corta (el Mac, la red, la máquina), se vuelve a lanzar lo mismo: las partes con caché
completo en el Mac se saltan, y una parte con checkpoint en el Mac se sube y se REANUDA (el
procesador lo admite si la firma coincide: mismo vídeo, mismo modelo, misma configuración).
"""

from __future__ import annotations

import json
import logging
import pickle
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.cloud.colab_cli import ColabCLI, ErrorColab, sha256

logger = logging.getLogger(__name__)

# Línea de progreso que escribe `detectar_y_cachear` en cada checkpoint (processor.py).
RE_PROGRESO = re.compile(r"(\d+)/(\d+) frames \(\s*\d+ %\) · (\d+) ms/frame")
MARCA_FIN_PARTE = "✓ deteccion "


class TrabajoAbortado(RuntimeError):
    """Se para a propósito (presupuesto, colgado, entrada mala). La máquina se apaga igual."""


@dataclass(frozen=True)
class Progreso:
    hechos: int  # frames procesados (con el muestreo: 1 de cada 3 originales)
    total: int
    ms_por_frame: float


def leer_progreso(log: str) -> Progreso | None:
    """La ÚLTIMA línea de progreso del log, o None si aún no hay checkpoint."""
    encontradas = RE_PROGRESO.findall(log)
    if not encontradas:
        return None
    h, t, ms = encontradas[-1]
    return Progreso(int(h), int(t), float(ms))


def proyectar_cu(
    frames_pendientes: int, ms_por_frame: float, tarifa_hora: float
) -> float:
    """CU que costará lo que falta, al ritmo medido y con la tarifa real de la cuenta."""
    horas = frames_pendientes * ms_por_frame / 1000 / 3600
    return horas * tarifa_hora


def commit_subido(raiz: Path, git: Callable = subprocess.run) -> str:
    """El commit actual, solo si está en GitHub. Si no, la máquina no podría clonarlo."""

    def run(*args):
        r = git(["git", "-C", str(raiz), *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise TrabajoAbortado(f"git {' '.join(args)} falló: {r.stderr}")
        return r.stdout.strip()

    commit = run("rev-parse", "HEAD")
    # refrescar lo que se sabe de GitHub; si la red falla, valen las referencias del último push
    # (11-nov: un corte de ssh a github.com abortó un lanzamiento que no tenía nada mal)
    r = git(
        ["git", "-C", str(raiz), "fetch", "-q", "origin"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        logger.warning(
            "git fetch falló (%s): se usan las referencias locales", r.stderr.strip()
        )
    if not run("branch", "-r", "--contains", commit):
        raise TrabajoAbortado(
            f"El commit {commit[:8]} no está en GitHub. Súbelo (git push) antes de lanzar: la "
            "máquina clona el repo y tiene que correr exactamente este código."
        )
    return commit


def cache_completo(ruta: Path) -> bool:
    """¿El caché de detecciones del Mac es el FINAL (no un checkpoint)?"""
    try:
        with open(ruta, "rb") as f:
            return bool(pickle.load(f).get("completo"))
    except (OSError, pickle.UnpicklingError, EOFError):
        return False


@dataclass
class Parte:
    nombre: str  # alevinb_p1
    video: Path  # en el Mac


@dataclass
class Trabajo:
    """Lo que cambia de un partido a otro. El resto (ciclo, vigilancia, apagado) es común."""

    nombre: str
    partes: list[Parte]
    script: str  # script del repo que detecta, con `--fase deteccion`
    args: list[str]  # argumentos fijos del script (p. ej. --imagen original)
    modelo: Path  # pesos del detector en el Mac (no están en el repo)
    destino: Path  # carpeta del Mac donde quedan los cachés
    frames_por_parte: dict[str, int] = field(
        default_factory=dict
    )  # para el presupuesto
    # cachés que produce cada parte, en el orden de descarga (el ancla de reanudación, AL FINAL)
    ficheros: tuple[str, ...] = ("colores", "cache")


class Orquestador:
    def __init__(
        self,
        cli: ColabCLI,
        cfg: dict,
        trabajo: Trabajo,
        raiz: Path,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.time,
        git: Callable = subprocess.run,
    ):
        self.cli, self.cfg, self.t, self.raiz = cli, cfg, trabajo, raiz
        self.dormir, self.reloj, self.git = dormir, reloj, git
        self.sesion = f"{cfg['maquina']['prefijo_sesion']}-{trabajo.nombre}"
        r = cfg["rutas_remotas"]
        self.r_repo, self.r_datos, self.r_salida = r["repo"], r["datos"], r["salida"]
        self.informe: dict = {"sesion": self.sesion, "partes": {}}
        self._ultimo_ck: dict[str, tuple[int, float]] = {}

    # ── utilidades remotas ────────────────────────────────────────────
    def _shell(self, comando: str, limite_s: int = 120) -> str:
        """Un comando CORTO de shell en la máquina, vía el kernel (sin configurar ssh)."""
        codigo = (
            "import subprocess, sys\n"
            f"r = subprocess.run({comando!r}, shell=True, capture_output=True, text=True)\n"
            "print(r.stdout[-4000:]); print(r.stderr[-4000:], file=sys.stderr)\n"
            "assert r.returncode == 0, f'código {r.returncode}'\n"
        )
        return self.cli.python(self.sesion, codigo, limite_s)

    def _en_segundo_plano(self, nombre: str, comando: str, cwd: str) -> None:
        """Lanza `comando` suelto en la máquina, SI NO ESTÁ YA CORRIENDO.

        Idempotente a propósito: `colab exec` puede colgarse y reintentarse (ColabCLI.python), y
        un reintento no puede lanzar dos detecciones ni dos vigías. Deja `<nombre>.pid`, el log
        en `<nombre>.log` y, al acabar, el código de salida en `<nombre>.rc`.
        """
        d = self.r_salida
        envoltorio = f"{comando}; echo $? > {d}/{nombre}.rc"
        self.cli.python(
            self.sesion,
            "import os, subprocess\n"
            f"pidf = '{d}/{nombre}.pid'\n"
            "def vivo(pid):\n"
            "    try:\n        return open(f'/proc/{pid}/stat').read().split()[2] != 'Z'\n"
            "    except OSError:\n        return False\n"
            "if os.path.exists(pidf) and vivo(int(open(pidf).read())):\n"
            "    print('ya corre')\n"
            "else:\n"
            f"    if os.path.exists('{d}/{nombre}.rc'): os.remove('{d}/{nombre}.rc')\n"
            f"    p = subprocess.Popen(['bash', '-c', {envoltorio!r}], cwd={cwd!r},\n"
            f"        start_new_session=True, stdout=open('{d}/{nombre}.log', 'ab'),\n"
            "        stderr=subprocess.STDOUT)\n"
            "    open(pidf, 'w').write(str(p.pid))\n",
        )

    def _esperar(self, nombre: str, limite_s: float, cada_s: float = 15) -> None:
        """Espera a que acabe un `_en_segundo_plano`; si sale con error, lanza con su log."""
        t0 = self.reloj()
        while self.reloj() - t0 < limite_s:
            self.dormir(cada_s)
            out = self.cli.python(
                self.sesion,
                "import os\n"
                f"rc = open('{self.r_salida}/{nombre}.rc').read().strip() "
                f"if os.path.exists('{self.r_salida}/{nombre}.rc') else ''\n"
                "print('RC=' + rc)\n",
            )
            rc = out.split("RC=")[-1].strip()
            if rc == "0":
                return
            if rc:
                log = self._shell(f"tail -c 3000 {self.r_salida}/{nombre}.log")
                raise TrabajoAbortado(f"`{nombre}` salió con {rc}:\n{log}")
        raise TrabajoAbortado(f"`{nombre}` no terminó en {limite_s:.0f} s")

    def _subir_comprobado(self, local: Path, remoto: str) -> None:
        """Sube en trozos y compara la huella: un vídeo truncado no da error, da basura."""
        t0 = self.reloj()
        self.cli.subir_grande(self.sesion, local, remoto)
        logger.info(
            "Subido %s (%.0f MB en %.0f s)",
            local.name, local.stat().st_size / 1e6, self.reloj() - t0,
        )  # fmt: skip

    # ── 1. antes de encender ──────────────────────────────────────────
    def comprobar_antes(self) -> str:
        faltan = [str(p.video) for p in self.t.partes if not p.video.exists()]
        if not self.t.modelo.exists():
            faltan.append(str(self.t.modelo))
        if faltan:
            raise TrabajoAbortado(f"Faltan en el Mac: {faltan}")
        commit = commit_subido(self.raiz, self.git)
        self._fijar_tope()
        self.informe["commit"] = commit
        return commit

    def _fijar_tope(self) -> None:
        saldo = self.cli.saldo()
        reserva = self.cfg["presupuesto"]["reserva_cu"]
        if saldo.unidades - self.cfg["presupuesto"]["max_cu"] < reserva:
            logger.warning(
                "Saldo %.1f CU: con el tope de %.0f quedaría por debajo de la reserva (%.0f). "
                "El tope efectivo baja a %.1f CU.",
                saldo.unidades,
                self.cfg["presupuesto"]["max_cu"],
                reserva,
                max(saldo.unidades - reserva, 0),
            )
        self.tope_cu = min(self.cfg["presupuesto"]["max_cu"], saldo.unidades - reserva)
        if self.tope_cu <= 0:
            raise TrabajoAbortado(
                f"Saldo {saldo.unidades:.1f} CU: no llega a la reserva ({reserva} CU)"
            )
        self.informe.update(saldo_inicial_cu=saldo.unidades, tope_cu=self.tope_cu)

    # ── 2. preparar la máquina ────────────────────────────────────────
    def preparar(self, commit: str) -> None:
        repo = self.cfg["repo"]
        self._shell(
            f"rm -rf {self.r_repo} && git clone -q {repo['url']} {self.r_repo} && "
            f"git -C {self.r_repo} checkout -q {commit} && "
            f"mkdir -p {self.r_datos} {self.r_salida} && nvidia-smi -L",
            limite_s=300,
        )
        # instalar tarda minutos: en segundo plano, y el modelo sube mientras tanto
        self._en_segundo_plano(
            "instalar", f"pip install -q -r {repo['requisitos']}", self.r_repo
        )
        rel = self.t.modelo.resolve().relative_to(self.raiz.resolve())
        self._subir_comprobado(self.t.modelo, f"{self.r_repo}/{rel}")
        self._esperar("instalar", limite_s=1500)
        self._arrancar_vigia()

    def _arrancar_vigia(self) -> None:
        tras = self.cfg["vigilancia"]["huerfana_tras_s"]
        self._en_segundo_plano(
            "vigia",
            f"python scripts/vigia_colab.py --pid-fichero {self.r_salida}/trabajo.pid "
            f"--latido {self.r_salida}/latido --tras-s {tras}",
            self.r_repo,
        )

    # ── 3-5. una parte ────────────────────────────────────────────────
    def _rutas(self, parte: Parte) -> dict:
        return {
            "video": f"{self.r_datos}/{parte.nombre}.mp4",
            "cache": f"{self.r_salida}/cache_{parte.nombre}.pkl",
            "colores": f"{self.r_salida}/colores_{parte.nombre}.pkl",
            "log": f"{self.r_salida}/{parte.nombre}.log",
        }

    def _lanzar_en_segundo_plano(self, parte: Parte, con_chequeo: bool) -> None:
        r = self._rutas(parte)
        argv = [
            "python", self.t.script, *self.t.args, "--fase", "deteccion",
            "--salida", self.r_salida, "--videos", r["video"], "--nombres", parte.nombre,
        ]  # fmt: skip
        if not con_chequeo:
            argv.append("--sin-chequeo")
        # el log de la parte es el que lee el sondeo; `trabajo.pid` es el que mira el vigía
        self._en_segundo_plano(
            "trabajo", " ".join(shlex.quote(a) for a in argv) + f" >> {r['log']} 2>&1",
            self.r_repo,
        )  # fmt: skip

    def _sondear(self, parte: Parte) -> dict:
        """Una pregunta a la máquina: ¿vive el proceso?, cola del log. Y toca el latido."""
        r = self._rutas(parte)
        salida = self.cli.python(
            self.sesion,
            "import json, os, pathlib\n"
            f"pathlib.Path('{self.r_salida}/latido').touch()\n"
            f"pid = int(open('{self.r_salida}/trabajo.pid').read())\n"
            "try:\n    os.kill(pid, 0); est = open(f'/proc/{pid}/stat').read().split()[2]\n"
            "    vivo = est != 'Z'\nexcept OSError:\n    vivo = False\n"
            f"log = open('{r['log']}', errors='replace').read()[-6000:]\n"
            # uso de la GPU en este instante: si va baja, la GPU espera a la CPU (vídeo, color)
            "import subprocess\n"
            "gpu = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used',"
            " '--format=csv,noheader'], capture_output=True, text=True).stdout.strip()\n"
            # el progreso se lee del CHECKPOINT en disco, no solo del log: el script remoto no
            # tenía `logging` configurado y las líneas de progreso del procesador no salían
            "import pickle, time\n"
            f"ck = '{r['cache']}'\n"
            "try:\n    n = len(pickle.load(open(ck, 'rb'))['cache']); mt = os.path.getmtime(ck)\n"
            "except Exception:\n    n, mt = 0, 0.0\n"
            f"inicio = os.path.getmtime('{self.r_salida}/trabajo.pid')\n"
            "print(json.dumps({'vivo': vivo, 'log': log, 'gpu': gpu, 'n': n, 'mt': mt,"
            " 'inicio': inicio}))\n",
        )
        return json.loads(salida.strip().splitlines()[-1])

    def _bajar_caches(self, parte: Parte) -> None:
        """Trae los cachés de una parte al Mac, como PAREJA coherente aunque el detector siga.

        El procesador escribe colores primero y detecciones al final (el ancla). Para que la pareja
        bajada no tenga detecciones POR DELANTE de los colores (frames sin color al reanudar), la
        foto se toma en orden inverso: primero el ancla, luego los colores, que solo pueden ser
        iguales o más nuevos. Y se colocan en el orden del procesador: el ancla, la última.
        """
        r = self._rutas(parte)
        temporales = {}
        for clave in reversed(self.t.ficheros):  # foto: el ancla primero
            destino = self.t.destino / Path(r[clave]).name
            temporales[clave] = destino.with_suffix(".descargando")
            self.cli.bajar_grande(
                self.sesion, r[clave], temporales[clave]
            )  # con huella
        for clave in self.t.ficheros:  # colocar: el ancla al final
            temporales[clave].replace(self.t.destino / Path(r[clave]).name)

    def _vigilar(self, parte: Parte, ya_gastado_cu: float, tarifa: float) -> None:
        vig = self.cfg["vigilancia"]
        ultimo_respaldo = ultimo_avance = self.reloj()
        hechos_antes, proyectado = -1, False
        while True:
            self.dormir(vig["sondeo_s"])
            try:
                s = self._sondear(parte)
            except (
                ErrorColab
            ) as err:  # un sondeo fallido no mata el trabajo; tres seguidos sí
                logger.warning("Sondeo fallido: %s", str(err)[:300])
                self._fallos = getattr(self, "_fallos", 0) + 1
                if self._fallos >= 3:
                    raise
                continue
            self._fallos = 0
            if MARCA_FIN_PARTE + parte.nombre in s["log"]:
                logger.info("%s: detección terminada", parte.nombre)
                return
            if not s["vivo"]:
                raise TrabajoAbortado(
                    f"{parte.nombre}: el proceso murió sin terminar. Cola del log:\n"
                    + s["log"][-2000:]
                )
            p = leer_progreso(s["log"]) or self._progreso_checkpoint(parte, s)
            if p and p.hechos != hechos_antes:
                hechos_antes, ultimo_avance = p.hechos, self.reloj()
                logger.info(
                    "%s: %d/%d frames · %.0f ms/frame · GPU %s",
                    parte.nombre, p.hechos, p.total, p.ms_por_frame, s.get("gpu", "?"),
                )  # fmt: skip
                self.informe.setdefault("uso_gpu", []).append(s.get("gpu"))
                if not proyectado:
                    proyectado = True
                    self._comprobar_presupuesto(parte, p, ya_gastado_cu, tarifa)
            if self.reloj() - ultimo_avance > vig["sin_progreso_s"]:
                raise TrabajoAbortado(
                    f"{parte.nombre}: {vig['sin_progreso_s']} s sin avanzar el checkpoint"
                )
            if self.reloj() - ultimo_respaldo > vig["respaldo_cada_s"] and p:
                logger.info("Respaldo del checkpoint de %s en el Mac", parte.nombre)
                self._bajar_caches(parte)
                ultimo_respaldo = self.reloj()

    def _progreso_checkpoint(self, parte: Parte, s: dict) -> Progreso | None:
        """Progreso a partir del checkpoint en disco: frames cacheados y su hora de escritura.

        El ritmo sale de dos checkpoints seguidos (diferencia de frames y de hora, ambas de la
        máquina); con uno solo, desde el arranque del proceso (incluye cargar el modelo: algo
        pesimista, que para un presupuesto es el lado bueno).
        """
        n, mt = int(s.get("n") or 0), float(s.get("mt") or 0)
        if n <= 0:
            return None
        previo = self._ultimo_ck.get(parte.nombre)
        if previo and n > previo[0] and mt > previo[1]:
            ms = (mt - previo[1]) / (n - previo[0]) * 1000
        else:
            inicio = s.get("inicio")
            ms = (mt - float(mt if inicio is None else inicio)) / n * 1000
        if not previo or n != previo[0]:
            self._ultimo_ck[parte.nombre] = (n, mt)
        total = self.t.frames_por_parte.get(parte.nombre, n)
        return Progreso(n, total, max(ms, 0.0))

    def _comprobar_presupuesto(
        self, parte: Parte, p: Progreso, ya_gastado_cu: float, tarifa: float
    ) -> None:
        """Con el ritmo REAL del primer checkpoint: ¿cabe todo lo que queda en el tope?"""
        pendientes = p.total - p.hechos
        siguientes = False
        for otra in self.t.partes:
            if otra.nombre == parte.nombre:
                siguientes = True
                continue
            if siguientes and not cache_completo(
                self.t.destino / f"cache_{otra.nombre}.pkl"
            ):
                pendientes += self.t.frames_por_parte.get(otra.nombre, p.total)
        cu = ya_gastado_cu + proyectar_cu(pendientes, p.ms_por_frame, tarifa)
        horas = pendientes * p.ms_por_frame / 3.6e6
        self.informe["proyeccion"] = {
            "ms_por_frame": p.ms_por_frame,
            "frames_pendientes": pendientes,
            "horas": round(horas, 2),
            "cu_total": round(cu, 1),
            "tarifa_cu_hora": tarifa,
        }
        logger.info(
            "PROYECCIÓN: %.0f ms/frame · %d frames pendientes · %.1f h · %.1f CU (tope %.1f)",
            p.ms_por_frame, pendientes, horas, cu, self.tope_cu,
        )  # fmt: skip
        if cu > self.tope_cu:
            raise TrabajoAbortado(
                f"Proyección {cu:.1f} CU > tope {self.tope_cu:.1f} CU. Se para y se guarda el "
                "checkpoint; sube `presupuesto.max_cu` si lo quieres igualmente."
            )

    # ── el ciclo entero ───────────────────────────────────────────────
    def lanzar(self, mantener: bool = False) -> dict:
        self.t.destino.mkdir(parents=True, exist_ok=True)
        pendientes = [
            p
            for p in self.t.partes
            if not cache_completo(self.t.destino / f"cache_{p.nombre}.pkl")
        ]
        hechas = [p.nombre for p in self.t.partes if p not in pendientes]
        if hechas:
            logger.info("Ya completas en el Mac, se saltan: %s", hechas)
        if not pendientes:
            return self.informe
        commit = self.comprobar_antes()
        t_encendido = self.reloj()
        logger.info("Encendiendo %s (%s)", self.sesion, self.cfg["maquina"]["gpu"])
        self.cli.nueva(self.sesion, self.cfg["maquina"]["gpu"])
        tarifa = 0.0
        try:
            if self._drive():
                self._montar_drive()
            self.preparar(commit)
            tarifa = self.cli.saldo().tarifa_hora
            self.informe["tarifa_cu_hora"] = tarifa
            subida = self._subir_parte_en_hilo(pendientes[0])
            for i, parte in enumerate(pendientes):
                subida.join()
                if subida.error:
                    raise subida.error
                if i + 1 < len(pendientes):  # la siguiente sube mientras esta detecta
                    subida = self._subir_parte_en_hilo(pendientes[i + 1])
                gastado = (self.reloj() - t_encendido) / 3600 * tarifa
                self._lanzar_en_segundo_plano(parte, con_chequeo=(i == 0))
                t0 = self.reloj()
                self._vigilar(parte, gastado, tarifa)
                self._bajar_caches(parte)
                destino = self.t.destino / f"cache_{parte.nombre}.pkl"
                if not cache_completo(destino):
                    raise TrabajoAbortado(f"{destino.name} llegó sin marca de completo")
                self.informe["partes"][parte.nombre] = {
                    "minutos": round((self.reloj() - t0) / 60, 1)
                }
            subida.join()
        except BaseException:
            # lo que haya avanzado queda en el Mac para reanudar
            for parte in pendientes:
                try:
                    self._bajar_caches(parte)
                    logger.info("Checkpoint de %s guardado en el Mac", parte.nombre)
                except Exception:  # noqa: BLE001 — puede no haber empezado esa parte
                    pass
            raise
        finally:
            horas = (self.reloj() - t_encendido) / 3600
            self.informe["horas_encendida"] = round(horas, 2)
            self.informe["cu_estimadas"] = round(horas * tarifa, 2)
            if mantener:
                logger.warning(
                    "La máquina %s SIGUE ENCENDIDA (--mantener)", self.sesion
                )
            else:
                self._apagar()
                logger.info("Máquina %s apagada (%.2f h encendida)", self.sesion, horas)
        return self.informe

    def _apagar(self, intentos: int = 5) -> None:
        """Apaga la máquina, reintentando: un corte de red en este momento la dejaba encendida.

        11-nov: el Mac perdió la red unos minutos, el `stop` se colgó y la L4 siguió gastando hasta
        apagarla a mano. Se reintenta con esperas crecientes; si aun así no se puede, se avisa a
        gritos con el comando exacto, porque ya solo queda el interruptor de hombre muerto.
        """
        for i in range(1, intentos + 1):
            try:
                self.cli.parar(self.sesion)
                return
            except ErrorColab as err:
                logger.warning(
                    "No se pudo apagar (intento %d/%d): %s", i, intentos, err
                )
                self.dormir(30 * i)
        logger.error(
            "LA MÁQUINA %s PUEDE SEGUIR ENCENDIDA. Apágala con: "
            "python scripts/gpu_colab.py parar",
            self.sesion,
        )

    def _montar_drive(self, intentos: int = 2) -> bool:
        """Monta Drive y COMPRUEBA que quedó montado (la CLI sale bien aunque falle).

        11-nov: «mount failed» dentro de la máquina y la CLI siguió como si nada (el Enter llegó
        después del tiempo de espera de Google). Si tras dos intentos no está, no se para: los
        vídeos se suben desde el Mac, que es más lento pero no depende de nadie.
        """
        for i in range(1, intentos + 1):
            logger.info(
                "Montando Drive (%d/%d): ACEPTA el permiso en el navegador y pulsa Enter "
                "AQUÍ en cuanto lo aceptes (si tardas, Google da el montaje por caducado)",
                i,
                intentos,
            )
            try:
                self.cli.montar_drive(self.sesion)
            except ErrorColab as err:
                logger.warning("drivemount falló: %s", err)
            out = self.cli.python(
                self.sesion,
                "import os\nprint('MONTADO=' + str(os.path.ismount('/content/drive')))\n",
            )
            if "MONTADO=True" in out:
                logger.info("Drive montado")
                return True
        logger.warning("Drive no se montó: los vídeos se subirán desde el Mac")
        self.cfg = {**self.cfg, "video": {**self.cfg["video"], "origen": "mac"}}
        return False

    def _drive(self) -> bool:
        return (self.cfg.get("video") or {}).get("origen") == "drive"

    def _copiar_de_drive(self, parte: Parte, destino: str) -> bool:
        """Copia el vídeo de Drive al disco de la máquina. False si en Drive no está.

        Medido el 11-nov: la máquina lee de Drive a ~57 MB/s y desde el Mac se sube a ~6 MB/s. Se
        copia al disco local (no se lee de Drive en directo) para que la ruta del vídeo sea la
        misma que si se hubiera subido: la firma del checkpoint la incluye, y así se puede
        reanudar venga de donde venga. Y se compara la huella con la del Mac: el de Drive tiene
        que ser EL MISMO fichero que se cortó y verificó, no otro con el mismo nombre.
        """
        origen = f"{self.cfg['video']['carpeta_drive']}/{parte.video.name}"
        t0 = self.reloj()
        out = self._shell(
            f"if [ -f {shlex.quote(origen)} ]; then cp {shlex.quote(origen)} "
            f"{shlex.quote(destino)} && echo COPIADO; else echo NO_ESTA; fi",
            limite_s=600,
        )
        if "COPIADO" not in out:
            logger.info("%s no está en Drive: se sube desde el Mac", parte.video.name)
            return False
        if self.cli.sha_remoto(self.sesion, destino) != sha256(parte.video):
            raise TrabajoAbortado(
                f"{parte.video.name}: el de Drive NO es el mismo fichero que el del Mac"
            )
        logger.info(
            "Copiado de Drive %s (%.0f MB en %.0f s)",
            parte.video.name, parte.video.stat().st_size / 1e6, self.reloj() - t0,
        )  # fmt: skip
        return True

    def adjuntar(self, mantener: bool = False) -> dict:
        """Se engancha a una máquina que YA está detectando: vigila, descarga y apaga.

        Para cuando el vigilante del Mac se cae (o hay que cambiarlo) sin querer perder lo que la
        GPU lleva hecho: el proceso remoto sigue solo y el vigía de la máquina la mantiene
        encendida mientras corra. Aquí no se enciende, no se prepara ni se sube nada.
        """
        pendientes = [
            p for p in self.t.partes
            if not cache_completo(self.t.destino / f"cache_{p.nombre}.pkl")
        ]  # fmt: skip
        self.t.destino.mkdir(parents=True, exist_ok=True)
        self._fijar_tope()
        tarifa = self.cli.saldo().tarifa_hora
        t0 = self.reloj()
        logger.info(
            "Enganchado a %s; vigilando %s", self.sesion, [p.nombre for p in pendientes]
        )
        try:
            for parte in pendientes:
                self._vigilar(parte, 0.0, tarifa)
                self._bajar_caches(parte)
                destino = self.t.destino / f"cache_{parte.nombre}.pkl"
                if not cache_completo(destino):
                    raise TrabajoAbortado(f"{destino.name} llegó sin marca de completo")
                self.informe["partes"][parte.nombre] = {"descargada": True}
        except BaseException:
            for parte in pendientes:
                try:
                    self._bajar_caches(parte)
                    logger.info("Checkpoint de %s guardado en el Mac", parte.nombre)
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            horas = (self.reloj() - t0) / 3600
            self.informe["horas_vigiladas"] = round(horas, 2)
            if mantener:
                logger.warning(
                    "La máquina %s SIGUE ENCENDIDA (--mantener)", self.sesion
                )
            else:
                self._apagar()
                logger.info("Máquina %s apagada", self.sesion)
        return self.informe

    def _subir_parte_en_hilo(self, parte: Parte) -> threading.Thread:
        """Sube el vídeo (y el checkpoint del Mac, si lo hay) sin bloquear la vigilancia."""

        def subir():
            try:
                r = self._rutas(parte)
                if not (self._drive() and self._copiar_de_drive(parte, r["video"])):
                    self._subir_comprobado(parte.video, r["video"])
                locales = {k: self.t.destino / Path(r[k]).name for k in self.t.ficheros}
                if all(f.exists() for f in locales.values()):
                    logger.info(
                        "Hay checkpoint de %s en el Mac: se REANUDA", parte.nombre
                    )
                    for k, f in locales.items():  # mismo orden: el ancla al final
                        self._subir_comprobado(f, r[k])
            except (
                BaseException
            ) as err:  # noqa: BLE001 — se relanza en el hilo principal
                hilo.error = err

        hilo = threading.Thread(
            target=subir, name=f"subida-{parte.nombre}", daemon=True
        )
        hilo.error = None
        hilo.start()
        return hilo
