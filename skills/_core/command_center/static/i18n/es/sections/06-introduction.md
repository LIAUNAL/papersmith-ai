---
{
  "section": "introduction",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/06-introduction.md",
      "quote": "Seis funciones argumentativas, en orden fijo, distribuidas en 7–13 párrafos."
    }
  },
  "blocks": [
    {
      "id": "block-1",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "El conjunto de datos — la condición, población o proceso que contiene"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery"
    },
    {
      "id": "block-2",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "este bloque se deriva de las contribuciones, leídas en sentido inverso"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Convertir la necesidad general en un problema técnico concreto, y descomponerlo en los problemas específicos que la propuesta resuelve."
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "este bloque se deriva de las contribuciones, leídas en sentido inverso"
          }
        }
      ]
    },
    {
      "id": "block-3",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Bloque 3 — estado del arte y brecha depende del planteamiento del problema cuando no hay sección de Trabajos Relacionados"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "El cierre es la brecha conjunta, y la conjunción es lo que la convierte en brecha."
          }
        }
      ],
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Bloque 3 — estado del arte y brecha depende del planteamiento del problema cuando no hay sección de Trabajos Relacionados"
          }
        },
        {
          "target": "related-work",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Cuando existe una sección de Trabajos Relacionados, este bloque se redacta después de ella."
          }
        }
      ]
    },
    {
      "id": "block-4a",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "la idea central proviene de la sección de métodos, donde la propuesta se define y se nombra"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "la presentación y la cláusula de propósito provienen del bloque 2 — la cláusula refleja sus problemas específicos, en el mismo orden"
          }
        },
        {
          "target": "introduction.block-4b",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "el anuncio del conteo proviene de `introduction.block-4b`, en su forma parcial."
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "la idea central proviene de la sección de métodos, donde la propuesta se define y se nombra"
          }
        }
      ]
    },
    {
      "id": "block-4b",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Los resultados"
          }
        },
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Se hereda, nunca es un objetivo de redacción."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Se hereda, nunca es un objetivo de redacción."
          }
        }
      ]
    },
    {
      "id": "block-5",
      "requires_facts": [
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "El diseño experimental — escenarios, comparaciones, criterios, análisis complementarios"
          }
        },
        {
          "value": "results",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Los resultados"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "block-6",
      "requires_facts": [
        {
          "value": "skeleton",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "El esqueleto de secciones del manuscrito"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---
# Introducción

**Extensión** 900–1650 palabras · 7–13 párrafos
**No incluye** ecuaciones, figuras ni tablas
**Incluye** 18–41 referencias distintas, concentradas en los bloques 1 a 3

## Regla estructural global

Seis **funciones argumentativas**, en orden fijo, distribuidas en 7–13 párrafos.
Función y párrafo no son la misma unidad: los bloques 2 y 3 se expanden.

1. por qué importa el tema
2. qué problemas concretos deben resolverse
3. las soluciones existentes los resuelven solo en parte
4. una propuesta cuyas contribuciones responden a esos problemas
5. cómo se valida cada propiedad prometida
6. cómo se organiza el resto del artículo

**Correspondencia buscada:** `problem i → state-of-the-art limitation i →
contribution i → property i → instrument i → evidence i`. La cadena comienza en el
problema, no en la contribución: una contribución que entrega una propiedad que ningún
problema declarado necesitaba no tiene nada que la motive.

**La propiedad lleva el mismo nombre en cada eslabón** — no un sinónimo, las mismas
palabras. Si el problema se nombra de una manera en el bloque 2, la contribución entrega eso,
el bloque 5 nombra el instrumento para eso, y el bloque de resultados trata sobre eso. Sin
el nombre compartido, la cadena es interpretable en lugar de verificable.

El requisito es la mitad fuerte: ningún problema enunciado queda sin respuesta, y
ninguna propiedad declarada queda sin una forma identificable de evaluación. Un problema
puede responderse mediante **un componente de la propuesta o mediante un análisis en la
evaluación** — no necesariamente mediante un componente. La correspondencia uno a uno es una
preferencia, no un requisito.

## Insumos por bloque

No hay un orden entre estos bloques — hay un grafo. Cada bloque se redacta tan
pronto como existe su insumo. **Dos bloques admiten una forma parcial**: se escriben a partir
del diseño y se completan a partir de la medición.

### Insumos externos

| Insumo | Desbloquea |
|---|---|
| El **conjunto de datos** — la condición, población o proceso que contiene | 1 |
| El **esqueleto de secciones** del manuscrito | 6 |
| El **diseño experimental** — escenarios, comparaciones, criterios, análisis complementarios | 5 parcial |
| Los **resultados** | 4b completo, 5 completo |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `introduction.block-2` — el problema general y los específicos | `materials-and-methods.mm-proposal` — cada contribución se lee en sentido inverso como la deficiencia que resuelve, nombrada con el vocabulario aceptado del campo |
| `introduction.block-3` — estado del arte y brecha, dependiente del planteamiento del problema | `introduction.block-2` — el planteamiento del problema, general y específico, descompuesto allí |
| `introduction.block-4a` — la prosa de presentación | `introduction.block-2` — la presentación y la cláusula de propósito, que reflejan sus problemas específicos en el mismo orden |
| `introduction.block-4a` — la prosa de presentación | `introduction.block-4b` — el anuncio del conteo, enunciado antes de que la lista lo enumere |
| `introduction.block-4a` — la prosa de presentación | `materials-and-methods.mm-proposal` — la sección que define y nombra la propuesta, de la cual se extrae la idea central |
| `introduction.block-4b` — la lista de contribuciones, heredada en lugar de redactada | `materials-and-methods.mm-proposal` — la sección que define y nombra cada contribución |

### Decisiones estructurales

- **Bloque 3 — estado del arte y brecha** depende del planteamiento del problema
  cuando no hay sección de Trabajos Relacionados — su propia arista `after` hacia
  `introduction.block-2` lo expresa ahora que `problem-statement` es un
  hecho de clase producida — **y** del planteamiento del problema **y de la
  sección de Trabajos Relacionados ya escrita** cuando existe una sección de Trabajos
  Relacionados — el caso condicional entre secciones que expresa la segunda arista
  `after` de este mismo bloque hacia `related-work`.
- **`introduction.block-4a` / `block-4b` son dos bloques, no uno.** La
  propia línea de extensión del contrato lo dice — "Dos párrafos físicos, 120-180
  palabras en total" — y los nombra `Paragraph 4a - the prose` y
  `Paragraph 4b - the list`. Son ids separados porque se redactan
  a partir de insumos distintos: la cláusula de propósito de 4a depende del bloque 2, mientras que la
  lista de contribuciones de 4b se hereda directamente de
  `materials-and-methods.mm-proposal`, nunca del bloque 2. El propio 4a también
  depende de 4b, por el conteo anunciado. Fusionarlos en un solo nodo
  confundiría un bloque que necesita el planteamiento del problema con uno que
  no lo necesita.
- **Partes compuestas dentro de `introduction.block-4b`** (decisión adoptada 5):
  la forma completa de 4b — el efecto que logra cada contribución — se redacta
  después de su forma parcial, una vez que llegan los resultados. Es una nota de secuencia de redacción
  dentro de un nodo, nunca una dependencia de un bloque hermano.
- **Partes compuestas dentro de `introduction.block-5`**: la forma completa de 5 — la
  oración de evidencia — se redacta después de la forma parcial de 5, una vez que llegan los resultados.
  Es la misma secuencia interna del nodo que en el bloque 4, nunca una dependencia de un
  bloque hermano.

**El bloque 4a se nutre de tres fuentes, una por oración:**

- la **presentación y la cláusula de propósito** provienen del bloque 2 — la cláusula refleja
  sus problemas específicos, en el mismo orden;
- la **idea central** proviene de la sección de métodos, donde la propuesta se define y se nombra;
- el **anuncio del conteo** proviene de `introduction.block-4b`, en su forma parcial.

### Qué puede escribirse antes de medir

Con la propuesta formulada y el conjunto de datos elegido, antes de que se haya ejecutado un solo
experimento, los bloques **1, 2, 3, 4a, 4b en forma parcial, y 6** pueden redactarse. Con el
diseño experimental establecido, se agrega **5 en forma parcial**.

Los resultados aportan solo el cierre de dos bloques que ya están escritos: el
efecto logrado por cada contribución y la oración de evidencia. La introducción se
construye por completo antes de medir; la medición la completa, no la origina.

### El ciclo que debe cerrarse a mano

**Los resultados mandan.** Pueden contradecir el efecto que prometió una contribución, y
cuando lo hacen, el texto se corrige para ajustarse a ellos — nunca al revés.

La corrección no se detiene en 4b. El bloque 2 se derivó de esa contribución, y
el bloque 3 del bloque 2. Al completar 4b, recorra la cadena en sentido inverso y verifique que
cada problema enunciado todavía tenga respuesta y que ninguna contribución quede sin un
problema que la motive. Este es el único punto de la sección donde la medición puede
invalidar lo que ya está escrito.

En la práctica, la mayor parte de la cadena sobrevive, y por eso vale la pena seguir el grafo
en lugar de esperar: un efecto contradicho suele revisar un elemento y una cláusula,
no el argumento.

## Bloque 1 — Contextualización

**Función.** Introducir el dominio de aplicación y el fenómeno que motiva el
trabajo, su relevancia y la necesidad general que justifica estudiarlo.

**Secuencia.** dominio → fenómeno de interés → relevancia → necesidad general.

**Extensión.** Un párrafo, 145–200 palabras. Se admite un segundo solo bajo la
condición indicada más abajo. Nunca tres.

**El fenómeno lo fijan los datos, no el método.** Ancle el contexto en la
condición, población o proceso que el conjunto de datos realmente contiene. Cambiar el
conjunto de datos reescribe este párrafo por completo aun cuando el método sea idéntico: enuncie
el dominio, el fenómeno y la relevancia sobre lo que se midió, no sobre la familia de
técnicas empleadas. Un contexto escrito sobre el método deja al lector sin
saber de qué trata el trabajo.

**No nombre aquí el conjunto de datos.** Lo que ancla el contexto es la condición,
población o proceso, no el nombre del conjunto de datos — el nombre pertenece al bloque 5.

**Cuándo se divide en dos.** El párrafo debe recorrer las cuatro dimensiones y cerrar
conduciendo hacia el problema técnico. Divídalo solo cuando el paso del dominio amplio
al escenario específico requiera un cambio explícito de escala — del campo general a
la población, institución o territorio concretos del estudio — y forzarlo en
un solo párrafo produzca una oración de transición artificial. Fuera de ese caso, uno.

**No pertenece aquí.** La propuesta, su nombre, sus componentes, sus contribuciones
ni ningún detalle experimental.

## Bloque 2 — Planteamiento del problema

**Función.** Convertir la necesidad general en un problema técnico concreto, y descomponerlo
en los problemas específicos que la propuesta resuelve.

**Secuencia.** problema general → específico 1 → específico 2 → [específico 3] →
requisitos que una solución adecuada debería satisfacer.

**Extensión.** 1–3 párrafos, 130–365 palabras.

**Anide los problemas: uno general que nombra el paradigma, y los específicos dentro
de él.** El problema general es el nombre del campo o de la tarea, no una dificultad; los
específicos son las dificultades. Enuncie primero el general, reconociendo que
solo está parcialmente resuelto, y abra la enumeración solo después de eso.

**Nombre los problemas con la terminología aceptada del estado del arte.** Esto
no es cosmético: el nombre de cada problema es la clave de búsqueda con la que el bloque 3 encontrará
su literatura. Un problema descrito con vocabulario propio en lugar del vocabulario del campo no tiene
ninguna familia metodológica que lo aborde, y el bloque 3 se queda sin nada que encadenar.

**Cada problema específico corresponde a una capacidad que la propuesta incorpora** —
por lo cual este bloque se deriva de las contribuciones, leídas en sentido inverso. No introduzca
ninguna dificultad que el trabajo no vaya a abordar.

**Cierre consolidando los requisitos** que una solución adecuada debería satisfacer. Ese
cierre es lo que habilita la brecha en el bloque 3, y sus términos son los ejes que la evaluación
medirá: enúncielos con las mismas palabras que el bloque 5 usará más adelante.

**Conteo.** Dos o tres problemas específicos.

## Bloque 3 — Estado del arte y brecha

**Función.** Presentar las familias de métodos que han abordado los problemas del
bloque 2, organizadas **en torno a esos problemas y no como una enumeración de trabajos o
autores**.

**Por familia:** qué problema aborda → qué ventaja aporta → qué
limitación conserva.
**En conjunto:** soluciones existentes → avances → limitaciones → brecha conjunta.

**La extensión depende de si el artículo tiene su propia sección de Trabajos Relacionados.** Esa
es una decisión sobre la estructura del manuscrito, y se toma antes de redactar
el bloque.

**El principio organizador es el mismo en ambos casos: una unidad por problema enunciado.** Lo que
difiere es de qué está hecha la unidad — un párrafo aquí, un bloque de párrafos en la
sección dedicada.

**Con una sección de Trabajos Relacionados — un solo párrafo, 230–380 palabras.** Este párrafo es
el resumen de esa sección. Por problema, una o dos oraciones: la familia cuya
limitación motiva la contribución, y esa limitación. Las variantes y las estrategias
alternativas no se nombran aquí — viven en la sección. El párrafo cierra con la
brecha conjunta.

**Cuando existe una sección de Trabajos Relacionados, este bloque se redacta después de ella.** Resume
la sección, y un resumen no puede preceder a lo que resume. Sin esa sección,
el bloque depende solo del planteamiento del problema.

**El corte entre los dos lugares:** este bloque conserva, por problema, la familia cuya
limitación motiva la contribución. Todo lo demás que atacó ese mismo
problema es una variante, y pertenece a la sección dedicada.

**Sin una sección de Trabajos Relacionados — un párrafo por problema enunciado, 130–300 palabras
cada uno, 550–990 palabras en total.** Cada problema recibe su propio párrafo, que recorre
las familias que lo han atacado en progresión y termina en lo que ninguna de ellas
resolvió. Desarrolle la nomenclatura de cada método en su primera aparición. Organizar por
problema y no cronológicamente es lo que hace explícita la correspondencia con el bloque 2.

**Dos aclaraciones, para que nada se agregue aquí por analogía con la sección
dedicada.** No se agrega a la introducción ningún párrafo panorámico: los bloques 1 y 2 ya
hacen ese trabajo, y duplicarlo es ruido. Y las formas cronológica y taxonómica
de recorrer un problema no aplican donde la unidad es un párrafo — aquí hay una
familia y su limitación, sin taxonomía que desplegar.

**La progresión se encadena.** Cada párrafo, y cada familia dentro de un párrafo,
parte de la limitación de la anterior, y ese encadenamiento es explícito en la
oración inicial: la nueva familia aparece *porque* la anterior falló en
algo nombrado. Una enumeración cronológica que no encadena limitaciones no es un
estado del arte — es una lista.

**El cierre es la brecha conjunta, y la conjunción es lo que la convierte en brecha.** No
basta con decir que cada familia tiene limitaciones: establezca que las soluciones existentes
resuelven los problemas **por separado y no simultáneamente**, y por lo tanto no
satisfacen conjuntamente los requisitos enunciados al final del bloque 2. La palabra que expresa
esa simultaneidad debe estar presente.

**Cuando existe una sección de Trabajos Relacionados, esta brecha y la brecha de cierre de esa sección dicen
lo mismo con distinta profundidad.** Son una sola afirmación enunciada dos veces, y deben
concordar.

**Excepción de orden.** El bloque puede dividirse, adelantando una mitad antes del bloque 2,
cuando el problema no puede enunciarse sin presentar primero la tecnología habilitadora.
En ese caso el orden es: habilitador → problema → familias.

## Bloque 4 — Propuesta y contribuciones (`block-4a`, `block-4b`)

**Función.** Presentar el método por nombre y propósito, la idea central que articula sus
componentes, y enumerar las contribuciones.

**Secuencia.** presentación → objetivo general → idea central → contribución 1 → 2 → …

**Extensión. Dos párrafos físicos, 120–180 palabras en total.**

### Párrafo 4a — la prosa. Tres movimientos, dos o tres oraciones.

1. **Presentación y objetivo.** Nombre completo, acrónimo entre paréntesis, la categoría del
   artefacto, y una cláusula de propósito **que refleja los problemas específicos del bloque 2 en
   el mismo orden**. El verbo va en primera persona del plural y aparece **exactamente una vez en
   toda la introducción**: todo lo anterior es trabajo de otros.
2. **La idea central.** Una oración, un mecanismo, sin matemáticas y sin
   símbolos. Es lo que hace nueva a la propuesta, no lo que hace.
3. **El anuncio.** Cierre el párrafo enunciando el número de componentes y
   terminando en dos puntos, que es lo que abre la lista. Anuncie el conteo antes de
   enumerarlo, siempre.

### Párrafo 4b — la lista.

**El número de elementos es el número de contribuciones que tiene la propuesta.** Se hereda, nunca es un objetivo de redacción. Lo que la redacción exige es solo que el conteo se
anuncie en 4a antes de enumerarse aquí, y que la lista concuerde en número,
orden y denominación con los componentes de la sección de métodos.

Abra cada elemento con **el nombre del componente seguido de dos puntos**, y continúe
con una sola oración que indique qué hace y qué problema enunciado previamente
resuelve. Esos nombres son el contrato propio de la sección de métodos — esta lista usa los
mismos, en el mismo orden.

No abra los elementos con un verbo en primera persona en lugar del nombre de un componente: sin un
nombre, no es posible volver a referirse al componente más adelante.

**La cláusula del efecto logrado es la parte que espera los resultados.** Lo que cada
contribución introduce y qué función cumple provienen de la formulación; el
efecto que se afirma que logra proviene de la medición.

**Una sola cita, en 4a.** El párrafo 4a puede citar el trabajo previo que la propuesta extiende, adherida a él; desde 4b hasta el final de la introducción, no cite nada.

## Bloque 5 — Evaluación de la propuesta

**Función.** Resumir cómo se valida la propuesta, en correspondencia directa con
las contribuciones enunciadas.

**Secuencia.** escenario de evaluación → datos o tareas → métodos de comparación → criterios o
métricas → análisis complementarios → evidencia general.

**Extensión.** Un párrafo, 65–135 palabras.

**Nombre todo por su nombre propio:** los conjuntos de datos, los métodos con los que se compara,
y los ejes sobre los que se barre la comparación. Nombre también los análisis complementarios,
porque son los que responden a las propiedades que ninguna contribución cubre — típicamente las
que no tratan sobre el desempeño.

**Nombrar aquí un conjunto de datos no le otorga crédito.** Ninguna cita aparece en este bloque. Un
conjunto de datos externo conlleva una obligación de crédito, y esta se cumple donde se describe el conjunto de datos
— en la subsección de conjuntos de datos — con su referencia allí. Nombrarlo aquí
sin referencia es correcto; dejarlo sin referencia donde se describe no lo es.

**Cada propiedad declarada en el bloque 4 debe tener aquí su forma identificable de evaluación.** Desempeño, robustez, interpretabilidad, estabilidad, eficiencia, coherencia,
generalización: si se prometió, se evalúa, y aquí es donde se nombra el instrumento
— **con el mismo nombre que le dieron el problema y la contribución**.

**Los primeros cinco movimientos provienen del diseño experimental; solo el cierre proviene
de los resultados.** Escenario, datos, comparaciones, criterios y análisis complementarios
pueden decidirse antes de ejecutar nada.

**Cierre con evidencia, no con valores.** Enuncie la dirección del resultado y los ejes
en los que mejora, sin citar ninguna cifra, porcentaje ni tabla. Los números
pertenecen a la sección de resultados.

## Bloque 6 — Organización del artículo

**Función.** Orientar al lector sobre la estructura. Nada más.

**Extensión.** Un párrafo, 32–42 palabras.

Es una fórmula fija:

`The remainder of this paper is organized as follows: Section [N] [verb] the [content]. … Finally, Section [N] [verb] the concluding remarks.`

- Una cláusula por sección, en orden.
- Cada sección aparece en exactamente una cláusula. Secciones adyacentes con una función
  relacionada pueden compartir una.
- El verbo varía según la sección (`introduces`, `presents`, `describes`, `reviews`,
  `details`, `discusses`).
- La cláusula final abre con `Finally,` o `Lastly,`.

**No introduzca ningún argumento, problema, contribución, método ni resultado nuevo.**

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025): ítems A003, A006, A007, A009, A012, A013, A021, A022, A023 y A026 del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo la meta.

**Tamaño medido.** 7–9–15 párrafos; 850–1166–1604 palabras, unas 73–102–139 líneas;
105–123–178 palabras por párrafo; sin subsecciones, ecuaciones, figuras ni tablas;
23–27–45 citas, 1,7–4,2 por párrafo.

**Los movimientos que hacen las introducciones del grupo**, diez de diez: lo que está en
juego en la aplicación, a menudo anclado en un objetivo de salud pública o social; las
dificultades de los datos; las familias de métodos previos, cada una cerrada por una oración
que abre con *However* y nombra su limitación; la brecha conjunta; la propuesta, introducida
por la bisagra *To address these limitations, this work introduces* seguida del nombre
completo y el acrónimo entre paréntesis; las contribuciones, como una lista anunciada por
*The main contributions of this work are as follows:*; y la hoja de ruta de cierre, *The
remainder of this paper is organized as follows:*.

**Citas.** Numéricas, entre corchetes. La mayoría de los marcadores cita una sola obra; un
grupo cita a lo sumo cuatro, enumeradas con comas (`[31,32,33,34]`), nunca como rango. Una
cita cierra la oración que respalda, o sigue al nombre del método al que da crédito; nunca
es el sujeto de una oración.

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para portar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una sola vez; los procedimientos que se ejecutaron van en voz pasiva y en pasado (*was evaluated using*).
- **Conectores que usa el grupo** para pasar de una afirmación a otra: *However*, *Specifically*, *In particular*, *Moreover*, *Notably*, *Overall*. Cada uno abre una oración y cumple una sola función: contraste, acotación, adición, énfasis, síntesis.
- **El método tiene un solo nombre.** Se desarrolla junto con su acrónimo en su primera aparición, tanto en el resumen como en el cuerpo, y en adelante se usa *the proposed* seguido del acrónimo.
- **Presente y pretérito perfecto.** El campo *has addressed*; el problema *remains*.
- **La novedad se afirma por contraste, no por prioridad.** *Unlike previous approaches,
  the proposed …*; la afirmación de ser el primero aparece solo cuando se buscó
  expresamente en el estado del arte.

## Convenciones transversales

- **Ubique la cita al final de la oración que respalda.** Una oración, una
  afirmación atribuida. Una oración que necesitaría dos citas son dos oraciones.
  Agrupe los rangos.
- **No use la cita como frase nominal** — *el trabajo en [N] hace X*, *el
  método de [N] combina*. Convierte el argumento en un catálogo de trabajos individuales
  en lugar de un recuento de familias.
- **Densidad:** una cita cada una o dos oraciones en los bloques 1 a 3; **ninguna
  cita a partir del bloque 4, salvo el trabajo previo que extiende 4a**.
- **Toda afirmación sobre el campo lleva una cita.** Las afirmaciones sobre la
  propia propuesta no llevan ninguna.
- **Desarrolle los acrónimos en su primera aparición**, y en adelante use solo el acrónimo — incluido
  el de la propia propuesta.
- **Enuncie el conteo antes de enumerar**, en cualquier bloque que enumere.
- **Ninguna ecuación, figura ni tabla en ninguna parte de la sección.**

## Descalificadores

- Una ecuación, una figura o una tabla.
- Un contexto escrito sobre la familia de métodos en lugar del fenómeno que contiene el conjunto
  de datos.
- El conjunto de datos nombrado en el bloque 1.
- Un conjunto de datos nombrado en el bloque 5 y dejado sin referencia donde se describe.
- Tres párrafos de contextualización.
- Un problema específico al que no responde ni un componente de la propuesta ni un análisis
  en la evaluación.
- Un problema nombrado con vocabulario propio en lugar de la terminología aceptada del
  campo.
- El bloque 2 sin su enunciado de cierre de requisitos.
- Un párrafo del bloque 3 que no termina en una limitación.
- El bloque 3 sin un cierre de brecha conjunta, o con una brecha enunciada como suma de
  limitaciones separadas.
- La brecha de este bloque y la brecha de cierre de la sección de Trabajos Relacionados en desacuerdo.
- El bloque 3 con más de aproximadamente 400 palabras cuando existe una sección de Trabajos Relacionados, o con menos de
  aproximadamente 500 cuando no existe.
- Una variante o estrategia alternativa nombrada en el bloque 3 cuando existe una sección de Trabajos
  Relacionados: estas pertenecen a esa sección.
- El bloque 3 escrito como resumen de una sección de Trabajos Relacionados que todavía no existe.
- Un párrafo panorámico agregado a la introducción.
- El conteo anunciado en 4a que no coincide con el número de elementos de 4b.
- La lista de 4b que difiere en número, orden o denominación de los componentes de la
  sección de métodos.
- Una contribución que no está motivada por ningún problema del bloque 2.
- Una propiedad declarada en el bloque 4 sin una evaluación nombrada en el bloque 5.
- Una propiedad nombrada de manera distinta en los bloques 2, 4 y 5 — un sinónimo en lugar de las mismas
  palabras.
- Una cifra, porcentaje o valor en el bloque 5.
- Una cita en cualquier parte a partir del bloque 4, distinta de la cita de 4a al trabajo previo que la propuesta extiende.
- Una cita ubicada en cualquier lugar que no sea el final de la oración que respalda.
- Una cita usada como frase nominal.
- El bloque 6 ausente, o que nombra secciones que no existen, o que repite una.
- Un 4b completado cuyos efectos logrados no se verificaron de vuelta contra el bloque 2 y,
  a través de él, contra el bloque 3.
