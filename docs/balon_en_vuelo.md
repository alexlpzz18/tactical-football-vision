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
