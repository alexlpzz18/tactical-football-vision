# Integración en `main` de las ramas del 22-26 oct (fix-23oct-a … h), SIN encender nada

**Punto de reversión**: la etiqueta `pre-integracion-23oct` = `main` en 2e94e35, antes del merge.

## Qué se hace
1. Se fija en el YAML de F7 (`configs/team_classification_benja.yaml`)
   `arbitro.viterbi.activo: false`, y se comprueba que F11 (`configs/team_classification.yaml`,
   sin sección `campo` → formato `f11`) también la tiene apagada.
2. Un test demuestra que un `activo: false` EXPLÍCITO en el YAML GANA al valor por defecto de F7.
3. Merge de `fix-23oct-h` (que contiene de la a a la g) a `main` con `--no-ff`.

## Criterio (antes de medir)
- Con las cachés del benjamín (parte entera y tramo de 60 s, v3) y la de Villaviciosa (60 s), el CSV
  de equipos de `desde_cache` es **idéntico byte a byte**:
  - desde `main` ANTES del merge (`pre-integracion-23oct`);
  - desde `main` DESPUÉS del merge, con la pista apagada.
- Si no lo es, se dice qué difiere.
- pytest en 0 sobre `main` tras el merge.

¿Qué podría estar inventando? «Idéntico» cubre `desde_cache` (tracking, equipos y CSV), no el modo
`full` (detección) ni el balón. El modo `full` cambia a propósito: guarda la puntuación de chaleco
en F7 y falla antes de detectar si el config es incoherente. Con la pista apagada, ninguno de los
dos cambios afecta a la salida.

## Cómo encender la pista del árbitro en F7 (y cómo revertir)

**Encender**: en `configs/team_classification_benja.yaml`, bloque `arbitro:`:

```yaml
  viterbi:
    activo: true        # antes: false
    variante: anade
    modelo_emision: configs/arbitro_viterbi_benja.json
```

- También vale BORRAR la línea `activo`: entonces decide el formato, que en F7 la enciende
  (`src/campo_modelo.py::DEFECTOS_POR_FORMATO`).
- Hace falta la puntuación de chaleco, de una de estas dos formas:
  - `rutas.cache_chaleco` en el config del processor (ya está en los tres del benjamín:
    `data/tracking_benja/cache_chaleco_*.pkl`; vienen de Drive, o se generan con
    `python scripts/cache_chaleco.py --config CONFIG --salida RUTA`);
  - una caché de detección hecha en modo `full` con `deteccion.chaleco_banda` (la clave `chaleco`).
- Si no hay ninguna de las dos, `desde_cache` da error. El modo `full` lo da ANTES de detectar.

**Apagar otra vez**: `activo: false` en la misma línea. Con eso la salida es idéntica byte a byte a
la de antes del merge (criterio de arriba).

**Revertir la integración entera** (deshacer el merge en `main`, conservando la historia):

```bash
git checkout main && git revert -m 1 <commit-del-merge> && git push origin main
```

o, para volver EXACTAMENTE a como estaba (reescribe la historia de `main`, solo con el OK de Alex):

```bash
git checkout main && git reset --hard pre-integracion-23oct && git push --force-with-lease origin main
```

**F11 (Villaviciosa)**: `configs/team_classification.yaml` no tiene sección `campo`, así que su
formato es `f11` y la pista está APAGADA por defecto (`DEFECTOS_POR_FORMATO["f11"]`). No tiene clave
`viterbi`. Encenderla exige una banda medida para Villaviciosa (`scripts/colab_arbitro_villa.py`,
sin ejecutar).
