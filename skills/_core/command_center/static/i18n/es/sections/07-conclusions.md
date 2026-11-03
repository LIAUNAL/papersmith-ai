---
{
  "section": "conclusions",
  "position": 9,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/07-conclusions.md",
      "quote": "No añaden nada — toda afirmación aquí ya existe antes, con más detalle."
    }
  },
  "blocks": [
    {
      "id": "concl-block-1",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "Las contribuciones, tal como se definieron — mismo número, orden y nombres que en la introducción y en la sección de métodos"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "Las contribuciones, tal como se definieron — mismo número, orden y nombres que en la introducción y en la sección de métodos"
          }
        }
      ]
    },
    {
      "id": "concl-block-2",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "Los resultados, un hallazgo por contribución o hipótesis, en el orden en que los presentan los métodos y los resultados"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "concl-block-3",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "concl-block-4",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "Las limitaciones, de las que es el subconjunto pertinente, y una referencia por dirección"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "limitations.lim-proposal-items",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "Las limitaciones, de las que es el subconjunto pertinente, y una referencia por dirección"
          }
        }
      ]
    }
  ]
}
---
# Conclusiones

**Extensión** 350–950 palabras · 3 a 6 párrafos
**No contiene** ecuaciones, figuras ni tablas
**Contiene** citas en un solo lugar: el bloque de trabajo futuro

Las conclusiones las leen personas que no leerán el artículo. Deben sostenerse
por sí solas. No añaden nada — toda afirmación aquí ya existe antes, con más detalle.

## Cuatro bloques funcionales

| Bloque | Párrafos | Palabras |
|---|---|---|
| 1 — La propuesta y sus componentes | 1, siempre el primero | 60–226 |
| 2 — Los hallazgos, uno por contribución | 1 por contribución o hipótesis | 80–180 cada uno |
| 3 — La consecuencia más allá del método (opcional) | párrafo propio, o el cierre del bloque 2 | ~50–120 |
| 4 — Trabajo futuro | 1, siempre el último | 55–180 |

Los bloques 2 y 3 pueden compartir un párrafo; los bloques 1 y 4 nunca se fusionan con nada.
El número de párrafos sigue al número de contribuciones: tres contribuciones con un
párrafo de implicación suman seis.

## Bloque 1 — La propuesta y sus componentes

Tiempo pasado. Nombre completo, sigla y la categoría del artefacto. Luego los N
componentes reformulados, en una de tres formas:

- **`First / Second / Third`** como oraciones separadas, tras anunciar el número;
- **una lista en línea** dentro de una sola oración, la forma más compacta;
- **prosa con conectores**: *integrando A … la incorporación de B permite …
  además C*.

**Mismo número, mismo orden, mismos nombres** que la lista de contribuciones de la introducción y
las subsecciones de la sección de métodos.

**Cerrar con lo que distingue al método de sus alternativas**: la propiedad, no
el número. Lo que no requiere, lo que no necesita modificar, aquello de lo que no
depende.

## Bloque 2 — Los hallazgos, uno por contribución

**Un párrafo por contribución, en el orden en que la presentan los métodos y los
resultados.** Cada párrafo responde a su contribución —o a la hipótesis que esa
contribución puso a prueba— con el hallazgo que los resultados reportaron para ella:
competidores con nombre, ejes con nombre y las condiciones bajo las cuales se cumplió
el hallazgo. Una contribución sin párrafo de hallazgo es una contribución que las
conclusiones olvidaron; un párrafo de hallazgo que no responde a ninguna contribución
es un resultado que el artículo no prometió.

**Como máximo una cifra principal por contribución, idéntica a la de los resultados.**
Cite un valor solo cuando el valor es lo importante; de lo contrario, manténgase en
comparativos. Una cifra citada lleva su dispersión cuando los resultados la dieron, y
debe coincidir carácter por carácter con la sección de resultados: mismo valor, misma
unidad, misma precisión.

**Nada nuevo.** Ningún experimento, figura, comparación o interpretación que la
sección de resultados no contenga ya. Las conclusiones comprimen la evidencia; nunca
le añaden nada.

