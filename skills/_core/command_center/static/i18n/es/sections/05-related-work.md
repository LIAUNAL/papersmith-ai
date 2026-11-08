---
{
  "section": "related-work",
  "position": 4,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/05-related-work.md",
      "quote": "Cada afirmación aquí pertenece al trabajo de otros, y la sección argumenta qué dejan sin resolver esos trabajos en conjunto."
    }
  },
  "blocks": [
    {
      "id": "rw-preamble",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "La lista de problemas específicos — para anunciar los bloques y su orden"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "La lista de problemas específicos — para anunciar los bloques y su orden"
          }
        }
      ]
    },
    {
      "id": "rw-panorama",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "El problema general del planteamiento del problema"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "optional": true,
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "El problema general del planteamiento del problema"
          }
        }
      ]
    },
    {
      "id": "rw-problem-blocks",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "Los problemas específicos, un bloque cada uno"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "optional": true,
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "Los problemas específicos, un bloque cada uno"
          }
        }
      ]
    },
    {
      "id": "rw-closing",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "La brecha se enuncia en dos lugares — el cierre de esta sección y el cierre del bloque de estado del arte de la introducción — y deben decir lo mismo a distintas profundidades."
          }
        }
      ],
      "after": [
        {
          "target": "related-work.rw-problem-blocks",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "Nombre los frentes que quedan abiertos — tantos como bloques haya."
          }
        }
      ]
    },
    {
      "id": "rw-synthesis-artefact",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "Las propiedades (contribuciones) que declara la propuesta"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "Las propiedades (contribuciones) que declara la propuesta"
          }
        }
      ],
      "figure": {
        "components_from": "contributions",
        "ordered": false,
        "excludes": [],
        "caption_enumerates": true,
        "caption_decodes": false,
        "mandatory": false
      }
    }
  ]
}
---
# Trabajos relacionados

**Extensión** 820–1700 palabras
**No contiene** ecuaciones
**Contiene** un bloque por cada problema enunciado, y una tabla (o figura) de síntesis de 7–12 trabajos

Cada afirmación aquí pertenece al trabajo de otros, y la sección argumenta qué dejan sin resolver esos trabajos en conjunto.

## Si la sección existe

<!-- Pregunta abierta 1 (design.md, `the-phases-are-derived-not-remembered`):
resuelta a nivel de bloque — cada bloque `rw-*` lleva `optional: true` en el
front matter. Sin cambio de esquema, sin ampliar `_TOP_LEVEL_ALLOWED`. Esto es
lo que significa "toda la sección es condicional" en la granularidad de bloque que
el contrato ya maneja. -->

Esta es una sola decisión con dos criterios, y cualquiera de ellos basta para crear la
sección:

- **¿El linaje necesita más de un párrafo por problema?** Si cada problema se
  resuelve en un solo párrafo, el material permanece comprimido en la
  introducción.
- **¿Se quiere la tabla comparativa?** El artefacto de síntesis vive aquí y en ningún
  otro lugar.

**Si la sección no existe:** no hay párrafo de panorama, no hay
artefacto de síntesis en ninguna parte del artículo, y el bloque de estado del arte de la
introducción se expande a un párrafo por cada problema enunciado. La tabla no se traslada a otra
sección — se pierde junto con la sección.

La decisión gobierna dos lugares a la vez, por lo que se toma antes de redactar cualquiera de ellos.

## Regla estructural global

Cinco bloques. El tercero se repite — una vez por cada problema enunciado.

1. preámbulo
2. panorama general del problema
3. un bloque por cada problema específico
4. cierre: frentes abiertos y la brecha
5. artefacto de síntesis

