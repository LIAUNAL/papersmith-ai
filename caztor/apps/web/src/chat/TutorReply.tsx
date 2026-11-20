import { Markdown } from "./Markdown.tsx";
import { TexMath } from "./TexMath.tsx";
import "./TutorReply.css";

/** A PaperSmith tutor's structured turn (math-tutor, experiments-tutor), as its JSON block says it. */
interface TutorAnswer {
  reply: string;
  [field: string]: unknown;
}

const FENCE = /```json[ \t]*\n([\s\S]*?)\n```/;

/** The text around a tutor's JSON answer, and the answer; null when the text holds no such block. */
export function splitTutorAnswer(text: string): { before: string; answer: TutorAnswer; raw: string; after: string } | null {
  const match = FENCE.exec(text);
  if (match === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(match[1]!);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed) || typeof (parsed as { reply?: unknown }).reply !== "string") return null;
  return { before: text.slice(0, match.index).trim(), answer: parsed as TutorAnswer, raw: match[1]!, after: text.slice(match.index + match[0].length).trim() };
}

const text = (value: unknown): string | null => (typeof value === "string" && value.trim() !== "" ? value : null);
const list = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).filter((item) => item.trim() !== "") : []);

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="tutor-reply__section">
      <div className="tutor-reply__label">{label}</div>
      {children}
    </div>
  );
}

/** A tutor's answer as readable sections, with the raw JSON folded below for whoever needs it. */
export function TutorReply({ answer, raw }: { answer: TutorAnswer; raw: string }) {
  const assessment = typeof answer["assessment"] === "object" && answer["assessment"] !== null ? (answer["assessment"] as Record<string, unknown>) : null;
  const level = assessment?.["level"];
  const label = text(assessment?.["label"]);
  const gaps = list(assessment?.["gaps"]);
  const formulas = list(answer["latex"]);
  const risks = list(answer["risks"]);
  return (
    <div className="tutor-reply">
      {text(answer["image_reading"]) === null ? null : (
        <Section label="What the image shows">
          <Markdown text={answer["image_reading"] as string} />
        </Section>
      )}
      <Markdown text={answer.reply} />
      {text(answer["question"]) === null ? null : (
        <Section label="Question">
          <Markdown text={answer["question"] as string} />
        </Section>
      )}
      {formulas.length === 0 ? null : (
        <Section label="Formulas">
          {formulas.map((formula, index) => (
            <TexMath key={index} tex={formula.trim().replace(/^\$\$?|\$\$?$/g, "")} display />
          ))}
        </Section>
      )}
      {assessment === null ? null : (
        <Section label="Assessment">
          <p>{[label, typeof level === "number" ? `(level ${level})` : null].filter(Boolean).join(" ")}</p>
          {text(assessment["evidence"]) === null ? null : <Markdown text={assessment["evidence"] as string} />}
          {gaps.length === 0 ? null : (
            <ul>
              {gaps.map((gap, index) => (
                <li key={index}>{gap}</li>
              ))}
            </ul>
          )}
        </Section>
      )}
      {risks.length === 0 ? null : (
        <Section label="Risks">
          <ul>
            {risks.map((risk, index) => (
              <li key={index}>{risk}</li>
            ))}
          </ul>
        </Section>
      )}
      {text(answer["novelty_link"]) === null ? null : (
        <Section label="Why it matters for the novelty">
          <Markdown text={answer["novelty_link"] as string} />
        </Section>
      )}
      {text(answer["next_step"]) === null ? null : (
        <Section label="Next step">
          <Markdown text={answer["next_step"] as string} />
        </Section>
      )}
      {text(answer["deliberation_prompt"]) === null ? null : (
        <Section label="For /experimental-deliberation">
          <pre className="tutor-reply__formula">{answer["deliberation_prompt"] as string}</pre>
        </Section>
      )}
      <details className="tutor-reply__raw">
        <summary>Raw answer (JSON)</summary>
        <pre>{raw}</pre>
      </details>
    </div>
  );
}