## Bloque 3 — La consecuencia más allá del método (opcional)

Lo que el lector se lleva, más allá del hecho de que el método funcionó. No es un resultado ni
una contribución: es una consecuencia. Responde a *y qué*. Cerca de la mitad de los
artículos del grupo la incluyen; escríbala cuando la consecuencia es real y omítala en
caso contrario.

Dos variantes; el artículo elige según de quién sea el problema:

- **Para quien lo implementa**: el costo de adopción es bajo: no hay que
  modificar nada, el método se integra en los flujos existentes, el tiempo de ejecución disminuye.
- **Para quien vive el problema**: algo se vuelve posible que antes no lo era: el
  factor detrás de una decisión puede rastrearse, el proceso es auditable donde
  la regulación lo exige.

Puede ser su propio párrafo o las oraciones de cierre del bloque 2. Es la única parte
de la sección que se dirige a alguien fuera del subcampo.

## Bloque 4 — Trabajo futuro

Siempre al final. **El único bloque de la sección que cita**: una referencia por
dirección, que muestra que la dirección está viva en la literatura. Todo lo anterior
no cita nada.

**Es el último párrafo de la sección, y un párrafo propio.** Abre tras un punto y
aparte, nunca como una oración que continúa el párrafo anterior. `write` y
`humanize --apply` abren el cuerpo de este bloque con una línea en blanco, y `verify`
reporta un bloque de trabajo futuro que se funde con el párrafo de arriba
(`own-paragraph`).

**El trabajo futuro es el subconjunto pertinente de las limitaciones, con una referencia por
dirección.** Cada dirección responde a una limitación declarada: una dirección por
limitación pertinente, cada una con su cita.

**Las limitaciones mismas no se desarrollan aquí.** Viven en la sección de
limitaciones; este bloque nombra solo las direcciones que motivan.

**La reducción va en un solo sentido.** Una limitación puede quedar sin dirección:
no todo está pensado para repararse. Pero ninguna dirección queda sin una limitación
que la motive: **una dirección sin limitación correspondiente significa que la limitación
nunca se declaró**, no que la dirección sea innecesaria. Se corrige declarando la
limitación, no eliminando la dirección.

Eso es lo que hace verificable el acoplamiento entre las dos secciones.

Cada dirección es lo bastante específica como para ser un artículo: una extensión con nombre, no una esperanza.
El bloque cierra con la aplicabilidad que esas direcciones ampliarían.

## Opcional

**Una advertencia de alcance.** Cuando los resultados podrían leerse como un hallazgo sobre el dominio
y no sobre el modelo, diga cuál de los dos son. Esto conlleva la misma
disciplina de atribución que una cifra citada: indicar a qué pertenece la afirmación.

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025): ítems A008, A017, A018 (Elsevier), luego A003, A006, A007, A009, A021, A022 y A026 (MDPI) del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo la meta.

**Tamaño medido.** 2–4,5–10 párrafos; unas 255–610–952 palabras; sin ecuaciones,
figuras ni tablas; 0–4–9 citas, en su mayoría en las oraciones de trabajo futuro.

**Forma medida.** 10/10 abren reformulando la propuesta y 10/10 cierran con el trabajo
futuro; 5/10 repiten cifras principales de los resultados; 7/10 ponen limitaciones
dentro de las conclusiones, lo que este contrato no sigue: las limitaciones permanecen
en su propia sección y las conclusiones solo extraen de ellas el trabajo futuro; cerca
de la mitad incluyen un párrafo de implicación; solo uno introdujo evidencia que los
resultados no contenían.

**Forma.** Titulada *Conclusions*, o *Concluding Remarks and Future Work*. Abre
reformulando el método en pasado (*This work introduced …, a …*), recorre los
hallazgos en el orden de las contribuciones y cierra con el trabajo futuro enumerado
como *First*, *Second*, *Third*.

**Redacción.**