### Directivas: correspondencia con las familias de la introducción y tríada de cada subsección
Se organiza en correspondencia directa con las 3 a 7 familias metodológicas o alternativas establecidas en los párrafos 3 y 4 de la introducción:
- **Párrafo de contexto inicial:** un primer párrafo que da contexto a los problemas y métodos estudiados, enmarcando directamente las familias que siguen.
- **Una subsección por familia:** cada familia presentada en el estado del arte de la introducción recibe su propia subsección (`\subsection{...}`).
- **Tríada interna de cada subsección (2 a 3 párrafos cada una):**
  1. *Fundamentos*: raíces teóricas, formulación matemática y supuestos operativos.
  2. *Métodos principales*: arquitecturas primarias, algoritmos representativos clave y trabajos de referencia.
  3. *Principales desafíos*: cuellos de botella críticos, modos de falla abiertos y cuestiones sin resolver.
- **Volumen de citas:** cada subsección de familia debe citar entre 5 y 10 trabajos alternativos distintos.
- **Horizonte de referencias:** entre la introducción y el trabajo relacionado, el manuscrito debe citar en conjunto entre 30 y 40 referencias.

**El principio organizador es una unidad por cada problema enunciado**, el mismo principio que
gobierna el bloque de estado del arte de la introducción. Lo que cambia es de qué está
hecha la unidad: un párrafo en la introducción, un bloque de párrafos aquí.

**El corte entre los dos lugares:** la introducción conserva, por problema, la familia
cuya limitación motiva la contribución. Todo lo demás que abordó ese mismo
problema es una variante, y vive aquí.

## Bloque 1 — Preámbulo

Un párrafo de unas 40 palabras, dos oraciones, **sin citas**. Nombra los bloques
que siguen y su orden. Nada más.

Es el único párrafo de la sección que no cierra con una limitación, porque
no caracteriza ninguna familia.

## Bloque 2 — Panorama general del problema

Un párrafo, de unas 150 palabras. Tome el **problema general** — el que nombra el
paradigma, no las dificultades — y enuncie toda la trayectoria que recorrió la
literatura: de dónde vino el campo y hacia dónde se movió.

Es panorama, no revisión: no desarrolle ninguna familia ni atribuya ninguna limitación particular.
Su función es permitir que los bloques que siguen comiencen directamente en su problema.

## Bloque 3 — Un bloque por cada problema específico

Tantos bloques como problemas específicos declare el planteamiento del problema. Dos o tres.
Cada bloque se compone de:

- **un párrafo que lleva el linaje principal** — la misma familia que la introducción
  conservó, aquí con su progresión completa;
- **uno o dos párrafos adicionales** que llevan las variantes, las estrategias
  alternativas y los intentos parciales que abordaron el mismo problema y que la
  introducción dejó fuera.

Cada párrafo cierra con la limitación de su familia. Cada bloque cierra con lo que
ninguna de sus familias resolvió.

**Cada bloque abre nombrando su problema y enunciando su propia trayectoria** antes
de recorrerla, y **parte del cierre del bloque anterior**: la deficiencia con la que
terminó el problema anterior es lo que motiva el siguiente. Los bloques son una cadena, no
islas paralelas.

Tamaño de párrafo: 130–300 palabras. Nada en esta sección supera las 300 palabras.

**Los bloques pesan aproximadamente lo mismo.** Un bloque de 700 palabras frente a uno de 220 dice que el
segundo problema fue mencionado en lugar de revisado.

### Dos maneras de recorrer un bloque, elegidas según la naturaleza del problema

**Cronológica** — cuando el problema es *cómo se ha resuelto esta tarea*. Una tarea tiene una
historia.

1. la familia fundadora, con lo que aporta y su limitación estructural;
2. las familias intermedias, un párrafo cada una, cada una partiendo de la limitación
   anterior;
3. la familia más reciente, que es o bien la que la propuesta **adopta** — y el
   párrafo cierra diciendo por qué es adecuada — o bien la que **desplaza**, y
   el párrafo cierra con una limitación.

**Taxonómica** — cuando el problema es *cómo se ha logrado esta propiedad*. Una propiedad
no tiene historia; tiene tipos.

1. enuncie toda la taxonomía en un párrafo breve que no desarrolle ninguna parte de ella;
2. declare cuál rama es la relevante y por qué;
3. recorra esa rama, familia por familia, cada párrafo sobre su limitación.

