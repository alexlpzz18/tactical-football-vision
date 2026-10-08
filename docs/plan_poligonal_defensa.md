# Plan: la línea defensiva como POLIGONAL + altura media de la defensa (8-oct-2026)

Solo local, sin GPU, sin tocar producción. Viene de `docs/plan_lineas_tacticas.md`: la línea
defensiva recta (UN jugador, el extremo) no pasó el criterio por presencia. La poligonal usa N
jugadores y su altura MEDIA es un promedio, que debería aguantar mejor un jugador que falte o sobre.
El criterio (`scripts/poligonal_defensa.py::CRITERIO`) se commitea ANTES de ver números del sistema.

## La regla

Por frame y equipo, de los jugadores de CAMPO (sin portero): los **N más cercanos a su propia
portería**, ordenados por la coordenada lateral (y) y unidos con segmentos consecutivos.
**N es un parámetro de entrada** (el entrenador conoce su sistema): aquí N = 4 para el blanco, que
juega con 4 defensas. La **altura media** es la x media de esos N, expresada como distancia a su
propia portería. El lado de cada equipo sale de `deducir_lados` (A defiende x = 0) y está
comprobado con los porteros (`docs/plan_lineas_tacticas.md`).

## Paso 1: oráculo con el GT (sin sistema)

Los roles están en `docs/gt_identidad_benja.md`, no en el XML. Id de la tabla = track del XML + 1,
comprobado por el equipo y por el número de observaciones de cada track.
- **Blanco (A)**: centrales #4 y #7, laterales #2 y #8 → tracks 0-3. ¿Elige la regla "los 4 más
  retrasados" exactamente a esos 4? % de frames, solo los frames con los 4 anotados (dos de ellos
  faltan en algunos: 52 y 51 observaciones de 60). Y qué pasa cuando el equipo ataca: el acierto por
  tercios de la x media del bloque blanco, y quién se cuela cuando falla.
- **Naranja (B)**: el GT solo nombra un central y un lateral; dos jugadores no tienen rol. **No se
  puede saber quiénes son sus defensas: no se mide.**

## Paso 2: el sistema contra el GT

Poligonal y altura media con las posiciones del sistema (la salida de producción de hoy, regenerada
desde el caché en un temporal), contra las MISMAS calculadas con las posiciones del GT (la misma
regla en los dos lados). **Solo en los frames donde el sistema tiene los N defensas en la zona
visible**: al menos N jugadores de campo del equipo, y sus N más retrasados con x ≥ 28 m.

- Vértices: los dos conjuntos van ordenados por y y se emparejan en orden; error = distancia en metros.
- **Criterio**: altura media con **mediana ≤ 1 m y p90 ≤ 3 m**; vértices con **mediana ≤ 1,5 m**.
  Con menos de 10 frames: **NO CONCLUYENTE**.
- Decide el BLANCO (N = 4, su sistema real). El naranja se informa aparte con N = 4 como SUPUESTO
  (no conocemos su sistema), sin veredicto.

⚠️ **Aviso calculado antes de medir**: el blanco defiende x = 0, así que sus defensas viven casi
siempre por DEBAJO de 28 m. Con el GT, el bloque blanco entero está a x ≥ 28 en solo 12 de 60
frames, así que caben pocos frames, y lo más probable es NO CONCLUYENTE.

## Paso 3

Si pasa: clip de 30 s (zona visible, desde el minuto 5, los dos relojes), con la poligonal SOLO
cuando hay N vértices. Si no pasa: se documenta el negativo y no se dibuja nada.

## Resultado (8-oct-2026)

**Paso 1 — oráculo (posiciones del GT, sin sistema).** Blanco, 51 frames con los 4 defensas
anotados: **la regla "los 4 más retrasados" elige exactamente a los 4 defensas en 19 (37 %)**.
Cuando falla se cuela casi siempre el **mediocentro #10** (30 de 32; el delantero, 2) y se queda
fuera **un lateral** (el derecho 16 veces, el izquierdo 16): los laterales suben por delante del
mediocentro. **Atacando es peor**: por tercios de la x media del bloque blanco, retrasado 6/17,
medio 9/17, adelantado 4/17. Naranja: el GT no dice quiénes son sus defensas; no se mide.

⇒ **La poligonal de "los N más retrasados" NO es la línea defensiva** en 2 de cada 3 frames,
aunque las posiciones sean perfectas. Es un problema de la REGLA, no del sistema.

**Paso 2 — sistema contra GT (la misma regla en los dos lados, solo con los N en zona visible).**

| | frames válidos | altura: mediana | altura: p90 | vértices: mediana | ¿pasa? |
|---|---|---|---|---|---|
| **Blanco, N = 4 (decide)** | **12** (48 fuera de zona) | 0,28 m | 1,38 m | 0,63 m | **sí** |
| Naranja, N = 4 supuesto (informativo) | 48 (12 fuera de zona) | 0,60 m | 2,21 m | 0,87 m | sí |

**Pasa, pero con 12 frames**, apenas por encima del mínimo de 10: el blanco defiende x = 0 y sus
4 más retrasados están rara vez a ≥ 28 m (en el partido entero, el 35,9 % de los frames). La altura
MEDIA aguanta lo que tumbó a la línea recta: es una media de 4, no un extremo.

**Paso 3 — el clip** (`outputs/poligonal_defensa_benja.mp4`, 30 s, 3,7 MB, no se versiona): archivo
15:54,0-16:23,9, reproductor 17:27,0-17:56,9; la poligonal blanca visible el 100 % del tiempo.
**Sin GT en esa ventana.** Dibuja la poligonal solo con los 4 vértices en zona visible (si no, "no
medibles"), la altura media como número y, abajo, el aviso de que "los 4 más retrasados" solo son la
defensa en el 37 % de los frames. El naranja va rotulado "N supuesto".

**Qué haría falta para que fuera "la defensa"**: saber QUIÉN es defensa, no solo dónde está. Con
identidades estables bastaría con fijar los 4 una vez (lo da el entrenador o se deduce de la
alineación). Hoy una persona son N identidades (CLAUDE.md), así que eso depende de la asociación.
