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
