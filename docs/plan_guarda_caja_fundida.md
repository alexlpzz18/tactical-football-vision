# Plan: guarda de CAJA FUNDIDA (3-oct-2026) — SOLO MEDICIÓN

Origen: `docs/cambio_de_identidad_por_caja_fundida.md` (el caso 525 y el punto 4: 704
saltos persistentes en 20 min, 118 con caja fundida). Encargo de Alex: medir una regla
que parta identidades en un cambio de persona, **sin tocar producción**. Este plan y el
criterio (en código, `scripts/medir_guarda_caja_fundida.py::CRITERIO`) se commitean
ANTES de lanzar ninguna variante.

## Antecedente que condiciona todo

Ya existe un corte por velocidad (`src/tracking/corte_velocidad.py`) y se midió
**negativo** sobre ByteTrack: IDF1 0,443 → 0,402 con las mismas 5 quimeras
(`perfiles.py::_SOLO_INTERPOLA`). Cortaba por velocidad sin más. La puerta de re-entrada
sí funciona porque corta **solo donde el sistema ya está adivinando**. Esta regla tiene que
ser de esa segunda familia: pocas decisiones, cada una con dos señales.

## 1. La regla candidata

Se aplica a las identidades de ByteTrack **después de la puerta de re-entrada y antes del
cosido por pureza**, el mismo sitio que la puerta: "partir y luego unir". Si un corte es
de más, el cosido puede volver a unirlo. Una mezcla no la deshace nadie.

Para cada par de observaciones consecutivas de una identidad (posiciones SIN suavizar):

| | señal | umbral |
|---|---|---|
| (a) salto | > 3 m en un paso (dt ≤ 0,35 s) | el del punto 4 |
| (a) dentro del campo | mediana del segundo anterior en `[0, largo] × [-1, ancho+1]` | fuera hay público y árboles |
| (a) persistente | la mediana del segundo siguiente está a > 3 m de la del anterior (≥ 3 obs a cada lado) | el del punto 4 |
| (b) caja fundida | en la observación del salto o en la anterior: alto ≥ 1,25× **o** ancho ≥ 1,5× la mediana de ESA identidad en ±2 s | alto: el del punto 4; ancho: BACKLOG (28-sep), >1,5× multiplica por 2,7 la probabilidad de fusión |
| (c) se mueve la caja ENTERA | desplazamiento persistente del borde SUPERIOR (px) ≥ 0,5× el del borde INFERIOR (px) | ver abajo |

Se mira la observación del salto **y la anterior** porque el salto puede ocurrir al
ENTRAR en la caja fundida (el pie pasa al de delante, como en la 525) o al SALIR de ella.

Donde se cumple todo, la identidad se parte justo en ese salto.

### Cómo se evita partir identidades buenas por el temblor del pie (en el fondo 3 m ≈ 10 px)

Tres capas, de la más barata a la más específica:

1. **Persistencia** (ya estaba en el punto 4): un pie que tiembla vuelve. Con medianas de
   1 s a cada lado, un error suelto o el temblor de 3,5 px no mueve la mediana 3 m.
2. **La caja fundida**. En la verificación a ojo del punto 4, las falsas alarmas (el pie
   que se desplaza porque se tapan las piernas) estaban todas en el estrato SIN fundir.
3. **(c) se mueve la caja entera, no solo el pie.** Es la física de las falsas alarmas:
   cuando las piernas se tapan o reaparecen, el borde inferior se desplaza y **la cabeza
   se queda donde estaba**. Cuando la identidad pasa a otra persona, se mueve la caja
   entera, cabeza incluida. El umbral (0,5) es relativo: no depende de la profundidad
   ni de los metros por píxel, así que vale igual en el fondo, cerca de la cámara y en
   Villaviciosa.

⚠️ La capa 2 tiene un hueco conocido: cuando unas piernas tapadas reaparecen, la caja
crece hacia abajo y puede pasar el 1,25× de alto. La capa 3 está para ese caso.

## 2. Ramas que se miden

| rama | salto (a) | fundida (b) | caja entera (c) | para qué |
|---|---|---|---|---|
| `base` | — | — | — | producción tal cual |
| `salto` | ✓ | | | ¿basta el salto? (el punto 3 de Alex) |
| `salto_entera` | ✓ | | ✓ | ¿basta el salto con el anti-temblor? |
| `salto_fundida` | ✓ | ✓ | | la regla de Alex, (a)+(b) |
| `candidata` | ✓ | ✓ | ✓ | **la candidata**, la que se juzga |

