---
{
  "section": "results-and-discussion",
  "position": 7,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-results-and-discussion.md",
      "quote": "La discusión es inferencial por defecto y asertiva por excepción."
    }
  },
  "blocks": [
    {
      "id": "rd-general-task",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "Los resultados — las ejecuciones principales, contra las líneas base"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "rd-contribution-blocks",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "La propiedad que una contribución prometió, y el instrumento que la configuración nombró para ella"
          }
        },
        {
          "value": "results",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "Entrada los resultados de los experimentos"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "results-and-discussion.rd-general-task",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "Un bloque de mecanismo abre nombrando el resultado del bloque anterior como la pregunta que viene a responder."
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "La propiedad que una contribución prometió, y el instrumento que la configuración nombró para ella"
          }
        }
      ]
    },
    {
      "id": "rd-cost",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "Entrada los resultados de los experimentos"
          }
        },
        {
          "value": "implementation",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "La implementación — la configuración más exigente, y el hardware declarado en la configuración experimental"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "results-and-discussion.rd-contribution-blocks",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "Un bloque de mecanismo abre nombrando el resultado del bloque anterior como la pregunta que viene a responder."
          }
        }
      ]
    }
  ]
}
---
# Resultados y Discusión

**Extensión** 1170–4150 palabras · de dos a cinco bloques de contenido, más las limitaciones al final
**Entrada** los resultados de los experimentos
**Contiene** 3–12 figuras y 0–8 tablas — la sección del artículo con mayor densidad de artefactos
**No contiene** un preámbulo, un artefacto de cierre ni una sola ecuación numerada

## Una sección, nunca dos

La discusión no es un bloque. No hay un tramo separado de prosa de discusión: la
discusión es **el tercer tiempo de cada lectura de artefacto, en el mismo párrafo que
el número que explica**. Por eso ambas son una sola sección y por eso no pueden
separarse.

## Aquí no se introduce nada

**Cada escenario, partición, métrica, línea base, prueba estadística, variante de ablación,
barrido de sensibilidad y medida de interpretabilidad que se lee en esta sección fue declarado en
la configuración experimental.** Esta sección aplica el protocolo y lee lo que este
produjo; nunca elige una prueba, añade una línea base ni improvisa una ablación después de
ver los números.

## Los bloques

Cada bloque está presente cuando la configuración declaró lo que el bloque lee, y solo entonces — el
orden siguiente vale para cualquier tipo de artículo, sea cual sea su dominio.

**0. El escenario controlado**, cuando la configuración declaró uno. Primero: la propuesta sobre
datos cuya verdad de referencia se conoce — sintéticos o simulados — mostrando la propiedad que el
problema nombra en condiciones en las que puede verificarse. Es breve, y es lo que
hace creíbles los bloques sobre datos reales.

**1. La tarea general.** La evidencia de que la propuesta funciona en la tarea para la que fue
construida: la métrica principal, sobre los datos principales, contra las líneas base. Este bloque
contiene el grueso de la sección — entre el 40% y el 66% de ella — y cierra con la prueba
estadística que declaró la configuración.

**2. Un bloque por contribución.** Cada uno valida la propiedad que esa contribución
prometió, usando el instrumento que la configuración experimental nombró para ella, en el orden en que
se definieron las contribuciones. **Una contribución de interpretabilidad se lee dos veces**: lo que
muestran sus explicaciones — mapas, filtros, pesos, estructura recuperada — y cuán fieles
son, según la medida que declaró la configuración frente a los métodos de explicación
competidores. Una lectura cualitativa por sí sola es una ilustración, no evidencia.

**3. Ablación y sensibilidad**, cuando la configuración las declaró. Una lectura por
variante de ablación, en el orden de la configuración, cada una indicando lo que cuesta eliminar esa
contribución; luego cada barrido, indicando dónde la propuesta es estable y dónde no lo es. Este
es el bloque que muestra que cada contribución se gana su lugar.

