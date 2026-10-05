# Calibración AUTOMÁTICA del campo desde las líneas: NO VIABLE en el benjamín (dos intentos)

Pregunta (Alex, 3-oct-2026): ¿se puede estimar la homografía detectando solo las líneas
pintadas, con una precisión comparable a la de los 19 clics manuales? Plan y criterio
commiteados antes de medir: `docs/plan_calibracion_automatica.md` (commit 125d5bf).
Método: `src/homography/auto_calibracion.py` (no lo importa el pipeline). Medición:
`scripts/medir_calibracion_automatica.py --busqueda {estrecha|amplia}`.

**Conclusión: no viable con este método en este campo.** Los dos intentos suspenden la
precisión (a, b). El fallo no es de la maquinaria: en una escena sintética recupera la
cámara a < 3 px. Lo que falla es esta escena: marcas que no están en el modelo F7 y la
mitad cercana fuera de plano. Por eso aparecen soluciones falsas que la búsqueda no
consigue evitar.

Villaviciosa no se midió: su vídeo no está en local, y no se usó ningún sustituto.

## Resultados

| | (a) clics: auto vs manual (px) | (b) pies del GT | (c) dispersión, aceptados | (d) controles | viable |
|---|---|---|---|---|---|
| criterio | auto ≤ 1,5 × manual | ≤ 1,0 m | ≤ (a), ≥ 16/20 | todos S < 0,5 | |
| intento 1 (búsqueda estrecha) | **684** vs 11,2 ✗ | **28,0 m** ✗ | 46 px ✓*, 19/20 ✓ | ✓ (0,13-0,46) | **no** |
| intento 2 (búsqueda amplia) | **59,7** vs 11,2 ✗ | **2,28 m** ✗ (p90 3,7) | **247 px** ✗, 19/20 ✓ | ✓ (0,13-0,37) | **no** |

\* El 46 px del intento 1 "pasa" solo porque se compara con su propio error de (a), que es
enorme. El criterio es correcto, pero con un (a) tan malo ese punto no dice nada.

En el intento 2 los 20 frames caen en dos grupos: unos a 43-75 px de los clics y otros a
~330 px. Son el valle bueno y uno falso, el del campo desplazado sobre las líneas de
cerca. Y la confianza los acepta a los dos.

## Por qué falla (causas medidas, no supuestas)

1. **Hay marcas que no están en el modelo y que imitan a las que sí están.** En el campo
   hay semicírculos frente a las áreas, áreas pequeñas en el fondo y dos líneas paralelas
   largas junto a la cámara. El modelo F7 del reglamento (área 26×12, círculo de 6 m) no
   las tiene. Visto en el frame de desarrollo: el ajuste colocaba el **círculo central sobre
   el semicírculo grande de cerca** y desplazaba el campo media longitud. Las líneas de cerca
   son las más largas en píxeles, así que pesan más que nada.
2. **Primero fue un problema de coste, y después de búsqueda.** Contar como fallo cada punto
   del modelo fuera de plano hacía que un campo ENCOGIDO dentro del encuadre ganara a la
   solución correcta. Se añadió el coste inverso (cuánta línea detectada explica el modelo)
   y, con él, la H manual sí tiene menor coste que las soluciones falsas (0,77 frente a
   0,87 con τ = 25 px). Desde ahí, el fallo es de búsqueda: el valle bueno es estrecho.
   El intento 2 (semillas diversas) llega a él en algunos frames y en otros no.
3. **La confianza S no distingue un ajuste bueno de uno malo.** Separa "hay líneas" (0,5-0,6)
   de "no las hay" (controles aleatorios: 0,13-0,25). Pero acepta 19 de 20 frames con
   errores de 43 a 685 px. Un producto que se calibre solo necesita saber cuándo ha fallado,
   y esto no lo sabe.
4. **El ajuste fino (ICP) no ayuda en la escena real**, ni partiendo de la H manual
   (11,2 → 12,2 px): las marcas que no están en el modelo también tiran de él. En la escena
   sintética funciona.

### Fallos propios corregidos por el camino (en el frame de desarrollo, antes de medir)

- Máscara del campo: la envolvente convexa del verde se comía la grada y la ladera de hierba
  natural. Ahora se usa el tono del césped artificial (~54) y el contorno exterior relleno.
- Rejilla de cámaras: solo apuntaba a puntos DEL campo, pero la cámara real tiene el eje
  óptico sobre el horizonte, a ~140 m. Ahora llega más allá del campo.
- Truncar en vez de redondear al pasar a píxel: 7 px de deriva del ICP partiendo de la
  solución exacta. Lo cazó el test sintético (`tests/test_calibracion_automatica.py`).
  Afectaba a la primera corrida del intento 1, que se repitió.

## Lo que sí sale de esto (sin medir más que un frame)

**6 clics bien elegidos valen lo que 19.** Con los 6 puntos más nítidos (centro, medio campo
contra las dos bandas, las esquinas del área lejana y el penalti lejano), el error en los 13
puntos NO usados es de **12,8 px**. La H de 19 clics da **14,0 px** en esos mismos puntos, y
eso que los usó para ajustarse. Los clics del borde de la imagen (`box_left_*`, 45-70 px de
residuo) estropean más de lo que aportan. Es un solo frame de un solo campo: es una pista,
no una cifra para el producto.

## Qué haría falta para pasar a producto

1. **Modelar el campo REAL, no el del reglamento.** Las marcas que no están en el F7 son la
   primera causa del fallo. Hay dos opciones: una plantilla por campo, que se crea una vez
   (los campos de base se repiten cada semana), o un modelo con marcas opcionales
   (semicírculos, áreas pequeñas, un segundo marcaje) que el ajuste pueda activar.
2. **Una confianza que sepa decir "he fallado"**: por ejemplo, la coherencia entre frames
   (los dos grupos de 60 y 330 px se ven al comparar frames) o un residuo por línea, no global.
3. **Con paneo**: una H por frame, que exige todo lo anterior y además seguimiento entre
   frames (`docs/paneo_y_gran_angular.md`).
4. **Con 0,5x**: distorsión. El modelo de plano deja de valer: hay que estimar la lente a la
   vez que la H (K, k1, k2) o corregirla antes con una calibración propia.
5. **Otros campos F7/F11**: el método es paramétrico (largo, ancho, marcas), pero cada
   marcaje superpuesto es un caso nuevo. Hasta tener (1) y (2), lo realista es
   **semiautomático**: 4-6 clics guiados en lugar de 19.

## Reproducir

```bash
python scripts/medir_calibracion_automatica.py --busqueda estrecha   # intento 1, ~35 min
python scripts/medir_calibracion_automatica.py --busqueda amplia     # intento 2, ~45 min
```
Resultados en `outputs/calibracion_automatica/resultados_*.json`. Solo guarda frames en memoria.
