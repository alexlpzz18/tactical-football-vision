# Staff que entra en el campo: etiqueta por observación DENTRO (30-oct-2026)

Rama `staff-dentro-del-campo`, sale de `main`. Cambio de producción detrás de un flag. Criterios
escritos y commiteados ANTES de medir.

## El caso

En la salida A1 (13:15.7-13:45.7 del archivo, 14:48.7-15:18.7 del reproductor), el lateral derecho
de A no entra en el contorno de su equipo.
- Es la identidad **590**. De 11:41 a ~13:05 del archivo es una persona parada fuera de la banda
  derecha: mediana a −0,7 m de la línea, 0,32 m/s.
- Después salta al lateral y lo sigue hasta 13:28.
- La regla de staff decide **por identidad entera**, y `etiquetar_por_observacion` se salta a las
  identidades de staff («el staff no juega en ninguna»). Así, los ~25 s del lateral salen grises.
- En los 20 min hay 287 filas de staff dentro del campo, a > 2 m de las líneas: el 2 % del staff,
  ~29 s, en 3 identidades (590: 226; 442: 42; 545: 19).
- Alex: **es imprescindible que el lateral salga bien**, aunque pese poco, porque cae en una salida
  de balón.

## La regla (la de Alex, acotada a lo que se puede medir)

- **Fuera del campo, nadie cuenta.** Ya es así en la pizarra y en el informe; no cambia.
- **Dentro del campo, una observación de una identidad de staff se etiqueta como la de un
  jugador**: ventana de color de 1,5 s, catálogo arbitral, y después la pista del árbitro.
  - «Dentro» = el pie a ≥ 1,0 m de las cuatro líneas, para que el temblor de la proyección no meta
    al entrenador de la banda (0,42 m/px en el fondo).
  - La ventana solo promedia observaciones de DENTRO, para que los recortes del entrenador no voten
    por el lateral.
- Flag: `agregacion.por_observacion.staff_dentro_del_campo` (`activo`, `margen_m`) en
  `team_classification_benja.yaml`. Con él apagado, la salida es la de siempre.
- **Lo que NO se hace aquí**: reconocer al entrenador que entra en el campo por su color, aprendiendo
  antes el del árbitro en los primeros minutos.
  - Es el «tercer grupo por color», cerrado tres veces: en un recorte de 15-40 px, el árbitro está
    tan cerca de su prototipo como un jugador (0,884 frente a 0,936) (`docs/arbitro.md`).
  - Un entrenador de otro color tiene el mismo problema: el clasificador es de dos clases y le
    asignará A o B.
  - El criterio 2 dice si en este partido algún miembro del staff entra en el campo. Si nadie
    entra, ese caso no existe aquí.

## Criterios

1. **El lateral**: las filas de la 590 dentro del campo (margen 1 m) en [785, 808,3] s llevan
   etiqueta **A en ≥ 90 %**. Además, Alex lo ve bien en el visor.
2. **¿Qué podría estar inventando?** Una miniatura de cada racha que pasa de staff a A/B en los
   20 min, con la caja de la PROPIA detección de la fila. Ninguna puede ser alguien que no juega
   (entrenador, línier, suplente). Si alguna lo es, se dice, con su número.
3. **No rompe**:
   - GT de 30 s ≤ 9/723 y hoja de 120 ≤ 2/120;
   - solo cambian filas de identidades de staff: todas las demás, idénticas;
   - **Villaviciosa**: CSV idéntico byte a byte (allí `por_observacion` está apagado).
4. Informativo: fichas de A de media en A1, antes y después.

Pasa si se cumplen 1, 2 y 3, con pytest en 0 y un test de comportamiento del flag. No se fusiona a
`main` sin el OK de Alex.
