# Plan: calibración SEMIAUTOMÁTICA (4-6 clics guiados) — 5-oct-2026

Viene del negativo de `docs/calibracion_automatica.md`: con 6 clics bien elegidos salían
12,8 px en los 13 puntos no usados, contra 14,0 de los 19 clics. Este plan y el criterio
(`scripts/medir_subconjuntos_clics.py::CRITERIO`) se commitean ANTES de medir.

## Datos: dos campos, un frame cada uno

- **Benjamín (F7)**: 19 clics sobre `data/calibracion_benja/frame.png`.
- **Villaviciosa (F11)**: 13 clics sobre `data/calibracion/frame_corregido.png`, ya
  corregido de distorsión (con un residuo radial conocido). No es un sustituto del vídeo:
  son clics reales de otro campo, y sirven para ver si una regla se generaliza.

⚠️ Límites que se dicen ya: **un frame por campo, y los clics los hizo una sola persona.**
La "verdad" de los puntos no usados es otro clic, con su propio ruido. Si la diferencia
entre opciones es menor que ese ruido, se dirá que no se puede decidir.

## 1. Qué subconjuntos de 4, 5 y 6 puntos funcionan

Para cada k ∈ {4, 5, 6} y cada subconjunto (benjamín: 3.876 + 11.628 + 27.132; Villaviciosa:
715 + 1.287 + 1.716), H por mínimos cuadrados con esos k puntos. Error = mediana, en
píxeles, sobre los puntos NO usados. Los subconjuntos degenerados (tres puntos casi
alineados que dejan la H mal condicionada) se cuentan aparte, no se esconden.

**Referencias**:
- `base19` (la del criterio de Alex): el error de la H de TODOS los clics evaluada en los
  mismos puntos no usados. Parte con ventaja, porque esos puntos estaban en su ajuste.
- `loo` (honesta): para cada punto, el error de la H ajustada con todos los demás, y la
  mediana. Es lo que vale de verdad "todos los clics" fuera de muestra.

**Lo que se juzga es una REGLA fijada ahora, no el mejor subconjunto encontrado.** Elegir el
mejor de 27.000 y medirlo sobre los mismos puntos es elegir el ruido a favor. La búsqueda
exhaustiva se informa (mejor, mediana, percentil de la regla), pero no decide.

**Regla principal (R1)**: de los puntos a ≥ 30 px del borde de la imagen, los k que
**maximizan el área de su envolvente convexa en la imagen**. Solo usa posiciones en
píxeles, sin mirar ningún error. En la herramienta se aplica igual: con 4 puntos ya hay una
H provisional, que proyecta los puntos del modelo que faltan, y se piden los que más
agrandan la envolvente.

**Regla secundaria (R2)**, informativa: la misma, pero solo con **cruces de rectas** (sin
puntos del círculo ni de penalti, que son más difíciles de clicar con precisión).

## 2. Cómo se valida la H sin la confianza S

Tres validadores candidatos:

- **V1, cobertura de líneas**: de los puntos del modelo proyectados que caen en el césped,
  fracción a ≤ 4 px de un píxel de línea detectado (`auto_calibracion.mascara_lineas`). Ojo:
  es la misma medida que S, que no sirvió como OBJETIVO de una búsqueda. Aquí se usa sobre
  una H que viene de clics humanos, que es otra pregunta, y se mide si funciona.
- **V2, jugadores dentro del campo**: pies de las cajas del detector (cachés, 50 frames)
  proyectados con la H; fracción dentro del campo ± 3 m.
- **V3, coherencia de los clics** (solo k ≥ 5): error "dejando uno fuera" DENTRO del propio
  subconjunto. No necesita imagen.

**Criterio de utilidad de un validador**: sobre todos los subconjuntos de un campo, "bueno" =
error ≤ `base19` y "malo" = error ≥ 2 × `base19`. Un validador sirve si el **AUC entre
buenos y malos es ≥ 0,80 en los DOS campos**. Uno que no llega no entra en la herramienta.

## 3. La herramienta

`scripts/herramienta_calibracion.py` genera un HTML autocontenido, como las de los GT (el
frame y la máscara de líneas en base64):
1. Pide los puntos del modelo parametrizado (`src/campo_modelo.py`, F7 o F11), uno a uno,
   con un dibujo del campo que señala cuál toca. Primero los más fáciles de encontrar; se
   puede saltar cualquiera.
2. Con 4 puntos, calcula la H, dibuja el campo encima del frame y PROPONE los siguientes
   (los que más agrandan la envolvente, regla R1). Avisa si un clic cae a < 30 px del borde.
3. Valida solo con los validadores que pasen el criterio, y exporta un JSON con los
   puntos y la H (píxel → metros, la convención de `homografia_*.npy`), además del `.npy`
   generado desde ese JSON con `calcular_homografia`. No se integra en el pipeline.

## Criterio (resumen; el que manda es el código)

1. R1 con k = 4, 5 o 6: error mediano en los puntos no usados ≤ `base19`, **en los dos
   campos**. Se informa el k más pequeño que lo cumple.
2. Un validador entra en la herramienta si su AUC ≥ 0,80 en los dos campos.
