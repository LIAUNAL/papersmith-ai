---
{
  "section": "materials-and-methods",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-materials-and-methods.md",
      "quote": "La propuesta ya existe."
    }
  },
  "blocks": [
    {
      "id": "mm-preamble",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "Nombra las subsecciones que siguen y su orden."
          }
        }
      ]
    },
    {
      "id": "mm-dataset",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "El conjunto de datos — cuando esta sección es su dueña"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "mm-borrowed-machinery",
      "requires_facts": [
        {
          "value": "formulation",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "La formulación matemática de la propuesta"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "mm-proposal",
      "requires_facts": [
        {
          "value": "formulation",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "La formulación matemática de la propuesta"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "produces_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "Esta sección define las contribuciones."
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-borrowed-machinery",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "enunciar la propuesta como un delta sobre la maquinaria prestada, con una referencia explícita a la ecuación anterior por su número"
          }
        },
        {
          "target": "materials-and-methods.mm-dataset",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "La propuesta es siempre el último bloque de la sección. Sin excepción."
          }
        }
      ],
      "figure": {
        "components_from": "contributions",
        "ordered": true,
        "excludes": ["dataset", "baseline"],
        "caption_enumerates": true,
        "caption_decodes": true,
        "mandatory": true
      }
    }
  ]
}
---
# Materiales y métodos

**Extensión** 1000–3950 palabras · 2 a 9 subsecciones
**Contiene** el planteamiento del problema, la maquinaria prestada, la propuesta (incluido su mecanismo de interpretabilidad) y un diagrama de síntesis
**No contiene** ningún resultado, número medido, comparación ni protocolo de evaluación

Esta sección define las contribuciones. Aquí nombra cada una y le da su
definición formal, en la notación que reutiliza todo lo que viene después; la introducción
recibe esa lista y se redacta a partir de ella.

## Aquí no se decide nada

La propuesta ya existe. Esta sección no la elige, no la mejora ni argumenta
a su favor: traslada una formulación existente a esta estructura. Donde la sección
parece estar decidiendo algo, está informando una decisión tomada en otro lugar.

## Preámbulo

Opcional: siete de los diez artículos medidos del grupo no lo tienen, y su primera
subsección empieza de inmediato. Cuando se escribe, es un párrafo de 60–120 palabras, sin
citas, que nombra el método una vez. Nombra las subsecciones que siguen y su orden. Nada más: ni motivación,
ni problema, ni resultado.

## Orden de las subsecciones

Tres posiciones, con el planteamiento del problema abriendo la parte formal. La tercera posición es
invariante. Cada posición está ligada a un elemento que la introducción ya enunció, y
ese vínculo es lo que impide que la sección vuelva a argumentar el artículo.

| Posición | Subsecciones | Párrafos | Palabras cada una | Realiza de la introducción |
|---|---|---|---|---|
| 1 — El conjunto de datos, cuando esta sección es su dueña | 1 o 2 | 3–12 | 300–1000 | la aplicación nombrada en la motivación; los conjuntos de datos que nombró |
| Planteamiento del problema (abre la parte formal) | 0 o 1 | 1–4 | 80–350 | el problema, formalizado |
| 2 — La maquinaria prestada | 1 a 3, una por pilar | 3–12 cada una | 180–1480 | los pilares, uno a uno, en el orden de la introducción |
| 3 — **La propuesta** | 1 a 3, una por contribución o una con el listado | 3–12 cada una | 380–1420 | la novedad: cada contribución, bajo la propiedad que aporta |

**Lo que nunca aparece aquí:** la motivación (cero oraciones), la evaluación de la
propuesta y cualquier cosa medida. El entrenamiento, la búsqueda de hiperparámetros, las métricas, las líneas base,
el protocolo de validación y la estadística pertenecen a la configuración experimental, siempre.

