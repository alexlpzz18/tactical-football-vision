# La resolución local en el cosido por pureza: medida en las dos patas (16-oct-2026) — NO CONCLUYENTE, y fabrica quimeras

Plan y criterio, commiteados antes de medir: `docs/plan_resolucion_en_cosido.md` (commit
fac2b3c). Guarda de comportamiento: `tests/test_interruptores_de_config.py` (commit 6dc2e6a).
Script: `scripts/medir_resolucion_en_cosido.py`. **Nada de producción ha cambiado**: hoy el
cosido sigue corriendo con `resolucion=None`, y `jitter_px` sigue sin leerlo nadie en el perfil
`bytetrack`.

## Resultado en una línea

Arreglar el cableado (que la resolución llegue al cosido) **no mueve ni una cifra contra el GT
en ninguna de las dos patas**: en el benjamín ninguna de las uniones que cambia cae en la
ventana del GT, y en Villaviciosa el CSV sale idéntico (allí el escalado está apagado). El
criterio lo declara **NO CONCLUYENTE**: ningún punto empeora y la mejora no se puede medir.
Pero en los 20 minutos **fabrica quimeras**: de las 24 uniones nuevas dentro del campo, **10
juntan trozos que en la base tenían etiquetas distintas**. Una de ellas pega 53 s de un jugador
al árbitro y manda 495 filas de jugador a `otro`. **Recomendación: no adoptar.**

## Los números (base = producción reproducida byte a byte)

La base reproduce las cifras del banco de la guarda de caja fundida, y el equipo equivocado del
script coincide con el de `comparar_escalas.py` (control del casado).

**Benjamín** (20 min; GT de 14 personas en 30 s, frames 9750-10635):

| rama | equipo equiv. | quimeras | ids/persona | centroide | anchura | faltan | sobran | DetA | AssA | IDF1 | identidades (20 min) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 1,24 % (9) | 4/18 | 3,071 | 1,453 | 1,275 | 0,758 | 0,842 | 0,328 | 0,260 | 0,353 | 435 |
| **candidata** | = | = | = | = | = | = | = | = | = | = | **415** |
| solo_espacial | = | = | = | = | = | = | = | = | = | = | 419 |
| solo_velocidad | = | = | = | = | = | = | = | = | = | = | 431 |

(«=» es idéntico a la base hasta el último decimal impreso.)

**Villaviciosa** (60 s, todo dentro del GT):

| rama | equipo equiv. | quimeras | ids/persona | centroide | anchura | faltan | sobran | DetA | AssA | IDF1 | CSV |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 23,58 % (358) | 3/36 | 6,000 | 4,817 | 5,710 | 2,960 | 1,935 | 0,207 | 0,224 | 0,228 | — |
| **candidata** | = | = | = | = | = | = | = | = | = | = | **idéntico** |
| solo_espacial / solo_velocidad | = | = | = | = | = | = | = | = | = | = | idéntico |
| villa_forzada (informativa) | 23,67 % (360) | 4/35 | 5,591 | 4,851 | 5,774 | 2,950 | 1,930 | 0,205 | 0,226 | 0,231 | distinto |

Villaviciosa sale idéntica por construcción, como avisaba el plan: su `tracking.yaml` no tiene
`escalado_resolucion`, así que `desde_config` devuelve None también para el cosido.
`villa_forzada` (resolución forzada, con el 3,5 px del benjamín, que en Villaviciosa no está
medido) es **solo informativa**: fragmenta menos (6,00 → 5,59) pero sube una quimera, dos
observaciones de equipo equivocado y 3-6 cm de centroide y anchura. Todo eso cae dentro de la
cuarentena de ruido de esa pata (`docs/suelo_de_ruido.md`), y no se lee como resultado.

## Veredicto del criterio, punto por punto (candidata)

| punto | benja | villa |
|---|---|---|
| 1 no empeora (equipo, quimeras, centroide, anchura, faltan, sobran, DetA, AssA, IDF1) | ✓ (idéntico) | ✓ CSV idéntico |
| 2 no inventa (Wilson, cambio de etiqueta a través de la unión) | ✓ (IC 0,19-0,55 contra 0,30 de la base) | — |
| 3 mejora | **NO CONCLUYENTE**: 0 uniones cambiadas dentro de la ventana (pedía ≥ 5) | — |

`pasa = None` → **NO CONCLUYENTE**. Según el plan, decide Alex con los datos de 20 minutos
delante. Son los de abajo.

## Lo que pasa en los 20 minutos (sin GT)

**Uniones del cosido: 226 → 262** (40 nuevas, 4 perdidas). Ninguna en la ventana del GT.

