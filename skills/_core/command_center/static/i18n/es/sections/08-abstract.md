---
{
  "section": "abstract",
  "position": 2,
  "after": [
    {
      "target": "conclusions",
      "source": {
        "file": "sections/07-conclusions.md",
        "quote": "El resumen se escribe después de esta sección, porque la comprime."
      }
    }
  ],
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/08-abstract.md",
      "quote": "Cada oración aquí comprime algo que el artículo ya establece, y nada en ella alcanza más allá de este trabajo."
    }
  },
  "blocks": [
    {
      "id": "slot-1",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "El conjunto de datos — la condición, población o proceso que contiene"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-2",
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
      "citations": "none",
      "after": [
        {
          "target": "abstract.slot-4",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "este bloque se deriva de las contribuciones, leídas en sentido inverso"
          }
        },
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
      "id": "slot-3",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "La formulación matemática llega al resumen ya traspuesta, como las contribuciones enumeradas propias de la sección de métodos, nunca desde el documento de propuestas"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "abstract.slot-2",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "La cláusula de propósito refleja las deficiencias de la posición 2, en el mismo orden."
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "La formulación matemática llega al resumen ya traspuesta, como las contribuciones enumeradas propias de la sección de métodos, nunca desde el documento de propuestas"
          }
        }
      ]
    },
    {
      "id": "slot-4",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "La formulación matemática llega al resumen ya traspuesta, como las contribuciones enumeradas propias de la sección de métodos, nunca desde el documento de propuestas"
          }
        },
        {
          "value": "results",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "Los resultados"
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "La formulación matemática llega al resumen ya traspuesta, como las contribuciones enumeradas propias de la sección de métodos, nunca desde el documento de propuestas"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-5",
      "requires_facts": [
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "El diseño experimental"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-6",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "Los resultados"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-7",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "Los resultados"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---
# Resumen

**Extensión** 216–280 palabras · 7–14 oraciones · **un solo párrafo**
**No contiene** citas, ecuaciones, figuras, tablas ni referencias a secciones
**Unidad de composición** la oración, no el párrafo

El resumen es todo el argumento a una quincuagésima parte de su escala, y para la mayoría de los lectores es
el artículo completo. Debe ser autocontenido: ninguna referencia hacia adelante, ningún acrónimo
sin definir, nada que solo tenga sentido después de seguir leyendo. Cada oración aquí
comprime algo que el artículo ya establece, y nada en ella alcanza
más allá de este trabajo.

## Regla estructural global

Siete **posiciones funcionales**, en orden fijo. Posición y oración no son la misma unidad:
cinco de las siete se expanden. La forma más corta es una oración por posición; la más larga
expande las posiciones 1, 2, 4, 5 y 6 hasta llegar a catorce.

| Posición | Función | Oraciones | Palabras por oración |
|---|---|---|---|
| 1 | Contexto | 1–2 | 9–31 |
| 2 | Problema | 1–2 | 15–29 |
| 3 | **La propuesta, nombrada** | **1, siempre** | 15–34 |
| 4 | Anuncio y componentes | 1 en línea, o 1 + N | 49–85 en línea |
| 5 | Validación | 1–4 | 14–35 |
| 6 | Resultado o contribución secundaria | 1–2 | 16–31 |
| 7 | **Veredicto** | **1, siempre, y al final** | 11–28 |

Dos posiciones nunca se expanden ni se mueven: la propuesta ocupa exactamente una oración,
y el veredicto ocupa exactamente una oración y es la última del resumen.

La posición de componentes es la oración más larga — o el bloque más largo — del resumen.
Es el único lugar donde la oración se alarga deliberadamente; en todo lo demás,
comprima.

## Lo que el resumen omite

El resumen lleva el mismo argumento que la introducción, menos dos de sus bloques:

- **El estado del arte no tiene posición.** Sobrevive como media cláusula dentro de
  la posición 2, en la forma *los métodos existentes tienen dificultades para …*. Nada más: no se nombra
  ninguna familia, no se recorre ningún linaje.
- **La organización del artículo nunca aparece.** No se nombra ni se
  referencia ninguna sección.

## Insumos por posición

No hay un orden entre las posiciones — hay un grafo, el mismo que gobierna la
introducción. Cuatro de las siete se pueden redactar antes de medir nada.

### Insumos externos

| Insumo | Desbloquea |
|---|---|
| El **conjunto de datos** — la condición, población o proceso que contiene | `slot-1` |
| El **diseño experimental** | `slot-5` |
| Los **resultados** | `slot-4` (la cláusula del efecto logrado), `slot-6`, `slot-7` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `abstract.slot-2` — Problema | `abstract.slot-4` — cada componente leído al revés como la deficiencia que resuelve |
| `abstract.slot-2` — Problema | `materials-and-methods.mm-proposal` — este bloque se deriva de las contribuciones, leídas en sentido inverso |
| `abstract.slot-3` — Propuesta | `abstract.slot-2` — para la cláusula de propósito |
| `abstract.slot-3` — Propuesta | `materials-and-methods.mm-proposal` — La formulación matemática llega al resumen ya traspuesta, como las contribuciones enumeradas propias de la sección de métodos, nunca desde el documento de propuestas |
| `abstract.slot-4` — Anuncio y componentes | `materials-and-methods.mm-proposal` — La formulación matemática llega al resumen ya traspuesta, como las contribuciones enumeradas propias de la sección de métodos, nunca desde el documento de propuestas |

La formulación matemática llega al resumen ya traspuesta, como las contribuciones enumeradas propias de la sección de métodos, nunca desde el documento de propuestas.

El resumen está más bloqueado por la medición que la introducción: las posiciones 6 y 7 necesitan
los resultados completos, la posición 4 los necesita para la mitad de cada elemento, y no hay
equivalente de los bloques de estado del arte u organización de la introducción que se puedan escribir
temprano. Cuando los resultados cambian, esta sección se corrige para que coincida con ellos.

## Posición 1 — Contexto

Una o dos oraciones. Enuncie el campo y el fenómeno que motiva el trabajo, y
por qué fallar allí es costoso.

Áncrelo en la condición, población o proceso que contiene el conjunto de datos, no en la
familia de técnicas empleadas — la misma regla que gobierna el bloque de apertura de la
introducción. Una sola oración basta cuando el dominio es de conocimiento común; un dominio
técnico necesita dos, una para situar el campo y otra para acotar al escenario específico.

## Posición 2 — Problema

Una o dos oraciones. Abra con un adversativo — la brecha se enuncia contra el
contexto, no junto a él.

Nombre la carencia específica, nunca "persisten desafíos". Se usan dos oraciones cuando
hay dos deficiencias distintas, una por oración. El estado del arte se
absorbe aquí como una sola cláusula que atribuye la carencia a los métodos existentes.

Cuando los problemas deben satisfacerse en conjunto, dígalo en esta posición: la palabra que expresa
esa simultaneidad es lo que convierte dos limitaciones en una sola brecha.

## Posición 3 — La propuesta, nombrada

**Exactamente una oración.** Nunca dividida, nunca movida.

Lleva cuatro cosas: el nombre completo, el acrónimo entre paréntesis, la categoría del
artefacto y el único mecanismo que lo hace nuevo. La cláusula de propósito refleja las deficiencias de la posición 2, en el mismo orden.

El verbo en primera persona que introduce la propuesta aparece exactamente una vez en todo el
resumen. Todo lo anterior a esta oración pertenece al trabajo de otros.

## Posición 4 — Anuncio y componentes

**El número de elementos es el número de contribuciones que tiene la propuesta.** Es
heredado, nunca una meta de redacción. Anuncie la cantidad antes de enumerarla.

Hay dos formas disponibles. Elija una y manténgala — nunca las mezcle.

**En línea.** Anuncio y lista en una sola oración, con el anuncio terminado en
dos puntos, enumeradores romanos, punto y coma entre elementos. Una oración de 49 a 85 palabras.
Compresión máxima.

**Expandida.** El anuncio se convierte en su propia oración breve, terminada en punto, y
cada componente recibe una oración propia que abre con un ordinal. Más legible, y
hace que cada componente sea citable por sí solo.

Cada elemento enuncia qué es el componente y qué función cumple. La cláusula
que afirma un efecto logrado es la parte que espera los resultados.

No abra un elemento con un verbo en primera persona en lugar del nombre del componente.

## Posición 5 — Validación

De una a cuatro oraciones, en este orden: escenario, datos o tareas, métodos con los que se
compara, criterios o métricas, análisis complementarios.

Nombre todo por su nombre propio. Cuando la posición se expande, cada uno de esos elementos
ocupa su propia oración, en ese orden — el escenario nunca se enuncia después del
resultado.

Toda propiedad que la propuesta afirma debe tener su instrumento nombrado aquí.

## Posición 6 — Resultado o contribución secundaria

Una o dos oraciones. Aquí es donde llega la contribución secundaria — la propiedad
que ningún componente entrega y que, en cambio, responde un análisis, típicamente la
que no trata sobre el desempeño.

### Aquí se permiten cifras, bajo tres condiciones

Una cifra se admite solo cuando la cifra **es** el hecho que se enmarca. Este es el
único lugar del artículo donde aparece un número fuera de la sección de resultados, y
existe porque el resumen se lee por sí solo: un resultado que debe enmarcarse no tiene
otro lugar donde llegar. La introducción nunca lleva uno.

1. **Es un permiso, no una convención.** Si el resumen funciona con comparativos,
   se queda en comparativos. Una cifra no es decoración para el veredicto.
2. **La cifra enuncia a qué pertenece, en la misma oración.** Si el número
   caracteriza un componente base y no la contribución, dígalo explícitamente.
   Sin esa cláusula el resumen se atribuye un mérito que no le es propio.
3. **La unidad es un hecho enmarcado, no un número.** Un solo hecho puede necesitar dos valores
   para enunciarse; eso es uno, no dos.

Una cifra citada aquí queda vinculada a la sección de resultados y debe coincidir exactamente con ella.

## Posición 7 — Veredicto

**Exactamente una oración, la última, y de las más cortas.** De 11 a 28 palabras.

Enuncia la dirección del resultado y nombra los ejes en los que el trabajo mejora
— los mismos ejes enunciados como requisitos en la posición 2. Abre con un adverbial sumativo
o una fórmula de confirmación.

No introduce nada: ninguna propiedad nueva, ningún número nuevo, ninguna afirmación nueva.

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025): ítems A003, A006, A007, A009, A012, A013, A021, A022, A023 y A026 del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo la meta.

**Tamaño medido.** Un párrafo de 139–236–311 palabras, sin encabezados.

**Los movimientos, en orden:** contexto; el desafío, abierto por *However* o *Yet*; la
limitación de los métodos existentes; la propuesta, introducida por *To address …, we propose*
o *This work introduces* con el nombre completo y el acrónimo; el mecanismo en dos a
cuatro oraciones, con sus componentes a menudo numerados (i)–(iv); los datos y el protocolo; el
resultado comparativo; y una implicación de cierre (*These results support …*).

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para portar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una sola vez; los procedimientos que se ejecutaron van en voz pasiva y en pasado (*was evaluated using*).
- **Las transiciones salen de la relación entre afirmaciones, no de una lista.** Primero se nombra la relación (contraste, causa, consecuencia, desarrollo, ejemplo) y se expresa con el propio contenido de la oración: una cláusula (*yet*, *so*, *although*), un sujeto que remite a lo anterior (*that gap*, *this cost*), o ningún conector cuando el orden de las oraciones ya lo dice. Un conector de repertorio (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) es la excepción: nunca el mismo dos veces en cinco oraciones, nunca la mayoría de las aperturas de un párrafo, y un conector de síntesis (*Overall*, *Taken together*) como máximo una vez por sección.
- ***because* y *where* conservan su función.** *because* enuncia una causa que el método o los datos establecen, como máximo una vez cada varias oraciones y nunca encadenado (*because …, and because …*); *where* abre la cláusula que sigue a una ecuación y define sus símbolos, y en ningún otro lugar de la prosa (se usa *in which*, *when* o dos oraciones). Una valoración es una oración propia, no un *, which indicates …* final.
- **El método tiene un solo nombre.** Se desarrolla junto con su acrónimo en su primera aparición, tanto en el resumen como en el cuerpo, y en adelante se usa *the proposed* seguido del acrónimo.

## Convenciones transversales

- **Un solo párrafo.** Sin saltos de línea, sin viñetas, sin encabezados.
- **Ninguna cita de ningún tipo**, incluidas las de trabajos previos de los propios autores.
- **Expanda todo acrónimo en su primera aparición**, incluido el de la propia propuesta. Un
  dominio denso en acrónimos los expande todos, por muchos que sean.
- **Enuncie la cantidad antes de enumerarla.**
- La forma de enumeración aquí es distinta de la de la introducción: numerales romanos
  en línea, u ordinales uno por oración. La cantidad, el orden y la denominación deben coincidir con la
  lista de la introducción y con los componentes de la sección de métodos.

## Descalificadores

- Más de un párrafo.
- Una cita, una ecuación, una figura, una tabla o una referencia a una sección.
- Un acrónimo sin expandir.
- Más de 300 o menos de 200 palabras.
- Una posición faltante. Las siete están presentes incluso en la forma más corta.
- La propuesta dividida en dos oraciones, o sin llevar su nombre completo, acrónimo,
  categoría y mecanismo.
- El veredicto que no va al final, o expandido más allá de una oración, o que introduce algo nuevo.
- La posición de componentes que no es la más larga del resumen.
- Formas de componentes en línea y expandida mezcladas.
- Una cantidad, orden o denominación de componentes que no concuerda con la introducción o la
  sección de métodos.
- La cantidad anunciada sin ser enumerada, o enumerada sin ser anunciada.
- El escenario de evaluación enunciado después del resultado que produjo.
- Una familia nombrada de métodos previos, o un linaje recorrido: eso pertenece al estado
  del arte, que no tiene posición aquí.
- Una sección nombrada o referenciada.
- Una cifra citada sin enunciar a qué pertenece.
- Una cifra citada que no coincide exactamente con la sección de resultados.
- Una propiedad afirmada sin instrumento nombrado en la posición 5.
- Una referencia hacia adelante de cualquier tipo.
