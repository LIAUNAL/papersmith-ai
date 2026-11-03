---
{
  "section": "back-matter",
  "position": 10,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/10-back-matter.md",
      "quote": "Cada bloque aquí es un hecho externo, no una decisión."
    }
  },
  "blocks": [
    {
      "id": "bm-author-contributions",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "author-roles",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "Los author-roles — la lista de autores y los roles confirmados de cada autor"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-funding",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "grant-title",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "El grant-title y el grant-code — el título registrado del proyecto de financiamiento, el financiador y el código"
          }
        },
        {
          "value": "grant-code",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "El grant-title y el grant-code — el título registrado del proyecto de financiamiento, el financiador y el código"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-data-availability",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "La repository-url — la URL del repositorio del proyecto y la fecha en que se verificó"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-code-availability",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "La repository-url — el repositorio de código que produjo los números reportados, y su versión o commit"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-ethics-statement",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "La ethics-approval — el comité que aprobó, el código y la fecha de aprobación, y cómo se obtuvo el consentimiento, o Not applicable. para datos públicos"
          }
        }
      ],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-informed-consent",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "La ethics-approval — el comité que aprobó, el código y la fecha de aprobación, y cómo se obtuvo el consentimiento, o Not applicable. para datos públicos"
          }
        }
      ],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-conflicts-of-interest",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "bm-acknowledgments",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "back-matter.bm-funding",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "Presente solo cuando hay un proyecto o institución que agradecer que no esté ya nombrado en el financiamiento."
          }
        }
      ]
    },
    {
      "id": "bm-supplementary-materials",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-abbreviations",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-appendices",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-highlights",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-graphical-abstract",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-ai-use-declaration",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---
# Material final

El bloque administrativo que va después de las conclusiones y antes de las referencias.
No es prosa científica: es la superficie de rendición de cuentas del artículo: quién hizo qué,
quién pagó, dónde están los datos y el código, cómo se usó la IA y qué podría sesgar el trabajo.

Cada bloque es una etiqueta en línea en negrita seguida de prosa, salvo que la revista le
asigne una sección propia. Sin subsecciones. Esta es la parte más mecánica del artículo y la
que con más probabilidad estará mal en el envío, porque nadie la trata como escritura.

## Los bloques, en este orden

| Bloque | Obligatorio | Palabras |
|---|---|---|
| Contribuciones de los autores | sí | 37–44 |
| Financiamiento | sí; su ubicación sigue a la revista | 55 por proyecto |
| Declaración de disponibilidad de datos | sí | 7–22 |
| Disponibilidad del código | sí | 7–25 |
| Declaración del comité de ética institucional | cuando la revista la pide, o se estudiaron personas o animales | una o dos oraciones |
| Declaración de consentimiento informado | cuando la revista la pide, o se estudiaron personas | una oración |
| Conflictos de interés | sí | una oración |
| Agradecimientos | solo si hay un proyecto que agradecer, o la revista ubica allí el financiamiento o la declaración de IA | ~25 |
| Materiales suplementarios | solo si el artículo los incluye | una oración por elemento |
| Abreviaturas | opcional | una línea por término |
| Apéndices | solo si el artículo los necesita | — |
| Highlights | revistas de Elsevier | 3–5 viñetas |
| Resumen gráfico | revistas de Elsevier, opcional | una imagen |
| Declaración de uso de IA | sí, siempre | 40–90 |

## La ubicación sigue a la revista

La lista de bloques es la misma para todo artículo; dónde queda cada bloque y cómo se
titula lo decide la editorial de la revista seleccionada (`venue select` la registra).

**El material final se presenta después de las conclusiones y antes de las referencias, en toda revista.**
En `main.tex` cada bloque de declaración queda por encima de la línea `\bibliography` (o del
entorno `thebibliography`); la declaración de uso de IA, cuando es una sección propia, es
la última de ellas, inmediatamente antes de las referencias.
**Los apéndices siguen a las referencias**, salvo que las guías de la revista indiquen otra
cosa; ninguna familia editorial de las siguientes lo hace. `verify` informa el orden
(`back-matter-order`), y `venue build` siempre lo emite, sea cual sea el orden del archivo
canónico.

- **Elsevier.** Los highlights y un resumen gráfico se envían con el manuscrito.
  Contribuciones de los autores CRediT, una declaración de intereses en competencia y
  **el financiamiento dentro de los Agradecimientos**. La declaración de uso de IA es
  **una sección propia, inmediatamente antes de las referencias**.
- **MDPI.** Contribuciones de los autores, un **bloque de Financiamiento propio**,
  Declaración del comité de ética institucional, Declaración de consentimiento
  informado (*Not applicable.* cuando los datos son públicos), Declaración de
  disponibilidad de datos y Conflictos de interés con la oración sobre el papel del
  financiador. La declaración de uso de IA va **dentro de los Agradecimientos**.
- **IEEE.** La declaración de uso de IA va en los Agradecimientos y nombra las
  secciones que contienen contenido generado por IA.
- **Cualquier otra revista.** La plantilla neutral respecto de la editorial que aparece
  más abajo, como sección propia sin número antes de las referencias, salvo que las
  instrucciones para autores indiquen otra cosa.

## Cada declaración es un párrafo propio

Las contribuciones de los autores, la financiación, las declaraciones de disponibilidad
de datos y de código, las declaraciones de ética y de consentimiento, los conflictos de
interés y los agradecimientos abren cada uno un párrafo propio, tras un punto y aparte:
nunca dos declaraciones seguidas como oraciones consecutivas de un mismo párrafo. Sus
bloques van uno tras otro en `main.tex` y sus marcadores son comentarios, así que
`write` y `humanize --apply` abren cada uno de estos cuerpos con una línea en blanco, y
`verify` reporta una declaración que se funde con la anterior (`own-paragraph`).

## Contribuciones de los autores

Una fórmula, por eso su extensión apenas varía. Los roles CRediT, separados por
punto y coma, cada uno seguido de las iniciales de los autores que lo desempeñaron, separadas por comas
con *y* antes de la última. Luego la oración de cierre habitual que indica que todos los
autores han leído y aceptado la versión publicada.

**Cada autor aparece en al menos un rol.** Los roles son los que cada autor
confirmó, no los inferidos a partir del trabajo. **Una herramienta de IA nunca es autora**
ni desempeña un rol.

## Financiamiento

Una entrada por subvención. Cada una lleva el **título registrado exacto** del proyecto, en su
idioma original, el financiador y el código de la subvención. Cuando una subvención apoya a un autor
específico y no al trabajo en su conjunto, nombre a ese autor junto con ella.

Los códigos de subvención se copian de los registros de financiamiento, nunca se reescriben de memoria.

Cuando la revista ubica el financiamiento dentro de los agradecimientos, las mismas
entradas van allí, sin cambios.

## Declaración de disponibilidad de datos

La URL del repositorio más la fecha en que se verificó. La URL debe resolver, y debe
contener el código que produjo los números reportados.

Cuando los datos no pueden publicarse, dígalo en una línea e indique la vía para solicitarlos.
No remita a un repositorio que contiene solo código dando a entender que contiene los datos.

Indique qué es público y qué no lo es: son afirmaciones distintas.

## Disponibilidad del código

Separada de la declaración de datos, porque código y datos son afirmaciones distintas.
La URL del repositorio, la fecha en que se verificó y la versión o el commit que produjo
los números reportados. Cuando el código no puede publicarse, dígalo e indique la vía
para solicitarlo.

## Declaración del comité de ética institucional

El comité que aprobó, el código de aprobación y la fecha de aprobación, copiados del
registro de aprobación. Cuando el estudio usó solo datos públicos y anonimizados y
ningún comité lo revisó, la declaración es *Not applicable.*, y la declaración de
disponibilidad de datos nombra la fuente pública que lo justifica.

## Declaración de consentimiento informado

Una oración: se obtuvo el consentimiento de todos los sujetos que participaron en el
estudio, o *Not applicable.* cuando no se reclutó a ningún sujeto humano. Nunca afirme
un consentimiento que el registro de aprobación no muestre.

## Conflictos de interés

Una oración que declara que no existen.

El único caso que requiere más: cuando un autor está afiliado a una organización con
interés en los resultados (normalmente la que suministró los datos), nombre la
afiliación explícitamente y repita la declaración para ese autor. El silencio sobre una
afiliación conocida es el fallo que este bloque existe para prevenir.

Cuando la revista lo pide, añada la oración sobre el papel del financiador: los
financiadores no tuvieron ningún papel en el diseño del estudio, los análisis, la
redacción del manuscrito ni la decisión de publicar.

## Agradecimientos

Presente solo cuando hay un proyecto o institución que agradecer que no esté ya
nombrado en el financiamiento. Una o dos oraciones. También aloja el financiamiento y
la declaración de uso de IA cuando la revista los ubica aquí.

## Materiales suplementarios

Una oración por elemento: qué es y desde dónde se descarga. Cada elemento listado aquí
se referencia desde la sección del cuerpo que lo necesita.

## Abreviaturas

Opcional; ninguno de los artículos medidos del grupo incluye una. Cuando la revista la
pide, una línea por abreviatura, en el orden de primera aparición, con exactamente el
desarrollo que usa el cuerpo.

## Apéndices

Se usan cuando un material es necesario para reproducir el trabajo pero rompería el flujo de
la sección que lo necesita: artefactos textuales, o una tabla completa de parámetros cuando la
configuración experimental contiene solo los valores que se razonaron.

Identificados con letras, con subsecciones numeradas bajo su letra. **Cada apéndice se referencia
desde la sección del cuerpo que lo necesita**; uno que nada referencia es peso muerto.

Si el artículo tiene apéndices o no se decide para cada artículo. Cuando los tiene, van
después de las referencias, nunca entre las declaraciones.

**Un apéndice que ocupa una página o menos no es un apéndice.** Su contenido va a la
sección del cuerpo que lo necesita, donde se lee en contexto y no a una vuelta de
página: Materiales y Métodos para una derivación, una demostración o un detalle formal
del método, y la configuración experimental para una tabla de parámetros, un detalle de
protocolo o una configuración. Solo el material de más de una página queda después de
las referencias. `verify` estima la extensión impresa de cada apéndice a partir de la
fuente y reporta uno que cabe en una página (`appendix-length`), nombrando la sección a
la que pertenece.

## Highlights

De tres a cinco viñetas, cada una de como máximo 85 caracteres con espacios, cada una
una sola afirmación: la propuesta y luego un hallazgo por contribución, en el orden de
las conclusiones. Los highlights comprimen las contribuciones y los hallazgos del
artículo, después de que las conclusiones los enuncian; no añaden nada que las
conclusiones no contengan, y un número en un highlight es idéntico al de los resultados.

## Resumen gráfico

Opcional, para las revistas que lo aceptan: una sola imagen de la propuesta y de su
hallazgo principal, legible sin el artículo. Reutiliza el diagrama de métodos o una
figura de resultados en lugar de inventar una afirmación nueva.

## Declaración de uso de IA

**Siempre presente.** Todo artículo que escribe este flujo se produjo con agentes de IA,
así que siempre hay algo que declarar. La declaración se construye a partir del registro
de uso de IA del flujo: el agente de cada fase, las sesiones del arnés con su
herramienta, las rondas de aprobación del operador, las revisiones y los bloques del
artículo que redactaron los agentes. `packet` adjunta ese registro a este bloque; la
declaración enuncia lo que muestra, nunca menos y nunca más.

Nombre las herramientas y, cuando el registro la contiene, su versión; indique para qué
se usaron (las fases y las secciones que redactaron); indique que los autores revisaron
y editaron el resultado en las compuertas de aprobación registradas y asumen plena
responsabilidad. Cuando una versión no está en el registro, la aporta el operador.

Nombre el framework que ejecutó el flujo y cite su repositorio, a partir del campo
`framework` del registro: papersmith, con su versión cuando está registrada, en
https://github.com/LIAUNAL/papersmith-ai (en LaTeX, `\url{https://github.com/LIAUNAL/papersmith-ai}`).
La cita va en la primera oración de la declaración, junto a los entornos que ejecutaron
los agentes, por ejemplo "the authors used AI agents orchestrated by the papersmith
framework (version 0.58.2, \url{https://github.com/LIAUNAL/papersmith-ai}) and run in
[harnesses] to [uses]".

Redacción por revista, con los corchetes completados a partir del registro (el texto
va en el idioma del artículo):

- **Elsevier**, titulada "Declaration of generative AI and AI-assisted technologies in
  the manuscript preparation process": "During the preparation of this work the
  author(s) used [NAME OF TOOL / SERVICE] in order to [REASON]. After using this
  tool/service, the author(s) reviewed and edited the content as needed and take(s)
  full responsibility for the content of the published article."
- **MDPI**, dentro de los Agradecimientos: "During the preparation of this
  manuscript/study, the author(s) used [tool name, version information] for the
  purposes of [description of use]. The authors have reviewed and edited the output and
  take full responsibility for the content of this publication."
- **IEEE**, dentro de los Agradecimientos: las herramientas, para qué se usaron y las
  secciones que contienen contenido generado por IA, por su nombre.
- **Cualquier otra revista**: "During the preparation of this work, the authors used [tools]
  to [uses], in [sections]. The authors reviewed and edited all generated content and
  take full responsibility for the content of this publication."

**Cuando los agentes generaron o ejecutaron código o experimentos**, la configuración
experimental lleva además una oración de métodos que dice qué partes de la
implementación y de las ejecuciones produjeron o ejecutaron agentes de IA, y cómo se
verificaron. El registro de uso de IA indica si eso ocurrió.

El uso de IA solo para gramática u ortografía también nombra la herramienta: los
artículos del grupo que lo declaran nombran Grammarly, Quillbot con ChatGPT, o Gemini
con Claude.

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025): ítems A008, A017 y A018 (Elsevier), luego A003, A006, A007, A009, A021, A022 y A026 (MDPI) del banco de artículos del laboratorio.

**Bloques medidos.** Los tres artículos de Elsevier incluyen Highlights, una sección de
declaración de IA antes de las referencias, contribuciones de los autores CRediT, una
declaración de intereses en competencia y el financiamiento dentro de los
Agradecimientos. Los artículos de MDPI incluyen Contribuciones de los autores,
Financiamiento, una Declaración del comité de ética institucional y una Declaración de
consentimiento informado (*Not applicable.* en 4 de 7), una Declaración de
disponibilidad de datos, Conflictos de interés con la oración sobre el papel del
financiador y la declaración de IA dentro de los Agradecimientos. 6 de 10 declaran uso
de IA (Grammarly; Quillbot con ChatGPT; Gemini con Claude); ninguno incluye una lista
de Abreviaturas.

## Entradas

Cada bloque aquí es un hecho externo, no una decisión. Nada de ello se deriva del
artículo, salvo los highlights, que comprimen lo que las conclusiones ya enuncian:
se escriben al final, una vez que existen las conclusiones, y no llevan ninguna arista
entre secciones porque el material final se presenta después de toda sección del cuerpo y no
restringe ninguna otra sección.

### Entradas externas

| Entrada | Desbloquea |
|---|---|
| Los **author-roles** — la lista de autores y los roles confirmados de cada autor | `bm-author-contributions` |
| El **grant-title** y el **grant-code** — el título registrado del proyecto de financiamiento, el financiador y el código | `bm-funding` |
| La **repository-url** — la URL del repositorio del proyecto y la fecha en que se verificó | `bm-data-availability` |
| La **repository-url** — el repositorio de código que produjo los números reportados, y su versión o commit | `bm-code-availability` |
| La **ethics-approval** — el comité que aprobó, el código y la fecha de aprobación, y cómo se obtuvo el consentimiento, o *Not applicable.* para datos públicos | `bm-ethics-statement`, `bm-informed-consent` |
| Cualquier afiliación de un autor con una organización interesada | `bm-conflicts-of-interest` |
| El proyecto o la institución que agradecer | `bm-acknowledgments` |
| Los archivos suplementarios que incluye el artículo | `bm-supplementary-materials` |
| Las abreviaturas que usa el cuerpo, cuando la revista pide la lista | `bm-abbreviations` |
| Las secciones del cuerpo que necesiten uno | `bm-appendices` |
| La editorial de la revista seleccionada, que decide los highlights y el resumen gráfico; las conclusiones escritas, que los highlights comprimen | `bm-highlights`, `bm-graphical-abstract` |
| El registro de uso de IA del flujo, adjuntado por `packet` | `bm-ai-use-declaration` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `back-matter.bm-acknowledgments` — presente solo cuando hay un proyecto o institución que agradecer que no esté ya nombrado en el financiamiento | `back-matter.bm-funding` — las entradas de financiamiento que ya nombran cualquier proyecto o institución acreditados allí |

## Descalificadores

- Un autor sin rol.
- Un rol atribuido sin que el autor lo confirme.
- Una herramienta de IA listada como autora, o que desempeña un rol CRediT.
- Un título o código de subvención reproducido de memoria en lugar de copiado.
- Financiamiento ubicado contra la regla de la revista: un bloque aparte donde la revista
  lo pone en los agradecimientos, o al revés.
- Una URL de repositorio que no resuelve, o que contiene código incapaz de producir los
  números reportados.
- Una fecha de acceso faltante en la URL.
- Una declaración de disponibilidad de datos que afirma que son públicos datos que no lo son.
- La disponibilidad del código incorporada a la declaración de datos.
- Un código de aprobación o una afirmación de consentimiento no copiados del registro de aprobación.
- Una afiliación interesada conocida sin declarar.
- Una declaración ubicada después de las referencias, o un apéndice ubicado antes de ellas.
- Un apéndice o un elemento suplementario que ninguna sección del cuerpo referencia.
- Un apéndice que cabe en una página en lugar de estar en la sección del cuerpo que lo necesita.
- Dos declaraciones fundidas en un mismo párrafo.
- Contenido de un apéndice que contradice la configuración experimental.
- Un highlight que afirma algo que las conclusiones no contienen, o un número que difiere
  de los resultados.
- Ninguna declaración de uso de IA.
- Una declaración de uso de IA cuyas herramientas, usos o secciones contradicen el
  registro de uso de IA del flujo, o que omite la oración de métodos cuando los agentes
  generaron o ejecutaron código o experimentos.
- Una declaración de uso de IA ubicada contra la regla de la revista.
