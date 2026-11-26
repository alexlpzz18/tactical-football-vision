# Segunda opinión, comprobaciones #1 y #2 + interruptor SigLIP en el alevín B (26-nov-2026)

Rama `alevinb-preparacion`. Nada toca `main` ni los configs de producción de `main`. Criterios fijados
por Alex antes de medir (en su mensaje del 26-nov).

## #1. Oráculo completo en F11 (GT del alevín A, 30 s)

`scripts/desglose_f11.py` (escalera de oráculos + Shapley de `desglose_del_error.py`) sobre el CSV de
producción con los configs de `main` (`outputs/literatura/banco/villa/posiciones_actual.csv`).

| | sistema | parte de «faltan» (MIS) | parte de «sobran» (EXT) | parte de la etiqueta (LAB) |
|---|---|---|---|---|
| anchura | 5,71 m | **60 %** | 2 % | — |
| centroide | — | 38 % | 7 % | 42 % |
| profundidad | — | — | — | 92 % |

**Criterio: arreglar SOLO «faltan» baja la anchura un 59 % (> 30 %) ⇒ CUMPLE: la presencia lejana
pasa a prioridad.** El 69 % de los que faltan están en el tercio lejano, donde falta el 47 % de las
personas del GT.

«Sobran», como pidió Alex, aparte: de 393 filas A/B que no casan con ningún jugador, solo **8 (2 %)**
están a ≤ 2 m del árbitro del GT; el 66 % son filas desplazadas 2-5 m de su persona y el 32 %,
el resto. En F11 el árbitro NO es el problema de los sobrantes (a diferencia del benjamín, donde era
la mitad); lo son las filas mal puestas, que es asociación.

## #2. Premisa de B1: fondo fijo para la camiseta verde oscuro

`scripts/premisa_fondo_fijo.py`, fotogramas con el ffmpeg CLI. Mini-GT a ojo del alevín B (30
verdes, 49 blancos). Pecho = 12-45 % del alto, 15-85 % del ancho. Fondo = mediana de 40 fotogramas del
mismo minuto (sin los ± 2 s del propio fotograma).

**Vibración** (100 fotogramas seguidos, dos tramos): máximo **0,22 px** sobre la banda de edificios y
vallas del fondo ⇒ **cumple** (< 1 px). ⚠️ Control del instrumento: la primera medida, sobre el
techo de la grada, daba 0,05 px sin ventana y 250 px con ventana de Hanning; el techo está pegado a la
cámara (se mueve con ella) y tiene destello del sol, así que no vale. Una franja del campo lejano da
picos de 40-50 px: son jugadores que pasan. La banda buena es la estática y con textura.

**Pecho verde que se conserva** (mediana por recorte):

| máscara | verdes | blancos | verdes cerca · medio · lejos |
|---|---|---|---|
| anti-césped de producción (H 35-85, S ≥ 40, V ≥ 40) | **73,8 %** | 100 % | 38 · 87 · 100 % |
| primer plano \|I − B\| > 15 | **52,8 %** | 62 % | 56 · 53 · 24 % |
| primer plano > 25 | 34,7 % | 48 % | 42 · 33 · 15 % |

**Criterio (≥ 60 % con el fondo fijo frente a < 20 % con la anti-césped): NO CUMPLE por los dos
lados.** La premisa de la revisión externa («la máscara anti-césped borra la camiseta verde oscuro»)
es falsa en este partido: el verde de la equipación es lo bastante oscuro o apagado para quedar fuera
de la banda del césped, salvo cerca de la cámara (38 %). Y el primer plano conserva menos que la
máscara actual, sobre todo lejos (24 %), donde un jugador de 15-20 px se parece al césped en
intensidad. **B1 no se integra; no bloquea la hoja de 300 recortes.**

## Interruptor `siglip.activo` en el alevín B

`configs/team_classification_alevinb.yaml` (solo en esta rama), código en
`src/team_classification/siglip_equipos.py`; el processor solo lo lee si el bloque existe y está activo.

- **Apagado = idéntico byte a byte** al CSV de la rama sin el interruptor (`cmp`).
- El selector, dentro del pipeline: 2.058 parejas, kappa HS 0,643, SigLIP 0,800 ⇒ **elige SigLIP**.
- Banco (`outputs/alevinb_siglip/resultados.json`):

| | apagado | SigLIP |
|---|---|---|
| mini-GT a ojo (79 jugadores) | 79,7 % | **86,1 %** |
| ... sobre los 73 con fila A/B | 86,3 % | **93,2 %** |
| cambios A↔B por minuto | 122,9 | **87,5** |
| fichas simultáneas > 11 (A · B) | 63 · 41 % | 54 · 52 % |

El 86,1 % frente al 89,9 % de la evaluación fuera de línea no es una contradicción: el banco cuenta
como fallo a los 6 jugadores que la producción deja sin fila (3) o manda a staff (3), los mismos 6
con el interruptor apagado y encendido; la evaluación fuera de línea etiquetaba la detección
directamente, sin reglas.

Pizarra regenerada: `outputs/visor_alevinb_siglip/index.html`. Superposición, 10:00-10:30 del archivo,
con y sin SigLIP: `outputs/alevinb_siglip/superposicion_10m00s_{siglip,apagado}.mp4` (los colores se
fuerzan con `--colores`: los prototipos de color de los dos equipos salen casi blancos con el sol).

La adopción en `main` sigue pendiente de la hoja de 300 recortes.
