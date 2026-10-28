# Pizarra 14:00-15:30 con la configuración de `main`, sin suavizado visual (28-oct-2026)

Sin código nuevo de producción.

- **Ruta**: `outputs/pizarra_28oct_h/pizarra_14_00_15_30.html`. El CSV del tramo está al lado
  (`posiciones_14_00_15_30.csv`, 13.143 filas, t = 840,0-929,9 s; 37 identidades).
- **Tramo**: 14:00-15:30 del archivo = 15:33-17:03 del reproductor. Es el mismo del clip 1.
- **Cómo**:
  - `scripts/generar_replay.py` de `main` (que no tiene la histéresis de `mejoras-28oct-g`);
  - `--config-campo configs/campo_benja.yaml` (F7, `espejar: y`, ficha de 0,8 m);
  - `--meta` con los colores del clasificador;
  - `--suavizado-visual-ventana 1`: sin la mediana de 3 muestras, se pinta la etiqueta cruda de
    cada observación.
- **El CSV es el de `main`**: `outputs/diagnostico_26oct_b/posiciones_main.csv`. Hoy se comprobó que
  sale idéntico byte a byte a un `desde_cache` fresco (`diagnostico_28oct_g.md`, bloque 1).
- **¿Números o solo puntos?** **Números.** Cada jugador es un disco del color de su etiqueta con el
  **número de identidad** dentro, en blanco (`ctx.fillText(DATOS[i].id, …)` en
  `src/report/replay_tactico.py`). El balón no lleva número. No hay opción para quitarlos.
  - Consecuencia para quien la mire: un cambio de identidad en un cruce se ve como un CAMBIO DE
    NÚMERO, aunque el color no cambie (el evento 2 del clip 1, por ejemplo). Es justo lo que el 28-oct
    (g) encontró: 7 de los 10 parpadeos que vio Alex son cajas que pasan a otra identidad.
- **Este CSV solo trae jugadores**: el balón va aparte (`cache_balon_p1.pkl`), así que en esta
  pizarra no sale.

## CLAUDE.md

En «Rutas cerradas», dos líneas nuevas: la puerta de calidad de caja (0 de 11, sin recortes
anormales en esos casos) y el color estable ≥ 1 s como solución general (3 de 10). `mejoras-28oct-g`
queda sin fusionar.
