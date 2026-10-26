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

## Resultado (26-oct): CUMPLE

| caché | referencia | resultado |
|---|---|---|
| benjamín, parte entera | variante 2 (`outputs/adopcion/posiciones_benja_p1_viterbi.csv` = `v2_anade.csv`) | **idéntico byte a byte** |
| benjamín, 60 s v3 | `viterbi_benja60_v3_v2_anade.csv` | **idéntico byte a byte** |
| benjamín, 60 s v4 | `viterbi_benja60_v4_v2_anade.csv` | **idéntico byte a byte** |
| Villaviciosa, 60 s (F11) | el CSV de `pre-viterbi-f7` | **idéntico byte a byte** (F11 sigue apagado) |

- **La comparación discrimina**: con la pista apagada, el CSV del benjamín difiere del encendido en
  exactamente **5.238 filas**, todas de A/B a `otro`. Es el efecto medido de la variante 2: la pista
  corrió.
- **Error claro sin caché de chaleco**: el test
  `test_encendida_sin_chaleco_el_error_es_claro_y_no_escribe_csv` comprueba que, sin
  `rutas.cache_chaleco`, sale un `ValueError` que dice «ENCENDIDO», cómo arreglarlo
  (`rutas.cache_chaleco`, `deteccion.chaleco_banda`, o `activo: false`) y que no deja ningún CSV a
  medias. En el modo `full`, el fallo es ANTES de cargar el detector
  (`tests/test_bucle_deteccion_chaleco.py`).
- **Que un `false` explícito gana al formato** sigue cubierto
  (`test_un_activo_false_explicito_gana_al_defecto_de_f7`): es lo que permite apagar la pista con una
  línea.

**Cómo apagarla**: `activo: false` en `configs/team_classification_benja.yaml`. **Revertir**:

```bash
git checkout main && git revert -m 1 <commit-del-merge> && git push origin main
```