**4. Costo, cuando se afirma el costo.** Uno o dos párrafos, una figura. Medido en la
configuración más exigente, y enunciado como tal para que la estimación se lea como
conservadora.

**5. Limitaciones.** Al final, siempre, bajo su propio contrato.

**Un bloque puede cerrar con un párrafo de síntesis** — *Taken together*, *Overall* — que
enuncia lo que el bloque estableció y remite a sus artefactos. La sección en sí
nunca cierra con uno; esa es la tarea de las conclusiones.

### Organizar por escenario en su lugar

Cuando el trabajo tiene escenarios experimentales disímiles — dominios distintos, regímenes
de datos distintos — los bloques pueden organizarse uno por escenario, cada uno recorriendo
internamente desempeño-y-luego-mecanismo. **La correspondencia con las contribuciones se
sigue enunciando**, para que el lector sepa qué bloque valida qué contribución.
Organizar por escenario sin decirlo es lo que hace perder la correspondencia.

## La cadena que termina aquí

> **problema *i* → contribución *i* → propiedad *i* → instrumento *i* → evidencia *i***

El problema se declaró en el planteamiento del problema, la brecha dijo que nadie lo había resuelto,
la contribución lo responde, la configuración nombró el instrumento que lo mide, y
esta sección es donde aparece la evidencia. **La propiedad lleva el mismo nombre
a través de los cinco eslabones** — no un sinónimo, las mismas palabras.

La obligación va en ambos sentidos:

- **cada contribución tiene un bloque aquí**, y
- **cada bloque aquí pertenece a una contribución o a la tarea general.**

Un bloque que no pertenece a ninguna es una medición que nadie pidió.

## Cómo se presenta un resultado

La forma es la misma para una figura y para una tabla. Dos posiciones sintácticas:

**El artefacto como sujeto gramatical**, seguido de un verbo de lectura y de lo que
muestra.

**El artefacto como referencia dentro de la afirmación** — la forma usada siempre que hay un
valor:

> **[la afirmación en palabras] + [el valor entre paréntesis] + [la referencia al artefacto]**

**La referencia apunta al subelemento exacto, no al artefacto en su conjunto.**
Cuando un artefacto tiene partes — paneles, columnas, bandas de filas, lados, regiones sombreadas — la
referencia nombra la parte. Enviar al lector a un artefacto completo para encontrar un número es
enviarlo a buscarlo.

**Los verbos de lectura son un conjunto cerrado con un gradiente.** Los neutros dicen que el artefacto
exhibe algo: *presenta, muestra, ilustra, representa, proporciona*. Los asertivos
dicen que establece algo: *revela, demuestra, confirma, identifica*. Use la
forma asertiva solo cuando el artefacto zanja la cuestión.

## Cada artefacto se referencia antes de aparecer

Cualquier objeto numerado — figura, tabla o panel — se referencia en el cuerpo **antes**
de aparecer. Sin excepción.

El valor diagnóstico es lo esencial: **un artefacto que aparece sin referencia previa
está mal ubicado o está muerto.** Aplicar esta regla es la forma de encontrar una figura a la que nada en el
artículo hace referencia.

## El movimiento de tres tiempos

Por artefacto: **señalarlo → leerlo en números → dar el mecanismo.** Los tres, en
ese orden, en el mismo párrafo. El tercer tiempo es lo que separa reportar de
explicar.

**Un número en la prosa viene con su referencia.** La prosa nunca introduce un valor que ningún
artefacto muestre.

## La discusión: tres registros

El tercer tiempo se presenta en tres registros, y no son intercambiables.

| Registro | Proporción | Forma | Cuándo |
|---|---|---|---|
| **Inferencial** | ~57% | *indica, sugiere, es consistente con, refleja* | el mecanismo se infiere del patrón |
| **Asertivo** | ~30% | *porque, debido a, se deriva de, se atribuye a* | el mecanismo es una propiedad conocida de la formulación o de los datos, no una inferencia a partir del resultado |
| **Corroborativo** | ~13% | *confirma, refuerza* | el resultado concuerda con un bloque anterior o con un comportamiento establecido |