**La ubicación del conjunto de datos es una decisión estructural, y se toma una sola vez.** Si el
conjunto de datos pertenece a esta sección, va primero, y la sección abre con los datos. Si
pertenece en cambio a la configuración experimental, esta sección empieza directamente con la
maquinaria y se mantiene puramente formal, sin ninguna figura distinta del diagrama
de la propuesta. La decisión cambia el contrato de ambas secciones, por lo que se registra en lugar
de improvisarse.

**La propuesta es siempre el último bloque de la sección. Sin excepción.** Cuando
abarca varias subsecciones, estas son consecutivas y nada las sigue.

## Posición 1 — El conjunto de datos

De 3 a 12 párrafos, en una subsección o en dos (sintéticos y reales, o una por fuente).
Una o dos figuras: el protocolo de adquisición, siempre, para un conjunto real, y muestras
representativas cuando ayudan. Cero a dos
tablas: listas de variables o estadísticas descriptivas. Pocas ecuaciones: la segmentación o
el ventaneo que define una muestra es la habitual.

Secuencia de párrafos:

1. Por qué estos datos responden a la pregunta, y su procedencia.
2. Un párrafo por conjunto de datos o sitio, cuando hay varios.
3. La adquisición (protocolo, sensores, tarea), remitiendo a su diagrama del protocolo de
   adquisición, que cierra la explicación del conjunto de datos.
4. Lo que se descartó, y luego el preprocesamiento conservado.
5. Cómo se construye una muestra, con su notación.
6. Cuando los sujetos o las fuentes se repiten, cómo se mantienen juntos para que nada se filtre
   entre particiones; la partición en sí corresponde a la configuración experimental.

Se abre según de quién sean los datos:

- **Datos propios o construidos:** procedencia y período de tiempo en la primera oración, luego
  el objetivo que justifica esas variables.
- **Datos públicos:** por qué *estos* conjuntos responden a la pregunta y qué los hace diferentes
  entre sí.

**Indique lo que se descartó antes de indicar lo que se conservó**: exclusiones, filtros
de calidad, registros eliminados.

**Un conjunto de datos real cierra con su diagrama del protocolo de adquisición.** Cuando
los datos se capturaron (registrados de pacientes, sujetos, máquinas, plantas o sitios, y no
generados por un simulador), la explicación de cada conjunto real termina en una figura que
el agente `diagram-author` dibuja siguiendo
`skills/paper-writing/references/data-acquisition-diagram.md`: la captura en el orden en que
ocurrió (quién o qué se mide, el montaje, la tarea o condición de operación, la cadena de
adquisición, el registro almacenado, cómo se corta una muestra). Sus etapas se ilustran con
pictogramas del dominio tomados de `skills/paper-writing/references/pictograms.tex` (un
paciente con gorro de EEG, un generador o una máquina), nunca solo con cajas. Es el último
artefacto de la explicación del conjunto de datos, y el párrafo de adquisición la referencia
antes de que aparezca. Un conjunto sintético no tiene captura que mostrar y no lleva esta
figura.

**Aquí se paga la deuda de crédito de la introducción.** Un conjunto de datos nombrado en
la introducción sin referencia se nombra aquí con una.

## Planteamiento del problema

La parte formal abre con el problema, enunciado en símbolos: de uno a cuatro párrafos,
como subsección propia o como párrafos iniciales de la primera subsección de
maquinaria. Los espacios de entrada y de salida, las etiquetas o anotaciones, y el objetivo formal:
el estimador, el objetivo o el `\arg\min` al que responderá la propuesta. Cada propiedad que
nombra el planteamiento del problema de la introducción recibe aquí el mismo nombre que lleva allí.
No se necesita cita salvo que el planteamiento mismo sea prestado.

## Posición 2 — La maquinaria prestada

De una a tres subsecciones, cada una un cuerpo de teoría existente que la propuesta necesita: **una
por pilar que nombra la introducción, en el orden de la introducción.** Aquí
reside el grueso de las matemáticas del artículo.

Secuencia de párrafos de cada subsección: la notación, luego un párrafo por ecuación
con su cláusula *donde*, y luego la lectura en la que se apoya la propuesta.

