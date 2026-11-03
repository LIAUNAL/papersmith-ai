---
{
  "section": "title-and-keywords",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/09-title-and-keywords.md",
      "quote": "El título enuncia qué es la cosa, no qué tan bien le fue."
    }
  },
  "blocks": [
    {
      "id": "title",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "Las contribuciones, ya definidas — el título selecciona entre ellas"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "keywords",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "keyword-bounds",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "Los keyword-bounds y la classification-line — los requisitos de la revista destino"
          }
        },
        {
          "value": "classification-line",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "Los keyword-bounds y la classification-line — los requisitos de la revista destino"
          }
        }
      ],
      "citations": "none",
      "after": [
        {
          "target": "title-and-keywords.title",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "El título lleva el adjetivo; la palabra clave lleva el sustantivo."
          }
        }
      ]
    }
  ]
}
---
# Título y palabras clave

**Extensión** título 10–13 palabras · palabras clave 3–5
**Incluye** ningún número, ningún porcentaje, ninguna afirmación de superioridad

El título es la única afirmación irrevocable del artículo: es lo que se cita, se indexa y se
busca. Las palabras clave son la superficie de recuperación — los términos que escribirá un lector que necesita este
artículo sin saber que existe.

## El título es una máquina de ranuras

| Ranura | Obligatoria | Qué es |
|---|---|---|
| Acrónimo, seguido de dos puntos | no | El nombre que se pretende que el método lleve en la literatura |
| Artículo | no | *A* o *An* |
| **Adjetivo de propiedad** | **sí** | La propiedad que agrega la contribución — y va primero |
| **Mecanismo** | **sí** | De qué está hecho el método, nombrado explícitamente |
| Sustantivo de artefacto | no | *Framework*, *approach*, *network* — la categoría de la cosa |
| **Tarea** | **sí** | Para qué sirve el método |
| Dominio o lugar | no | Solo cuando el trabajo está ligado a él |

**Las tres ranuras obligatorias provienen de la propuesta**: la propiedad es la que
agregan las contribuciones, el mecanismo es lo que las realiza, la tarea es la que
nombró el planteamiento del problema.

**El adjetivo de propiedad va primero**, justo después del artículo o del acrónimo. El
título abre con la propiedad, no con el mecanismo — es lo primero que el lector
lee.

**Tres ranuras son opcionales, y cada una tiene una condición.** El sustantivo de artefacto se omite
cuando los propios mecanismos son el título. El dominio o lugar aparece solo cuando
el trabajo no se transfiere más allá de él. El acrónimo aparece solo cuando se pretende que
se convierta en el nombre público del método, y entonces lleva dos puntos y el resumen lo
desarrolla.

## Los guiones cumplen dos funciones distintas

**Un guion corto une un par modificador** — dos palabras que juntas modifican a una tercera.

**Una raya media (en dash) une términos de igual rango en una serie** — dimensiones del mismo rango, sin que ninguna
modifique a otra.

Confundirlos cambia lo que dice el título: con un guion corto, el primer término de una
serie de términos de igual rango se lee como modificador del último.

## Lo que nunca aparece en el título

Ningún número, ningún porcentaje, ningún comparativo, ninguna afirmación de superioridad. El título enuncia
qué es la cosa, no qué tan bien le fue.

Mayúsculas de título (Title Case), con preposiciones y artículos en minúscula.

## Palabras clave

**De tres a cinco, separadas por punto y coma.** En minúscula por defecto; los acrónimos en mayúsculas;
los nombres propios conservan sus mayúsculas.

**No son una reformulación del título.** Aproximadamente un tercio repite un término que el título
ya incluye; el resto agrega algo para lo que el título no tuvo espacio. Una lista de palabras clave
que solo hace eco del título ha desperdiciado toda su superficie de recuperación.

**Qué aportan las agregadas**, en tres tipos:

1. **Los mecanismos que el título omitió** — el estimador, la arquitectura, el
   método de reducción, lo que no haya cabido.
2. **La modalidad de datos o la población** — el tipo de datos, la familia de tareas, la
   condición o el entorno concretos estudiados.
3. **La propiedad en su forma buscable.** El título lleva el adjetivo; la
   palabra clave lleva el sustantivo.

**Ordenadas de la más amplia a la más específica:** primero la tarea o el dominio, luego la propiedad,
luego la maquinaria.

**Cada palabra clave aparece en el cuerpo.** Una palabra clave ausente del artículo es una palabra clave
inventada para el motor de búsqueda.

## Formato de revisión del manuscrito y anonimato de los autores

### Modo de revisión a una columna
El manuscrito canónico se presenta y compone en **formato de revisión, a una columna** (`onecolumn`, por ejemplo, `\documentclass[11pt,onecolumn,a4paper]{article}` con márgenes de revisión estándar e interlineado de 1.5). Los formatos a dos columnas o finales de la editorial se reservan para la adaptación a la revista tras la aceptación, mediante la habilidad `venue`.

### Metadatos de autoría anonimizados en los borradores iniciales
En la redacción inicial del manuscrito **no se incluyen nombres de autores, afiliaciones institucionales ni correos de contacto**. Todos los metadatos de autoría permanecen anonimizados y se fijan explícitamente como marcadores de posición (escritos en inglés y suprimidos para la revisión por pares; nunca un marcador en español):
```latex
\author{Author names withheld \\ \textit{Affiliations and contact e-mails to be provided}}
```
Solo cuando todo el manuscrito ha sido redactado, compilado y supera todas las verificaciones con el usuario se pide al operador que aporte las identidades de los autores, sus afiliaciones y los datos de correspondencia.

