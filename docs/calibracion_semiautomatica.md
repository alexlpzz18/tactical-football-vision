# Calibración SEMIAUTOMÁTICA: 6 clics guiados (5-oct-2026)

Plan y criterio commiteados antes de medir: `docs/plan_calibracion_semiautomatica.md`
(commit aa27503). Medición: `scripts/medir_subconjuntos_clics.py`. Herramienta:
`scripts/herramienta_calibracion.py` (no se integra en el pipeline).

## En una línea

**Con 6 puntos elegidos por una regla geométrica simple, la homografía queda igual o mejor
que con todos los clics, medido fuera de muestra, en los dos campos.** El criterio que se
fijó (compararla con TODOS los clics evaluados sobre sus propios puntos) no se cumple en
Villaviciosa por 0,7 px, muy por debajo del ruido de un clic: **con un frame por campo no se
puede decidir esa diferencia.** Con **4 puntos NO es fiable** (96 px en Villaviciosa). **Ningún
validador automático** separa las H buenas de las malas, así que la validación es visual.

## 1. Qué puntos funcionan

| | R1, k=4 | R1, k=5 | R1, k=6 | todos, en muestra | todos, dejando uno fuera (honesta) |
|---|---|---|---|---|---|
| **benjamín** (19 clics) | 16,8 vs 14,8 ✗ | **13,1 vs 15,0 ✓** | **12,7 vs 15,1 ✓** | 13,1 | 17,6 |
| **Villaviciosa** (13 clics) | **95,8** vs 6,6 ✗ | 9,2 vs 4,9 ✗ | 5,4 vs 4,7 ✗ | 6,7 | 8,4 |

Mediana en píxeles sobre los puntos NO usados; "vs" es la H de todos los clics evaluada en
esos mismos puntos (el listón del criterio, que es optimista porque los usó para ajustarse).

- **R1** = de los puntos a ≥ 30 px del borde, los k con mayor envolvente convexa en la imagen.
  Es mejor que el 90-95 % de los subconjuntos posibles en el benjamín y que el 99-100 % en
  Villaviciosa con k = 5-6. Con k = 4 en Villaviciosa solo supera al 53 %: con cuatro puntos,
  uno malo (allí `halfway_bottom`, el peor clic, con 95 px dejando uno fuera) no tiene quien
  lo compense.
- **El mejor subconjunto posible** (7,5 px en el benjamín, 2,6 en Villaviciosa con k = 6) está
  **sesgado**: es el mejor de miles, elegido sobre los mismos datos. Se informa, no se usa.
- **R2** (solo cruces de rectas) no aporta sobre R1: igual en Villaviciosa, y en el benjamín
  mejor con k = 4 y peor con k = 6.

**Puntos que estropean y que ayudan** (efecto de incluirlos, k = 6; coincide en los dos campos):

| estropean | ayudan |
|---|---|
| los del **círculo central** (+2,4 a +3,5 px) y el **centro** (+0,6 / +3,2) | **esquinas del campo**, **esquinas del área** que tocan la banda o el fondo, **penalti** cercano (−5,3 en el benjamín) |
| clics pegados al **borde** de la imagen (`box_left_top` en x = 0: 81 px dejando uno fuera) | |

Tiene sentido: los puntos del círculo y el centro están todos juntos en medio de la imagen
(poca palanca) y no son cruces nítidos de dos rectas.

## 2. El flujo

**Puntos que pide** (del modelo parametrizado `src/campo_modelo.py`; el mismo orden en F7 y
F11, porque se pide por TIPO de punto y cada modelo pone sus medidas):

1. Esquinas del campo (4) → 2. medio campo contra las bandas (2) → 3. esquinas del área sobre
   la línea de fondo (4) → 4. esquinas interiores del área (4) → 5. penaltis (2) →
   6. bases de los postes (4) → 7. centro → 8. círculo (4).
   Lo que no se ve se salta (la cámara del benjamín no ve las esquinas cercanas).
2. **Con 4 puntos** hay una H provisional: se dibuja el campo encima del frame y, a partir de
   ahí, se pide el punto visible (proyectado a ≥ 30 px del borde) que **más agranda la
   envolvente** (R1), dejando el centro y el círculo para el final.
3. **Mínimo 6 puntos** para exportar (con 4 no es fiable). Aviso si un clic cae a < 30 px del borde.

**Validación SIN la confianza S**, medida con AUC entre H buenas y malas sobre todos los
subconjuntos (útil si ≥ 0,80 en los dos campos):

| validador | benjamín | Villaviciosa | entra |
|---|---|---|---|
| V1 cobertura de líneas (el campo proyectado cae sobre píxeles de línea) | 0,80 | 0,61 | no |
| V2 jugadores del detector dentro del campo | 0,62 | **0,37** (al revés) | no |
| V3 coherencia de los clics (cada uno predicho por los demás) | 0,62 | 0,57 | no |

**Ninguno entra.** V2 sale al revés en Villaviciosa: una H mala puede meter a todo el mundo
dentro del campo, y "están dentro" no dice "están en su sitio". V3 castiga los puntos de los
extremos, que se extrapolan peor y son justo los que más ayudan. Así que la herramienta
**no da un veredicto automático**. Valida a la vista, con el campo dibujado encima del
frame en toda la imagen (lo que un humano ve en segundos y ninguna de estas métricas
captura), y el error "dejando uno fuera" solo va al JSON exportado, marcado como informativo.

## 3. La herramienta

```bash
python scripts/herramienta_calibracion.py --config configs/campo_benja.yaml \
    --frame data/calibracion_benja/frame.png --salida outputs/calibrar_benja.html
```

HTML autocontenido (el frame en base64, 0,5 MB), como las herramientas de GT. Pide punto a
punto, con un mapa del campo que marca cuál toca, una **lupa ×4** para clicar el cruce exacto,
y la H provisional dibujada encima desde el cuarto clic. Exporta
`puntos_marcados_<campo>.json` (el formato de `calcular_homografia.py`) y la H píxel → metros.

Comprobado:
- la homografía en JS es **igual a la de OpenCV** con 4, 7 y 19 puntos (DLT normalizada +
  refinado de reproyección; sin el refinado se separaba hasta 0,5 m con 19 puntos). Test con
  node: `tests/test_herramienta_calibracion.py`;
- en el navegador, con los 6 puntos de la regla sobre los clics del benjamín: el clic queda a
  ≤ 1,4 px de donde se pretende con un lienzo de 1.462 px de ancho (el redondeo del evento al
  píxel de pantalla). Dos fallos cazados en esa prueba: el clic se convertía con la caja
  EXTERIOR del lienzo (contando el borde), y en ventanas estrechas el panel lateral
  desbordaba la página.

## Límites (dichos sin generalizar)

- **Un frame por campo, y los clics los hizo una sola persona.** La "verdad" de los puntos no
  usados es otro clic con su ruido (6,7-13 px de residuo en muestra). Diferencias por debajo
  de eso, como los 0,7 px de Villaviciosa con k = 6, no se pueden decidir.
- Villaviciosa es un frame corregido de distorsión con residuo radial: allí los puntos
  extremos son a la vez los que más palanca dan y los más deformados.
- La herramienta no se ha probado con un usuario real clicando: el tiempo y los errores de
  identificación (confundir qué esquina es cuál) están por medir.