**La maquinaria cierra con la brecha.** El último párrafo de la subsección que la propuesta
modifica enuncia, en una o dos oraciones, la limitación de esa pieza prestada con las
palabras que usa el planteamiento del problema: *este término es una entropía cruzada, por lo que se degrada
con ruido en las etiquetas*. Es técnica, nunca la motivación de la aplicación, y es el
único lugar donde el problema reaparece antes de la propuesta.

**Ordenada de modo que cada subsección use solo símbolos que las anteriores declararon.** Es
una cadena de notación, no una lista de temas.

**Cada subsección abre declarando la notación, antes de cualquier ecuación.** Ninguna subsección
matemática abre con una ecuación. Use notación por comprensión con un dominio de índice
explícito para una colección.

**Desarrollada solo hasta la profundidad con que la propuesta la usa.** Más que eso es trabajo relacionado
que se filtra.

## Posición 3 — La propuesta

Siempre al final. La parte menos citada del artículo. De una a tres subsecciones: una por
contribución, o una que las contiene todas y cierra con el listado.

**La interpretabilidad es una contribución de esta sección cuando el artículo la reivindica.** Su
mecanismo (el mapa de atribución, la puntuación de relevancia, el parámetro legible) se
define aquí con su ecuación, como cualquier otra contribución. Lo que revela sobre los datos
es un resultado.

**La evaluación de la propuesta nunca es una contribución de esta sección.** El protocolo,
las métricas, las líneas base y la estadística son de la configuración experimental, siempre.

**1. Apertura: nombrar el método y enunciar su contexto.** Donde sea posible, enunciar la
propuesta como un delta sobre la maquinaria prestada, con una referencia explícita a la
ecuación anterior por su número, para que el lector sepa exactamente qué cambió respecto de
lo que acaba de leer. Una oración puede recordar la brecha con la que cerró la maquinaria; no más.

**2. Su propia notación**, si la propuesta introduce símbolos que la maquinaria no
tenía.

**3. Las contribuciones, definidas, en el orden que esta sección establece.** La
lista de la introducción sigue este orden, nunca al revés. Cada una: qué
introduce, su ecuación y el símbolo que deja disponible para la siguiente. Cada
contribución se define aquí y en ningún otro lugar.

**Cada contribución se define bajo la propiedad que aporta**, nombrada con las mismas
palabras que el planteamiento del problema usa para esa propiedad. La lista de contribuciones de la introducción
reutiliza luego ese nombre exacto. Ese nombre compartido es lo que hace que la cadena desde el
problema hasta la evidencia sea trazable y no simplemente plausible.

**4. La combinación general.** La única expresión que reúne todas las contribuciones:
la suma, el objetivo compuesto o lo que corresponda al caso. Dos
posiciones, ambas admisibles: al final, construyendo las piezas y cerrando con la
integración; o al inicio, enunciando el objetivo completo con sus restricciones y
luego descomponiéndolo.

Este es el único lugar del artículo donde todas las contribuciones aparecen juntas, y
es la recompensa de la cadena de notación: **cada símbolo que contiene debe remontarse a una
declaración previa.** Uno que no lo haga significa que la cadena se rompió antes.

Cuando la contribución es un sistema en lugar de una formulación, la combinación la
llevan la enumeración de etapas y el diagrama. Allí el diagrama no es un
resumen: es la combinación misma.

**La lista de contribuciones debe poder leerse como una lista, en el propio orden del diagrama.** Dos
estructuras lo cumplen, y solo una de ellas se necesita en cada caso:

- **Cada contribución es su propia subsección.** El seccionamiento ya es la lista
  ordenada: sus encabezados nombran las contribuciones, en orden, y el lector las encuentra como
  estructura en lugar de como prosa. No se requiere nada más, y una lista de `\item`
  que repita esos mismos encabezados unas líneas después es redundancia, no un mandato.
