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
