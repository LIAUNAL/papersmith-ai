---
{
  "section": "experimental-setup",
  "position": 6,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-experimental-setup.md",
      "quote": "Nada aquí se descubre: cada condición que esta sección enuncia ya estaba fijada cuando se ejecutaron los experimentos."
    }
  },
  "blocks": [
    {
      "id": "es-preamble",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "es-dataset",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "El conjunto de datos — cuando esta sección lo posee"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "es-assessment",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "Qué propiedad afirma cada contribución — si fue prometida, aquí es donde se nombra su instrumento"
          }
        },
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "El diseño experimental — los métodos competidores, los ejes y los criterios del corpus construido a propósito, establecidos como un único protocolo de comparación"
          }
        },
        {
          "value": "gap",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "La brecha — que ninguna referencia estándar mide lo que se afirma, razón por la cual existe el corpus construido a propósito"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "experimental-setup.es-dataset",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "Su única dependencia que NO es interna son los datos que debe mostrar entrando, que residen en `es-dataset` cuando el conjunto de datos pertenece a esta sección"
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "Qué propiedad afirma cada contribución — si fue prometida, aquí es donde se nombra su instrumento"
          }
        },
        {
          "target": "introduction.block-3",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "La brecha — que ninguna referencia estándar mide lo que se afirma, razón por la cual existe el corpus construido a propósito"
          }
        },
        {
          "target": "related-work.rw-closing",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "La brecha — que ninguna referencia estándar mide lo que se afirma, razón por la cual existe el corpus construido a propósito"
          }
        }
      ],
      "figure": {
        "ordered": false,
        "excludes": ["internal component of the proposal"],
        "caption_enumerates": true,
        "caption_decodes": false,
        "mandatory": true
      }
    },
    {
      "id": "es-training-details",
      "requires_facts": [
        {
          "value": "implementation",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "La implementación de los experimentos y su configuración — lo que realmente se ejecutó"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    }
  ]
}
---
# Configuración Experimental

**Extensión** 800–3500 palabras · un preámbulo opcional y dos subsecciones
**Contiene** todo el protocolo de evaluación — los datos tal como se usan, las métricas, los métodos comparados, la prueba estadística, el diseño de ablación y de sensibilidad, las medidas de interpretabilidad — y un diagrama de cierre
**No contiene** ningún resultado

Esta sección responde *¿obtendría yo sus números si ejecutara esto por mi cuenta?*. Convierte
el método en un protocolo: qué se mide, contra qué se mide y bajo qué
condiciones exactas. Cada número de la sección de resultados debe poder rastrearse hasta algo
declarado aquí.

La sección de métodos dice lo que el modelo **es**. Esta dice lo que se le **hizo**. Nada aquí se descubre: cada condición que esta sección enuncia ya estaba fijada cuando se ejecutaron los experimentos.

## La evaluación vive aquí, toda ella

**Cada elemento de la evaluación se declara en esta sección y en ninguna otra**: los
escenarios y los datos tal como se usan, la partición, las métricas, los métodos comparados, la
prueba estadística, las variantes de ablación, los barridos de sensibilidad y las medidas que
evalúan una contribución de interpretabilidad. La sección de métodos define la propuesta
y nunca la evalúa; la sección de resultados lee lo que se declaró aquí y nunca
introduce un elemento de protocolo propio. En los artículos medidos del grupo, la
prueba, la ablación e incluso las líneas base aparecieron a menudo por primera vez en los
resultados — el defecto que esta regla elimina.

**Cada bloque aplica cuando el artículo tiene lo que el bloque cubre, y solo entonces.** Un método
sin parámetros aprendidos no tiene búsqueda de hiperparámetros; una propuesta de un solo componente
no tiene nada que ablacionar; un artículo que no afirma interpretabilidad no declara ninguna
medida de interpretabilidad. El contrato fija dónde va cada elemento y cómo se
escribe, nunca que todo artículo deba llevarlos todos.

## Las dos subsecciones separan el diseño de la ejecución

**Evaluación y Comparación de Métodos es el diseño de la comparación. Detalles de Entrenamiento
es su ejecución.** Todo lo que responde a *qué se mide y contra qué* es
diseño. Todo lo que responde a *con qué valores y en qué máquina se ejecutó* es
ejecución. Son lo mismo antes y después de ejecutar.

La sección tiene dos subsecciones. Cuando los conjuntos de datos no pertenecen a la sección de
métodos, son el primer bloque de Evaluación y no una tercera subsección.