- **Las contribuciones se integran en la prosa.** Entonces la lista no tiene otra forma, y
  se escribe una inmediatamente antes del puntero de cierre: un `\item` de LaTeX por
  contribución, nombrándola exactamente como se definió arriba, en el propio orden del diagrama,
  nada más por ítem.

En cualquier caso, lo que el propio Components Check de la sección contrasta con el diagrama es
esa lista ordenada de nombres, sea cual sea de las dos la que la contenga.

**Inferencia, cuando el modelo es probabilístico.** La distribución predictiva o sus
momentos cierran la formulación, después de la combinación general y antes del puntero.

**5. El cierre: puntero y diagrama de síntesis.** Obligatorio. La última oración en prosa
remite a la figura por su número y dice qué sintetiza; la figura sigue
inmediatamente.

**Opcional, y solo donde haya algo que decir:** una cláusula sobre convergencia o
estabilidad, que distinga la consistencia del estimador de la convergencia
empírica del entrenamiento. Pertenece aquí y no a la configuración experimental: esa
sección es procedimiento en tiempo pasado, y un argumento de convergencia es una afirmación en tiempo presente
sobre la formulación.

### El diagrama de síntesis

- **Resume la contribución en detalle.** Quien vea solo esta figura y su leyenda puede
  decir qué entra al método, qué hace cada etapa, qué es nuevo, qué se optimiza y qué
  sale. Sus partes, en orden de lectura: las entradas como objetos matemáticos
  (símbolos y formas, nunca un conjunto de datos con nombre); la representación a la
  que se llevan; las etapas centrales, dibujadas como arquitectura de red cuando el
  método es una red y como diagrama de flujo en otro caso; un panel numerado por
  contribución, con su mecanismo y su ecuación clave; las pérdidas, que confluyen en el
  objetivo total que enuncia la combinación general; las salidas, por símbolo y
  significado; y una leyenda para sus flechas y colores. La guía
  `skills/paper-writing/references/contribution-diagram.md` describe cada parte, la
  gramática visual y el presupuesto de tamaño.
- **Sus paneles de contribución son la lista de contribuciones**: exactamente los mismos
  componentes, en el mismo orden, con los mismos nombres que les da la propia lista de
  esta sección. Cada panel lleva en la fuente la marca `% node:`; las entradas, etapas,
  pérdidas y salidas que los rodean son contexto y no llevan ninguna.
- **La leyenda enumera los paneles en ese orden** y decodifica todo lo que la figura
  codifica: si hay colores, la leyenda dice qué significa cada uno.
- **Muestra el método, no el experimento.** En él no aparece ningún conjunto de datos ni
  ninguna línea base, ni como panel ni como contexto; esos pertenecen al propio diagrama
  de la configuración experimental. Un recuadro que aparece en ambos significa que uno
  de los dos está mal. Tampoco aparece una métrica ni un valor medido: la figura lleva la
  matemática básica del método, nunca un resultado.
- **El Components Check al que se somete este diagrama lo compara con la propia lista
  de este mismo bloque.** Es una deriva interna del bloque, nunca una corroboración
  entre secciones: no se consulta nada fuera de este bloque.

## Todo artefacto se referencia antes de aparecer

Cualquier objeto numerado (figura, tabla o panel) se referencia en el cuerpo **antes** de
que aparezca, y el puntero apunta al subelemento exacto cuando el artefacto tiene
partes. Un artefacto que aparece sin referencia previa está mal ubicado o muerto.

## Continuidad

Todo debe leerse como continuo, y la continuidad aquí es verificable, no una sensación.

**Cada símbolo se remonta a su declaración.** Cada subsección usa solo lo que las
anteriores declararon, y la propuesta abre nombrando lo que toma de la
maquinaria.

**Ningún símbolo se reutiliza para una cantidad distinta.** Cuando dos cantidades naturalmente
coincidirían en la misma letra, sepárelas con un diacrítico y declare ambas en la
misma oración, para que el lector vea la distinción una sola vez.

**Un diacrítico marca una relación con un objeto ya declarado**, nunca es decoración.
Cuatro usos:

