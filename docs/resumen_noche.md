# Resumen de la noche (19-20 nov 2026)

Todo en la rama **`literatura-sota`** (sale de `alevinb-preparacion`), subida a `origin`. Nada en
`main`, ningún YAML de producción tocado, nada en `data/`, nada fusionado ni borrado. Todo lo nuevo
está detrás de interruptores APAGADOS.

**Comprobación de base**: con los interruptores apagados, esta rama da el CSV **idéntico byte a byte**
al de `main` en Villaviciosa, el benjamín de 60 s y el benjamín entero (`scripts/identidad_con_main.py`).

## Tabla

| # | tarea | estado | resultado frente al criterio | dónde |
|---|---|---|---|---|
| 1a | Deep-EIoU sin apariencia (código propio: el repo no tiene licencia) | **hecha, no cumple** (2 intentos) | IDF1 +1,0-2,5 puntos (pedía +5); intercambios entre rivales en cruce SUBEN (20 → 25-27); equipo equivocado del benjamín 1,2 → 2,2-2,5 % | `docs/plan_literatura.md` |
| 1b | Postproceso global tipo GTA-link | **hecha, no cumple** (2 intentos) | apariciones: sin cambio en el tramo 14:00-15:30, −40 % en el alevín A y SUBEN en el alevín B (pedía −50 % sin bajar IDF1 por equipo). Lo bueno: IDF1 global +3,7 y parpadeo de color 45 → 9-21/min en el benjamín | ídem |
| 2 | Parpadeo en cruces: preguntas | **hecha** | (a) «congelar» era en **metros** (R = 1,5-2 m); (b) la ventana de 1,5 s está **centrada**; (c) se guarda **solo la etiqueta**, no la probabilidad | `docs/plan_parpadeo_torso.md` |
| 2a | Máscara de torso tapado en la imagen (> 15 % del pecho, ±3 obs.) | **hecha, no cumple** | parpadeo 48 → 49/min (pedía ≤ 24); equipo equivocado 1,2 → 1,9 % (GT) y 0,9 → 1,8 % (hoja de 120) | ídem |
| 2b | Intercambio de colas entre rivales con colores invertidos | **hecha, no cumple** | parpadeo 48 → 44 (−8 %); equipo 1,2 → 1,7 %; IDF1 de A 0,64 → 0,53 | ídem |
| 3 | Lente F11 con largo y ancho libres | **ya estaba hecha (30-oct), no cumple** | mediana 1,13 m (pedía ≤ 0,5), la zona lejana empeora. **Largo 96,1 m (93,3-97,8) · ancho 64,3 m (63,5-65,5)**; el 100 × 64 solo queda fuera si las áreas están a reglamento. No se ha repetido (sería reabrir una ruta cerrada) | `docs/lente_f11.md` |
| 4 | Superposición táctica sobre el vídeo (30 s) | **hecha (prototipo)** | contorno de cada equipo, líneas defensa-medio-ataque promediadas en 3 s y distancias entre líneas en metros, sin números de identidad. Benjamín 14:00-14:30 | `outputs/literatura/superposicion/benja_14m00s.mp4` (+ 3 capturas) |
| 5 | Motor del informe con SkillCorner | **hecha (borrador)** | conversor de SkillCorner a NUESTRO formato de CSV + motor que lee ese formato: métricas de forma por tramos de 10 s (largo y anchura del bloque, altura de la defensa, distancia entre líneas, ocupación de zonas), con y sin balón, e informe de 1 página con «3 cosas a entrenar» por reglas. Acredita a SkillCorner | `outputs/literatura/informe/1874553_local.html` |
| 6 | Scripts de GPU de los métodos 3-6 | **preparada** (3 de 4) | probados en CPU con 3 fotogramas: pose (3), franjas (4), SigLIP (5). WASB (6) **bloqueado**: sin código de entrenamiento oficial y sin etiquetas del balón en juego | `docs/celdas_gpu_literatura.md` |
| — | Método 3 (pelvis con pose), medido en CPU | **hecha, no cumple** (2 intentos) | temblor lejano −10 % en el benjamín y +18 % en el alevín A (pedía −30 %); en el F11 la pose solo es fiable en el 3,4 % de las detecciones lejanas | `docs/plan_literatura.md` |
| — | Método 5 (SigLIP + UMAP + K-means), medido en CPU | **hecha, no cumple (1 intento)** | **alevín A: error 24,8 → 13,2 %** por recorte (27,0 → 12,6 % con voto); **benjamín: 7,1 → 10,0 %** (empeora) | ídem |
| — | Método 4 (recortes en la franja lejana), medido en CPU | **PENDIENTE de la medida corregida** | la primera medida era inválida por un fallo mío (cajas sin desplazar al fotograma); se está repitiendo | ídem |

## Lo que te toca a ti por la mañana

1. **Lo más prometedor de la noche es SigLIP en el F11**: divide por dos el error de equipo del alevín A
   (24,8 → 13,2 %), pero empeora el benjamín. Propuesta de segundo intento (decides tú si se hace): que
   cada partido elija entre el histograma y SigLIP con la consistencia física que ya funcionó con el
   brillo. Para medirlo en el alevín B hace falta tu **hoja de 300 recortes** marcada.
2. **Mira el vídeo de la superposición** (`benja_14m00s.mp4`) y dime si esa forma de enseñar el bloque es
   la que quieres: es el criterio humano que ninguna métrica sustituye.
3. **Mira el borrador del informe** (`1874553_local.html`): las referencias de las «3 cosas a entrenar»
   son proporciones del campo puestas a mano. Hay que decidir si te valen como punto de partida o
   preferimos calibrarlas con partidos de base.
4. **Hoja de 40 fotos del balón** (`outputs/hoja_balon_visible/index.html`, ~10 min): decide si merece la
   pena etiquetar el balón (y desbloquea WASB).
5. **Lente F11**: lo pendiente desde octubre sigue igual: medir de verdad el campo de Villaviciosa (largo,
   ancho, área y círculo).

## Notas de método (cosas que pasaron y conviene saber)

- La primera comprobación de identidad con `main` dio una diferencia en Villaviciosa. Era de mi
  comprobación (cargaba el config de equipos por defecto de la rama), no del código; corregida.
- La medida de la hoja de 120 empezó dando «109 marcas sin fila»: las coordenadas de la hoja son del
  recorte ampliado, no del fotograma. Corregida antes de leer nada.
- El método 4 dio tres variantes idénticas hasta el decimal y por eso se revisó: era un fallo mío.
- `pip install` en el entorno del detector subió numpy y rompía torch; devuelto a numpy 1.26.4 antes de
  seguir. Ese entorno (`~/.venvs/detector-cpu`) tiene ahora también umap-learn 0.5.7, onnxruntime y
  rtmlib.