## Preámbulo

Opcional: cuatro de las diez configuraciones medidas del grupo no tienen preámbulo. Cuando se escribe, un
párrafo de 30–80 palabras, sin citas: el propósito del protocolo y luego los bloques
que la sección especifica, en orden. Puede remitir al diagrama de cierre.

## Subsección 1 — Evaluación y Comparación de Métodos

Nueve bloques. Cada uno es condicional a que el artículo tenga lo que cubre, salvo las
métricas.

**1. Los conjuntos de datos** — solo cuando la sección de métodos no los posee. Primero. Cuando
hay varios escenarios, los controlados van primero — sintético, luego
semisintético, luego real — y **cada escenario se nombra según la propiedad del
problema que exige** (un nivel de ruido, un nivel de dispersión, un cambio de dominio), para que el lector
sepa qué parte del problema prueba cada uno. Una corrupción o simulación aplicada a
los datos — anotadores simulados, ruido inyectado, entradas enmascaradas — se define aquí, con
su ecuación. Cuando los conjuntos de datos viven aquí y uno de ellos es real, su explicación
cierra con su diagrama del protocolo de adquisición, como prescribe la ranura del conjunto de
datos de la sección de métodos: dibujado por el agente `diagram-author` siguiendo
`skills/paper-writing/references/data-acquisition-diagram.md`, con sus etapas ilustradas con
pictogramas del dominio tomados de `skills/paper-writing/references/pictograms.tex`, nunca
solo con cajas, y como último artefacto de la explicación del conjunto de datos.

**2. El anuncio de la división** — cuando el marco tiene dos mitades disímiles.
Cada mitad hace entonces su propio recorrido por los bloques que siguen.

**3. Los ejes de comparación.** Las arquitecturas, backbones o variantes sobre los que se
barre la comparación, cada uno con su tabla de estructura — capas, dimensiones, número de parámetros
— y su cita. El eje es tan parte del protocolo como la métrica.

**4. Los métodos competidores.** Un elemento de lista cada uno, una cita cada uno y, cuando sea
posible, **su propia ecuación definitoria**. No se limite a nombrar una línea base: formalícela.
Un competidor escrito como un objetivo no deja duda sobre qué versión se ejecutó.

**5. Las métricas cuantitativas.** Cada una definida por una ecuación numerada, con su glosario
de símbolos inmediatamente **después** de la ecuación, no antes. Este es el
lugar con mayor densidad de ecuaciones del artículo fuera de la sección de métodos, y cada ecuación
aquí es la definición de una métrica.

**Cada instrumento se nombra bajo la propiedad que mide**, usando las mismas palabras
que el planteamiento del problema y la contribución usaron para esa propiedad. Un sinónimo rompe
la cadena que va del problema a la evidencia.

**6. Los instrumentos cualitativos o complementarios.** Las técnicas de visualización o de atribución
que respaldan las afirmaciones que ninguna métrica mide, cada una con su cita. Estas
son las que responden a las propiedades que una contribución prometió y que una métrica no puede alcanzar.

**Cuando la interpretabilidad es una contribución, se evalúa dos veces**: mediante la
lectura cualitativa nombrada aquí, y mediante una medida de fidelidad — una puntuación de eliminación,
de perturbación o de recuperación de una estructura conocida — frente a los métodos de atribución o de
explicación con los que compite, cada uno citado. La sección de métodos definió el
mecanismo; este bloque nombra cómo se juzgan sus explicaciones.

**7. El corpus de evaluación construido a propósito** — solo cuando ninguna referencia estándar mide
lo que se afirma. Descríbalo aquí: su tamaño, su composición y una tabla de
ejemplos. Sin él, la métrica de esa mitad no significa nada.

**8. La prueba estadística** — siempre que la propuesta se compare con algo. La
prueba, el procedimiento post hoc y la corrección por comparaciones múltiples, el nivel de
significancia y **la unidad sobre la que se ejecuta la prueba** (particiones, semillas, sujetos, conjuntos de datos). Los
resultados la aplican; no la eligen.

**9. El diseño de ablación y de sensibilidad** — cuando la propuesta tiene componentes que
pueden eliminarse o perillas que pueden barrerse. **Una variante de ablación por contribución**,
en el orden de la sección de métodos, cada una eliminando esa contribución o reemplazándola por
la pieza prestada que modifica, bajo el mismo protocolo. Luego los barridos de sensibilidad:
cada perilla que expone la sección de métodos y que se varía, con su rango. Cada variante y
cada barrido se nombra aquí para que los resultados solo puedan leerlo.

