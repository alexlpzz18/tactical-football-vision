# Plan: clasificación de equipos con brillo y pantalón (feature v2), para TODOS los campos

Escrito el 12-nov-2026, ANTES de medir. Encargo de Alex: arreglar los equipos del alevín B, pero
**no ajustando este partido**: un sistema que funcione en todos los campos y con todas las
equipaciones; si un día hace falta entrenar más, se verá.

## El síntoma y la premisa (comprobada antes de construir)

- Alevín B, parte 1, tramo 10-15 min: mediana de **4 de A y 15 de B por fotograma** (deberían ser
  ~10 y ~10). Colores de los prototipos: `#c6ebd6` y `#b7e2eb`, los dos claros.
- Equipaciones vistas en los recortes: una **clara** (blanca/celeste) y otra **negra**, más un
  árbitro amarillo flúor y un portero rojo.
- La feature de producción (v1) es un histograma de TONO y SATURACIÓN del pecho, sin brillo
  (`feature_v2.py`: «el negro no se distingue del blanco ni del gris»). Y el clasificador recorta
  SIEMPRE a esos 256 valores (`color_classifier._solo_hs`), aunque el caché traiga la v2.
- ⇒ Con una equipación negra, la v1 no tiene con qué separarla. No es un umbral de este campo: es
  una limitación de la representación, y aparecerá en cualquier partido con negro (o gris, o
  blanco contra blanco con pantalón distinto).

## El cambio (uno, general, detrás de un interruptor)

`ParametrosClasificadorColor` gana dos pesos, **por defecto 0** (= hoy, bit a bit):

- `peso_v_pecho`: peso del bloque de BRILLO del pecho (16 valores);
- `peso_pantalon`: peso del bloque HS del PANTALÓN (64 valores).

Con algún peso > 0 y una feature v2, el clasificador trabaja sobre
`[HS_pecho, peso_v · V_pecho, peso_p · HS_pantalón]` **renormalizado a norma 1**, así que las
distancias siguen en la escala de los umbrales calibrados (fusión 0,5-1,3). El árbitro, el cosido y
las oclusiones siguen con el bloque HS (no se tocan). Una feature v1 con pesos > 0 se queda en HS
(no hay bloques que añadir) y se avisa.

## Cómo se mide (las tres patas, el mismo arnés)

- **Benjamín** (F7, GT 29,5 s) y **Villaviciosa** (F11, GT 60 s): cachés v2 que ya existen
  (`*_v2color.pkl`), `desde_cache` de producción, `foto_de_estado.medir`: equipo equivocado
  (casado 1-a-1, 2 m), recuento correcto por equipo, centroide.
- **Alevín B** (F11, sin GT): caché v2 recalculado en el Mac (`scripts/colores_v2_mac.py`, con el
  control de ≥ 99 % de coincidencia del bloque v1 con producción). Medidas sin GT:
  - equilibrio por fotograma: mediana de min(A,B)/max(A,B) en el campo (hoy 4/15 = 0,27);
  - jugadores de campo por equipo en el campo: mediana de A y de B (F11 ⇒ ~10 cada uno, menos lo
    que no se ve);
  - **hoja de control** de 60 filas al azar del tramo 10-15 min con la CAJA DE LA FILA
    (`auditar_hojas`, CLAUDE.md): equipo a ojo contra la etiqueta.
- Barrido `peso_v_pecho` ∈ {0; 0,25; 0,5; 1} × `peso_pantalon` ∈ {0; 0,5; 1}.

## Criterios (fijados antes de mirar resultados)

1. **Interruptor real**: con los dos pesos a 0 el CSV es IDÉNTICO byte a byte al de hoy (test), y
   con un peso > 0 cambia (test de comportamiento, CLAUDE.md).
2. **Benjamín**: equipo equivocado ≤ el de los pesos 0 + 0,5 puntos, y recuento «ambos ok» sin
   bajar más de 2 puntos.
3. **Villaviciosa**: lo mismo que el benjamín.
4. **Alevín B**: equilibrio mediano ≥ 0,7 y hoja de control ≥ 90 % de acierto en jugadores.
5. **Una sola configuración para todos**: se elige el CENTRO de una meseta COMÚN a las tres patas.
   Si no hay meseta común, el parámetro no existe y se dice (CLAUDE.md).
