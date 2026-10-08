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
