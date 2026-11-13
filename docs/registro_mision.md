# Registro de la misión: un sistema que analice bien CUALQUIER partido (F7 y F11)

Memoria entre sesiones. Cada entrada: hipótesis, criterio previo, resultado, decisión, siguiente paso.
Encargo de Alex del 13-nov-2026 (definición de terminado, método y restricciones: en el propio encargo).

## Partidos de desarrollo y de validación (declarado ANTES de ajustar nada)

| partido | papel | por qué | estado de los datos |
|---|---|---|---|
| benjamín F7 (Gredos), parte 1 | **desarrollo** | todo el sistema está ajustado sobre él | cachés completos, GT de 30 s |
| alevín A F11 (Casarrubuelos), tramo de 60 s | **desarrollo** | lleva meses de banco («Villaviciosa») | cachés, GT de 30 s |
| alevín B F11 (Dux), parte 1 | **desarrollo** | es el caso que falla y sobre el que se va a iterar | cachés completos, mini-GT de equipo a ojo (79 jugadores) |
| **cadete A F11**, parte 1 | **validación** | mismo campo y cámara, otro partido, otras equipaciones, nunca mirado | vídeo cortado; **sin detecciones (GPU)** |
| **alevín B, parte 2** | **validación** (débil: mismo partido, otra luz y campos cambiados) | no se ha procesado ni mirado | vídeo cortado; **sin detecciones (GPU)** |
| **F11 de Bazán** (1920×798) | **validación** | otro campo y otra cámara | **el vídeo no está en este Mac** |

No se ajusta nada mirando los de validación. Un cambio solo se adopta si mejora o no empeora en todos.

## Entrada 1 (13-nov): línea base y conciliación

Instrumento: `scripts/linea_base_mision.py`. Simula a 10 Hz lo que dibuja `replay_tactico` (sus dos
filtros y su interpolación), SIN histéresis. **Control del instrumento**: en el tramo 14:00-15:30 del
benjamín da 48,0 cambios de color/min y 27,3 eventos/min, las cifras ya conocidas (`pizarra_fichas.md`).
«Zona visible» = interior del campo a ≥ 2 m de las líneas (proxy; en el benjamín sobrecuenta la franja
que la cámara no ve). Salidas en `outputs/linea_base_mision/`.

| criterio (objetivo) | benjamín 5-20 min | alevín A 60 s | **alevín B, parte 1 (30 min)** |
|---|---|---|---|
| 1. cambios A↔B por min (≤ 5) | 34,1 | 131,2 | **122,0** |
| 2. saltos > 3 m en 0,2 s, por min (0) | 0,0 | 50,1 | **51,7** |
| 2. p99 de velocidad de ficha (≤ 9 m/s) | 5,3 | 13,5 | **15,0** |
| 3. apariciones/desapariciones por min (≤ 5) | 22,7 | 119,2 | **70,3** |
| 3. simultáneas A · B: p50 (tope 7 u 11) | 6 · 7 | 13 · 10 | **13 · 10** |
| 3. % del tiempo por encima del tope, A · B | 4,1 · 14,0 | 76,1 · 19,5 | **63,7 · 40,6** |
| identidades por minuto | 13,9 | 84,2 | **44,8** |
| vida mediana de una identidad | 37,9 s | 12,2 s | **15,5 s** |

Alex tiene razón: el F11 es de otro orden de magnitud que el benjamín en los tres criterios.
Criterios 4 y 5 (exactitud): en el alevín B solo hay el mini-GT de equipo (79,7 %; objetivo ≤ 2 % de
error ⇒ muy lejos). No hay verdad de posición ni de identidad en el alevín B ni en validación: hace
falta (ver «Lo que necesito de Alex»).

### De dónde sale cada cosa (conciliación en los datos)

**Cambios de color (122/min)**
- En la pizarra y en los datos cuadran (122,0 contra 122,4): no es un fallo de dibujo.
- 91,3/min son entre dos filas REALES seguidas; 31,1/min llevan una fila interpolada.
- ⚠️ **Los introduje yo el 12-nov** al encender el voto por ventana de 1,5 s en el F11. Con el voto por
  identidad (producción anterior) hay **0 cambios/min**, pero con los equipos mal (4 contra 15 por
  fotograma, y B por encima de 11 el 100 % del tiempo). Cambié un error largo por muchos cortos: el
  acierto del mini-GT sube (66 → 80 %) y la pizarra parpadea. Las dos cosas están mal; no revierto
  hasta medir la H1, pero NO es adoptable así.
