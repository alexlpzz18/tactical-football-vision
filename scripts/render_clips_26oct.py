#!/usr/bin/env python
"""Tres clips con cajas de `main` tal cual (pista del árbitro encendida en F7). SOLO renderiza.

docs/diagnostico_26oct_b.md, bloque B. Necesita la captura de `scripts/diag26b.py capturar`
(identidades, voto de cada identidad, etiqueta final por observación y pista del árbitro).

- Frames SIEMPRE por el lector común (`src/utils/video_ffmpeg.py`, el ffmpeg CLI = producción).
- Codifica con el ffmpeg CLI en h264 (libx264), 1280 px de ancho, 10 fps (los frames procesados).
- El balón es el que elige `main` (`generar_video_detecciones.balon_activo`): sin máscara ni
  recorte de campo.

Uso:
    python scripts/render_clips_26oct.py --captura outputs/diagnostico_26oct_b \\
        --salida outputs/clips_26oct
"""

import argparse
import importlib.util
import json
import pickle
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml
from PIL import Image, ImageDraw, ImageFont

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
CONFIG = R / "configs/processor_benja_parte_entera.yaml"
CAMPO = R / "configs/campo_benja.yaml"
CACHE_BALON = R / "data/tracking_benja/cache_balon_p1.pkl"
FPS = 29.97002997002997
LARGO, ANCHO = 62.0, 40.0
DURACION_S = 75.0  # ventanas 2 y 3
ANCHO_SALIDA = 1280
REGION_CAMPO_AL_LADO = (940.0, 603.0)  # cx <, cy < (23-oct e): SOLO para describir
# BGR
COLOR = {
    "A": (235, 187, 183),
    "B": (6, 90, 245),
    "portero_A": (235, 187, 183),
    "portero_B": (6, 90, 245),
    "otro": (0, 230, 255),
    "staff": (150, 150, 150),
}
COLOR_BALON = {"dentro": (60, 220, 60), "fuera": (40, 40, 255)}


