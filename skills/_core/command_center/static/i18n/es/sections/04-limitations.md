---
{
  "section": "limitations",
  "position": 8,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/04-limitations.md",
      "quote": "Cada ítem se argumenta en lugar de reportarse, y recurre a algo externo a este trabajo para el estándar que no alcanza."
    }
  },
  "blocks": [
    {
      "id": "lim-opening-concession",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "Los resultados — el logro concreto que sí respaldan"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "lim-proposal-items",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "La sección matemática llega a este bloque ya transpuesta, como las propias contribuciones enumeradas de la sección de métodos -- sus decisiones de diseño se leen allí, una por una, no del documento de propuestas"
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "La sección matemática llega a este bloque ya transpuesta, como las propias contribuciones enumeradas de la sección de métodos -- sus decisiones de diseño se leen allí, una por una, no del documento de propuestas"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "produces_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "Recorra la sección matemática en busca de vacíos en la propuesta:"
          }
        }
      ]
    },
    {
      "id": "lim-validation-items",
      "requires_facts": [
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "El diseño experimental — lo que se fijó en lugar de buscarse, lo que se probó en un único punto"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "lim-failure-mode",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "Los resultados — la peor celda reportada, y el desempeño de la línea base allí"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "lim-closing",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "optional": true
    }
  ]
}
---
# Limitaciones

**Extensión** 180–410 palabras · 1 párrafo, o 2 cuando el segundo contiene un modo de falla
**Ítems** de 3 a 5
**Contiene** al menos una cita por ítem · ninguna figura, ninguna tabla, ninguna ecuación y ninguna
medición nueva

Esta subsección enuncia lo que los resultados reportados **no** establecen. Su fuente de
verdad es la inversa de todas las demás partes de la sección de resultados: aquellas se escriben
a partir de lo que los artefactos muestran, esta a partir de lo que no logran mostrar. Cada ítem se
argumenta en lugar de reportarse, y recurre a algo externo a este trabajo para el estándar que no
alcanza.

## La apertura es una concesión

*Aunque / Si bien / A pesar de* **[un logro concreto que los resultados sí respaldan]**,
deben reconocerse varias limitaciones.

La concesión es obligatoria y nombra algo específico, no una fórmula. Puede
llevar el puente hacia el trabajo futuro en la misma oración — *que a su vez abren vías
para la investigación futura*.

## La anatomía de un ítem

Cinco movimientos. Los cuatro primeros son obligatorios; alcance el quinto siempre que sea posible.

**1. Nombrar la decisión o el límite.** Un valor fijo, una estrategia compartida, una
escala no explorada, una cuadrícula predefinida, una línea base elegida, una aproximación. **Nunca una
sensación.** *El desempeño puede variar* no es una limitación; *el coeficiente de ponderación es
estático* sí lo es.

**2. Conceder su beneficio.** *Aunque este diseño permite X* / *Si bien esta elección
favorece la reproducibilidad y permite la comparación directa*. Esto es lo que separa una
limitación de un descuido: la decisión se tomó por una razón, y la razón se
enuncia.

**3. Enunciar el costo.** Qué restringe, qué puede pasar por alto, qué impide.

**4. Enunciar la consecuencia para la afirmación.** *Por lo tanto, la resolución del resultado
está parcialmente restringida por …* / *las contribuciones estimadas aún pueden depender de …* —
lo que el artículo, en consecuencia, no puede afirmar.

**5. Enunciar lo que daría la alternativa, y lo que costaría.** *… podría
mejorar el desempeño, aunque con un mayor costo computacional.* Esto responde la
pregunta que el lector se hace sin que se le pida: **si sabían que era una limitación, ¿por qué no
la corrigieron?**

### Cada ítem lleva al menos una cita

La cita es lo que hace que la limitación sea verificable y no confesional. Se
ubica en uno de dos lugares:

- **En la alternativa que la corregiría** — quien ya la propuso. Este es el
  lugar natural cuando el ítem alcanza el movimiento 5.
- **En el hecho de que el problema es conocido** en la literatura, cuando el ítem se detiene en
  el movimiento 4.

## Dos recorridos, dos tipos de vacío

Los ítems provienen de dos lugares, y se hacen ambos recorridos. Algunos artículos tienen ítems de
solo uno, lo que generalmente significa que el otro recorrido no se hizo.

**Recorra la sección matemática en busca de vacíos en la propuesta:**

- un coeficiente fijo donde es posible uno adaptativo;
- una heurística donde es posible una elección fundamentada;
- una cuadrícula o partición predefinida que restringe la resolución del resultado;
- una línea base o referencia elegida de la que depende el resultado;
- una aproximación que ignora una estructura de dependencia conocida;
- una fundamentación teórica que la formulación no incorpora;
- un régimen de operación en el que el método se degrada;
- la generalidad de la formulación fuera del tipo de problema probado.

**Recorra el diseño experimental en busca de vacíos en la validación:**

- una única configuración de hiperparámetros compartida, sin búsqueda por escenario;
- evaluación en una única fuente, sitio o cohorte, con la transferibilidad sin probar;
- una escala sin caracterizar — probada en una sola;
- un tamaño de muestra que restringe la generalización;
- heterogeneidad o armonización de los datos sin resolver;
- dependencia de la calidad y completitud de los datos de entrada.

**La regla verificable:** cada ítem nombra una decisión en la formulación o una decisión
en el diseño experimental. Un ítem que no nombra ninguna de las dos es una sensación, y no se
incluye.

## El segundo párrafo: el modo de falla cuantitativo

Se escribe cuando hay un régimen que vale la pena aislar. Cuatro movimientos:

1. **Nombrar el régimen concreto en el que el método es más débil.**
2. **Señalar la peor celda de una tabla ya reportada**, por número. Nunca una nueva
   medición.