6. ¿Qué podría estar inventando? Que el brillo separe **luz y sombra** en vez de equipos (el sol
   de este partido). Control: el equilibrio por bloques de 5 min de la parte entera, separando los
   minutos del destello, y que el reparto no siga a la mitad del campo con sombra.

Si no pasa, el siguiente paso NO es otro umbral: es una representación aprendida (embeddings) o
etiquetado, y se decide con Alex.

---

## Resultado (12-nov): NO CUMPLE en ninguna pata. Primera vía cerrada.

`scripts/banco_equipos_v2.py` (resultados en `outputs/banco_equipos_v2/resultados.json`). Control:
con pesos 0 el benjamín da **1,245 % sobre 723** casadas, la cifra de producción (CLAUDE.md).

| pesos (brillo, pantalón) | benjamín: eq. mal · centroide · ambos ok | Villaviciosa: eq. mal · centroide · ambos ok | alevín B: equilibrio 10-15 min |
|---|---|---|---|
| 0, 0 (hoy) | 1,2 % · 0,47 m · 52 % | 22,2 % · 4,69 m · 2 % | 0,25 (4 A / 15 B) |
| 0,25, 0 | 1,2 % · 0,46 m · 52 % | 22,8 % · 4,33 m · 6 % | 0,07 |
| 0,5, 0 | 2,1 % · 0,49 m · 50 % | 21,7 % · 4,90 m · 1 % | 0,00 |
| 1, 0 | 1,4 % · 2,39 m · **0 %** (361 casadas) | 26,2 % · 3,84 m · 7 % | 0,00 |
| 2, 0 | 1,9 % · 2,45 m · **0 %** | 22,7 % · 4,42 m · 6 % | 0,00 |
| 0, 0,5 | 2,1 % · 0,49 m · 50 % | 22,6 % · 4,66 m · 3 % | — |
| 0, 1 | 1,9 % · 0,49 m · 50 % | 23,0 % · 5,07 m · 1 % | — |

- **Pantalón**: empeora el benjamín (+0,7-0,8 puntos) y Villaviciosa (centroide hasta 5,1 m). Fuera.
- **Brillo**: solo 0,25 pasa en el benjamín; en Villaviciosa mejora centroide y recuento pero el
  equipo equivocado sube +0,6 (criterio ≤ +0,5); desde 1 el benjamín se rompe (la mitad de los
  jugadores a `otro`: separa por LUZ, que era el riesgo del criterio 6). Y en el alevín B, el caso
  que motivaba todo, **empeora** a cualquier peso. Sin meseta común ⇒ el parámetro no existe.

### Un fallo de MEDIDA cazado por el camino

`foto_de_estado.medir` busca el mejor emparejamiento A/B para el equipo equivocado, pero el
CENTROIDE lo calcula suponiendo A del sistema = A del GT. Con brillo 0,5 el fit llamó A al otro
equipo (lo llama A al grupo más grande) y el centroide salió **10,98 m**: la distancia entre los dos
equipos, no un fallo. El banco mide ahora con los dos nombres. ⚠️ `foto_de_estado.py` sigue con esa
suposición y debería corregirse (con A/B estables entre corridas no se nota).

### Lo que de verdad pasa en el alevín B (comprobado mirando recortes)

- Las equipaciones son **blanca con rayas azules** y **VERDE OSCURO** (no negra, como dije).
- La máscara anti-césped FIJA (H 35-85, S ≥ 40, V ≥ 40) borra gran parte de la camiseta verde
  pensando que es césped. Es un problema GENERAL: cualquier equipo de verde.
- Pero arreglar la máscara no basta: con la máscara medida por fotograma (v3,
  `mascara_posicion`) los dos grupos de un KMeans de 2 siguen MEZCLADOS (hoja de 449 recortes de
  40 frames). Con la neblina de este vídeo y 21-29 px, el blanco sale verdoso-azulado y el verde
  apagado: **en un recorte suelto, el histograma HS casi no distingue los dos equipos.**
- Pista lateral sin explicar: el equilibrio de la línea base sube con el minuto (0,19 → 0,82). Ajustar
  solo con los minutos 25-35 NO lo arregla (todo a 0): la luz no es la causa principal.