Como aquí la unidad es un bloque y no un párrafo, una rama descartada puede ocupar un
párrafo propio en lugar de una sola oración. Para eso es el espacio adicional de
esta sección.

## Bloque 4 — Cierre: frentes abiertos y la brecha

Un párrafo, 100–125 palabras, de 3 a 5 oraciones.

1. **Una fórmula de recapitulación.**
2. **Nombre los frentes que quedan abiertos — tantos como bloques haya.** Dos bloques, dos
   frentes.
3. **Enuncie cuáles de ellos aborda la propuesta**, cerrando con la propuesta por su nombre.

**La brecha no siempre es metodológica.** Un trabajo puede estar limitado por su mecanismo, pero
también por la **tarea** que resuelve o por los **datos** que usa: cercano en método y lejano
en alcance. Cuando la brecha es de alcance y no de mecanismo, dígalo explícitamente — un
lector que conoce ese trabajo, de lo contrario, se preguntará por qué no bastaba ya.

## Bloque 5 — Artefacto de síntesis

Una tabla comparativa por defecto; una figura de evolución solo cuando el punto es el
linaje, no la comparación. Cualquiera de las dos formas ubica **de 7 a 12 trabajos**,
sin contar la fila de la propuesta.

**Sus dimensiones son las propiedades en las que gana la propuesta** — se derivan
de las contribuciones, no de lo que resulte fácil de tabular. La fila de la propuesta es
la única que cubre todas las columnas.

Va después del cierre, precedido por **un párrafo de referencia de una oración que nombra
las dimensiones en el cuerpo** antes de que aparezca la tabla. La variante es un artefacto
por cada bloque del bloque 3, ubicado al cierre de ese bloque; en ese caso la referencia es la
última oración del bloque, y los 7 a 12 trabajos se cuentan entre esos artefactos.

Nombre las dimensiones en el cuerpo, nunca solo en el encabezado de la tabla.

### La tabla de síntesis

**Filas: de 7 a 12 trabajos, y luego la propuesta como última fila.** Un trabajo gana una
fila por su relevancia para los pilares y las contribuciones del artículo — el
representante más fuerte de su familia en las propiedades que reclama la propuesta, no el
más citado ni el más reciente. Cada familia que desarrolla esta sección tiene al menos una
fila; una familia con varias filas las mantiene contiguas.

**Columnas: la familia y luego los ejes de comparación.** Cada eje es un pilar, una
contribución o una propiedad que declara la propuesta, nombrado en la oración de
referencia del cuerpo. Un eje que todas las filas cumplen no distingue nada y se elimina;
también se elimina un eje que ninguna contribución reclama.

**El redactor elige la disposición que se lee más rápido y explica por qué en una línea
de su informe:**

- una **matriz de marcas** cuando todos los ejes son propiedades de sí/no;
- una **tabla compacta de atributos** cuando un eje toma un valor breve (un régimen de
  datos, una clase de modelo, un esquema de validación);
- **filas agrupadas por familia** — una fila de etiqueta `\multicolumn` por familia, o una
  columna de familia — cuando varios trabajos comparten familia y la agrupación es en sí
  misma el argumento.

**Las celdas son concisas y exactas:** un símbolo (`\checkmark`, `--`, una marca parcial) o
como máximo tres palabras. Ninguna oración, ninguna cláusula, ninguna celda que sea solo
una cita. La leyenda es la clave: decodifica cada símbolo y abreviatura que usan las
celdas, de modo que la tabla se lee sin el cuerpo. La cita va en la celda del propio
trabajo, una sola vez.

**Cabe en la caja de texto.** Reglas de `booktabs` y un `tabularx` a `\linewidth`, bajo
las reglas de tablas de los contratos 02 y 03 (*Las tablas quedan dentro de la caja de
texto*): el mismo rango de texto (de 0,70 a 0,90 veces el tamaño del cuerpo), sin escalar
para que quepa, y una tabla demasiado ancha se divide o se transpone, nunca se encoge.

## Todo artefacto se referencia antes de aparecer

