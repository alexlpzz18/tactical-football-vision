# El balón en vuelo casi no se ve: diagnóstico (2-oct-2026)

Lo vio Alex en el fragmento de revisión: el balón alto casi nunca sale. **Solo
diagnóstico, sin solución todavía.** Tiempos en reloj de ARCHIVO (el reproductor de
Alex va +1:33).

## Dónde se pierde

Frames sin balón elegido DENTRO de un vuelo o pase largo (entre dos posiciones elegidas
a > 8 m en ≤ 2 s): **687**. En qué etapa se queda cada uno:

| etapa | frames | qué significa |
|---|---|---|
| el detector no da nada | 176 (26 %) | ni el balón ni nada |
| solo quedan marcas del campo | 247 (36 %) | el balón tampoco está entre las detecciones |
| **lo quita la plausibilidad** (proyecta fuera del campo) | **146 (21 %)** | había detección |
| lo quita el selector | 84 (12 %) | 52 por pequeño, 32 por continuidad |
| lo quita la regla del staff | 34 (5 %) | |

⚠️ El criterio "> 8 m en ≤ 2 s" mezcla vuelos con cambios de objeto: es una cota, no un
recuento de vuelos.

## Lo confirmado: la plausibilidad tira balones aéreos REALES, por construcción

La homografía es de SUELO: un balón por el aire se proyecta donde la recta de la cámara
corta el césped, que para un balón alto sobre el fondo cae **más allá de la portería**
(x de 66 a 417 m en los casos vistos). `filtrar_balon_plausible` lo quita por estar fuera
del campo. Mirado a ojo:

- de 20 detecciones quitadas DENTRO de vuelos: **6 son el balón en el aire sin duda**
  (contra los árboles o el cielo, 10-19 px, confianza 0,58-0,74), ~7 dudosas, ~7 otra cosa;
- de 30 al azar de las 3.646 quitadas en todo el partido: ~3 balón en el aire; el resto
  es basura de verdad (balones del campo de al lado, balones en la tierra tras la línea,
  cabezas junto a la portería del fondo). 2.946 de las 3.646 proyectan más allá del fondo,
  que es justo donde va a parar también el balón aéreo: **por posición no se separan**.

Es el mismo tipo de fallo de siempre (algo bueno quitado por un filtro que se diseñó
contra otra cosa), pero aquí no es GreedyNMM ni las marcas: es la plausibilidad.

## Lo que NO se ha podido medir

- **La composición del entrenamiento** (cuántos ejemplos de balón en vuelo, con
  desenfoque, contra el cielo): el dataset del balón no está en este Mac. Hace falta
  Drive/Colab.
- **Cuántos balones altos se ven en la imagen y el detector no da**: el 62 % de los
  frames de vuelo no tiene ninguna detección del balón, pero sin un GT de "dónde está el
  balón alto" no se sabe si el balón era visible (o salía de plano, o iba tapado). A la
  escala de la hoja de revisión no se distingue a ojo.
- Una pista sin confirmar: la franja que se trocea a resolución completa va de y = 534 a
  805 px; por encima solo actúa el frame entero reducido a 1.280. En todo el partido solo
  133 de 24.901 detecciones están por encima de la franja, y 3 de los 6 balones aéreos
  claros sí se detectaron ahí (y = 365, 492, 525). No dice si se pierden muchos más.

## Paso barato 1: ¿más resolución por encima de la franja? (2-oct-2026)

**No puede recuperar ninguno de los 6 casos confirmados**: los 6 sí los detectó el
detector (3 por encima de la franja, a y = 365/492/525, y 3 dentro); los perdió la
plausibilidad. La resolución solo podría afectar al 62 % de huecos de vuelo SIN
detección, que no tienen GT.

No se ha podido probar aquí: el modelo (`best_balon_v1.pt`) está en el Drive
sincronizado, pero en este entorno torch está compilado para numpy 1.x y hay numpy
2.4.6 (`CLAUDE.md` fija `numpy<2.1`): la inferencia falla con "Numpy is not available".
Arreglarlo es cambiar el entorno; no se ha tocado. Coste estimado SIN medir: una segunda
franja de 5 tiles por encima de y = 534 cuesta del orden de lo que ya cuesta la franja
actual, así que entre +10 y +30 min sobre los 29 min del mixto por parte en una T4.
Medible en Colab (o aquí con el entorno arreglado) contando detecciones nuevas en los
huecos de vuelo y mirándolas a ojo.

## Paso barato 2: readmitir lo que tira la plausibilidad por CONTINUIDAD (simulado)

Simulación sobre los cachés, sin tocar producción. Las 3.646 detecciones que tira la
plausibilidad (menos las de celdas de marca) vuelven como candidatos del Viterbi del
Plan 1, en tres variantes:

| variante | readmitidas elegidas | en huecos de vuelo | 6 casos | muestra de 30 a ojo |
|---|---|---|---|---|
| A: sin restricción | 1.747 | 239 | — | (no se miró) |
| B: no pueden EMPEZAR una pista (salto = ∞) | 1.023 | 227 | 6/6 | 12 balón · 6 dudosas · **12 basura** |
| **C: B + la racha tiene que SALIR y VOLVER al suelo por continuidad, ≤ 2,5 s** | **604** | **214** | **6/6** | **20 balón · 6 dudosas · 4 basura** |

B no basta: la basura del fondo (personas, la grada, tierra) está "cerca" en píxeles
del balón cuando el balón va por el fondo, y la puerta de 1.000 px/s la deja pasar. C es
la forma de vuelo de verdad —un vuelo sale de un pie y cae al césped— y se queda con
~2/3 de balón real (en el aire, saques de banda con el balón sobre la cabeza, rebotes en
la grada).

**Viable con lo que ya existe** (el Viterbi con un candidato que no puede abrir pista, y
una comprobación posterior de entrada y salida), pero NO construido. Dos condiciones
antes de adoptarlo:

1. Estas filas no son posiciones: la homografía de suelo las pone a decenas de metros.
   Tienen que entrar como **aéreas (`es_real = 0`)**, fuera de contactos y posesión. Lo
   que aportan es CONTINUIDAD (la pista no se corta en un vuelo) y, en una vista sobre
   el vídeo real, el balón dibujado en su píxel, que sí es correcto.
2. Medir lo que inventa: ~13 % de basura clara y ~20 % de dudosas en la muestra.
