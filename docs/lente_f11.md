# Lente de verdad para la cámara F11 de Villaviciosa (30-oct-2026)

Rama `lente-f11`, sale de `main`. **Primero lo que no toca producción.** Criterios escritos y
commiteados ANTES de medir. Máximo dos intentos. A `main` solo va documentación.

## El problema

La corrección actual (k1 = −1,5, k2 = 0,5, focal = ancho de la imagen) **se dobla**: el polinomio
r·(1 + k1·r² + k2·r⁴) alcanza su máximo en r ≈ 0,51 con valor ≈ 0,328, es decir, a **~840 px del
centro**. Nada del fotograma original más allá de ese radio llega a la imagen corregida, y las
esquinas cercanas del campo están a ~1.300 px. Ningún clic lo arregla.

## Hechos comprobados antes de empezar

- El vídeo del GT es `alevinA_casarrubuelos_f11_fijo_p1.mp4`, **2560 × 1064 nativo**, 25 fps. El
  1920 × 798 que se decía en `plan_generalizacion_f11.md` es Bazán, otro campo.
- El GT (`ground_truth_tracking`, frames 7500 + 15·k, 100 frames) y los 13 clics antiguos están en
  píxeles de la imagen CORREGIDA. Se pasan al original con el mismo polinomio de `cv2.undistort`.
- **Punto 4, misma cámara**: el cadete y el alevín tienen la misma resolución y, en 1.612 puntos de
  la estructura fija, el desplazamiento es < 0,5 px en todo el fotograma (residuo mediano 0,8 px).
  ⇒ Los clics valen para los dos partidos y la lente se reutiliza. La pose del cadete se reajusta con
  esos puntos fijos.

## 1. Herramienta

`scripts/herramienta_lente.py` → HTML con el fotograma ORIGINAL. Se puede alternar entre el alevín y
el cadete, porque están alineados: si un jugador tapa una marca en uno, se ve en el otro.
- **Cruces**: marcas de medidas conocidas.
- **Líneas rectas**: 3-5 puntos sobre cada línea, sin saber a qué metro caen; solo se sabe en qué
  línea están.

## 2. Ajuste y elección de modelo

- **Parámetros**: pose (6), focal (1), centro óptico (2) y lente; más, por cada punto de línea, su
  posición a lo largo de la línea (1 incógnita, porque aporta 2 ecuaciones).
- **Modelos**: ojo de pez (`cv2.fisheye`, 4 coeficientes) contra racional (`cv2.projectPoints` con
  k1-k6, sin tangencial).
- **Validación cruzada**: dejando fuera cada cruce, se ajusta con el resto (las líneas siempre
  dentro) y se predice ese cruce **en metros**, de píxel a metros. Se elige por la **mediana** de
  ese error; con menos de un 5 % de diferencia gana el de menos parámetros (ojo de pez). El error de
  ajuste se informa, pero no decide.
- **Se rechaza un modelo que se doble** (radio no monótono) dentro del radio máximo de la imagen: es
  el fallo que se quiere quitar.
- Informativo: largo y ancho libres, con las áreas de reglamento. Sale qué medidas pide el campo;
  100 × 64 nunca se midió.

## 3. ¿Mejora en metros?

⚠️ **La trampa**: el GT son cajas en píxeles, y sus metros salen de la misma calibración que se juzga.
Si una lente encoge las distancias, el error «sistema contra GT» baja sin mejorar nada. Por eso hay
dos medidas, y manda la primera:

- **A. Verdad independiente: las marcas del campo.** Error en metros en cada cruce dejado fuera,
  nueva frente a actual, por zona (cerca, media y lejos). Para la actual, los cruces del original
  más allá del pliegue se cuentan como «no representables».
- **B. La que pide Alex: sistema contra GT.** Mismas detecciones (`cache_detecciones_v4pre`), con el
  pie llevado a metros con cada calibración, y `desde_cache` entero:
  - posición: mediana del error, casado 1-a-1 a 2 m;
  - centroide por equipo y frame;
  - IC 95 % de la diferencia con bootstrap por frames;
  - **se informa la razón de escala** (m/px nueva entre actual) por zona, para no confundir la
    escala con la mejora.

**Pasa a proponerse para producción solo si** (a la vez):
1. A: la mediana del error baja **≥ 30 %** y en ninguna zona sube;
2. B: el centroide baja con el IC de la diferencia sin tocar 0, y esa bajada **no** se explica por la
   razón de escala (error en B dividido por la razón de escala, también con IC sin tocar 0);
3. el benjamín no cambia (no tiene lente; se comprueba el CSV byte a byte).

## 5. Recall por zona, imagen original frente a corregida

- 100 frames del GT. **Corregida**: la caché de producción. **Original**: detector en CPU (venv con
  numpy 1.26, `best_v4pre.pt`, los mismos parámetros) sobre el frame sin corregir.
- Cajas del GT llevadas al original con el polinomio. Emparejado de CENTRO 1-a-1, como en
  `diagnostico_23oct_e.md` (el IoU no es comparable: las cajas cambian de forma). Zonas: los terciles
  de metros por píxel de aquel documento.
- **Control**: en CPU, con la imagen corregida, se reproducen las cajas de la caché (≥ 95 % a
  IoU ≥ 0,9) en 3 frames. Si no, el vídeo no es el de la caché y se dice.
- **Criterio**: detectar sobre el original se propone solo si **en ninguna zona pierde más de 2
  puntos** de recall. Si pierde, se sigue detectando sobre la corregida y solo se cambia la
  conversión de los pies. Se pierde entonces lo que queda fuera de la corregida, y se dice cuánto.
- **Lo que no mide**: el GT no anota lo que está fuera de la imagen corregida, justo la zona que se
  gana. Se cuenta cuántas detecciones aparecen allí, sin acierto.

¿Qué podría estar inventando?
- **Un modelo con muchos parámetros** se ajusta a los clics y se desboca entre ellos: por eso se
  elige con validación cruzada, y se dibuja el campo encima para verlo.
- **Los cruces cercanos son pocos y están en el extremo**: dejar uno fuera es extrapolar. Es un error
  pesimista a propósito.
- **Las marcas pintadas pueden no estar a reglamento.** El error de una marca puede ser de la pintura,
  no de la lente: por eso el ajuste con largo y ancho libres se informa.

---

# Decisión de Alex (30-oct): deciden las marcas, y con largo y ancho libres

El GT es circular para juzgar la calibración: sus metros salen de la misma calibración. Por eso la
medida B deja de decidir y la **A manda**. Criterio nuevo, fijado ANTES de calcularlo:

- **reajuste con largo y ancho del campo LIBRES** (áreas y círculo a reglamento), modelo racional;
- **validación cruzada en metros, por zona**: cada cruce dejado fuera se predice con el resto, contra
  su marca en el campo con las medidas estimadas en ESE reajuste;
- **pasa si: mediana ≤ 0,5 m y p95 ≤ 1,5 m en las marcas, sin empeorar en ninguna zona respecto a la
  calibración actual;**
- **incertidumbre del largo y el ancho**: el rango de los reajustes dejando fuera cada cruce y cada
  línea (jackknife), y remuestreando los clics con ruido del tamaño de los residuos;
- el recall (punto 5) se mira antes de proponer nada en producción.

⚠️ La validación cruzada es pesimista en las marcas de los extremos, porque dejarlas fuera es
extrapolar. Se informa también el error SIN dejar fuera, pero no decide.