- el mismo objeto tras una transformación;
- un estimador de una cantidad declarada;
- una versión normalizada de una cantidad declarada;
- la desambiguación de dos cantidades distintas que compartirían una letra.

## La extensión cuenta prosa, nunca matemáticas

Todo conteo de palabras de este contrato mide la prosa. Una ecuación destacada, su
etiqueta y su número no son prosa y no cuentan para ninguna extensión aquí.

**Una formulación cuyas matemáticas son largas no es por ello una formulación que deba
recortarse.** Las matemáticas se trasladan tal como están; lo que la extensión restringe es lo que se
escribe a su alrededor: la notación que declara sus símbolos, la oración que
anuncia cada expresión y la lectura que la sigue. Cuando una subsección excede
su extensión, lo que se ajusta es la prosa, nunca la derivación.

Una sección que omite pasos de las matemáticas de su propia fuente para ajustarse a un presupuesto de palabras ha
malinterpretado el presupuesto. Nada en este contrato lo autoriza.

## Ecuaciones: destacar y numerar son dos decisiones separadas

**Destacar por legibilidad.** Una expresión que no puede leerse en línea (de varias líneas,
con restricciones, con sumas sobre índices) se destaca. Lo que se lee en una línea
corrida permanece en el texto.

**Numerar toda ecuación destacada.** Los artículos del grupo las numeran todas, de modo que
el lector pueda nombrar cualquier expresión por su número. Numerar no es la promesa de una referencia
posterior; lo que esta sección debe garantizar es que exista cada número que sí cita.

**Las ecuaciones referenciadas se nombran por su número** entre subsecciones y entre secciones.
Esa referencia cruzada es lo que hace verificable la cadena de notación.

**Una referencia mira hacia atrás, nunca a una línea más arriba.** La oración que sigue a una
ecuación destacada expresa lo que se desprende de ella (la consecuencia, la lectura, el
paso siguiente) con sus propias palabras. Abrir esa oración nombrando la ecuación que el lector
acaba de terminar es redundancia, no una referencia cruzada. Lo mismo vale dentro de un
párrafo: un puntero por ecuación es suficiente, y un segundo en el mismo párrafo
no dice nada que el primero no haya dicho.

## Ambigüedad entre la ecuación y el código

Una ecuación puede estar escrita correctamente y aun así admitir dos lecturas: un objetivo
que suma sobre todas las clases cuando algunas están ausentes de un lote, una normalización cuyo
dominio no se enuncia.

**Donde una lectura es ambigua, la correcta se enuncia en el párrafo del
componente al que pertenece**, como una cláusula, no como un párrafo aparte. Cuál lectura es
correcta es un hecho sobre la implementación, no sobre las matemáticas: se lee de
lo que el código calcula.

**Lo que es un valor o un procedimiento no pertenece aquí**: tamaño de lote, tasa de aprendizaje,
calendario, hardware. Esos son de la configuración experimental.

**Pero todo parámetro ajustable que el método expone se nombra aquí**, aunque su valor se fije en
otro lugar. La configuración experimental no puede introducir un parámetro que no exista
en esta sección.

**El mismo corte se aplica a la elección de un parámetro.** Si la elección cambia la *forma* del
objetivo, se enuncia aquí como una cláusula en el párrafo del componente. Si es un
valor elegido dentro de una forma fija, pertenece a la configuración experimental.

## Citas

La densidad de citas cae bruscamente aquí: aproximadamente de cuatro a diez veces menor que en la
introducción. No es moderación: la introducción cita afirmaciones sobre el campo,
y esta sección cita **objetos**.

**La cita se adjunta al objeto que acredita, dondequiera que ese objeto esté en la
oración.** Esto difiere de la introducción, donde la cita respalda una afirmación
y por tanto cierra la oración. Cuando lo que se acredita aquí es una afirmación y no
un objeto, también cierra la oración.

**Un objeto matemático prestado llega con su procedencia adjunta a la oración
que lo anuncia, antes de que aparezca la ecuación.** El lector ve de quién es la definición
en el momento de leerla, no al final del párrafo.

