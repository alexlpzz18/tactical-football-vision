# Landing page 3D

Experiencia web en WebGL2: el recorrido de cámara baja desde el aire hasta el
campo y vuelve a subir hasta el cenital mientras se encienden las capas de
análisis. El entorno cambia de mundo cada 30 segundos sin interrumpir el
partido ni el tracking.

## Qué abrir

`landing.html` — la página, en un único fichero autocontenido. Se abre con
doble clic. No tiene dependencias ni hace ninguna petición externa.

## Cómo editarla

**No edites `landing.html` a mano**: está generado. Toca los ficheros de
`fuentes/` y vuelve a montarlo:

```
cd landing_page/fuentes
python3 montar.py landing.html ../landing.html
```

## Qué hay en fuentes/

| Fichero        | De qué se ocupa                                          |
|----------------|----------------------------------------------------------|
| `landing.html` | Estructura, textos y estilos de la página                |
| `landing.js`   | Motor: une todo, scroll, resolución adaptativa            |
| `guion.js`     | Recorrido de cámara y qué capas se encienden en cada hito |
| `env.js`       | Cielo, terreno, agua y el campo (shaders)                |
| `props.js`     | Arbolado, caserío, torres de luz; relieve en JS           |
| `jugadores.js` | Figuras de los jugadores, instanciadas                    |
| `partido.js`   | Simulación 11 contra 11 de la que salen las métricas      |
| `analisis.js`  | Capa de detección, estelas y geometría táctica            |
| `sombras.js`   | Mapa de sombras direccional                               |
| `escena.js`    | Orquesta los pases de dibujado                            |
| `core.js`      | Matrices y utilidades de WebGL                            |

## Notas

- Todo es procedural: no hay ni un modelo, textura o vídeo externo.
- Las cifras que aparecen (amplitud, profundidad, entre líneas) se **miden**
  sobre la simulación que se está viendo; no están escritas a mano.
- La resolución se ajusta sola buscando unos 55 fps, con tope de 9 Mpx.