El artefacto de síntesis — y cualquier otra figura o tabla que contenga esta sección — se
referencia en el cuerpo **antes** de aparecer, con la referencia apuntando al
subelemento exacto cuando tiene partes. Un artefacto que aparece sin referencia previa está
mal ubicado o está muerto.

## Temático, no catálogo

El párrafo trata sobre **familias**, no sobre trabajos individuales. El sujeto de las
oraciones es la familia o la capacidad.

**Marcador fiable de catalogación: la cita usada como sintagma nominal** — *el trabajo en
[N] usa*, *el método de [N] combina*. Si aparece, la sección está catalogando.

**Señal débil: menos de veinte palabras por oración.** Un párrafo temático tiene de 24 a
27; un catálogo baja a 13–18 porque concentra una oración breve por trabajo. Esto es
un indicio, no una prueba — los rangos se tocan en el borde.

La razón de fondo: **un catálogo no puede cerrar con una brecha, porque nunca produjo
una.** Si el párrafo enumera trabajos en lugar de caracterizar familias, no queda nada
por sintetizar.

## Citas

- **Al final de la oración que respaldan.** Una oración, una afirmación atribuida. Una
  oración que necesitaría dos citas son dos oraciones. Agrupe los rangos.
- **Nunca como sintagma nominal.**
- **De dos a seis por párrafo.** Ese es el número accionable; el total de referencias
  distintas es la consecuencia, no el objetivo.
- **Toda limitación atribuida a trabajos previos lleva una cita**, preferiblemente una
  de esa literatura y no de los propios autores.
- Esta sección no está necesariamente más citada que la introducción. Lo que cambia es
  la profundidad por familia.

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025): los ítems A003, A006, A007, A009, A012, A013, A021, A022, A023 y A026 del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una sola columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo el objetivo.

**Tamaño medido, en los tres artículos que conservan esta sección.** 6–13–22 párrafos;
604–1723–2264 palabras, unas 53–149–201 líneas; 101–103–133 palabras por párrafo; 2–3–5
subsecciones; 19–31–35 citas, 2.7–3.2 por párrafo. Los otros siete llevan el
estado del arte dentro de la introducción.

**Citas.** Numéricas, entre corchetes. La mayoría de las marcas citan un trabajo; un grupo cita
a lo sumo cuatro, enumerados con comas (`[31,32,33,34]`), nunca como un rango. Una cita cierra
la oración que respalda, o sigue al nombre del método que acredita; nunca es
el sujeto de una oración (*ref. [29] presents*).

**La sección puede cerrar con una tabla comparativa** que contrasta las propiedades de la propuesta
con los trabajos revisados: de 7 a 12 trabajos representativos, cada familia con al menos
una fila (Bloque 5).

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para llevar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una vez; los procedimientos que se ejecutaron van en pasiva en pasado (*was evaluated using*).
- **Las transiciones salen de la relación entre afirmaciones, no de una lista.** Primero se nombra la relación (contraste, causa, consecuencia, desarrollo, ejemplo) y se expresa con el propio contenido de la oración: una cláusula (*yet*, *so*, *although*), un sujeto que remite a lo anterior (*that gap*, *this cost*), o ningún conector cuando el orden de las oraciones ya lo dice. Un conector de repertorio (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) es la excepción: nunca el mismo dos veces en cinco oraciones, nunca la mayoría de las aperturas de un párrafo, y un conector de síntesis (*Overall*, *Taken together*) como máximo una vez por sección.
- ***because* y *where* conservan su función.** *because* enuncia una causa que el método o los datos establecen, como máximo una vez cada varias oraciones y nunca encadenado (*because …, and because …*); *where* abre la cláusula que sigue a una ecuación y define sus símbolos, y en ningún otro lugar de la prosa (se usa *in which*, *when* o dos oraciones). Una valoración es una oración propia, no un *, which indicates …* final.
- **El método tiene un solo nombre.** Se desarrolla con su acrónimo en el primer uso tanto en el resumen como en el cuerpo, y después se escribe *the proposed* seguido del acrónimo.

## Insumos por bloque

