# Diagnóstico 22-oct (g): cruces entre rivales o compañeros, asociación con color, la persona 21

Rama `fix-22oct-g`, sale de `fix-22oct-f`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque, **solo si pytest sale con código 0** (sin pipes). Producción solo cambia tras flag
(apagado = idéntico a `main`, comprobado byte a byte).

---

## Bloque A — ¿los cambios de persona en los cruces son entre rivales o entre compañeros? (solo medición)

Con la misma maquinaria del bloque A del 22-oct (f) (`scripts/diag22f_pureza.py`), GT de 30 s del
benjamín y de 60 s de Villaviciosa:
- **Cambios de persona en cruce** (las dos personas a < 2 m), separados en:
  - **entre rivales**: equipos distintos en el GT; los porteros cuentan en su equipo;
  - **entre compañeros**: el mismo equipo;
  - con el **árbitro**: Villaviciosa, que lo anota. Va aparte, porque el color sí lo distingue.

  Etapas: ByteTrack y CSV final.
- **Impureza por tipo**: las observaciones minoritarias de cada identidad (las que no son de su
  persona mayoritaria) se reparten según la persona minoritaria sea del equipo contrario a la
  mayoritaria (rival), del mismo (compañero) o el árbitro. Así se reparte la impureza de ByteTrack
  y la del CSV.
- **El 16,0 % de equipo equivocado por identidad** (benjamín, sin voto por observación: el CSV
  `diag_sin_por_obs_benja.csv` del 22-oct e; Villaviciosa, su 23,6 %, que ya es por identidad).
  Cada fila mal etiquetada se clasifica:
  - **mezcla con rival**: la persona mayoritaria de su identidad es del OTRO equipo. La identidad
    sigue a un rival y la fila es la minoría arrastrada;
  - **identidad del mismo equipo con rivales dentro**: la mayoritaria es de su equipo, pero la
    identidad contiene filas de rivales que pueden haber movido el color medio;
  - **identidad pura, mal coloreada**: ni una fila de rival. Error de color, no de asociación.
- **Techo de una solución de color**: la fracción «entre rivales» de los cambios en cruce y de la
  impureza. **Si es ≥ 70 %, se puede atacar con color; si no, no.**

¿Qué podría estar inventando? «Cruce» es a < 2 m de las personas del GT. Una persona que el GT no
anota (el árbitro en el benjamín) no cuenta.

## Bloque B — asociación con término de color (sobre las cachés; sin decodificar vídeo)

**B1, intento 1. Flag `tracking.coste_color`** (en el YAML de tracking; apagado por defecto).
- En la asociación de ByteTrack (`supervision`), el coste de cada par pista-detección pasa a ser:

  > coste = coste actual (1 − IoU, fusionado con la confianza) + λ · d / sep

  - d = distancia entre el modelo de color de la pista y la feature de la detección (bloque HS de
    la v1, la caché de producción);
  - sep = ‖A − B‖, la separación de los prototipos del partido.
- **Puerta**: si d / sep > `umbral`, ese par no se puede emparejar.
- **El modelo de la pista**:
  - es una media móvil exponencial (α = 0,2) de la feature, actualizada SOLO en frames sin
    solape: la detección no tiene IoU > 0,1 con ninguna otra caja del frame (el mismo umbral de
    cruce que usa `_detecciones_en_cruce`). En la actualización pesa 1 − máx. IoU;
  - en un frame solapado ni se actualiza ni se usa el color: ese par lleva el coste de hoy;
  - el término solo actúa cuando hay modelo de la pista y la detección está limpia.
- **λ y el umbral, relativos a sep**, fijados ANTES de medir los criterios:
  - **λ = 0,5**: una diferencia de color igual a la separación A−B suma medio punto de coste IoU;
  - **umbral = p99 de d / sep entre la pista y una detección limpia de la MISMA persona**, medido
    con el GT del benjamín en la pasada de hoy, para que la puerta no corte el 99 % de los
    emparejamientos buenos;
  - ⚠️ se calibra con la misma ventana del GT con la que se mide: el control (i) y la segunda
    caché (ii) protegen de un ajuste a esa ventana.

**B2, intento 2** (solo si B1 falla Y el bloque A da ≥ 70 % de cambios entre rivales):
- cortar las pistas en los intervalos de cruce (IoU > 0,1 con otra caja);
- reenlazar los trozos por continuidad de movimiento en metros (la posición predicha a velocidad
  constante, a ≤ 1,5 m) más el color de los frames limpios (d / sep ≤ el mismo umbral), con
  asignación húngara entre los trozos que salen y los que entran de cada cruce.

**Criterios** (los dos intentos, antes de medir):

| | hoy | criterio |
|---|---|---|
| impureza del CSV, benjamín | 22,8 % | **≤ 14** |
| impureza del CSV, Villaviciosa | 15,8 % | **≤ 11** |
| equipo equivocado por identidad, sin voto por observación (benjamín, ventana GT) | 16,0 % | **≤ 6 %** |
| detecciones asignadas por ByteTrack, benjamín | 98 % | **≥ 97 %** |
| detecciones asignadas por ByteTrack, Villaviciosa | 94 % | **≥ 93 %** (hoy ya está por debajo de 97: no más de 1 punto peor) |
| nº de identidades | — | **≤ hoy × 1,20** en las dos patas |
| partido entero (benjamín, producción con voto por observación): frames con otro ≥ 2 (filas reales) | 12,2 % | **≤ 8 %** |
| partido entero: frames con B > 7 | 28,5 % | **≤ 20 %** |

**Controles:**
- **(i) Color permutado.** El mismo término, con los vectores de color permutados al azar entre
  las detecciones del MISMO frame (semilla 0). No debe mejorar: impureza del CSV del benjamín ≥
  hoy − 1 punto. Si mejora igual, la mejora no viene del color.
- **(ii) Las dos cachés de 60 s del benjamín** (v3: `processor_benja.yaml`; v4:
  `processor_benja_v4.yaml`; las dos contienen la ventana del GT). Se mide el cambio de impureza
  respecto a la línea base de CADA caché. **Si cambia de signo entre cachés, no se adopta** (la
  lección de `margen_equipo`).

## Bloque C — la persona 21 de Villaviciosa (y las 6 y 0)

Con el GT (posiciones, sin vídeo): posición media; fracción de sus frames dentro de cada área
grande (F11, 100 × 64, áreas del modelo de campo); qué etiqueta le pone el sistema (filas casadas).
- **Si pasa la mayor parte del tiempo en un área**, es un portero con camiseta del color del rival
  y el fallo es de la regla de portero: se explica por qué la regla no lo corrige.
- **Si no**, la hipótesis sigue siendo un error de equipo en el GT, sin verificar.

Lo mismo para las personas 6 y 0 de Villaviciosa (las del offset sistemático del 22-oct d).

---

## Correcciones de proceso pedidas

- CLAUDE.md: la regla del commit (solo con pytest a código 0, sin pipes que se coman el código de
  salida).
- Donde ponga «SAHI 2×4»: con filas 2, columnas 4 y solape 0,2, `get_slice_bboxes` produce **15
  teselas (5 × 3)**, y `get_sliced_prediction` añade además una pasada de imagen completa
  (`perform_standard_pred=True` por defecto en SAHI 0.12.1). Son **16 inferencias por frame**, no 8.
