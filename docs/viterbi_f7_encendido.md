# Encender la pista del árbitro en F7 (`arbitro.viterbi.activo: true`)

Rama `viterbi-f7-on`, sale de `main` (3eb52c3). **Punto de reversión**: la etiqueta `pre-viterbi-f7`.
Criterio escrito y commiteado ANTES de medir. Solo se fusiona si el criterio se cumple y pytest da 0.

## El cambio
- En `configs/team_classification_benja.yaml` (F7): `arbitro.viterbi.activo: false` → `true`.
- **F11 sigue apagado**: `configs/team_classification.yaml` no tiene sección `campo` (formato `f11`)
  ni clave `viterbi`, así que `DEFECTOS_POR_FORMATO["f11"]` = apagado.

## Criterio (antes de medir)
1. **El CSV de equipos del benjamín con la pista encendida es idéntico byte a byte al de la variante
   2 ya medida**:
   - parte entera (`processor_benja_parte_entera.yaml`) contra
     `outputs/adopcion/posiciones_benja_p1_viterbi.csv`, que es idéntico al `v2_anade.csv` del 23-oct
     (d);
   - control adicional, el tramo de 60 s: v3 (`processor_benja.yaml`) contra
     `outputs/diagnostico_23oct_c/viterbi_benja60_v3_v2_anade.csv`, y v4 (`processor_benja_v4.yaml`)
     contra `…_v4_v2_anade.csv`.
   - Si no es idéntico: **no se fusiona**, y se dice qué difiere.
2. **Villaviciosa (F11) no cambia**: su CSV es idéntico byte a byte al de `pre-viterbi-f7`.
3. **Sin la caché de chaleco, el error sale CLARO y no es silencioso**:
   - `desde_cache` sin `rutas.cache_chaleco` (y sin la clave `chaleco` en la caché de detección)
     lanza un `ValueError` que dice qué falta y cómo arreglarlo, y no escribe ningún CSV;
   - el modo `full` sin banda lo lanza ANTES de cargar el detector.
4. pytest en 0 sobre la rama, y otra vez sobre `main` tras el merge.

¿Qué podría estar inventando? «Idéntico a la variante 2» prueba que encender la clave reproduce lo
medido; no vuelve a medir si la variante 2 es buena. Eso está en los diagnósticos del 23-oct (c, d
y e) y en las marcas de Alex del 26-oct (60/60 y 59/60).

## El ✗ de velocidad (anotado tal como se leyó)

El criterio del 23-oct (c), «velocidad de la pista > 9 m/s en ≤ 1 % de sus pasos», **NO se cumple**:
**1,03 %**. Se dejó el ✗ y **se leyó como no específico DESPUÉS de ver el fallo**: los jugadores del
GT, con el mismo muestreo, dan **2,28 % (2×)**, por el temblor de la detección
(`docs/diagnostico_23oct_d.md`, bloque 1). Es una lectura a posteriori, no un criterio fijado antes,
y así debe constar si se cita.