- El aviso estaba escrito en el config del benjamín («NO VIAJA» a Villaviciosa) y lo adopté mirando
  solo el equipo equivocado. Es el principio del criterio de adopción que solo mira lo que mejora.

**Saltos (52/min) y velocidades imposibles**
- No dependen de la etiqueta (salen iguales con el CSV de producción) ni de huecos: el 0 % ocurre
  dentro de un hueco; 139 de 144 pasos/min a > 15 m/s son entre dos filas reales seguidas.
- **No son cambios de persona.** En las detecciones crudas del seguimiento, el 6,8 % de los pasos de
  una identidad supera los 15 m/s (667/min), y de esos el **97 % mueve el pie ≤ 20 px** (mediana 5,9 px;
  4,4 px en vertical; la altura de la caja cambia 4,2 px sobre 25). Es el temblor del borde inferior de
  la caja multiplicado por la proyección rasante: 0,08 m/px cerca, 0,16 en medio, **0,38 m/px lejos**
  (y más en vertical). Pasos rápidos: 2,6 % cerca, 6,2 % en medio, 15,6 % lejos.
- El suavizado de producción (media de 0,5 s, igual en todo el campo) los baja de 667 a 144/min, y no
  basta. En el benjamín hay 0 porque allí el suavizado se alarga con la resolución local
  (`escalado_resolucion`, ~2 s); en el F11 está apagado y además se calcula con una homografía, que el
  alevín B no tiene (usa el modelo de lente).

**Apariciones y fichas de más (70 eventos/min; A por encima de 11 el 64 % del tiempo)**
- 44,8 identidades nuevas por minuto contra 13,9 del benjamín; vida mediana 15,5 s.
- Sin conciliar todavía: cuánto es fragmentación (muere una y nace otra cerca), cuánto duplicados (dos
  identidades sobre una persona) y cuánto gente que no juega (árbitro, calentamiento). Es el paso 0 de H3.

**Balón**: no hay línea base útil. El detector lo ve en el 9,4 % del tramo (2-4 px en casi todo el campo).

## Plan de hipótesis (criterios ANTES de medir; máximo dos intentos por ruta)

Orden por lo que más pesa en lo que ve Alex y por coste (todo en CPU sobre cachés salvo H4 y H5).

### H1. Posición: suavizado con el ruido LOCAL de la proyección, usando pasado y futuro
- **Qué**: sustituir en el F11 la media fija de 0,5 s por un suavizador de dos sentidos (RTS, velocidad
  constante) cuyo ruido de medida en cada punto es el temblor en píxeles (σ medido del detector)
  llevado a metros con el jacobiano de la cámara (homografía o modelo de lente). Lejos suaviza mucho,
  cerca casi nada. Detrás de un interruptor; el benjamín no cambia.
- **Argumento nuevo frente a las rutas cerradas** («suavizado por tiempo», «Kalman del balón»): allí la
  ventana era igual en todo el campo y el problema era otro; aquí está medido que el 97 % de los saltos
  es temblor de ≤ 20 px amplificado, con un factor 5× entre cerca y lejos.
- **Criterio**: alevín B, parte 1: 0 saltos > 3 m en 0,2 s y p99 ≤ 9 m/s.
- **Lo que no puede romper** (¿qué podría estar inventando? un jugador que no gira): (a) en la zona
  CERCANA, donde el píxel es fiable, la fila suavizada queda a ≤ 0,5 m (p95) de su propia detección;
  (b) contra el GT del alevín A (30 s): error de posición casado 1-a-1 no peor que hoy, por franja;
  (c) retraso en cambios de dirección: en un sintético con un giro de 90° a 6 m/s, error máximo ≤ 1 m;
  (d) centroide y anchura del alevín A no peores.
- **Control**: con el ruido de medida constante tiene que reproducir (± 5 %) las cifras de hoy.

