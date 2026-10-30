# ¿Sirve la pizarra para analizar una salida de balón? (30-oct-2026)

Rama `pizarra-salida-balon`, sale de `main` (con el arreglo de interpoladas). **Solo dibujo**: los
CSV de datos no se tocan. El balón se calcula con `scripts/procesar_balon.py` sobre el CSV del
arreglo y se escribe en `outputs/salida_balon/`, fuera de `data/`. La regla se fija ANTES de buscar
candidatas.

## 1. Candidatas: 3 salidas de balón por equipo, con una regla simple

- **Portería de cada equipo**, medida: el portero A tiene la mediana en x = 7,5 m y el B en 57,6, así
  que A defiende x = 0 y B defiende x = 62. Área F7: 12 m de fondo y 26 de ancho (`campo_modelo.py`).
- **Inicio (t_s)**: un frame con balón DETECTADO (`es_real = 1`, no aéreo) dentro del área propia del
  equipo T, o a ≤ 2 m de una fila `portero_T`.
- **El balón es de T**: el primer contacto con jugador atribuido en [t_s, t_s + 8 s] es de T (A o
  portero_A, o B o portero_B). Así se descarta un tiro del rival que acaba en el área.
- **Progresión ≥ 10 s**:
  - t_out es el primer frame posterior con balón detectado fuera del área propia, a ≤ 8 s de t_s;
  - en [t_out, t_out + 10 s] el balón detectado no vuelve al área propia;
  - y se aleja ≥ 15 m más de la portería propia que en t_out.
- **Calidad**: balón detectado en ≥ 50 % de los frames del caché de balón del tramo.
- **Tramo**: [t_s − 5 s, t_s + 25 s], 30 s. Entre dos candidatas del mismo equipo, ≥ 30 s.
- **Se proponen las 3 de cada equipo con más cobertura de balón**, con miniatura (el frame de t_s
  sacado con el ffmpeg de línea de comandos) y los dos relojes. Alex elige.

¿Qué podría estar inventando?
- **Un balón en el área puede ser un balón muerto o de un saque.** La regla no distingue un saque de
  puerta de una cesión. Se ve en la miniatura.
- **El contacto atribuido es una heurística de proximidad** (≤ 3 m al jugador más cercano), así que
  en un cruce puede dar el equipo equivocado.
- **El balón detectado en la mitad lejana** (x > 40) tiene más error: a 0,42 m/px, la «progresión»
  allí es menos fiable.

---

# Resultados del paso 1: solo 2 candidatas por equipo cumplen la regla

`python scripts/salida_balon.py candidatas` → `outputs/salida_balon/candidatas.html`, con una
miniatura por candidata y el balón marcado con un recuadro amarillo.

- **El balón**: `procesar_balon.py` sobre el CSV del arreglo. En los 20 min hay balón detectado en
  el 50 % de los frames del caché de balón, y 644 contactos, 497 de ellos con jugador atribuido.
- **Equipos**: A es el blanco, con su portero de negro en la portería de la cámara; B es el naranja.

| id | sale | tramo (archivo · reproductor) | inicio | avance | balón detectado |
|---|---|---|---|---|---|
| A1 | A | 13:15.7 → 13:45.7 · 14:48.7 → 15:18.7 | área (el portero, con el balón en la mano) | 25,6 m | 95 % |
| A2 | A | 4:59.8 → 5:29.8 · 6:32.8 → 7:02.8 | área | 27,5 m | 72 % |
| B1 | B | 13:06.7 → 13:36.7 · 14:39.7 → 15:09.7 | área | 41,1 m | 86 % |
| B2 | B | 18:18.3 → 18:48.3 · 19:51.3 → 20:21.3 | portero | 24,6 m | 85 % |

- **Solo 2 de cada equipo cumplen la regla** y no se ha relajado para llegar a 3: eso queda para
  Alex.
- **A1 y B1 se solapan**: B saca, el balón acaba en el área de A y A sale desde ahí.
- **Las salidas de B ocurren en el fondo**, donde 1 px vale hasta 0,42 m. Allí el balón y las
  fichas son menos fiables.

## ⚠️ Corrección del paso 1: la cobertura de balón estaba mal calculada

La «cobertura» dividía las detecciones de balón entre las FILAS de balón del CSV, y esas filas solo
existen donde hay pista de balón. Tenía que dividir entre todos los frames del caché de balón
(15 Hz). Lo cazó el visor, que daba 34-44 % de balón detectado donde las tarjetas decían 72-95 %.