### Metadatos de autoría revelados
Cuando el operador levanta el anonimato, el bloque `title-and-keywords.title` reemplaza el marcador por esta plantilla, y solo por esta:
```latex
\author{%
\begin{minipage}[t]{\dimexpr\textwidth-2\tabcolsep\relax}
\centering
First Author$^{1}$, Second Author$^{1,2}$, and Third Author$^{3,*}$\\[1ex]
\small
$^{1}$Departamento de Sistemas e Inform\'{a}tica, Universidad de Caldas, Manizales 170004, Colombia\\
$^{2}$Departamento de Electr\'{o}nica y Automatizaci\'{o}n, Universidad Aut\'{o}noma de Manizales, Manizales 170001, Colombia\\
$^{3}$AI-Lab, Signal Processing and Recognition Group, Universidad Nacional de Colombia, Sede Manizales, Manizales 170003, Colombia\\[1ex]
E-mails: \texttt{first.author@ucaldas.edu.co}, \texttt{second.author@ucaldas.edu.co}, \texttt{third.author@unal.edu.co}\\
$^{*}$Corresponding author: \texttt{third.author@unal.edu.co}
\end{minipage}}
```
`article` compone `\author` en una columna `c` centrada que nunca parte línea, así que una afiliación o una lista de correos escrita como línea `\\` suelta más ancha que la caja de texto invade el margen (un `Overfull \hbox` en `main.log`). La `minipage` de ancho `\textwidth-2\tabcolsep` vuelve el encabezado texto que parte línea. Mantenga una línea de autores con índices de afiliación en superíndice, una afiliación por línea en `\small`, y luego los correos y el autor de correspondencia. Separe las líneas con `\\`, nunca con `\par` ni una línea en blanco: `\author` no es un comando largo y un salto de párrafo dentro de él aborta el preámbulo. Verifique que `main.log` no tenga `Overfull \hbox` en la línea de `\maketitle` antes de dar el encabezado por terminado.

## La línea de clasificación

Algunas revistas exigen un código de clasificación temática después de las palabras clave. Ese es un
requisito externo, no una decisión de estilo: tómelo de las instrucciones de la revista destino,
junto con el número permitido de palabras clave.

## Estilo de la casa LIA

Medido sobre los diez artículos de método Q1 del grupo de 2025–2026 (SJR 2025): ítems A003, A006, A007, A009, A012, A013, A021, A022, A023 y A026 del banco de artículos del laboratorio. Los rangos son mínimo–mediana–máximo entre los artículos que tienen la sección; una línea compuesta tiene unas 12 palabras en un formato de una columna. Los rangos describen cómo escribe el grupo; la extensión indicada al inicio de este contrato sigue siendo la meta.

**Tamaño medido.** Títulos de 7–12–13 palabras, con mayúscula inicial en cada palabra principal (*title case*); 4–5–8 palabras clave.

**Los títulos del grupo** siguen *<Mechanism>-Based <Model> for <Task>* o *<Property>
<Mechanism> for <Qualified Task>*, y nueve de cada diez omiten el acrónimo del método. El
acrónimo aparece en el resumen y en el cuerpo.

## Insumos

### Insumos externos

| Insumo | Desbloquea |
|---|---|
| Los **keyword-bounds** y la **classification-line** — los requisitos de la revista destino | `keywords` |

### Cadena interna

| Bloque | Depende de |
|---|---|
| `title-and-keywords.title` — Las contribuciones, ya definidas — el título selecciona entre ellas | `materials-and-methods.mm-proposal` — las contribuciones enumeradas entre las que el título selecciona |
| `title-and-keywords.keywords` — la propiedad en su forma buscable, la forma sustantiva de lo que el título lleva como adjetivo | `title-and-keywords.title` — el adjetivo de propiedad con el que abre el título |

### Decisiones estructurales

- **Si el acrónimo aparece** se decide según si se pretende que
  se convierta en el nombre público del método — una decisión estructural, no una dependencia
  de un bloque.

## Descalificadores

- Menos de 10 o más de 16 palabras en el título.
- Ningún adjetivo de propiedad, o uno que no va primero.
- Ningún mecanismo nombrado.
- Ninguna tarea nombrada.
- Un número, un porcentaje o una afirmación de superioridad.
- Un acrónimo en el título sin dos puntos, o uno que el resumen no desarrolla.
- Un dominio o lugar nombrado cuando el trabajo no está ligado a él.
- Un guion corto donde los términos de igual rango en una serie necesitan una raya media.
- Menos de 3 o más de 5 palabras clave, o un número que la revista destino no permite.
- Una lista de palabras clave que solo repite términos del título.
- Una palabra clave ausente del cuerpo.
- Una línea de clasificación faltante cuando la revista destino la exige.
- Nombres reales de autores, afiliaciones o correos de contacto incluidos en la redacción inicial antes de la verificación completa del manuscrito con el usuario.
- Un manuscrito compuesto a dos columnas en lugar del modo de revisión a una columna (`onecolumn`).