**Nada aquí depende de una medición.** La sección se escribe completa antes de que
se ejecute un solo experimento. Cada bloque se remonta al planteamiento del problema, que proviene
de las contribuciones, que provienen de la formulación matemática — la raíz de
esta sección es la formulación.

### Insumos externos

| Insumo | Desbloquea |
|---|---|

### Cadena interna

| Bloque | Depende de |
|---|---|
| `related-work.rw-preamble` — La lista de problemas específicos — para anunciar los bloques y su orden | `introduction.block-2` — el planteamiento del problema, general y específico, descompuesto allí |
| `related-work.rw-panorama` — El problema general del planteamiento del problema | `introduction.block-2` — el planteamiento del problema, general y específico, descompuesto allí |
| `related-work.rw-problem-blocks` — Los problemas específicos, un bloque cada uno | `introduction.block-2` — el planteamiento del problema, general y específico, descompuesto allí |
| `related-work.rw-closing` — nombra los frentes que quedan abiertos, tantos como bloques haya | `related-work.rw-problem-blocks` — los bloques de problemas específicos cuya limitación no resuelta se convierte cada una en un frente nombrado |
| `related-work.rw-synthesis-artefact` — Las propiedades (contribuciones) que declara la propuesta | `materials-and-methods.mm-proposal` — las contribuciones enumeradas que tabula el artefacto de síntesis |

**El referente se movió.** El `components_from` de este bloque se resuelve ahora contra la sección
de métodos, no contra la introducción — sigue siendo una verificación real entre secciones, solo cambió su
origen.

**Obligación cruzada.** La brecha se enuncia en dos lugares — el cierre de esta sección
y el cierre del bloque de estado del arte de la introducción — y deben decir lo
mismo a distintas profundidades.

## Descalificadores

- Un bloque que no corresponde a ningún problema enunciado.
- Un problema enunciado sin bloque.
- Un preámbulo que revisa una familia, o que lleva una cita.
- Un panorama que atribuye una limitación a una familia particular.
- Un párrafo que no cierra con una limitación.
- Un bloque que no cierra con lo que ninguna de sus familias resolvió.
- Un bloque que no parte del cierre del anterior.
- Una limitación atribuida sin cita.
- Un párrafo de más de 300 palabras.
- Bloques de peso groseramente desigual.
- La ausencia del párrafo de cierre.
- Frentes nombrados en el cierre que no coinciden con el número de bloques.
- La ausencia del artefacto de síntesis.
- Un artefacto cuyas dimensiones no son las propiedades que declara la propuesta.
- Dimensiones nombradas solo en el encabezado de la tabla y no en el cuerpo.
- Menos de 7 o más de 12 trabajos en la tabla de síntesis, sin contar la fila de la propuesta.
- Una familia de esta sección sin fila en la tabla de síntesis.
- Una columna de la tabla de síntesis no vinculada a un pilar, contribución o propiedad que declara la propuesta, o una que comparten todas las filas.
- Una oración o una cláusula como prosa en una celda de la tabla de síntesis, o un símbolo que la leyenda no decodifica.
- Un artefacto que aparece antes de cualquier referencia a él, o que nada referencia en
  absoluto.
- Una cita usada como sintagma nominal.
- Una cita en cualquier lugar que no sea el final de la oración que respalda.
- Una ecuación.
- Una familia desarrollada tanto aquí como en el bloque de estado del arte de la introducción:
  cuando esta sección existe, ese bloque es un resumen.
- Una variante nombrada en la introducción: las variantes pertenecen aquí.
- La brecha de esta sección y la brecha de la introducción en desacuerdo.
- Un trabajo relacionado sin el párrafo de contexto inicial que enmarca los problemas y métodos estudiados.
- Cualquier familia metodológica presentada en el estado del arte de la introducción sin su subsección propia.
- Una subsección de familia con menos de 2 o más de 3 párrafos, o que omita los fundamentos, los métodos principales o los principales desafíos.
- Menos de 5 o más de 10 alternativas citadas por familia.
- Un total combinado de referencias entre la introducción y el trabajo relacionado fuera del rango de 30 a 40.