### Qué se cita aquí

**Una cita por objeto comparado.** Una por método competidor, una por eje o
arquitectura barrida, una por instrumento cualitativo y una por métrica **no estándar**.

**Las métricas estándar llevan una ecuación, no una cita.** La misma asimetría que en la
sección de métodos: lo que se toma prestado se cita, lo que es convencional se define.

**Cada decisión de protocolo lleva la cita que la justifica.** Los criterios de comparación
(por qué estas métricas y estas líneas base miden la propiedad reivindicada), la prueba
estadística con su procedimiento post hoc y su corrección, y la medida de fidelidad citan
cada una un artículo que usa o justifica esa elección, o el libro de referencia o el artículo
fundacional en aprendizaje de máquina, estadística, salud o el campo de la aplicación que la
establece. Un protocolo enunciado sin la razón por la que es el correcto se lee como una
elección arbitraria.

## Subsección 2 — Detalles de Entrenamiento

El bloque de reproducibilidad. Tiempo pasado, voz pasiva para el procedimiento. Seis espacios.

**1. Preprocesamiento y exclusiones.** Qué se filtró, descartó o remuestreó, y
por qué. Indique lo que se desechó antes de indicar lo que se conservó.

**2. El protocolo de partición.** Las divisiones, la estrategia de validación cruzada, la
estratificación.

**3. El optimizador y el calendario.** Cuando el método no se entrena — un estimador
analítico, una simulación, un resolvedor — este espacio y el siguiente contienen en su lugar sus
ajustes numéricos: tolerancias, iteraciones, discretización, presupuesto de muestreo.

**4. La búsqueda de hiperparámetros.** La herramienta, el muestreador, **la semilla**, el objetivo
que se minimiza y el rango de búsqueda por modelo. Nombrar la semilla y la configuración
del podador es el nivel en el que una ejecución se vuelve reproducible.

**5. Control de fuga de información.** Una oración explícita que indique que todo lo que requería una
referencia usó información únicamente de la partición de entrenamiento.

**6. Software y hardware.** Versión del lenguaje, versión del framework, versiones de las bibliotecas,
el entorno y el acelerador por modelo — obligatorio siempre que se reporten tiempos
en cualquier parte.

**Un valor viene con la razón por la que tiene ese valor.** Las cotas establecidas empíricamente
se enuncian junto con lo que la cota garantiza. La forma de un objetivo se justifica en
la sección de métodos; un valor dentro de una forma fija se justifica aquí.

**Cada parámetro ajustable tiene trazabilidad.** Un hiperparámetro nombrado aquí debe ser un símbolo declarado en
la sección de métodos.

### Qué se cita en los detalles de entrenamiento

**Cada decisión de protocolo cita lo que la justifica.** El preprocesamiento (una banda de
filtrado, una re-referenciación, un método de eliminación de artefactos), el protocolo de
partición (validación cruzada por sujeto o dejando uno fuera, la estratificación), el control
de fuga y el método de búsqueda de hiperparámetros llevan cada uno una cita a un artículo que
usa o justifica ese protocolo en el mismo tipo de datos, o al libro de referencia o artículo
fundacional en aprendizaje de máquina, estadística, salud o el campo de la aplicación que lo
establece. La cita se adjunta al protocolo que acredita. Las versiones de software y
bibliotecas llevan su propia cita cuando la revista lo pide; un valor elegido por los autores
lleva su razón, no una cita.

**La tabla completa de parámetros puede ir a un apéndice**, conservando en el cuerpo solo los
valores sobre los que se razonó. Ese es el uso correcto de un apéndice: el cuerpo
contiene lo que tiene una razón, el apéndice contiene lo que debe poder consultarse.

## Los párrafos abren con una oración, nunca con un rótulo

Los bloques numerados de arriba son nombres de este contrato, nunca del artículo. Cada
bloque se vuelve uno o más párrafos que abren con una oración, **nunca como un rótulo en
negrita** (`\textbf{Partition.}`), un encabezado en línea (`\paragraph{Metrics}`) ni un
elemento de lista en negrita. La primera oración de un párrafo presenta su tema y lleva
la transición desde el párrafo anterior mediante la relación entre ambos: los escenarios
llevan a cómo se dividen sus datos, la división a qué se compara sobre ella, la
comparación a cómo se puntúa y se prueba.