La candidata se declara AHORA. Las otras ramas son ablaciones: dicen si hace falta cada
pieza, no compiten por ser elegidas a posteriori.

**Control al azar**, por rama y con 10 semillas: el mismo número de cortes que la regla,
repartidos igual (los mismos que caen dentro de cada ventana del GT, dentro de esa
ventana; el resto, fuera), en observaciones que cumplan las mismas condiciones
mecánicas: ≥ 3 observaciones a cada lado y dentro del campo. Así el azar se juega en la
misma ventana donde se mide. Si solo se igualara el total en 20 min, casi ningún corte
al azar caería en los 30 s del GT y el control no controlaría nada.

## 3. Qué se mide y dónde

Cada rama corre la cadena de producción COMPLETA (`procesar_desde_cache`: equipos,
porteros, árbitro, etiqueta por observación, suavizado). El corte se inyecta envolviendo
`coser_por_pureza` dentro de `perfiles.py` desde el script de medición. **Ningún fichero de
producción cambia**. Guarda: la rama `base` del script tiene que dar un CSV idéntico al de
producción, o el script se para.

- **Benjamín**: la parte entera (20 min, `processor_benja_parte_entera.yaml`) contra el GT de
  14 personas (frames 9750-10635, 30 s). Es la única pata donde está la 525.
- **Villaviciosa**: `processor.yaml` (v4pre, 60 s) contra su GT (offset 7500).

Contra el GT, casado 1-a-1 con radio 2 m (`comparar_escalas.py`):
- **equipo equivocado** (%), el número de CLAUDE.md;
- **quimeras**: identidades con ≥ 10 casados cuya persona mayoritaria no llega al 60 %
  (la definición del banco);
- **fragmentación**: identidades distintas por persona del GT (media);
- **centroide y anchura**: error medio por (frame, equipo) contra el GT, el mismo
  protocolo que la base de `desglose_del_error.py`;
- **cortes verificables**: de los cortes dentro de la ventana con persona casada a los dos
  lados, cuántos separan a dos personas distintas. Es la precisión directa de la regla.

En los 20 min, sin GT (proxies; se dice que lo son):
- número de cortes, y cuántos deshace el cosido (los dos trozos acaban en la misma identidad);
- **cambio de etiqueta a través del corte**: la etiqueta mayoritaria del CSV en 2 s a cada
  lado. Un cambio de persona entre equipos o papeles lo enseña; uno dentro del mismo equipo, no.
  Se compara contra el azar;
- **trozos de árbitro o portero**: cuántos cortes tienen a un lado `portero_*` u `otro`;
- **la 525**: ¿se corta en t≈792,7 s? ¿Salen sus 165 s como `portero_B`? ¿El cosido lo deshace?

## 4. Aviso calculado ANTES de medir

La ventana del GT del benjamín es el 2,5 % de la parte. Si la regla cortara al ritmo de
los 118 fundidos del punto 4, caerían **~3 cortes** en ella; la rama `salto`, ~18. Con
tan pocos casos, el GT puede salir sin cambio aunque la regla sea buena. Por eso el
criterio declara NO CONCLUYENTE una pata con menos de 5 cortes en su ventana, en vez de
leer "no empeora" como "funciona". En ese caso, lo que más pesa son los 20 minutos (los
proxies contra el azar) y la 525. Y la verificación a ojo de una muestra queda como
siguiente paso.

## 5. El criterio (resumen; el que manda es el del código)

Por pata, contra `base`:
1. equipo equivocado: variante ≤ base;
2. quimeras: variante ≤ base en cada pata, y en la suma de las dos patas variante < base;
3. fragmentación: Δ ≤ +0,25 identidades por persona;
4. centroide y anchura: variante ≤ base + 0,01 m (1 cm: la resolución de lectura, no una
   barra de error);
5. contra el azar: en ≥ 9 de 10 semillas la regla queda estrictamente mejor que el azar
   (primero menos quimeras; si empatan, menos fragmentación). Y en 20 min, la tasa de
   cambio de etiqueta a través del corte supera al percentil 90 del azar.

Una pata con < 5 cortes en su ventana: los puntos 1-5 contra el GT se informan, pero su
veredicto es NO CONCLUYENTE, no "pasa". Esto es medición: pasar el criterio no adopta
nada. Abre la decisión de Alex.
