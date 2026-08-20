# Licencias de lo que hace falta para meter apariencia (19-ago-2026)

Requisito de Alex: nada incompatible con producto comercial. Precedente:
PRTreID y BPBReID están descartados por la Hippocratic License.

| componente | licencia | ¿comercial? |
|---|---|---|
| **GTA-Link** (código) | MIT | ✅ |
| **torchreid** / deep-person-reid (código) | MIT, © Kaiyang Zhou | ✅ |
| **OSNet `sports_model.pth.tar-60`** | entrenado en **SportsMOT** = **CC BY-NC 4.0** | ❌ |
| siglip-base-patch16-224 | Apache-2.0 | ✅ |
| dinov2-base | Apache-2.0 | ✅ |
| timm resnet50.a1_in1k | Apache-2.0 (ImageNet-1k) | ✅ |

## El bloqueo no está donde parecía

GTA-Link es MIT y torchreid también. **Lo que no se puede usar es el
checkpoint que GTA-Link recomienda**: el OSNet que le da su rendimiento
en deporte está entrenado sobre SportsMOT, que es CC BY-NC 4.0 — "not
primarily intended for commercial advantage". Para ACIIES queda fuera.

La salida es limpia: **GTA-Link es agnóstico al modelo**. Es
post-proceso sobre tracklets y el ReID entra como parámetro, así que se
puede integrar el algoritmo (MIT) alimentándolo con un embedding de
licencia libre. Encaja con la idea del embedding único.

## Dos cosas SIN cerrar (no darlas por buenas)

1. **Pesos del model zoo de torchreid** (OSNet en Market-1501 / MSMT17).
   No se encontraron los términos de esos datasets en fuentes fiables.
   Muchos datasets de ReID son "research only". Queda como **riesgo
   abierto**; si acabamos queriendo esos pesos hay que ir a la fuente
   original de cada dataset.
2. **ImageNet-1k**: los pesos de timm se publican Apache-2.0, pero el
   dataset original tiene términos de investigación. Que los pesos
   derivados sean libres es la práctica del sector, no una certeza
   jurídica. Esto no es asesoramiento legal; si el detalle importa para
   ACIIES, es consulta de abogado.

Con lo verificado, **los tres candidatos de embedding están limpios** y
se pueden benchmarkear sin problema.

---

## boxmot ahora es AGPLv3+ (19-ago-2026)

`boxmot` 22.0.0 se publica bajo **GNU Affero GPL v3 o posterior**. Para
Tactical Lens eso es un bloqueo **más grave que el del entorno**: la AGPL
obliga a publicar el código fuente a quien use el software **a través de
la red**, y nuestro producto es un SaaS. Usar boxmot obligaría a liberar
el pipeline entero.

El veto de CLAUDE.md era por romper el entorno (su v19 cambió la API y
subió numpy a 2.5). Ahora hay una segunda razón, independiente y
definitiva: **la licencia**. El veto se mantiene y ya no es negociable ni
aunque el entorno mejore.

## Deep-EIoU: mismo problema que GTA-Link

Deep-EIoU usa **el mismo `sports_model.pth.tar-60`** —el OSNet entrenado
en SportsMOT (CC BY-NC 4.0)— así que su rendimiento publicado (85,4 HOTA)
depende de un peso que no podemos usar comercialmente. Además, el repo
**no declara licencia** en su página principal, lo que por defecto
significa "todos los derechos reservados": sin licencia explícita no hay
permiso de uso.

## Consecuencia para el punto 4

Las dos vías obvias para "tracker con apariencia" están cerradas por
licencia, no por técnica:

| vía | bloqueo |
|---|---|
| boxmot (BoT-SORT, Deep-OC-SORT) | AGPLv3+ sobre un SaaS |
| Deep-EIoU | checkpoint CC BY-NC + repo sin licencia |

Queda **implementar la asociación con apariencia nosotros**, que es el
"camino B" que ya estaba diseñado: coste mixto `α·(1−IoU) + (1−α)·coseno`
con matching húngaro, alimentado por un embedding Apache-2.0 de nuestro
propio caché. El algoritmo de BoT-SORT está publicado en su paper; lo que
no se puede reutilizar es esa implementación concreta.