- *The real data were split by subject, so that no subject contributed samples to
  both the training and the test folds.* — abre la partición por lo que garantiza.
- *Three published methods were trained on those same folds, each formalized by the
  objective it minimizes.* — abre los métodos en competencia por el protocolo que comparten.
- *Every comparison was scored per subject, the unit the application decides on.* —
  abre las métricas por la unidad que fijó el párrafo anterior.

Deje que el propio contenido de la oración lleve la relación, como pide el estilo de la
casa: un conector de repertorio al inicio de cada párrafo (*Moreover*, *Furthermore*,
*In addition*) es el mismo esquema con otras palabras. Los métodos en competencia pueden
seguir formando una lista; sus elementos abren con el nombre de cada método en texto
plano. `write` rechaza un borrador de esta sección que abra un párrafo o un elemento con
énfasis (`DRAFT_BOLD_LEAD_IN`).

## Cada artefacto se referencia antes de aparecer

Cualquier objeto numerado — figura, tabla o panel — se referencia en el cuerpo **antes**
de aparecer, y la referencia apunta al subelemento exacto cuando el artefacto tiene
partes. Un artefacto que aparece sin referencia previa está mal ubicado o está muerto.

## Las figuras y tablas aquí son protocolo, nunca resultados

Nada en esta sección reporta un desempeño. Sus figuras ilustran el protocolo —
el calendario que se usó, el espectro de la entrada, la estructura del diseño —
y sus tablas contienen las arquitecturas de cada eje y los valores de los parámetros.

## El diagrama de cierre

La sección cierra con un diagrama, y **es el traspaso a la sección de resultados**.
Lo que el lector debe llevar consigo es el cruce, no los valores: los valores se
consultan cuando se necesitan, el cruce debe tenerse en mente para leer una tabla de resultados.

Muestra:

- qué datos entran;
- contra qué métodos se ejecuta la comparación;
- sobre qué ejes se barre;
- qué métrica sale de cada cruce;
- dónde se acoplan los instrumentos cualitativos;
- **la unidad de repetición** — sobre qué se promedia un único número reportado, y
  a través de qué se calcula su dispersión.

La propuesta es una fila del cruce, no el centro de la figura.

Esa unidad de repetición es el único elemento de ejecución admitido en el diagrama.
Sin ella, una celda del diagrama no puede leerse como una celda de una tabla. Todo lo demás
sobre la ejecución permanece en Detalles de Entrenamiento, que es donde se consulta.

**Su obligación con la sección de resultados:** cada tabla y cada figura de allí debe poder
ubicarse en este diagrama. Una celda reportada que el diagrama no contiene es una celda que el
diseño nunca declaró.

**Separación respecto del diagrama de métodos.** El diagrama de métodos muestra el método; este
muestra el experimento. La prueba: **ningún conjunto de datos ni ninguna línea base aparece en el
diagrama de métodos, y ningún componente interno de la propuesta aparece en este.** Una
caja que aparece en ambos significa que uno de ellos está mal.

## Las tablas quedan dentro de la caja de texto

Una tabla se imprime dentro de `\textwidth` a un tamaño legible, con la misma regla que
una figura (etiquetas, marcas de eje, leyendas y anotaciones incluidas): **todo texto de
una tabla o de una figura se imprime entre 0,70 y 0,90 veces el tamaño de la fuente del
cuerpo** (de 7 a 9 pt en un documento de 10 pt): nunca más pequeño, y nunca al tamaño
del cuerpo.

- **Las reglas son de `booktabs`** — `\toprule`, `\midrule`, `\bottomrule` — sin reglas
  verticales; una columna de prosa es una columna `X` de `tabularx`, de modo que la
  tabla toma el ancho del texto en lugar de excederlo.
- **La tabla va por debajo del tamaño del cuerpo, dentro del rango.** `\footnotesize`
  lo cumple a 10, 11 y 12 pt; `\small` solo con un cuerpo de 10 pt (supera 0,90 a 11 y
  12 pt); nunca `\normalsize`, el tamaño por defecto cuando la tabla no declara ninguno;
  `\scriptsize` y `\tiny` nunca cuando quedan por debajo del mínimo (`\scriptsize` lo
  alcanza solo a 10 pt).
- **Una tabla nunca se escala para que quepa.** Ni `\resizebox`, ni `\scalebox`, ni
  `adjustbox` por debajo de un factor de 0,85, ni escalar un `tabular` a
  `width=\textwidth`: escalar encoge el texto junto con la caja.