Se citan cinco cosas:

1. el origen de una definición o un estimador prestados;
2. el origen de un algoritmo o componente con nombre;
3. la procedencia de los datos: quién los publica y dónde están disponibles;
4. la justificación de que una variable importa, en la subsección del conjunto de datos;
5. una propiedad afirmada sobre el método que otros ya establecieron.

**Lo prestado se cita, lo propio no.** Ninguna ecuación de la propuesta lleva una cita.

## Evitar volver a motivar

El riesgo concreto de redundancia en esta sección es la motivación. El problema se planteó en
la introducción y la brecha se cerró antes de esta sección. Aquí una contribución se
**define**, no se justifica. Una cláusula de propósito por contribución es suficiente; un párrafo
que explique por qué importa el problema es material repetido.

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025), primero Elsevier y después MDPI: los ítems A008, A017, A018, A003, A006, A007, A009, A021, A022 y A026 del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una sola columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo el objetivo.

**Tamaño medido.** 14–25–46 párrafos; unas 1010–2210–5900 palabras, el máximo un caso
atípico que genera su propio conjunto de datos; 50–200 palabras por párrafo; 2–4–6
subsecciones; 5–21–35 ecuaciones destacadas; 4–10–28 citas; 0–2–3 figuras, por lo general
la arquitectura.

**Ubicación medida.** Siete de diez no tienen preámbulo. Seis de diez son dueños de su conjunto de datos.
Cada pilar que nombra la introducción recibe su propia subsección prestada, y la propuesta
va al final, con una subsección por contribución en la mitad de ellos. La motivación nunca se
repite; el problema reaparece en una a tres oraciones técnicas, como la brecha de una
pieza prestada justo antes de la propuesta.

**Forma.** La sección se titula *Materials and Methods*. Abre con el conjunto de datos
cuando la sección es su dueña, o con el planteamiento del problema y su notación; sigue la
maquinaria prestada, una subsección por pilar, y luego cada componente de la propuesta
recibe su propia subsección, con su nombre (*The proposed method's architecture*, *Loss
function*), con la combinación general y, para un modelo probabilístico, la
distribución predictiva al final. El entrenamiento y la evaluación son de la configuración experimental.

**Notación.**

- **Los escalares van en cursiva**: minúscula para valores e índices (*x*, *n*, *t*),
  mayúscula para conteos y dimensiones (*N*, *C*, *T*, *K*), cada conteo emparejado con
  su índice en minúscula. Las sumas llevan ambos límites, `\sum_{n=1}^{N}`.
- **Los vectores van en negrita minúscula** (`\mathbf{x}`), **las matrices en negrita mayúscula**
  (`\mathbf{X}`), y **los tensores también en negrita mayúscula**, distinguidos de las matrices por la
  forma con que se declaran (`\mathbf{X} \in \mathbb{R}^{C \times T \times F}`).
  Los vectores y matrices griegos usan `\boldsymbol{}`. Los artículos del grupo se dividen entre
  negrita recta y negrita cursiva; un artículo elige una y nunca las mezcla.
- **Toda variable se declara en su primer uso con su espacio**: *Let*
  `\mathbf{X} \in \mathbb{R}^{C \times T}` *denote …*. Los conjuntos numéricos van en negrita de pizarra
  (`\mathbb{R}`, `\mathbb{N}`), al igual que la esperanza y la divergencia
  (`\mathbb{E}`, `\mathbb{D}_{\mathrm{KL}}`).
- **Las letras caligráficas son para conjuntos, espacios, distribuciones y pérdidas**:
  `\mathcal{D}`, `\mathcal{X}`, `\mathcal{H}`, `\mathcal{N}(\mathbf{0}, \mathbf{I})`,
  `\mathcal{L}`. Un término de pérdida lleva un subíndice recto, `\mathcal{L}_{\mathrm{rec}}`.
