# Plan: equipos con una representación APRENDIDA (DINOv2) y máscara de césped medida

Escrito el 12-nov-2026, ANTES de medir. Segundo intento de la clasificación general de equipos
(el primero, brillo y pantalón de la feature v2, NO CUMPLE: `docs/plan_equipos_v2.md`). Elegido
por Alex. Si no paga, la siguiente vía es etiquetar unos pocos recortes por partido, y se decide
con él.

## Por qué esta vía

- En el alevín B el histograma HS de un recorte suelto casi no separa los dos equipos (blanco con
  rayas contra verde oscuro, con neblina, a 21-29 px), y la máscara anti-césped fija se come la
  camiseta verde (hoja de recortes, 12-nov).
- `docs/benchmark_embeddings.md`: con recortes de < 20 px el HSV da 0,000 en «distinto equipo» y
  los embeddings 0,20-0,25; con recortes grandes, el HSV gana. La pregunta es dónde cae cada pata.
- DINOv2-base es Apache-2.0 (`docs/licencias_apariencia.md`): válido para producto.

## Qué se construye (todo detrás de interruptores, por defecto apagado = hoy)

1. **Embeddings de cada detección** en GPU (`scripts/colab_embeddings_equipos.py`, lanzado con
   `gpu_colab.py`): DINOv2-base, recorte cuadrado con holgura (el de `generar_embeddings.py`), sobre
   el fotograma TAL CUAL lo vio el detector (corregido con la lente de Villaviciosa si toca; original
   en el alevín B). Clave `(frame_idx, det_idx)` del caché de detecciones de PRODUCCIÓN de cada pata,
   con el nombre del caché de origen guardado (el aviso de `generar_embeddings.py`).
2. **El clasificador acepta la representación** `clasificador_color.representacion`:
   `hs` (hoy) · `embedding` · `hs+embedding`. Con embedding, KMeans y fusión sobre el vector
   normalizado; los prototipos HS se siguen calculando aparte para el árbitro y la pizarra (la
   lección del primer intento).
3. **Máscara medida** (`deteccion.mascara_color: posicion`, que ya existe) en el bloque HS, recalculada
   en el Mac con el ffmpeg de línea de comandos y con su control de reproducción.

## Cómo se mide (el arnés del primer intento, `banco_equipos_v2.py`, con los nombres A/B corregidos)

- Benjamín y Villaviciosa contra GT: equipo equivocado (1-a-1, 2 m), recuento «ambos ok», centroide.
- Alevín B: equilibrio A/B por fotograma (tramo 10-15 y por bloques de 5 min) y una **hoja de control
  de 60 filas** del tramo 10-15 con la caja de la fila, equipo a ojo.
- Brazos: `hs` (control), `embedding`, `hs+embedding`, y cada uno con máscara fija y medida.

## Criterios (fijados antes de mirar resultados)

1. **Interruptor real**: `representacion: hs` da el CSV idéntico al de hoy; las otras lo cambian.
2. **Benjamín**: equipo equivocado ≤ hoy + 0,5 puntos y «ambos ok» sin bajar más de 2 puntos.
3. **Villaviciosa**: equipo equivocado ≤ hoy + 0,5 puntos y centroide no peor que hoy.
4. **Alevín B**: equilibrio mediano del tramo ≥ 0,7 y hoja de control ≥ 90 % en jugadores.
5. Un solo brazo para todos. Si ninguno pasa en las tres, no se adopta nada.
6. ¿Qué podría estar inventando? Un embedding también codifica POSTURA, TAMAÑO y FONDO: puede separar
   «cerca contra lejos» o «corriendo contra parado» en vez de equipos. Control: el reparto A/B por
   franja de profundidad (y en tercios) tiene que ser parecido en las dos mitades de la franja, y la
   hoja de control se reparte por zonas.

## Coste

Una pasada de GPU corta: ~16.000 fotogramas y ~510.000 recortes en total (el alevín B es casi todo).
Estimado < 40 min de L4 (< 1,5 CU), con el tope de presupuesto del orquestador.