- **Una tabla más ancha que `\textwidth` se divide, se transpone o se traslada** a un
  `table*` o a una página apaisada cuando la revista permite cualquiera de los dos —
  nunca se encoge por debajo del mínimo.
- **La leyenda va encima de la tabla.**

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025), primero Elsevier y después MDPI: los ítems A008, A017, A018, A003, A006, A007, A009, A021, A022 y A026 del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una sola columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo el objetivo.

**Tamaño medido.** 7–10–24 párrafos; unas 810–1190–3480 palabras, siendo el máximo un
caso atípico con su propio protocolo de simulación; 0–3–4 subsecciones; 0–2–8 ecuaciones
destacadas; 4–9–17 citas; 0–1–3 figuras y 0–1–2 tablas.

**Ubicación medida.** Ocho de diez tienen una configuración propia después de los métodos; seis
abren con un párrafo de propósito y hoja de ruta. Solo tres definen sus métricas mediante
ecuación, solo dos declaran aquí la prueba estadística y solo uno declara aquí su
ablación — el resto los presenta en los resultados, lo que este contrato prohíbe.

**Lo que enuncian las configuraciones del grupo, en este orden:**

1. el preprocesamiento de los datos, con cada parámetro que lo determina;
2. el esquema de validación — particiones, estratificación, y si los sujetos o registros
   se mantienen separados entre particiones;
3. la búsqueda de hiperparámetros — el método (optimización bayesiana, estimadores de Parzen
   estructurados en árbol), los rangos explorados y el valor seleccionado, en una tabla;
4. las líneas base, con la afirmación de que se ejecutaron con las mismas particiones y el mismo
   presupuesto de ajuste;
5. las métricas, con una ecuación solo cuando la métrica no es estándar;
6. la prueba estadística que decide la significancia — Friedman con una prueba post hoc
   por pares y una corrección de Holm o Bonferroni es la opción por defecto del grupo;
7. el hardware y la plataforma, y la URL del repositorio de código.

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para llevar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una vez; los procedimientos que se ejecutaron van en pasiva en pasado (*was evaluated using*).
- **Las transiciones salen de la relación entre afirmaciones, no de una lista.** Primero se nombra la relación (contraste, causa, consecuencia, desarrollo, ejemplo) y se expresa con el propio contenido de la oración: una cláusula (*yet*, *so*, *although*), un sujeto que remite a lo anterior (*that gap*, *this cost*), o ningún conector cuando el orden de las oraciones ya lo dice. Un conector de repertorio (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) es la excepción: nunca el mismo dos veces en cinco oraciones, nunca la mayoría de las aperturas de un párrafo, y un conector de síntesis (*Overall*, *Taken together*) como máximo una vez por sección.
- ***because* y *where* conservan su función.** *because* enuncia una causa que el método o los datos establecen, como máximo una vez cada varias oraciones y nunca encadenado (*because …, and because …*); *where* abre la cláusula que sigue a una ecuación y define sus símbolos, y en ningún otro lugar de la prosa (se usa *in which*, *when* o dos oraciones). Una valoración es una oración propia, no un *, which indicates …* final.
- **El método tiene un solo nombre.** Se desarrolla con su acrónimo en el primer uso tanto en el resumen como en el cuerpo, y después se escribe *the proposed* seguido del acrónimo.
- **Lo que se ejecutó va en pasado; lo que contiene una tabla, en presente.** *Each model
  was trained for*; *Table 3 lists the search ranges*.
- **Aquí no se redefine ningún símbolo.** La configuración reutiliza la notación de la sección de métodos;
  un parámetro que fija ya debe existir allí.
- **La sección se titula *Experimental Set-Up*.**

## Entradas

### Entradas externas

