# Plan: suavizado por TIEMPO real y sin cruzar saltos imposibles — SIN CONSTRUIR (9-oct-2026)

Hipótesis de Alex, solo el plan de medición. Viene de `docs/traza_por_etapas.md` (segunda vuelta):
el suavizado es una media móvil sobre MUESTRAS consecutivas con una ventana real de ~2 s, que
promedia a través de huecos de tiempo y de saltos imposibles. Así movió 0,8-6,4 m las 9 filas que
el post-proceso pierde en la ventana del GT.

**Expectativa honesta antes de medir**: la causa de fondo es la asociación (en 5 de 9 la identidad
recorre 2-3 personas). Esto solo limita el daño. El TECHO del beneficio es lo que cuesta el
suavizado entero: +0,066 m de centroide (IC 95 % [+0,033, +0,103], `docs/desglose_por_episodios.md`).
La meta es acercarse a la precisión de «sin suavizar» conservando el temblor de «con suavizado».

## Las variantes (cada cambio por separado, y luego juntos)

| | qué cambia | qué aísla |
|---|---|---|
| **V1, tiempo** | la ventana de cada muestra son las muestras reales a ±T/2 **segundos** de ella, con la MISMA longitud T que usa hoy esa trayectoria (base × escalado por resolución) | solo el efecto de no promediar a través de huecos: la longitud no cambia |
| **V2, saltos** | la trayectoria se parte en tramos donde un paso entre muestras reales supera **12 m/s** y se suaviza cada tramo por separado (la ventana de hoy) | solo el efecto de no cruzar saltos |
| **V3** | V1 + V2 | la combinación |

12 m/s es el umbral ya usado en el balón y por encima de cualquier niño de 8-9 años. No se barre:
si V2 no paga con 12, no se busca otro número. Como mucho dos intentos: el segundo solo puede
ajustar T (por ejemplo, el tope de la ventana en segundos), nunca la regla de los saltos.

## Las dos líneas base

- **B0 = producción de hoy**: el CSV regenerado desde el caché con el código actual (no el CSV
  viejo de `data/`).
- **B1 = sin suavizado** (`suavizado.activo: false`): la cota. Tiene la mejor precisión y el peor
  temblor. Sirve para leer cuánto del margen recupera cada variante: (B0 − V) / (B0 − B1).

El suavizado corre DESPUÉS de clasificar, así que no toca el fit de color: en Villaviciosa no se
activa el canal caótico del suelo de ruido (`docs/reglas_fisicas.md` §5). Las diferencias entre
variantes son solo posiciones.

## Las dos patas

- **Benjamín**: la parte entera (`processor_benja_parte_entera.yaml`). Con GT en la ventana de 5:25 a
  5:55 de archivo (de 6:58 a 7:28 del reproductor); sin GT, el partido entero.
- **Villaviciosa**: el tramo de 60 s (`processor.yaml`, caché `v4pre`) con su GT (offset 7500,
  paso 15). Usa el mismo suavizado (media, 0,5 s, escalado 1,0).

## Métricas y criterio (fijado aquí, antes de medir)

Diferencias PAREADAS contra B0, con IC 95 % por remuestreo de bloques de 5 s (el método del +0,066).
Para el temblor, el remuestreo es por identidades. Una diferencia «cuenta» si su IC excluye el 0.

**Qué arregla** (al menos una tiene que mejorar con IC, en al menos una pata):
1. Filas `es_real=1` a > 1 m de toda detección (benjamín hoy: 6,9 %; fondo 11,5 %).
2. Pérdidas de la etapa e de la traza (`scripts/traza_por_etapas.py`, radio 5 m; hoy 9 de 814).
3. Error de centroide por (frame, equipo) contra el GT.

**Qué podría estar rompiendo** (ninguna puede empeorar con IC, en ninguna pata):
4. **Temblor** (`scripts/temblor.py`: σ ≈ MAD(Δ²)/√6) **por franjas de profundidad** (x 0-20,
   20-40, 40-62 m), porque el suavizado existe para el fondo. Una variante que baja el temblor
   cerca y lo sube en el fondo NO pasa.
5. Pasos > 12 m/s en las filas pintadas (lo que se ve en el replay).
6. Anchura y profundidad del bloque contra el GT.
7. En Villaviciosa, además: IDF1 y AssA del banco (el suavizado no toca la identidad, pero mueve
   posiciones respecto al umbral de casado).

**Controles que tienen que salir EXACTOS** (si no, hay un bug y no se lee nada):
- el mismo número de filas por identidad que B0 (el suavizado no añade ni quita puntos);
- con la regla V1 y una trayectoria sin huecos ni saltos, el resultado byte a byte igual que B0
  (test sintético);
- las posiciones de entrada al suavizado idénticas en las cuatro corridas (espía, como en
  `scripts/diagnostico_filas_movidas.py`).

**Adopción**: mejora al menos una de 1-3 con IC, no empeora ninguna de 4-7 en ninguna pata y pasa
los controles. Y, como siempre, solo con el OK de Alex.