3. **Aportar la evidencia de que el régimen es difícil, no de que el método es malo** —
   típicamente el propio desempeño de la línea base en ese mismo régimen.
4. **Dar el mecanismo**: qué etapa del pipeline se rompe, y qué entrada la
   rompe.

El tercer movimiento es lo que separa *el método falla aquí* de *aquí nadie
tiene éxito*, y lo hace con un número que ya está en el artículo.

## El cierre

Opcional. O bien lo que daría abordar las limitaciones, o hacia dónde se
mueve el campo, con una cita.

## Acoplamiento con el trabajo futuro

El trabajo futuro es el subconjunto relevante de estos ítems. La obligación gemela vive aquí:
**un ítem se declara sabiendo que se le puede pedir una dirección**, y una dirección
huérfana en las conclusiones — una que no responde a ningún ítem de aquí — significa que falta un ítem
en esta lista, no que la dirección sea innecesaria.

Cuando un ítem alcanza el movimiento 5, la referencia sobre su alternativa es la misma que
lleva la dirección de trabajo futuro correspondiente.

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025): los ítems A003, A006, A007, A009, A012, A013, A021, A022, A023 y A026 del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una sola columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo el objetivo.

Nueve de los diez artículos enuncian sus limitaciones, y ninguno en una sección de primer nivel: cinco
como la última subsección de los resultados, titulada *Limitations*, y cuatro dentro de las
conclusiones, antes del trabajo futuro. Abren concediendo el alcance (*Despite the
performance of the proposed …, several limitations should be acknowledged.*) y
enumeran los ítems como *First*, *Second*, *Third*, cada uno emparejado con la dirección que
lo abordaría.

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para llevar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una vez; los procedimientos que se ejecutaron van en pasiva en pasado (*was evaluated using*).
- **Las transiciones salen de la relación entre afirmaciones, no de una lista.** Primero se nombra la relación (contraste, causa, consecuencia, desarrollo, ejemplo) y se expresa con el propio contenido de la oración: una cláusula (*yet*, *so*, *although*), un sujeto que remite a lo anterior (*that gap*, *this cost*), o ningún conector cuando el orden de las oraciones ya lo dice. Un conector de repertorio (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) es la excepción: nunca el mismo dos veces en cinco oraciones, nunca la mayoría de las aperturas de un párrafo, y un conector de síntesis (*Overall*, *Taken together*) como máximo una vez por sección.
- ***because* y *where* conservan su función.** *because* enuncia una causa que el método o los datos establecen, como máximo una vez cada varias oraciones y nunca encadenado (*because …, and because …*); *where* abre la cláusula que sigue a una ecuación y define sus símbolos, y en ningún otro lugar de la prosa (se usa *in which*, *when* o dos oraciones). Una valoración es una oración propia, no un *, which indicates …* final.
- **El método tiene un solo nombre.** Se desarrolla con su acrónimo en el primer uso tanto en el resumen como en el cuerpo, y después se escribe *the proposed* seguido del acrónimo.

## Entradas

### Entradas externas

| Entrada | Desbloquea |
|---|---|
| El **diseño experimental** — lo que se fijó en lugar de buscarse, lo que se probó en un único punto | `lim-validation-items` |
| Los **resultados** — la peor celda reportada, y el desempeño de la línea base allí | `lim-failure-mode` |
| Los **resultados** — el logro concreto que sí respaldan | `lim-opening-concession` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `limitations.lim-proposal-items` — las decisiones de diseño de la propuesta, leídas una por una como lo que cada una cuesta | `materials-and-methods.mm-proposal` — La sección matemática llega a este bloque ya transpuesta, como las propias contribuciones enumeradas de la sección de métodos -- sus decisiones de diseño se leen allí, una por una, no del documento de propuestas |

Se revisaron los `requires_facts` de todos los demás bloques (`results`, `experimental-design`)
y el propio cuerpo en prosa de este archivo en busca de una referencia al texto propio de un bloque hermano:
los cuatro ids restantes (`lim-opening-concession`, `lim-validation-items`,
`lim-failure-mode`, `lim-closing`) se apoyan solo en los hechos externos nombrados arriba;
no se encontró ninguna referencia en prosa a bloques hermanos para ellos.

La sección matemática llega a este bloque ya transpuesta, como las propias contribuciones enumeradas de la sección de métodos -- sus decisiones de diseño se leen allí, una por una, no del documento de propuestas.

### Decisiones estructurales

- **La cita de cada ítem** se ubica en la alternativa que lo corregiría, o en
  la literatura que ya conoce el problema — una regla que gobierna la ubicación
  de la cita de cada ítem, no una dependencia que nombra un bloque.

## Descalificadores

- Un ítem que no nombra ninguna decisión en la formulación ni ninguna en el diseño experimental.
- Un ítem sin cita.
- Un ítem que se detiene antes del movimiento 4 — la consecuencia para la afirmación sin enunciar.
- Un ítem que no concede ningún beneficio, lo que hace que se lea como un descuido en lugar de una
  decisión.
- Una medición nueva, o un valor que no está ya en una tabla reportada.
- Un modo de falla que no es visible en ninguna tabla reportada.
- Un régimen de falla nombrado sin el desempeño de la línea base en él.
- Solo ítems de la propuesta, o solo ítems de la validación — se omitió uno de los dos recorridos.
- Un ítem sobre el que no se puede construir ninguna dirección de trabajo futuro, cuando las conclusiones
  aun así contienen una dirección para él.
- Ubicación en las conclusiones, o en cualquier lugar que no sea la última subsección de los resultados.
- Una peor celda suavizada aquí mientras se enuncia sin rodeos en los resultados, o al
  revés.
- Una figura, una tabla o una ecuación.