| Entrada | Desbloquea |
|---|---|
| El **conjunto de datos** — cuando esta sección lo posee | `es-dataset` |
| Los **métodos competidores** — la lista de líneas base establecida en el estado del arte | `es-assessment` |
| Los **ejes** — sobre qué se barre la comparación | `es-assessment` |
| El **corpus construido a propósito** — que ninguna referencia estándar mide lo que se afirma | `es-assessment` |
| El **diseño experimental** — los métodos competidores, los ejes y los criterios del corpus construido a propósito, establecidos como un único protocolo de comparación | `es-assessment` |
| La **implementación** de los experimentos y su configuración — lo que realmente se ejecutó | `es-training-details` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `experimental-setup.es-assessment` — el panel "qué datos entran" del diagrama de cierre | `experimental-setup.es-dataset` — el bloque del conjunto de datos, cuando esta sección lo posee |
| `experimental-setup.es-assessment` — Qué propiedad afirma cada contribución — si fue prometida, aquí es donde se nombra su instrumento | `materials-and-methods.mm-proposal` — las contribuciones enumeradas para las que se nombra el instrumento |
| `experimental-setup.es-assessment` — La brecha — que ninguna referencia estándar mide lo que se afirma, razón por la cual existe el corpus construido a propósito | `introduction.block-3` — la brecha conjunta, condensada allí |
| `experimental-setup.es-assessment` — La brecha — que ninguna referencia estándar mide lo que se afirma, razón por la cual existe el corpus construido a propósito | `related-work.rw-closing` — la brecha conjunta, desarrollada allí |

### Decisiones estructurales

- **Cuántos bloques tiene Evaluación** lo decide la ubicación del conjunto de datos
  ya decidida en la sección de métodos — una decisión estructural, no una
  dependencia de un bloque específico.
- **El diagrama de cierre** es el cruce declarado por todo lo que Evaluación
  ya contiene, más la unidad de repetición — una regla de composición interna
  dentro del propio `es-assessment`. Su única dependencia que NO es interna son
  los datos que debe mostrar entrando, que residen en `es-dataset` cuando el
  conjunto de datos pertenece a esta sección; esa es una fila de la cadena de arriba, no una
  decisión estructural.

## Descalificadores

- Un conjunto de datos real descrito aquí cuya explicación no cierra con su diagrama del
  protocolo de adquisición, o cuyo diagrama es solo de cajas.
- Un paso de preprocesamiento, protocolo de partición, prueba estadística o criterio de
  comparación enunciado sin una cita que lo use o lo justifique.
- Una métrica nombrada pero no definida.
- Un glosario de métrica ubicado antes de su ecuación en lugar de después.
- Una cita en una métrica estándar, o una cita faltante en una no estándar.
- Un método competidor nombrado sin cita, o nombrado sin ser formalizado
  cuando existe una formalización.
- Un eje barrido sin declarar su estructura.
- Una propiedad afirmada por una contribución sin un instrumento nombrado aquí.
- Un instrumento nombrado con un nombre distinto al que la propiedad que mide lleva en
  el planteamiento del problema y en la contribución.
- Un artefacto que aparece antes de cualquier referencia a él, o al que nada referencia en
  absoluto.
- Una referencia a un artefacto completo cuando el valor está en una de sus partes.
- Un corpus construido a propósito usado sin ser descrito.
- Un hiperparámetro sin valor, o un valor que no coincide con la configuración que se
  ejecutó.
- Un parámetro ajustable que no existe en la sección de métodos.
- Una semilla, división o número de repeticiones omitido.
- Hardware omitido mientras se reportan tiempos.
- Ninguna declaración de control de fuga de información.
- Un resultado, una comparación medida o una cifra de desempeño.
- Una comparación con métodos competidores sin prueba estadística declarada, o una prueba
  declarada sin la unidad sobre la que se ejecuta.
- Una contribución que puede eliminarse sin variante de ablación declarada, o una perilla
  barrida en los resultados sin un barrido declarado aquí.
- Una contribución de interpretabilidad sin instrumento cualitativo o sin medida de
  fidelidad declarada aquí.
- Un escenario que no dice qué propiedad del problema exige.
- Un párrafo o elemento de lista que abre con un rótulo en negrita o un encabezado en línea.
- La ausencia del diagrama de cierre.
- Una tabla o figura de resultados que no puede ubicarse en el diagrama de cierre.
- Una caja compartida entre el diagrama de cierre y el diagrama de métodos.
- Cualquier elemento de ejecución en el diagrama de cierre distinto de la unidad de repetición.
- La tabla completa de parámetros en el cuerpo cuando solo se razonó sobre algunos valores, o
  una tabla de apéndice que contradice el cuerpo.
- Una tabla que excede `\textwidth`, o cuyo texto se imprime por debajo de 0,70 o por
  encima de 0,90 veces el tamaño de la fuente del cuerpo (incluida una tabla dejada al
  tamaño del cuerpo).
- Una tabla escalada con `\resizebox`, `\scalebox` o `adjustbox` por debajo de 0,85, o
  escalada a `\textwidth`.
- Una tabla con reglas verticales, o una tabla cuya leyenda queda debajo de ella.