**La discusión es inferencial por defecto y asertiva por excepción.** Dos de cada
tres explicaciones dicen con qué es *consistente* el número, no qué lo *causó*. Una
discusión escrita enteramente en el registro asertivo afirma un conocimiento causal
que el experimento no produjo.

**Las formas son un repertorio, no un estribillo.** Cada registro enumera varias formas
para que la discusión pueda variarlas: ninguna forma abre ni enlaza dos explicaciones
seguidas, y *because* — la forma asertiva más directa — se usa como máximo una vez por
párrafo, nunca encadenada (*because …, and because …*). Una explicación asertiva también
puede expresarse con un verbo (*stems from*, *follows from*) o con dos puntos que
introducen el mecanismo; una inferencial puede hacer de la valoración una oración propia
en lugar de un *, which indicates …* final.

**Está anclada.** La explicación se ubica en el mismo párrafo que el número que
explica. Nunca queda flotando.

**Se encadena entre bloques.** Un bloque de mecanismo abre nombrando el resultado del bloque anterior como la pregunta que viene a responder.

**La concesión pertenece a la discusión.** Donde un competidor gana un subcriterio,
dígalo, y diga qué compra esa pérdida.

**Tres cosas que la discusión no hace:** introducir una afirmación que ningún artefacto respalda;
reformular el número en palabras sin agregar un mecanismo; o saltar a implicaciones para
la práctica — eso pertenece a las conclusiones.

## Cuando una contribución no tiene competidor

Algunas contribuciones no tienen nada contra qué compararse, porque nada más hace
eso. Tres movimientos, en orden:

1. **Proyectar hacia un espacio compartido donde la comparación sea posible**, y mostrar
   **paridad** allí — paridad, no superioridad. Si la contribución opera sobre más
   dimensiones que cualquier competidor, redúzcala a la dimensión que comparten y muestre que
   se sostiene.
2. **Mostrar lo que solo esta contribución produce** — la parte en la que ningún competidor puede ser
   medido. No hay comparación allí porque no hay nada con qué comparar,
   y esa ausencia es el argumento.
3. **Si la paridad es en realidad una pérdida, concederla y enunciar qué se compra con ella.**

**La salvaguarda:** una pérdida concedida se empareja con una ganancia **medida**, no con una
afirmada. Ambas apuntan a un artefacto. *Perdemos aquí pero somos mejores allá* se sostiene solo si
*allá* tiene su propia celda reportada. Sin esta salvaguarda, cualquier resultado desfavorable puede
reciclarse como una virtud.

**Y la deficiencia aun así va a las limitaciones como un ítem.** Justificada aquí se lee
defensiva; declarada allá se lee honesta, y solo allá puede ganarse una dirección de
trabajo futuro.

## El tipo de artefacto sigue a la afirmación

Una cuadrícula de números es una tabla. Un patrón espacial, temporal o espectral es una figura.
Esta no es una preferencia de estilo: un bloque cuya afirmación es una comparación entre celdas
lleva tablas y puede no llevar ninguna figura, mientras que un bloque cuya afirmación es un patrón
lleva figuras y puede no llevar ninguna tabla.

## Citas

Nunca para un resultado: los números propios del artículo no llevan cita. Una cita aquí
acredita **un instrumento** usado para leer los datos, o **sustenta una idea en la que se
apoya la discusión**, y esas ideas se citan siempre:

- una explicación **interpretativa** (el mecanismo con el que un resultado *es consistente* o
  al que *se debe*) cita el trabajo que estableció ese mecanismo o ese comportamiento;
- un análisis de un método **de línea base** (por qué un competidor gana, pierde o falla bajo
  una condición) cita la fuente de la propiedad que invoca (el artículo del propio método o el
  trabajo que la caracterizó);
