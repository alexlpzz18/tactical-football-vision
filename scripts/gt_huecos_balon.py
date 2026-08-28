#!/usr/bin/env python
"""Tiras de frames alrededor de una pérdida de balón, para anotarlas a mano.

Idea de Alex (28-ago-2026), mejorada: *"enséñame un frame donde se ve el
balón y el siguiente donde no se ve, así te digo exactamente dónde
tendría que estar de verdad"*.

⚠️ POR QUÉ ESTO Y NO LO ANTERIOR. El primer intento pintaba una cruz en
la posición INTERPOLADA en el medio del hueco. Es inservible por dos
motivos que Alex vio antes que yo: en 4-5 s el balón hace lo que quiere,
así que una recta entre "última vez visto" y "vuelve a verse" no dice
nada; y la homografía inversa supone el balón EN EL SUELO, así que si iba
por el aire el píxel está desplazado decenas de metros. Sus palabras:
*"viendo a dónde están mirando todos los jugadores no tiene ninguna pinta
de que el balón esté donde tú has interpolado"*.

Lo que hace esta versión:

- **Ancla en el último frame CON balón**, no en el medio del hueco. En
  los frames inmediatamente siguientes el balón todavía tiene que estar
  cerca, así que la ventana de recorte se mantiene FIJA y el ojo compara.
- **No inventa ninguna posición.** En los frames sin balón no hay cruz:
  solo una marca tenue de dónde se vio por última vez, etiquetada como
  tal.
- **Rejilla con celdas nombradas**, para que la anotación sea precisa:
  "en el frame +2 el balón está en la C3".

Uso:
    python scripts/gt_huecos_balon.py --casos 4 --despues 3
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("gt_huecos")

# Ventana de recorte alrededor de la última posición vista. Generosa: en
# 0,1-0,3 s el balón no se va de aquí ni con un disparo.
ANCHO, ALTO = 900, 620
CELDA = 4  # rejilla CELDA x CELDA

# Las causas que Alex quiere poder marcar. Salen de sus palabras y del
# hallazgo del encuadre; "no lo encuentro" está a propósito, porque
# obligar a elegir cuando no se ve nada fabricaría GT falso.
CAUSAS = [
    ("fuera", "NO está en el plano (se sale del encuadre)"),
    ("tapado", "TAPADO por un jugador (se ve la jugada, el balón no)"),
    ("visible", "SE VE y no se detecta (fallo del detector)"),
    ("aire", "Está en el AIRE (se ve, pero volando)"),
    ("no_se", "No lo encuentro / no sabría decirlo"),
]


def marcar_bordes(rec, x1, y1, W, H):
    """Pinta en ROJO los lados donde el recorte toca el BORDE DE LA IMAGEN.

    Sin esto no se puede distinguir "el balón se sale del plano" de "el
    balón se sale de mi recorte", que es justo la pregunta.
    """
    h, w = rec.shape[:2]
    rojo, grosor = (0, 0, 235), 6
    lados = []
    if x1 <= 0:
        cv2.line(rec, (2, 0), (2, h), rojo, grosor)
        lados.append("izq")
    if x1 + w >= W:
        cv2.line(rec, (w - 3, 0), (w - 3, h), rojo, grosor)
        lados.append("der")
    if y1 <= 0:
        cv2.line(rec, (0, 2), (w, 2), rojo, grosor)
        lados.append("arriba")
    if y1 + h >= H:
        cv2.line(rec, (0, h - 3), (w, h - 3), rojo, grosor)
        lados.append("abajo")
    if lados:
        cv2.putText(
            rec,
            "BORDE DE LA IMAGEN: " + ", ".join(lados),
            (10, h - 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            rojo,
            2,
        )
    return rec


def rejilla(img):
    """Dibuja una rejilla con celdas nombradas A1..D4."""
    h, w = img.shape[:2]
    for i in range(1, CELDA):
        cv2.line(img, (w * i // CELDA, 0), (w * i // CELDA, h), (90, 90, 90), 1)
        cv2.line(img, (0, h * i // CELDA), (w, h * i // CELDA), (90, 90, 90), 1)
    for f in range(CELDA):
        for c in range(CELDA):
            cv2.putText(
                img,
                f"{chr(65+f)}{c+1}",
                (w * c // CELDA + 6, h * f // CELDA + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (120, 120, 120),
                1,
            )
    return img


def main():
    import pickle

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--balon", default="data/tracking_benja/cache_balon_p1.pkl")
    p.add_argument("--video", default="data/raw/benja_gredos_p1_20min.mp4")
    p.add_argument("--campo", default="configs/campo_benja.yaml")
    p.add_argument(
        "--homografia", default="data/calibracion_benja/homografia_benja.npy"
    )
    p.add_argument("--casos", type=int, default=4)
    p.add_argument("--despues", type=int, default=3, help="frames tras la pérdida")
    p.add_argument("--salida", default="outputs/gt_huecos")
    args = p.parse_args()
    logging.basicConfig(level=logging.ERROR)

    from src.balon.tracking_balon import filtrar_balon_plausible
    from src.campo_modelo import cargar_modelo

    modelo = cargar_modelo(config=args.campo)
    with open(args.balon, "rb") as f:
        datos = pickle.load(f)
    dets = filtrar_balon_plausible(
        {e["frame_idx"]: e["dets"] for e in datos["cache"] if e["dets"]}, modelo
    )
    tiempos = {e["frame_idx"]: e["t"] for e in datos["cache"]}
    sample = datos["sample"]
    vistos = sorted(dets)

    # ⚠️ MUESTREO VARIADO, no todo de la misma esquina. El primer intento
    # sacó solo huecos de la portería cercana y salieron cuatro veces la
    # misma escena —el balón yéndose por abajo a la izquierda—, que no
    # sirve para un GT. Se estratifica por ZONA y se reparte en el TIEMPO.
    todos = []
    for a, b in zip(vistos, vistos[1:]):
        dt = tiempos[b] - tiempos[a]
        if 1.0 < dt < 8.0:
            todos.append((a, b, dt, float(dets[a][0][0])))
    zonas = [
        ("cerca (x<20)", 0, 20),
        ("medio (20-45)", 20, 45),
        ("lejos (x>45)", 45, 99),
    ]
    por_zona = max(args.casos // len(zonas), 1)
    elegidos = []
    for nombre, lo, hi in zonas:
        z = sorted((c for c in todos if lo <= c[3] < hi), key=lambda c: tiempos[c[0]])
        paso = max(len(z) // por_zona, 1)
        tomados = z[::paso][:por_zona]
        elegidos.extend(tomados)
        print(f"  zona {nombre:<16} {len(z):>3} huecos, se muestran {len(tomados)}")
    elegidos = [(a, b, dt) for a, b, dt, _x in elegidos]
    print(f"huecos de 1-8 s en total: {len(todos)}; se muestran {len(elegidos)}")

    # Frames a leer: el último CON balón y los N siguientes SIN.
    pedidos = {}
    for a, b, dt in elegidos:
        secuencia = [a] + [a + sample * (i + 1) for i in range(args.despues)]
        for f in secuencia:
            pedidos.setdefault(f, []).append(a)

    cap = cv2.VideoCapture(args.video)
    objetivo = set(pedidos)
    cargados, n = {}, 0
    while cargados.keys() != objetivo:
        ok, img = cap.read()
        if not ok:
            break
        if n in objetivo:
            cargados[n] = img.copy()
        n += 1
        if n > max(objetivo) + 2:
            break
    cap.release()
    print(f"frames leídos: {len(cargados)} de {len(objetivo)}")

    Path(args.salida).mkdir(parents=True, exist_ok=True)
    generados = []
    for a, b, dt in elegidos:
        det = dets[a][0]
        cx = int((det[2] + det[4]) / 2)
        cy = int((det[3] + det[5]) / 2)
        img0 = cargados.get(a)
        if img0 is None:
            continue
        H, W = img0.shape[:2]
        x1 = max(min(cx - ANCHO // 2, W - ANCHO), 0)
        y1 = max(min(cy - ALTO // 2, H - ALTO), 0)
        tiras = []
        for i, f in enumerate(
            [a] + [a + sample * (k + 1) for k in range(args.despues)]
        ):
            img = cargados.get(f)
            if img is None:
                continue
            y2, x2 = y1 + ALTO, x1 + ANCHO
            rec = img[y1:y2, x1:x2].copy()
            rejilla(rec)
            marcar_bordes(rec, x1, y1, W, H)
            if i == 0:
                # el ÚNICO sitio donde se marca algo: aquí SÍ se detectó
                cv2.rectangle(
                    rec,
                    (int(det[2]) - x1 - 14, int(det[3]) - y1 - 14),
                    (int(det[4]) - x1 + 14, int(det[5]) - y1 + 14),
                    (0, 255, 0),
                    2,
                )
                etq = "SE VE (detectado aqui)"
                color = (0, 255, 0)
            else:
                # marca TENUE de dónde estaba, etiquetada como tal.
                # No es una prediccion: es el ultimo sitio conocido.
                cv2.circle(rec, (cx - x1, cy - y1), 26, (0, 140, 190), 1)
                etq = f"NO se detecta (+{i} muestra, {i*sample/datos['fps']:.2f}s)"
                color = (0, 170, 220)
            barra = np.zeros((40, ANCHO, 3), np.uint8) + 26
            cv2.putText(barra, etq, (8, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2)
            tiras.append(np.vstack([rec, barra]))
        if not tiras:
            continue
        fila = np.hstack(tiras)
        cab = np.zeros((44, fila.shape[1], 3), np.uint8) + 26
        cv2.putText(
            cab,
            f"t={tiempos[a]:.0f}s  hueco de {dt:.1f}s  "
            f"(el circulo naranja = ULTIMO sitio visto, NO una prediccion)",
            (8, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (235, 235, 235),
            2,
        )
        ruta = f"{args.salida}/hueco_t{int(tiempos[a]):04d}s.png"
        cv2.imwrite(ruta, np.vstack([cab, fila]))
        generados.append((ruta, tiempos[a], dt, float(dets[a][0][0])))
        print(f"  {ruta}")

    _hoja_de_anotacion(generados, args.salida)


def _hoja_de_anotacion(casos, salida):
    """HTML con las tiras y una casilla de CAUSA por caso.

    Se genera una hoja y no una tabla suelta porque la anotación tiene que
    hacerse MIRANDO la imagen: separar las dos cosas es como se anota mal.
    Las imágenes van embebidas en base64, así que el fichero es
    autocontenido y se puede abrir desde cualquier sitio.
    """
    import base64

    if not casos:
        return
    bloques = []
    for i, (ruta, t, dt, x) in enumerate(casos):
        # ⚠️ La hoja lleva las imágenes dentro, así que van reducidas y en
        # JPEG: con los PNG a tamaño real el HTML pesaba 44 MB y no se
        # abría. A 1800 px de ancho el balón sigue viéndose (la tira
        # original mide ~3600 y el balón unos 20 px).
        img = cv2.imread(ruta)
        if img is not None and img.shape[1] > 1800:
            esc = 1800 / img.shape[1]
            img = cv2.resize(img, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
        ok_enc, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])
        b64 = base64.b64encode(buf.tobytes()).decode()
        ops = "".join(
            f'<label><input type=radio name="c{i}" value="{k}"> {t2}</label>'
            for k, t2 in CAUSAS
        )
        bloques.append(
            f"""<section>
  <h2>Caso {i+1} &middot; t={int(t//60):02d}:{int(t%60):02d}
      <small>hueco de {dt:.1f}s &middot; balón a x={x:.0f} m</small></h2>
  <img src="data:image/jpeg;base64,{b64}">
  <div class=opts>{ops}</div>
  <input class=nota id="n{i}"
         placeholder="¿dónde está de verdad? (celda A1..D4, o lo que quieras)">
</section>"""
        )
    html = f"""<title>GT de huecos de balón</title>
<style>
 body{{font:15px/1.5 system-ui,sans-serif;margin:0;padding:24px;background:#111;color:#eee}}
 h1{{font-size:22px;margin:0 0 6px}} p.intro{{color:#aaa;max-width:70ch}}
 section{{margin:34px 0;padding:18px;background:#1b1b1b;border-radius:10px}}
 h2{{font-size:17px;margin:0 0 12px}} h2 small{{color:#999;font-weight:400}}
 img{{width:100%;border-radius:6px;display:block}}
 .opts{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 10px}}
 .opts label{{background:#262626;padding:8px 12px;border-radius:6px;cursor:pointer}}
 .opts label:hover{{background:#303030}}
 .nota{{width:100%;padding:9px;background:#262626;border:1px solid #333;
        border-radius:6px;color:#eee;font:inherit}}
 button{{position:fixed;right:24px;bottom:24px;padding:14px 20px;font:600 15px system-ui;
         background:#2d7;border:0;border-radius:8px;cursor:pointer}}
 pre{{background:#000;padding:16px;border-radius:8px;white-space:pre-wrap}}
</style>
<h1>GT de huecos de balón</h1>
<p class=intro>Para cada caso: el primer frame es el último donde el
sistema SÍ detecta el balón (recuadro verde). Los siguientes son los
inmediatamente posteriores, donde ya no lo detecta — <b>sin ninguna marca
inventada</b>; el círculo naranja es solo el último sitio conocido. La
<b>línea roja</b> marca el borde real de la imagen, para distinguir "se
sale del plano" de "se sale del recorte".</p>
{''.join(bloques)}
<button onclick="vol()">Copiar respuestas</button>
<pre id=out></pre>
<script>
function vol(){{
  let l=[];
  document.querySelectorAll('section').forEach((s,i)=>{{
    const r=s.querySelector('input[type=radio]:checked');
    const n=document.getElementById('n'+i).value.trim();
    l.push(`caso ${{i+1}} (${{s.querySelector('h2').textContent.trim().split('·')[1].trim()}}): `
           +(r?r.value:'SIN MARCAR')+(n?' | '+n:''));
  }});
  const t=l.join('\n');
  document.getElementById('out').textContent=t;
  navigator.clipboard&&navigator.clipboard.writeText(t);
}}
</script>"""
    ruta = f"{salida}/anotar.html"
    with open(ruta, "w") as f:
        f.write(html)
    print(f"\n  HOJA DE ANOTACIÓN: {ruta}")


if __name__ == "__main__":
    main()