def _mod(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def reloj(frame: int) -> str:
    t = frame / FPS
    r = t + 93
    return f"archivo {int(t // 60)}:{t % 60:04.1f}   ·   reproductor {int(r // 60)}:{r % 60:04.1f}"


def equipo(etiqueta) -> str:
    e = str(etiqueta)
    return e.replace("portero_", "") if e.startswith("portero_") else e


def fuera_m(mx: float, my: float) -> float:
    return float(np.hypot(max(0.0, -mx, mx - LARGO), max(0.0, -my, my - ANCHO)))


def _fuente(tam: int):
    for ruta in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default()


# ── datos ─────────────────────────────────────────────────────────────────────────────────────


def cargar(captura: Path) -> dict:
    cap = pickle.load(open(captura / "captura_main.pkl", "rb"))
    filtrado = {e["frame_idx"]: e["dets"] for e in cap["cache"]}
    ident_de = {}
    for i, obs in enumerate(cap["identidades"], start=1):
        for f, j in obs:
            ident_de[(f, j)] = i
    voto = {int(i): str(e) for i, e in cap["voto"].items()}
    final = cap["final"]
    csv = pd.read_csv(captura / "posiciones_main.csv")
    gv = _mod(R / "scripts/generar_video_detecciones.py", "gv")
    balon = gv.balon_activo(CACHE_BALON, captura / "posiciones_main.csv", CAMPO)
    return {
        "filtrado": filtrado,
        "ident_de": ident_de,
        "voto": voto,
        "final": final,
        "pista": cap["pista"],
        "csv": csv,
        "balon": balon,
    }


def etiqueta_obs(d: dict, i: int, f: int) -> str:
    return str(d["final"].get((i, f), d["voto"].get(i, "otro")))


def recuento(csv: pd.DataFrame) -> pd.DataFrame:
    """A / B / otro por frame: filas REALES dentro del campo (porteros en su equipo)."""
    r = csv[(csv.es_real == 1) & csv.x_m.between(0, LARGO) & csv.y_m.between(0, ANCHO)]
    c = (
        r.assign(e=r.etiqueta.map(equipo).where(lambda s: s.isin(["A", "B"]), "otro"))
        .groupby(["frame", "e"])
        .size()
        .unstack(fill_value=0)
    )
    for k in ("A", "B", "otro"):
        if k not in c:
            c[k] = 0
    return c


def balon_en(d: dict, f: int):
    """El balón activo más cercano en ±2 frames (el balón va a 1 de cada 2, los jugadores a 1/3)."""
    for delta in (0, -1, 1, -2, 2):
        if f + delta in d["balon"]:
            return d["balon"][f + delta]
    return None


def estado_balon(sel) -> tuple[str, float | None]:
    if sel is None:
        return "sin_deteccion", None
    det = sel[0]
    return ("fuera" if fuera_m(float(det[0]), float(det[1])) > 0 else "dentro"), float(
        det[6]
    )


# ── ventanas ──────────────────────────────────────────────────────────────────────────────────


def _rango(t0: float, t1: float) -> tuple[int, int]:
    return int(round(t0 * FPS)), int(round(t1 * FPS))


def ventanas(d: dict) -> dict:
    """Las tres ventanas con las reglas del informe (sin solaparse)."""
    csv = d["csv"]
    fin_s = csv.frame.max() / FPS
    v1 = (840.0, 930.0)
    # 2: parejas (A, B) reales a ≤ 2 m, sumadas por frame
    r = csv[(csv.es_real == 1)]
    pares = {}
    for f, g in r.groupby("frame"):
        eq = g.etiqueta.map(equipo).to_numpy()
        xy = g[["x_m", "y_m"]].to_numpy()
        a, b = xy[eq == "A"], xy[eq == "B"]
        if len(a) and len(b):
            dd = np.hypot(a[:, None, 0] - b[None, :, 0], a[:, None, 1] - b[None, :, 1])
            pares[f] = int((dd <= 2.0).sum())
    serie_p = pd.Series(pares)
    # 3: frames de la pista con la caja del árbitro ≥ 60 px de alto
    claros = []
    for f, j in d["pista"].items():
        det = d["filtrado"][f][j]
        if det[5] - det[3] >= 60:
            claros.append(f)
    serie_c = pd.Series(1, index=sorted(claros))

    def mejor(serie, prohibidas):
        mejor_t, mejor_v = None, -1
        for t0 in np.arange(0, fin_s - DURACION_S, 5.0):
            t1 = t0 + DURACION_S
            if any(not (t1 <= a or t0 >= b) for a, b in prohibidas):
                continue
            a, b = _rango(t0, t1)
            v = float(serie[(serie.index >= a) & (serie.index < b)].sum())
            if v > mejor_v:
                mejor_t, mejor_v = (float(t0), float(t1)), v
        return mejor_t, mejor_v

    v2, n2 = mejor(serie_p, [v1])
    v3, n3 = mejor(serie_c, [v1, v2])
    return {
        "1_balon_14_16": {
            "s": v1,
            "regla": "14:00-15:30, ventana de control del balón",
        },
        "2_cruces": {"s": v2, "parejas_A_B_a_2m": n2},
        "3_arbitro": {"s": v3, "frames_pista_caja_60px": n3},
    }


# ── dibujo ────────────────────────────────────────────────────────────────────────────────────


def _se_solapan(a, b) -> bool:
    """¿Se tocan dos rectángulos (x1, y1, x2, y2)?"""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def colocar_etiqueta(
    cx: int, cy: int, radio: int, ancho: int, alto: int, ocupadas
) -> tuple:
    """Esquina (x, y) para la etiqueta del balón que no pise ninguna de las `ocupadas`.

    Antes iba siempre a la derecha del círculo y pisaba «ÁRBITRO» cuando el balón estaba a sus
    pies. Se prueba, en orden: encima del círculo, a la derecha, a la izquierda y debajo; si las
    cuatro chocan, se sube la de encima de alto en alto hasta encontrar hueco (máximo 10 pasos).
    """
    margen = 4
    candidatas = [
        (cx - ancho // 2, cy - radio - margen - alto),  # encima
        (cx + radio + margen, cy - alto // 2),  # derecha
        (cx - radio - margen - ancho, cy - alto // 2),  # izquierda
        (cx - ancho // 2, cy + radio + margen),  # debajo
    ]
    x0, y0 = candidatas[0]
    candidatas += [(x0, y0 - k * (alto + margen)) for k in range(1, 11)]
    for x, y in candidatas:
        if not any(_se_solapan((x, y, x + ancho, y + alto), o) for o in ocupadas):
            return x, y
    return candidatas[0]


def _caja_texto(x, y, t, fuente) -> tuple:
    """Rectángulo que ocupa un texto de PIL (con el borde de 2 px del trazo)."""
    b = fuente.getbbox(t)
    return (x + b[0] - 2, y + b[1] - 2, x + b[2] + 2, y + b[3] + 2)


def dibujar(img, f: int, d: dict, cuenta, fuentes):
    textos = []  # (x, y, texto, color RGB, fuente) con PIL al final: tildes y «≠»
    dets = d["filtrado"].get(f, [])
    j_arb = d["pista"].get(f)
    for j, det in enumerate(dets):
        x1, y1, x2, y2 = (int(round(float(v))) for v in det[2:6])
        i = d["ident_de"].get((f, j))
        if i is None:
            cv2.rectangle(img, (x1, y1), (x2, y2), (90, 90, 90), 1)
            continue
        et = etiqueta_obs(d, i, f)
        col = COLOR.get(et, (255, 255, 255))
        grosor = 3 if et.startswith("portero_") else 2
        cv2.rectangle(img, (x1, y1), (x2, y2), col, grosor)
        texto = f"{equipo(et)} {i}" + (" POR" if et.startswith("portero_") else "")
        textos.append((x1, y1 - 20, texto, col[::-1], fuentes["peq"]))
        if et != d["voto"].get(i, "otro"):
            # la etiqueta del instante difiere del voto de su identidad
            cv2.rectangle(img, (x2 - 14, y1), (x2, y1 + 14), (255, 0, 255), -1)
            textos.append((x2 + 2, y1 - 2, "≠", (255, 0, 255), fuentes["peq"]))
        if j == j_arb:
            cv2.rectangle(img, (x1 - 5, y1 - 5), (x2 + 5, y2 + 5), (255, 255, 255), 5)
            textos.append((x1 - 4, y2 + 6, "ÁRBITRO", (255, 255, 255), fuentes["med"]))
    # balón
    sel = balon_en(d, f)
    estado, conf = estado_balon(sel)
    if sel is not None:
        det = sel[0]
        cx, cy = int((det[2] + det[4]) / 2), int((det[3] + det[5]) / 2)
        cv2.circle(img, (cx, cy), 16, COLOR_BALON[estado], 3)
        nombre = (
            "balón dentro del campo" if estado == "dentro" else "balón proyectado FUERA"
        )
        t = f"{nombre} {conf:.2f}"
        b = fuentes["peq"].getbbox(t)
        ocupadas = [_caja_texto(x, y, tt, fu) for x, y, tt, _, fu in textos]
        x, y = colocar_etiqueta(cx, cy, 16, b[2] - b[0] + 4, b[3] - b[1] + 4, ocupadas)
        textos.append((x, y, t, COLOR_BALON[estado][::-1], fuentes["peq"]))
    # cabecera: reloj, contador, bandera B > 7, balón
    a, b, o = (int(cuenta.get(k, 0)) for k in ("A", "B", "otro"))
    cv2.rectangle(img, (0, 0), (img.shape[1], 52), (0, 0, 0), -1)
    textos.append((10, 10, f"f{f}   {reloj(f)}", (255, 255, 255), fuentes["med"]))
    textos.append(
        (900, 10, f"A {a}   B {b}   otro {o}", (255, 255, 255), fuentes["med"])
    )
    if b > 7:
        textos.append((1180, 10, "B > 7", (255, 60, 60), fuentes["med"]))
    txt_b = (
        "balón: sin detección"
        if estado == "sin_deteccion"
        else f"balón: {estado} ({conf:.2f})"
    )
    textos.append((1400, 10, txt_b, (255, 255, 255), fuentes["med"]))
    pil = Image.fromarray(img[:, :, ::-1])
    dr = ImageDraw.Draw(pil)
    for x, y, t, c, fu in textos:
        dr.text((x, y), t, font=fu, fill=c, stroke_width=2, stroke_fill=(0, 0, 0))
    return np.asarray(pil)[:, :, ::-1].copy()


def render(nombre: str, t0: float, t1: float, d: dict, cuentas, salida: Path) -> dict:
    from src.tracking_data.processor import _build_camera_matrix, _corregir_distorsion
    from src.utils.video_ffmpeg import leer_frames_ffmpeg, tamano_video

    cfg = yaml.safe_load(open(CONFIG))
    video = R / cfg["rutas"]["video"]
    w, h = tamano_video(video)
    K = _build_camera_matrix(w, h)
    dist = np.array([cfg["distorsion"]["k1"], cfg["distorsion"]["k2"], 0, 0, 0], float)
    a, b = _rango(t0, t1)
    frames = [f for f in sorted(d["filtrado"]) if a <= f < b]
    ruta = salida / f"{nombre}.mp4"
    ff = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{w}x{h}",
            "-r",
            "10",
            "-i",
            "-",
            "-vf",
            f"scale={ANCHO_SALIDA}:-2",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(ruta),
        ],
        stdin=subprocess.PIPE,
    )
    fuentes = {"peq": _fuente(20), "med": _fuente(28)}
    n = 0
    for f, img in leer_frames_ffmpeg(video, frames):
        img = _corregir_distorsion(img, K, dist)
        cuenta = cuentas.loc[f].to_dict() if f in cuentas.index else {}
        ff.stdin.write(dibujar(img, f, d, cuenta, fuentes).tobytes())
        n += 1
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg falló escribiendo {ruta}")
    # se RELEE el fichero antes de dar el ✓ (la lección del vídeo truncado)
    leidos = int(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_read_frames,width,codec_name",
                "-of",
                "json",
                str(ruta),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.split('"nb_read_frames": "')[1]
        .split('"')[0]
    )
    if leidos != n:
        raise RuntimeError(f"{ruta}: escritos {n}, releídos {leidos}")
    return {
        "fichero": str(ruta),
        "archivo": f"{int(t0 // 60)}:{t0 % 60:04.1f}-{int(t1 // 60)}:{t1 % 60:04.1f}",
        "reproductor": f"{int((t0 + 93) // 60)}:{(t0 + 93) % 60:04.1f}-"
        f"{int((t1 + 93) // 60)}:{(t1 + 93) % 60:04.1f}",
        "frames": n,
        "MB": round(ruta.stat().st_size / 1e6, 1),
    }


# ── resumen del balón por zona ────────────────────────────────────────────────────────────────


def resumen_balon(d: dict, rango=None) -> dict:
    """Por tercio del campo (en profundidad, donde está la mediana de los jugadores en el frame)."""
    csv = d["csv"]
    r = csv[(csv.es_real == 1) & csv.x_m.between(0, LARGO) & csv.y_m.between(0, ANCHO)]
    mediana_x = r.groupby("frame").x_m.median()
    if rango is not None:
        a, b = _rango(*rango)
        mediana_x = mediana_x[(mediana_x.index >= a) & (mediana_x.index < b)]
    res = {}
    for zona, (lo, hi) in {
        "cerca (x 0-20,7)": (0, LARGO / 3),
        "media (x 20,7-41,3)": (LARGO / 3, 2 * LARGO / 3),
        "lejos (x 41,3-62)": (2 * LARGO / 3, LARGO + 1),
    }.items():
        fs = mediana_x[(mediana_x >= lo) & (mediana_x < hi)].index
        con = fuera = al_lado = 0
        for f in fs:
            sel = balon_en(d, int(f))
            estado, _c = estado_balon(sel)
            if sel is None:
                continue
            con += 1
            if estado == "fuera":
                fuera += 1
                det = sel[0]
                cx, cy = (det[2] + det[4]) / 2, (det[3] + det[5]) / 2
                al_lado += int(
                    cx < REGION_CAMPO_AL_LADO[0] and cy < REGION_CAMPO_AL_LADO[1]
                )
        res[zona] = {
            "frames": int(len(fs)),
            "con_balon_pct": round(100 * con / max(len(fs), 1), 1),
            "proyectado_fuera": fuera,
            "fuera_en_la_region_del_campo_de_al_lado": al_lado,
            "fuera_resto_(aereo_saques_otros)": fuera - al_lado,
        }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--captura", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    d = cargar(Path(args.captura))
    cuentas = recuento(d["csv"])
    vs = ventanas(d)
    res = {"ventanas": vs, "clips": {}, "balon_por_zona": {"partido": resumen_balon(d)}}
    for nombre, v in vs.items():
        t0, t1 = v["s"]
        res["clips"][nombre] = render(f"clip_{nombre}", t0, t1, d, cuentas, salida)
        res["balon_por_zona"][nombre] = resumen_balon(d, (t0, t1))
    texto = json.dumps(res, indent=1, ensure_ascii=False, default=lambda o: o.item())
    (salida / "clips.json").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