- un argumento de interpretabilidad **cualitativa** (que un mapa de atribución, un patrón de
  saliencia o una estructura aprendida es plausible) cita el conocimiento del dominio contra
  el que se contrasta (fisiología, física, la literatura de la aplicación).

El registro corroborativo siempre lleva su cita: lo que el resultado *confirma* se nombra con
su fuente. La cita se adjunta a la idea que sustenta, dentro de la oración que la enuncia.

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

**Tamaño medido.** 5–17–45 párrafos; unas 1080–2890–5750 palabras; 0–4–7
subsecciones; sin ecuaciones destacadas; 1–5–31 citas, usadas solo para anclar una
interpretación; 2–6–12 figuras y 0–2–8 tablas.

**Subsecciones, una por análisis, en este orden cuando están presentes:** el escenario
controlado o sintético; comparación con el estado del arte (media ± desviación estándar
sobre las repeticiones) cerrada por su prueba de significancia; un bloque por contribución,
incluida la interpretabilidad; ablación y sensibilidad; limitaciones, al final. Ocho de diez
fusionan resultados y discusión; seis abren con un escenario controlado; siete reportan una
prueba de significancia y siete un análisis de interpretabilidad, pero solo dos una ablación
explícita. Las subsecciones cierran con una síntesis *Taken together*; ninguna sección cierra con una.

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para llevar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una vez; los procedimientos que se ejecutaron van en pasiva en pasado (*was evaluated using*).
- **Las transiciones salen de la relación entre afirmaciones, no de una lista.** Primero se nombra la relación (contraste, causa, consecuencia, desarrollo, ejemplo) y se expresa con el propio contenido de la oración: una cláusula (*yet*, *so*, *although*), un sujeto que remite a lo anterior (*that gap*, *this cost*), o ningún conector cuando el orden de las oraciones ya lo dice. Un conector de repertorio (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) es la excepción: nunca el mismo dos veces en cinco oraciones, nunca la mayoría de las aperturas de un párrafo, y un conector de síntesis (*Overall*, *Taken together*) como máximo una vez por sección (aquí, una vez por subsección: la síntesis que la cierra).
- ***because* y *where* conservan su función.** *because* enuncia una causa que el método o los datos establecen, como máximo una vez cada varias oraciones y nunca encadenado (*because …, and because …*); *where* abre la cláusula que sigue a una ecuación y define sus símbolos, y en ningún otro lugar de la prosa (se usa *in which*, *when* o dos oraciones). Una valoración es una oración propia, no un *, which indicates …* final.
- **El método tiene un solo nombre.** Se desarrolla con su acrónimo en el primer uso tanto en el resumen como en el cuerpo, y después se escribe *the proposed* seguido del acrónimo.
- **Los resultados van en pasado, su lectura en presente.** *The proposed
  model reached*; *this suggests that*.
- **La interpretación se matiza, nunca es superlativa.** *Suggests*, *indicates*, *is
  consistent with*; no *remarkable*, *perfect*, *cementing*.
- **Los números van en línea**: `80.9 \pm 1.7\%`, con los mismos decimales en una tabla y
  en su texto.
- **El mejor valor de cada columna va en negrita, y la leyenda lo dice**: *Bold marks
  the best result for each metric.*
- **Una figura o tabla es el sujeto de su oración** (*Table 4 compares*, *As shown
  in Figure 5,*), y su leyenda es un sintagma nominal seguido de una a tres oraciones
  que explican los paneles, colores y abreviaturas — unas 30 a 60 palabras.

## Entradas

### Entradas externas

