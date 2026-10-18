# Plan reducido (10 imágenes): ¿el déficit de los minutos malos es solo encuadre? (28-sep-2026)

Rama `experimento/asociacion-global`. Continúa `docs/desglose_por_episodios.md`
(BACKLOG 31) y `docs/proximidad_deteccion.md`. Conteo manual de Alex sobre 10
imágenes (5 de `A_3-10`, la ventana peor por detecciones crudas; 5 de
`D_13-25_control`, la de control — pocas detecciones SIN estar cerca de
cámara), una cada 6 s, contando solo jugadores VISIBLES sin caja verde.

## Resultado

**A_3-10 (la peor ventana): 0 de 5 frames tiene a alguien visible sin caja.**

| frame | visibles | sin caja |
|---|---|---|
| s00 | 10 (con árbitro y porteros) | 0 |
| s06 | 9 | 0 |
| s12 | 9 | 0 |
| s18 | 7 | 0 |
| s24 | 8 | 0 |

**D_13-25_control (control): 4 de 5 perfectos, 1 con el fallo YA CONOCIDO.**

| frame | resultado |
|---|---|
| s00 | **2 fallos**: una caja funde a un jugador con el árbitro detrás (confirmado con zoom: caja "10", exactamente el mecanismo de `docs/proximidad_deteccion.md`); otra caja ocupa a dos jugadores, aunque el segundo también tiene su propio cuadrado |
| s06 | 11, perfecto |
| s12 | 9, perfecto |
| s18 | 13, perfecto |
| s24 | 13, perfecto |

## Lectura

**En la ventana MALA (A_3-10), nadie visible se queda sin caja — nunca, en los
5 frames.** El déficit de esa ventana (baja cuenta de detecciones crudas) no es
el detector fallando sobre gente que se ve: es que hay menos gente EN EL
ENCUADRE. Confirma directamente la hipótesis de Alex para esta ventana
concreta, con evidencia visual, no solo con el proxy de detecciones.

**En la ventana de CONTROL, el único fallo (1 de 5) es la fusión por
proximidad que ya medimos y cerramos** (`docs/proximidad_deteccion.md`,
BACKLOG 19): dos personas próximas en la imagen, una caja se traga a la otra.
No aparece ningún mecanismo nuevo.

**Con esta muestra (n=10, pequeña mostrar honestidad), no hay evidencia de
"algo más" además de:**
1. Encuadre genuino (gente fuera de plano) — la mayoría del efecto.
2. La fusión por proximidad — ya caracterizada, ya medida a escala (23 % de
   fallo a <20 px, ~4-9 % de las personas), ya cerrada como "no arreglable
   sin reentrenar o sin riesgo de posiciones mal calculadas".

**No aparece el mecanismo del "tercio 3" del GT** (filas desplazadas con
detecciones normales, sin encuadre ni fusión de por medio) en esta muestra —
pero tampoco se esperaba verlo aquí: estas dos ventanas se eligieron por
detección cruda (encuadre), no son las mismas franjas horarias que el tercio 3
ni que los candidatos de `docs/mas_episodios_como_tercio3.md` (10:00-10:45).
Ese hueco sigue sin resolver, y sigue necesitando su propio GT si se quiere
perseguir — no lo cierra este resultado.

## Veredicto sobre "el misterio del ruido grande"

**Se reduce, no desaparece del todo.** Con esta evidencia:
- El déficit de los minutos malos = encuadre. Confirmado, no solo por proxy.
- Lo que parecía "otro mecanismo sin nombre" en `D_13-25_control`, cuando se
  mira de cerca, es el mecanismo YA CONOCIDO (fusión), no uno nuevo.
- El único cabo suelto genuino que sigue sin nombre es el tipo de episodio del
  tercio 3 — raro (una vez visto), sin proxy fiable, y esta muestra de 10 no
  lo tocó ni para confirmarlo ni para descartarlo.

## Qué hacer con esto

1. BACKLOG 31 se cierra en la parte de "¿es solo encuadre?" — **sí, con esta
   evidencia**. Queda abierta solo la pieza del tercio 3, que es un fenómeno
   distinto y más raro, no el mismo déficit de las ventanas malas.
2. No hace falta ampliar el GT de recuento a las 120 imágenes completas: el
   plan reducido ya contestó la pregunta que lo motivaba.
3. Si se quiere seguir con el tercio 3, el camino es otro: mirar el vídeo
   directamente en 10:00-10:45 (la franja que más destacó en
   `docs/mas_episodios_como_tercio3.md`), no más GT de recuento.
