# Plan: calibración AUTOMÁTICA del campo desde las líneas (3-oct-2026)

Pregunta de Alex: ¿se puede estimar la homografía campo-imagen detectando solo las
líneas pintadas, con una precisión comparable a la de los 19 clics manuales? Se mide en el
benjamín. Solo CPU y sin redes preentrenadas. No se toca producción ni la homografía actual.
Este plan y el criterio (`scripts/medir_calibracion_automatica.py::CRITERIO`) se commitean
ANTES de medir.

**Villaviciosa: no se puede medir.** Su vídeo no está en local (`data/raw/` solo tiene el
del benjamín). Hay un `frame_corregido.png` suelto, pero Alex dijo que sin sustituto.

**Modelo del campo: 62 × 40, no 62,7 × 40,7.** En el repo no aparece 62,7 × 40,7. Los 19 clics y
`homografia_benja.npy` están en las coordenadas del modelo 62 × 40 de
`configs/campo_benja.yaml`, y la comparación solo tiene sentido en el mismo sistema.

## Lo que se ve en el frame (y lo que lo hace difícil)

- **Visible del modelo F7**: la línea de medio campo, el círculo central, el área lejana
  completa, la línea de fondo lejana, las bandas desde medio campo hasta el fondo y la línea
  del área cercana. **Fuera de plano**: la línea de fondo cercana y sus esquinas.
- **Marcas que NO están en el modelo**: semicírculos frente a las dos áreas, áreas pequeñas
  en el fondo y líneas de más junto a la cámara (otro marcaje superpuesto). Detrás de la
  grada asoma **otro campo con sus líneas**.

## Método (intento 1)

1. **Píxeles de línea.** Máscara del campo: césped verde en HSV, la componente conexa más
   grande y su envolvente convexa (así quedan fuera el otro campo y la grada). Dentro, las
   líneas son lo **claro y estrecho**: top-hat del brillo (lo que es más claro que su entorno
   en una ventana pequeña) con poca saturación. Se descartan las componentes cortas, que son
   sobre todo jugadores; las líneas y los arcos son largos.
2. **Sin Hough ni emparejado de segmentos.** Emparejar segmentos con líneas del modelo es
   un problema combinatorio, y es justo donde un círculo se confunde con un arco o un área
   con un área pequeña. En su lugar, se alinea el modelo ENTERO de una vez: el modelo F7 se
   muestrea en puntos (bandas, fondos, medio campo, círculo, las dos áreas), se proyecta con
   una H candidata, y el coste es la distancia de cada punto proyectado al píxel de línea
   más cercano (transformada de distancia, truncada). Solo cuentan los puntos que caen
   dentro de la imagen y de la máscara del campo.
3. **Inicialización robusta con una CÁMARA FÍSICA.** La H se parametriza como una cámara
   real: posición (x, y, altura), orientación (rumbo, inclinación, giro) y focal, sin
   distorsión, porque esta cámara no la tiene. Se barre una rejilla gruesa de cámaras
   plausibles alrededor del campo (detrás de cada portería y en cada banda, a 2-15 m de
   altura, apuntando a puntos del campo), con varias focales. Las mejores semillas se
   refinan (Nelder-Mead sobre los 7 parámetros) y al final se refina la H completa de 8
   grados de libertad (ICP: cada punto del modelo con su píxel de línea más cercano,
   mínimos cuadrados robustos, iterado).

### Que solo se vea una parte del campo

El coste solo mira los puntos del modelo que caen dentro del encuadre y del césped, así que
la línea de fondo cercana, fuera de plano, ni ayuda ni estorba. Para que la solución no sea
"proyectar el campo fuera de la imagen", se exige además una **fracción mínima de modelo
visible**. La cámara física impide las H degeneradas (encoger el campo a un rincón o
voltearlo), que son la trampa clásica de alinear con solo una parte del campo.

### Que el círculo, las áreas y las marcas no se confundan

- **Alineado global**: el círculo no puede caer sobre un semicírculo de área sin que, a la
  vez, el medio campo, las bandas y el área lejana dejen de cuadrar. Una sola H tiene que
  explicar todas las líneas del modelo a la vez.
- **Las marcas que no están en el modelo no se modelan**, y el coste solo va del modelo a
  la imagen. Una línea de más en la imagen no castiga; solo puede "atraer" si está más
  cerca que la línea buena, y la distancia truncada limita su tirón.
- **Varias semillas**: la rejilla explora orientaciones distintas, y la puntuación final
  decide cuál gana.

### Puntuación de confianza (para decir "no sé")

`S` = fracción de los puntos visibles del modelo que quedan a ≤ 4 px de un píxel de línea
tras el ajuste. Se **acepta** la H si `S ≥ 0,5`. Fijado ahora, sin haber visto ningún valor.

## Criterio (lo que manda es el código)

a) **19 clics como verdad independiente** (no se usan para ajustar): mediana del error de
   reproyección en píxeles con la H automática ≤ 1,5 × la mediana con la H manual. Con dos
   salvedades: la manual se mide sobre los mismos puntos con los que se ajustó, así que su
   error es optimista y el listón, exigente; y dos clics están en el borde de la imagen
   (`box_left_*`, x = 0 y x = 1919). Se informan aparte, pero cuentan.
b) **Pies del GT** (814 cajas, 60 frames): mediana de |pie con H auto − pie con H manual|
   ≤ 1,0 m (el suelo de ruido). Solo hace falta la H, no el vídeo.
c) **Robustez**: 20 frames repartidos por los 20 min, sacados con
   `posicionar_en_frame()`. Dispersión = mediana, sobre los 19 puntos del modelo, de la
   distancia en px de cada H a la proyección mediana de ese punto. Tiene que ser ≤ el
   error de (a).
   **Añadido**: además, se acepta (S ≥ 0,5) en ≥ 16 de los 20 frames. Si el método se
   abstuviera en la mitad, la dispersión de la otra mitad no diría nada de su robustez.
d) **Control**: el método tiene que RECHAZARSE (S < 0,5) en 10 máscaras de segmentos
   aleatorios (mismo número de píxeles de línea que la real) y en la máscara real volteada
   de arriba abajo (no hay perspectiva física que la explique). Si acepta alguna, "acierta
   cualquier cosa".

Viable = a, b, c y d. Si falla, un segundo intento de método como máximo, con el mismo
criterio. Si también falla, se documenta el negativo con su causa.