- **Las oraciones promedian 21–27 palabras.** Lo bastante largas para portar una afirmación y su matiz, nunca una cadena de tres cláusulas.
- **Una sola voz para todo el artículo.** Primera persona del plural (*we propose*) o impersonal (*this work introduces*), elegida una sola vez; los procedimientos que se ejecutaron van en voz pasiva y en pasado (*was evaluated using*).
- **Las transiciones salen de la relación entre afirmaciones, no de una lista.** Primero se nombra la relación (contraste, causa, consecuencia, desarrollo, ejemplo) y se expresa con el propio contenido de la oración: una cláusula (*yet*, *so*, *although*), un sujeto que remite a lo anterior (*that gap*, *this cost*), o ningún conector cuando el orden de las oraciones ya lo dice. Un conector de repertorio (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) es la excepción: nunca el mismo dos veces en cinco oraciones, nunca la mayoría de las aperturas de un párrafo, y un conector de síntesis (*Overall*, *Taken together*) como máximo una vez por sección.
- ***because* y *where* conservan su función.** *because* enuncia una causa que el método o los datos establecen, como máximo una vez cada varias oraciones y nunca encadenado (*because …, and because …*); *where* abre la cláusula que sigue a una ecuación y define sus símbolos, y en ningún otro lugar de la prosa (se usa *in which*, *when* o dos oraciones). Una valoración es una oración propia, no un *, which indicates …* final.
- **El método tiene un solo nombre.** Se desarrolla junto con su acrónimo en su primera aparición, tanto en el resumen como en el cuerpo, y en adelante se usa *the proposed* seguido del acrónimo.

## Entradas

Todo excepto el resumen debe existir. El resumen se escribe después de esta
sección, porque la comprime.

### Entradas externas

| Entrada | Desbloquea |
|---|---|
| Los **resultados**, un hallazgo por contribución o hipótesis, en el orden en que los presentan los métodos y los resultados | `concl-block-2` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `conclusions.concl-block-1` — Las contribuciones, tal como se definieron — mismo número, orden y nombres que en la introducción y en la sección de métodos | `materials-and-methods.mm-proposal` — las contribuciones enumeradas que aquí se reformulan |
| `conclusions.concl-block-4` — Las limitaciones, de las que es el subconjunto pertinente, y una referencia por dirección | `limitations.lim-proposal-items` — las limitaciones recopiladas de las que este bloque extrae su subconjunto pertinente |

La ubicación propia del bloque 3 (su propio párrafo o el cierre del bloque 2) es una
opción de ubicación (véase Decisiones estructurales), no una derivación de contenido a partir de
la propia prosa del bloque 2, por lo que `concl-block-3` no lleva ni una entrada externa ni
una fila de cadena interna.

### Decisiones estructurales

- **Bloque 3 — la consecuencia más allá del método** se elige según de quién sea
  el problema: del implementador o del dominio; es una decisión autoral, no un
  hecho obtenido de los datos ni una dependencia de un bloque hermano.

## Descalificadores

- Una afirmación, un número o una propiedad que no aparece en ninguna parte anterior del artículo.
- Evidencia nueva: un experimento, una figura, una comparación o una interpretación que
  la sección de resultados no contiene ya.
- Una lista de componentes que discrepa de la introducción o de la sección de métodos en número,
  orden o nombres.
- Una contribución sin párrafo de hallazgo en el bloque 2.
- El bloque 1 que no va primero, o el bloque 4 que no va al final.
- El bloque 1 que cierra con un número en lugar de con la propiedad distintiva.
- Un número que difiere de la sección de resultados, en valor, unidad o precisión.
- Más de una cifra principal para una misma contribución.
- Una dirección de trabajo futuro que no responde a ninguna limitación declarada.
- Un bloque de trabajo futuro que continúa el párrafo anterior en lugar de abrir el suyo.
- Una cita en cualquier lugar fuera del bloque de trabajo futuro.
- Una dirección de trabajo futuro sin referencia.
- Una dirección de trabajo futuro demasiado vaga para ser un artículo.
- Una ecuación, una figura o una tabla.
- Limitaciones desarrolladas aquí en lugar de en la sección de limitaciones.
- Más de 950 o menos de 350 palabras.
- Una sección que no puede leerse sin haber leído el artículo.