| | cobertura dada | real |
|---|---|---|
| A1 | 95 % | **36 %** |
| A2 | 72 % | **44 %** |
| B1 | 86 % | **56 %** |
| B2 | 85 % | **35 %** |

- **Con la regla bien aplicada (≥ 50 %) solo queda B1.** El script está corregido y
  `candidatas.html` es ya la pasada buena.
- Alex eligió **A1, A2 y B2** sobre la lista mala. El visor se hace con esas tres, guardadas en
  `outputs/salida_balon/elegidas_por_alex.json`, y la cobertura real va escrita en cada una.
- **Es la sexta vez que una herramienta que resume miente sobre lo que resume**: un denominador que
  solo cuenta donde ya hay dato.

## 2. El visor

`python scripts/salida_balon.py visor --ids A1 A2 B2 --modulos <dir>` →
`outputs/salida_balon/visor/salidas_de_balon.html`, con los clips al lado.

- **Vídeo y pizarra lado a lado y sincronizados.** El clip se corta con el ffmpeg de línea de
  comandos (`-ss` antes de `-i`, recodificado: exacto al frame). La pizarra se dibuja en el
  instante del vídeo. Hay pausa y velocidad 0,5× / 1×, y la barra del vídeo permite saltar.
- **Las fichas son las de la pizarra de producción**: `generar_replay.py` del tramo con el arreglo de
  interpoladas y la histéresis de 1 s. Se leen sus datos y se reproducen con el simulador de
  `posicionEn` (`fichas_pizarra.py`), muestreado a 20 Hz.
- **El balón** solo se pinta si hay una detección a ≤ 0,07 s y dentro del campo. El estado se
  escribe: «detectado», «detectado, por el aire», «proyecta fuera del campo (no se pinta)» o
  «no visible». Los huecos del balón no se rellenan.
- **Contorno** convexo de los jugadores de campo de cada equipo, sin el portero, y opción de la
  línea del último defensor.
- La pizarra va **orientada como la cámara**, con la portería de A abajo y la y creciendo hacia la
  izquierda (comprobado proyectando con la homografía).
- **Control de sincronía**: a 8 s de A1, el balón de la pizarra proyectado sobre el frame del clip
  cae encima del balón del vídeo (desfase de 0,01 s).

## 3. ¿Qué parte de la jugada es fiable?

Instantes a 20 Hz del tramo de 30 s; fichas visibles dentro del campo:

| tramo | balón detectado | no visible | fuera del campo | fichas A (p10-p90) | fichas B (p10-p90) | A ≥ 7 | B ≥ 7 |
|---|---|---|---|---|---|---|---|
| A1 | **37,7 %** | 62,3 % | 0 % | **4,34** (2-6) | 6,63 (6-7) | 2 % | 63 % |
| A2 | **44,3 %** | 48,8 % | 6,8 % | 6,39 (5-8) | 6,97 (6-8) | 55 % | 75 % |
| B2 | **34,5 %** | 60,3 % | 5,2 % | 5,53 (3-7) | 6,58 (6-7) | 52 % | 57 % |

- **El balón se ve en un tercio del tramo, o algo más.** Sirve para saber por dónde va la jugada,
  no para seguir cada pase.
- **A1 (A saca desde su portero) es justo el caso que el encuadre no ve**: la cámara está detrás de
  la portería de A y a x = 8 m solo ve 16 m de los 40 de ancho (CLAUDE.md). La salida de A se ve
  con 4,3 de sus 7 fichas de media. La presión de B sí se ve entera (6,6).
- **A2** es la más completa: 6,4 y 7,0 fichas.
- **En B2 (B saca desde el fondo)** las fichas de B están (6,6), pero el balón y las posiciones son
  del fondo, donde 1 px vale hasta 0,42 m.
- Más de 7 en p90 (A2, 8) son fichas de más: una persona en dos identidades, o el árbitro con
  etiqueta de equipo.

**Para juzgarlo**: la pizarra sirve para la FORMA de la presión rival y de la salida (contornos,
último defensor) cuando el juego está a x ≳ 20 m. En la salida de A desde su área faltan fichas por
el encuadre, y eso no lo arregla el software.

## Código

En la rama `pizarra-salida-balon`, sin fusionar:
- `scripts/salida_balon.py`
- `scripts/plantilla_salida_balon.html`

Las salidas van a `outputs/salida_balon/`. Los CSV de datos no se tocan.