### H2. Etiqueta de equipo estable SIN perder acierto: decidir con pasado y futuro
- **Paso 0 (premisa)**: de los 122 cambios/min, ¿cuántos son rachas cortas (< 2 s) flanqueadas por la
  misma etiqueta (ruido de la evidencia) y cuántos cambios sostenidos (la identidad cambió de persona)?
  En el benjamín la mitad era lo segundo y por eso «etiqueta por trozos» no pagó. Si en el F11 ≥ 70 %
  son rachas cortas, se construye; si no, se cierra sin construir.
- **Qué**: en vez de votar cada ventana por separado, la secuencia de evidencias de una identidad se
  decodifica entera (Viterbi de 2 estados con coste de cambio): cambia de equipo solo si la evidencia
  lo sostiene. No es histéresis de dibujo: cambia el DATO.
- **Criterio**: alevín B ≤ 5 cambios A↔B/min **y** mini-GT ≥ 79,7 − 1 punto; benjamín: equipo
  equivocado ≤ 1,2 + 0,3 puntos y cambios no mayores que hoy; alevín A: equipo equivocado ≤ 17,5 %.
- **Obligatorio informar**: jugadores-segundo mal etiquetados y duración de los episodios de error,
  antes y después (no cambiar errores cortos por largos). Para eso hace falta la hoja de H2 (abajo).

### H3. Presencia: fragmentos y duplicados
- **Paso 0**: conciliar los 70 eventos/min: (i) muertes con un nacimiento a ≤ 2 s y ≤ 5 m (fragmento
  re-enlazable); (ii) parejas de identidades a < 1,5 m durante > 1 s (duplicado); (iii) identidades que
  nunca son de un equipo (árbitro, gente de fuera). Decide qué se construye.
- **Qué (si (i) domina)**: re-enlace offline DENTRO de cada equipo, con el movimiento extrapolado en los
  dos sentidos sobre posiciones ya suavizadas por H1 (la ruta (a) de `mapa_rutas_cruces.md`, nunca
  probada; el veto de equipo necesita H2). Si (ii) domina: fusión de duplicados simultáneos del mismo
  equipo.
- **Criterio**: eventos ≤ 5/min y simultáneas ≤ 11 por equipo en ≥ 99 % del tiempo, con IDF1 dentro de
  cada equipo (GT del alevín A y del benjamín) ≥ el de hoy. Lo que se cumple por construcción no cuenta.

### H4. Recall lejano (GPU)
- Franjas lejanas ampliadas en la detección (hoy la red amplía ×1,07). Criterio: recall ≥ 80 % lejos sin
  subir los falsos positivos por fotograma más de un 10 %. Solo después de H1-H3: hoy no es lo que más
  se ve.

### H5. Balón: ruta nueva por MOVIMIENTO (cámara fija)
- El detector no puede ver 2-4 px. Con cámara fija, un balón en juego es una mancha pequeña que se
  mueve rápido: diferencia entre fotogramas + tamaño + trayectoria físicamente plausible (parábolas y
  rectas), con el detector de apariencia como confirmación donde exista.
- **Paso 0 (premisa, CPU)**: en los fotogramas donde el detector SÍ ve el balón (9,4 %), ¿aparece ahí
  una mancha en la diferencia de fotogramas, y cuántas manchas candidatas más hay por fotograma? Si el
  balón conocido aparece en ≥ 80 % y hay ≤ 20 candidatas, se construye el seguimiento por trayectoria.
- **Criterio final**: necesita verdad: un tramo de 60 s con el balón marcado en TODOS sus fotogramas
  (lección cerrada del 28-oct: frames sueltos no sirven).

## Lo que necesito de Alex (agrupado)

1. **GPU para validación**: procesar la detección de `cadete_villa_p1` (y, si quiere, la parte 2 del
   alevín B) con el orquestador de Colab que ya funciona. Coste como la parte 1 del alevín B.
2. **El vídeo de Bazán** en `data/raw/` (o en Drive) si quiere validar en otro campo.
3. **Marcas humanas** (una sola sesión, cuando H1-H2 estén medidas): hoja de equipo de ~150 filas
   repartida por el partido con la caja de la fila, en el alevín B y en el cadete (≈ 25 min cada una), y
   60 s de balón fotograma a fotograma para H5 (≈ 40 min).