| | nuevas | dónde |
|---|---|---|
| **fuera del campo** | **16** | x = 72-96 m, y = 51-75 m (el campo mide 62 × 40): público y árboles del fondo. No llegan al CSV. Por eso las identidades del CSV bajan 20 (435 → 415 = 24 nuevas − 4 perdidas dentro del campo) y no 36. Las dos uniones «imposibles» (> 6,5 m/s aun contando bien el ruido) son de aquí. |
| dentro del campo | 24 | ver la tabla siguiente |

De qué margen sale: el **espacial** da 28 de las 40 nuevas; el de **velocidad**, 9 (las de salto
rápido: mediana 8,2 m/s contra los 6,5 del veto).

**Diagnóstico POST HOC** (`--diagnostico`; se añadió después de medir y **no cambia el
veredicto**). ¿Qué etiqueta tenían en la BASE los dos trozos de cada unión nueva dentro del
campo?

| en la base, los dos trozos eran | uniones nuevas |
|---|---|
| la misma etiqueta (A-A, B-B, staff-staff) | 13 |
| **A y B** | **8** |
| **un jugador y el árbitro (`otro`)** | **1** |
| **un jugador y `staff`** | **1** |
| un lado sin etiqueta | 1 |

Una etiqueta de 2 s de un trozo se equivoca muy poco (el equipo equivocado es del 1,2 % por
observación), así que una unión A↔B es casi siempre **dos personas de equipos distintos**: una
quimera. 10 de 23 es mucho.

**La quimera que más pesa** (t = 786,1 s, x = 34 m). En la base, el jugador (id 618, `B`) sigue
su camino y el árbitro (id 658, `otro`, 133 s) entra justo a su lado 0,3 s después. Con los
márgenes, el cosido une los 53 s anteriores del jugador al trozo del árbitro: salto de 1,7 m
en 0,2 s (8,3 m/s), que el veto de 6,5 m/s paraba y el margen de velocidad (+6,7 m/s a esa
distancia de la cámara) deja pasar. La identidad resultante se etiqueta `otro` entera:

| filas que cambian de etiqueta entre base y candidata (casado por posición < 0,5 m) | n |
|---|---|
| B → otro | 398 (todas de esta quimera) |
| A → otro | 101 (97 de esta quimera) |
| A ↔ B | 16 |
| → staff | 2 |

Son 495 filas de un jugador que desaparecen del equipo durante 53 s. Es la lección de
«TODO CRITERIO QUE MUEVE FILAS HACIA UN CAJÓN...» de CLAUDE.md, y el GT no la podía ver: no anota
al árbitro y esos segundos están fuera de su ventana.

## Por qué el proxy del criterio no la vio (la lección de esta medida)

El punto 2 del criterio («¿qué inventa?») miraba el **cambio de etiqueta a través de la unión
en el CSV de la propia rama**, y dio ✓. Pero es ciego justo a lo que tenía que cazar: cuando dos
trozos se unen, la identidad se etiqueta junta y los dos lados salen con la misma etiqueta. La
quimera jugador + árbitro sale `otro → otro`, «sin cambio». **La decisión contaminaba su propia
medida.** La pregunta buena se hace sobre lo que había ANTES de decidir: la etiqueta de cada
trozo en la base. Es la variante de «una herramienta que RESUME puede mentir sobre el sistema
que diagnostica»: aquí el resumen lo fabricaba la propia variante.

## El intento 2 no se corre

El plan lo condicionaba a que la candidata NO PASARA y a que el diagnóstico señalara al veto de
velocidad. No se cumple ninguna de las dos: el veredicto es NO CONCLUYENTE, y el grueso de las
uniones nuevas sale del margen espacial (28 de 40). Además no arreglaría la quimera principal:
con el ruido contado sobre el hueco (3,5 px × 0,19 m/px / 0,2 s = 3,3 m/s) el veto quedaría en
9,8 m/s, y el salto de 8,3 m/s seguiría pasando.

## Qué queda abierto (decisión de Alex)

1. **No adoptar** el cableado (recomendado): no mejora nada medible, y en 20 min fabrica al
   menos una quimera jugador + árbitro que se come 53 s de un jugador, más 8 uniones A↔B.
   Si se acepta, la fila va a «Vías CERRADAS» de CLAUDE.md. No la he añadido: el criterio dijo
   NO CONCLUYENTE, no NEGATIVO, y el diagnóstico que inclina la balanza es post hoc.
2. **El interruptor muerto sigue ahí.** `perfiles._perfil_bytetrack` lee una clave que nadie
   escribe, y `configs/tracking_benja.yaml` dice «lo inyecta el processor». La guarda xfail
   estricta avisará si alguien lo cablea. Lo limpio sería quitar la lectura de `_resolucion` del
   perfil y corregir el comentario del YAML. Toca producción, aunque no cambie el CSV, así que
   va aparte y con su OK.
