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

---

## Resultado (12-nov): NO CUMPLE en el alevín B. Segundo intento cerrado (no se adopta).

Embeddings DINOv2 de las tres patas en una pasada de L4 (1,00 h, ~2 CU), sobre los cachés de
detecciones de PRODUCCIÓN. Control: `representacion: hs` reproduce producción en el benjamín
(1,245 % sobre 723).

| brazo | benjamín: eq. mal · centroide | Villaviciosa (producción): eq. mal · centroide | alevín B: equilibrio · mini-GT a ojo |
|---|---|---|---|
| hs (hoy) | 1,2 % · 0,47 m | 23,6 % · 4,37 m | 0,25 · 65,8 % |
| embedding | **29,9 %** · 3,70 m (361 casadas) | 18,8 % · 3,77 m | 0,12 · 64,6 % |
| hs+embedding 0,5 | 1,2 % · 0,47 m | 24,1 % · 4,09 m | 0,00 · — |
| hs+embedding 1 | 1,7 % · 0,49 m | **15,8 % · 3,30 m** | 0,00 · 55,7 % |
| hs+embedding 2 | 29,9 % · 3,70 m | 15,5 % · 4,80 m | 0,00 · — |

- **Benjamín y Villaviciosa con `hs+embedding 1` cumplen** sus criterios (benjamín justo: +0,4 y
  −1,7 puntos; Villaviciosa, mucho mejor). **El alevín B no**: ningún brazo pasa del 66 % en el
  mini-GT, que es casi lo que da «todos al mismo equipo» (62 % son blancos). Sin las tres, no se
  adopta (criterio 5).
- El embedding solo separa otra cosa en el benjamín (la mitad de los jugadores a `otro`): el riesgo
  del criterio 6 (postura, tamaño, fondo).

### Mini-GT del alevín B (nuevo, reutilizable)

`outputs/gt_equipos_alevinb/detecciones_120.csv`: 120 detecciones al azar del tramo 10-15 min, 40
por franja de profundidad, etiquetadas a ojo ANTES de ver ningún brazo (49 blancos, 30 verdes, 6
árbitro, 4 portero, 31 dudosas). Indexado por caja y frame. Se mide con
`scripts/medir_gt_equipos_alevinb.py`, que lee la etiqueta de la fila de ESA detección.

### Comprobación de premisa para la tercera vía: CON ETIQUETAS, sí se separan

Regresión logística sobre los 79 jugadores claros del mini-GT, por recorte suelto:

| features | 5 particiones (~63 de entreno) | 10 etiquetas por equipo (50 repeticiones) |
|---|---|---|
| HS (hoy) | 76 % | 70 % |
| DINOv2 | 84 % | 76 % |
| DINOv2 + v2 (brillo y pantalón) | 90 % | 87 % (p10 81 %) |

La información está en las features: lo que falla es el agrupado SIN etiquetas, que encuentra otro
eje (luz, postura). Con unas pocas etiquetas por partido, y el voto por ventana que ya hace el
sistema, la tercera vía tiene base medida.
