# Resumen del merge a main — para revisar ANTES de fusionar

`v4/caches-y-informe` → `main`. **69 commits, 142 ficheros, +24.981
líneas.** Las diez ramas apiladas de las últimas semanas están todas
contenidas en esta, así que es un único merge y luego se pueden borrar.

Ramas absorbidas: `feature/tracking-v4pre`, `feature/migracion-bytetrack`,
`feature/informe-v2`, `feature/balon`, `feature/analisis-ia`,
`barrido/fit-clasificador`, `barrido/suavizado`,
`barrido/asociacion-combinada`, `remedicion/v2color`,
`feature/tracking-ventana`.

## Lo que CAMBIA EL COMPORTAMIENTO por defecto

Esto es lo que hay que mirar con lupa; el resto es aditivo.

| cambio | de → a | por qué |
|---|---|---|
| `processor.yaml: tracking.perfil` | `candidato` → **`bytetrack`** | ByteTrack bate al tracker artesanal en todo lo que mide la calidad de una identidad: IDF1 0,406 vs 0,334, y **5 quimeras frente a 24** |
| `team_classification.yaml: agregacion.min_obs_para_otro` | (no existía) → **25** | Adoptado hoy. Cobertura 0,619→0,633, accuracy 0,750→0,804, puras mal 7→5. Neutro en el benjamín |
| `team_classification.yaml: staff.activo` | (no existía) → **true** | Quien vive fuera del campo no juega: quita al juez de línea del informe |
| `team_classification.yaml: arbitro.activo` | (no existía) → **true** | Catálogo absoluto de equipaciones arbitrales |

Todo lo demás en `tracking.yaml` (`bytetrack`, `cosido_pureza`,
`suavizado`, `consolidacion`, `corte_velocidad`, `presets`) son **claves
nuevas de etapas nuevas**, y las etapas viejas siguen disponibles por
config: el flujo `pipeline: legacy` no se ha tocado.

## Lo que entra DESACTIVADO y por qué

| pieza | estado | motivo |
|---|---|---|
| `puerta_reentrada.mirar_cruces` | **false** | Medido: sube las quimeras de 3 a 4 en Villaviciosa. El 0,840 del benjamín era la métrica premiando fragmentación (136 identidades para ~15 personas) |
| `puerta_reentrada.ponderar_por_tamano` | **false** | No cambia NINGUNA decisión en el banco |
| `arbitro.margen_equipo` | **0.0** | El arreglo funciona pero no sirve: el id 40 pasa de `otro` a `B` y el GT dice `A`. El catálogo era el síntoma; la causa está en `predict_color` |
| `src/tracking/asociacion_apariencia.py` | **no enchufado** | El camino B pierde contra ByteTrack: 8 quimeras frente a 3, IDF1 0,426 vs 0,546. Se conserva porque la función de coste y el radio físico son correctos y reutilizables |
| `src/tracking/coste_asociacion.py` | **no enchufado** | Idem |

## Lo que entra ACTIVO en el perfil del v4 (no es el default)

`configs/tracking_v4.yaml` y `tracking_benja_v4.yaml` NO son el default —
el default sigue siendo el v4pre— pero llevan adoptadas:

- **puerta de re-entrada con embedding de siglip, umbral 0,08**: quimeras
  4→3, del mismo equipo 2→1, IDF1 0,542→0,553.
- **filtro de confianza 0,45** y la caja de cambios propia del v4
  (buffer 1,5 · empar 0,995 · minf 2 · cosido 4/0,9).

## Dependencia NUEVA de producción

El caché de embeddings (`rutas.cache_embeddings`). Si falta, la puerta
cae a la firma de color automáticamente — no rompe— pero el perfil del v4
pierde su ventaja. **Hay que generarlo en la pasada de detección de cada
partido nuevo**, y su coste a escala de partido sigue **sin medir** (es
la tarea 5 pendiente).

## Riesgos conocidos del merge

1. **Superficie enorme**: 142 ficheros. No es revisable línea a línea; lo
   revisable son los cuatro defaults de arriba.
2. **`min_obs_para_otro` es neutro en el benjamín**, no positivo: mejora
   donde puede y no toca donde no aplica, pero no está probado que ayude
   en F7.
3. **Ningún cambio del v4 es el default todavía**, así que el merge no
   cambia el comportamiento de producción salvo por los cuatro puntos de
   la primera tabla.

## Comprobaciones antes de fusionar

- [ ] 305 tests verdes en la rama (hecho)
- [ ] Alex revisa los cuatro defaults de la primera tabla
- [ ] Decidir si las diez ramas absorbidas se borran tras el merge
- [ ] Confirmar que `data/` sigue fuera del control de versiones

---

## Ensayo del merge (19-ago-2026)

- **0 conflictos.** `main` no ha avanzado por su cuenta, así que el merge
  es un fast-forward limpio salvo por el `--no-ff` que conviene usar para
  que quede el punto de fusión en el historial.
- 305 tests verdes en la rama.
- Los cuatro defaults ya tienen el OK de Alex.

Comando, cuando él lo confirme:

```bash
git checkout main && git merge --no-ff v4/caches-y-informe && git push origin main
```

Y después, si quiere limpiar, las diez ramas absorbidas:

```bash
git branch -d feature/tracking-v4pre feature/migracion-bytetrack \
  feature/informe-v2 feature/balon feature/analisis-ia \
  barrido/fit-clasificador barrido/suavizado \
  barrido/asociacion-combinada remedicion/v2color feature/tracking-ventana
```

**No se ha fusionado**: queda a la espera de su confirmación.