| Entrada | Desbloquea |
|---|---|
| Los **resultados** — las ejecuciones principales, contra las líneas base | `rd-general-task` |
| La **implementación** — la configuración más exigente, y el hardware declarado en la configuración experimental | `rd-cost` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `results-and-discussion.rd-contribution-blocks` — un bloque de mecanismo abre nombrando el resultado del bloque anterior como la pregunta que viene a responder | `results-and-discussion.rd-general-task` — la evidencia de la tarea general, el bloque inmediatamente anterior |
| `results-and-discussion.rd-contribution-blocks` — La propiedad que una contribución prometió, y el instrumento que la configuración nombró para ella | `materials-and-methods.mm-proposal` — las contribuciones enumeradas a las que se rastrea cada propiedad |
| `results-and-discussion.rd-cost` — un bloque de mecanismo abre nombrando el resultado del bloque anterior como la pregunta que viene a responder | `results-and-discussion.rd-contribution-blocks` — la validación por contribución, el bloque inmediatamente anterior al costo |

### Decisiones estructurales

- **Cada artefacto** depende de las ejecuciones, y el diagrama de cierre de la configuración
  experimental debe poder ubicarlo — una regla transversal a todos los bloques de aquí,
  no una dependencia de un bloque específico.
- **El tercer tiempo** (la explicación mecanística) se apoya en la formulación,
  o en una propiedad de los datos — de nuevo transversal a todos los bloques, sin
  nombrar uno.
- **Limitaciones** vive en su propia sección, bajo su propio contrato — no es
  un bloque de esta sección y no tiene ninguna dependencia de ella.

## Descalificadores

- Un mecanismo interpretativo, un análisis de línea base o un argumento de interpretabilidad
  cualitativa enunciado sin una cita que lo sustente.
- Una ecuación numerada.
- Un preámbulo, o un artefacto de resumen de cierre.
- Un bloque que abre con prosa sin referencia a un artefacto.
- Un artefacto que aparece antes de cualquier referencia a él, o al que nada referencia en
  absoluto.
- Una referencia a un artefacto completo cuando el valor está en una de sus partes.
- Un número en la prosa que no aparece en ningún artefacto.
- Un artefacto que no puede ubicarse en el diagrama de cierre de la configuración experimental —
  una celda reportada que el diseño nunca declaró.
- Una afirmación de mejora sin la línea base sobre la que mejora, en el mismo artefacto.
- Una contribución sin un bloque aquí.
- Un bloque que no pertenece ni a una contribución ni a la tarea general.
- Una propiedad nombrada aquí con un nombre distinto al que le dieron el planteamiento del problema, la
  contribución o el instrumento.
- Un bloque organizado por escenario sin enunciar qué contribución valida.
- Una lectura de artefacto sin tercer tiempo — el número enunciado y nunca explicado.
- Una discusión escrita enteramente en el registro asertivo.
- Una explicación ubicada en un párrafo distinto del número que explica.
- Una pérdida concedida emparejada con una ganancia afirmada en lugar de una medida.
- Una deficiencia justificada aquí y ausente de las limitaciones.
- Una cita acreditada a un resultado.
- Una tabla usada para un patrón, o una figura usada para una cuadrícula de comparación.
- Las limitaciones ubicadas en cualquier lugar que no sea el final.
- La interpretación de un resultado que ningún artefacto contiene.
- Una comparación contra las líneas base sin prueba de significancia estadística.
- Un escenario, partición, métrica, línea base, prueba, variante de ablación, barrido o
  medida de interpretabilidad que la configuración experimental no declaró.
- Una variante de ablación o un barrido declarado en la configuración sin lectura aquí.
- Una contribución de interpretabilidad leída solo cualitativamente cuando la configuración declaró una
  medida de fidelidad para ella.
- La sección cerrando con un párrafo de síntesis.
- Una tabla con valores en negrita cuya leyenda no dice qué marca la negrita.
- Una tabla que excede `\textwidth`, o cuyo texto se imprime por debajo de 0,70 o por
  encima de 0,90 veces el tamaño de la fuente del cuerpo (incluida una tabla dejada al
  tamaño del cuerpo).
- Una tabla escalada con `\resizebox`, `\scalebox` o `adjustbox` por debajo de 0,85, o
  escalada a `\textwidth`.
- Una tabla con reglas verticales, o una tabla cuya leyenda queda debajo de ella.