- **Los operadores van en redonda**: `\operatorname{tr}`, `\operatorname{diag}`,
  `\operatorname{vec}`, `\operatorname{softmax}`, `\log`, `\exp`. La transpuesta es
  `^{\top}`, nunca un superíndice *T*; producto de Hadamard `\odot`; producto de Kronecker
  `\otimes`; normas `\lVert \cdot \rVert_2`; producto interno
  `\langle \cdot, \cdot \rangle`; un argumento genérico es `(\cdot)`; `\arg\min` y
  `\arg\max` llevan su variable debajo.
- **Parámetros y acentos**: los parámetros aprendibles son `\theta`, con subíndice del
  operador al que pertenecen (`f_{\theta}`); los hiperparámetros son letras griegas declaradas
  con su dominio (`\gamma \geq 0`). Un sombrero marca una estimación o predicción
  (`\hat{y}`), una tilde una cantidad transformada o intermedia
  (`\tilde{\mathbf{Z}}`), una barra una media, un asterisco un óptimo (`\theta^{*}`).
- **Una ecuación es parte de una oración.** La oración que la precede termina en dos puntos o
  en *as*; la ecuación cierra con una coma o un punto; la oración que la sigue abre
  en minúscula con *where* y define cada símbolo nuevo — de uno a cinco por cláusula,
  cerrada con *respectively* cuando se emparejan con una lista.

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para llevar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una vez; los procedimientos que se ejecutaron van en pasiva en pasado (*was evaluated using*).
- **Las transiciones salen de la relación entre afirmaciones, no de una lista.** Primero se nombra la relación (contraste, causa, consecuencia, desarrollo, ejemplo) y se expresa con el propio contenido de la oración: una cláusula (*yet*, *so*, *although*), un sujeto que remite a lo anterior (*that gap*, *this cost*), o ningún conector cuando el orden de las oraciones ya lo dice. Un conector de repertorio (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) es la excepción: nunca el mismo dos veces en cinco oraciones, nunca la mayoría de las aperturas de un párrafo, y un conector de síntesis (*Overall*, *Taken together*) como máximo una vez por sección.
- ***because* y *where* conservan su función.** *because* enuncia una causa que el método o los datos establecen, como máximo una vez cada varias oraciones y nunca encadenado (*because …, and because …*); *where* abre la cláusula que sigue a una ecuación y define sus símbolos, y en ningún otro lugar de la prosa (se usa *in which*, *when* o dos oraciones). Una valoración es una oración propia, no un *, which indicates …* final.
- **El método tiene un solo nombre.** Se desarrolla con su acrónimo en el primer uso tanto en el resumen como en el cuerpo, y después se escribe *the proposed* seguido del acrónimo.
- **Las definiciones van en presente.** *The encoder maps*, *the loss
  penalizes* — el método se describe como es, no como se construyó.
- **Un componente prestado se cita donde se nombra**, justo después de su nombre; las
  ecuaciones propias de la propuesta no llevan cita.
- **Una figura es el sujeto de su oración**: *Figure 2 illustrates the
  architecture*. Nunca es *Fig.*, ni un paréntesis suelto.

## Entradas

Nada aquí espera a un experimento. Pero sí espera a que exista el código.

### Entradas externas

| Entrada | Desbloquea |
|---|---|
| La **formulación matemática** de la propuesta | `mm-borrowed-machinery`, `mm-proposal` |
| El **conjunto de datos** — cuando esta sección es su dueña | `mm-dataset` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `materials-and-methods.mm-proposal` — enunciada como un delta sobre la maquinaria prestada, con una referencia explícita a la ecuación anterior por su número | `materials-and-methods.mm-borrowed-machinery` — la teoría prestada cuyas ecuaciones declaradas referencia la propuesta |
| `materials-and-methods.mm-proposal` — siempre el último bloque de la sección, sin excepción | `materials-and-methods.mm-dataset` — la subsección del conjunto de datos, cuando esta sección es su dueña |
| `materials-and-methods.mm-preamble` — nombra las subsecciones que siguen y su orden | `materials-and-methods.mm-proposal` — la última de las subsecciones que debe nombrar, por lo que el preámbulo se escribe una vez que existe cada subsección que anuncia |

### Decisiones estructurales

- **La lectura correcta de una ecuación ambigua** la decide la
  implementación: lo que el código calcula, no lo que dice la ecuación. Esta
  es una decisión registrada en el propio párrafo del componente afectado, no una
  dependencia de ningún otro bloque.

## Descalificadores

- Un conjunto de datos real cuya explicación no cierra con su diagrama del protocolo de
  adquisición, o cuyo diagrama es solo de cajas, sin pictogramas del dominio.
- Un símbolo usado sin haber sido declarado, o declarado dos veces con significados distintos.
- Dos cantidades distintas que comparten una letra sin un diacrítico que las separe, o un
  diacrítico que no marca ninguna relación con un objeto ya declarado.
- Un símbolo en la combinación general que no se remonta a ninguna declaración previa.
- Que la propuesta no sea el último bloque de la sección, o que sus subsecciones no sean
  consecutivas.
- Una subsección prestada para un pilar que la introducción nunca nombró, o un pilar nombrado
  sin subsección.
- Que la maquinaria pase a la propuesta sin enunciar la brecha de la pieza que la
  propuesta modifica.
- Más de dos oraciones que repitan el problema antes de una contribución, o cualquier
  oración sobre la motivación de la aplicación.
- Una contribución de interpretabilidad nombrada en la introducción cuyo mecanismo no se
  define aquí.
- Un protocolo de evaluación, métrica, línea base, partición o prueba estadística descritos aquí,
  o presentados como contribución.
- Una contribución definida aquí que la introducción no nombró, o nombrada allí y
  no definida aquí.
- Contribuciones en un orden distinto del que les dio la introducción.
- La ausencia del diagrama de síntesis.
- La lista de contribuciones no legible en ninguna de las dos formas (ni una subsección por
  contribución ni una lista ordenada inmediatamente antes del puntero de cierre), o una
  lista escrita cuando las contribuciones ya son subsecciones.
- Un conjunto de datos o una línea base que aparece en el diagrama de síntesis.
- Una contribución definida con un nombre distinto de la propiedad que aporta
  en el planteamiento del problema y en la introducción.
- Un parámetro usado por la configuración experimental que no se nombra en ninguna parte aquí.
- Un artefacto que aparece antes de cualquier referencia a él, o que nada referencia en
  absoluto.
- Un puntero a un artefacto completo cuando el valor está en una de sus partes.
- Un diagrama cuyos componentes difieren en número, orden o nombre de la lista
  de contribuciones.
- Una leyenda que no decodifica lo que la figura codifica.
- Teoría prestada desarrollada más allá de la profundidad con que la propuesta la usa.
- Una ecuación destacada y numerada que ninguna oración referencia nunca, que no define ninguna
  contribución y que no es la combinación general.
- Una subsección matemática que abre con una ecuación en lugar de con notación.
- Una ecuación referenciada por número en la oración inmediatamente posterior a su propia
  presentación, o referenciada dos veces por número dentro de un mismo párrafo.
- Una ecuación ambigua que queda con ambas lecturas abiertas.
- Un tamaño de lote, una tasa de aprendizaje, un calendario o un detalle de hardware enunciado aquí.
- Un argumento de convergencia trasladado a la configuración experimental.
- Una cita en una ecuación de la propuesta.
- Una definición prestada cuya oración de anuncio no lleva cita.
- Un conjunto de datos descrito aquí y dejado sin referencia.
- Un párrafo que vuelve a motivar el problema.
- Un resultado, un número medido o una comparación.
- Un vector, una matriz o un tensor compuesto sin negrita, o dos estilos de negrita mezclados en la sección.
- Una variable usada antes de declarar su espacio y sus dimensiones.
- Una ecuación destacada sin número, o una referida como *Eq.* en lugar de *Equation (n)*.
- Una transpuesta escrita como superíndice *T* en lugar de `^{\top}`.
