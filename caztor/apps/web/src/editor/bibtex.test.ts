import { StringStream } from "@codemirror/language";
import { describe, expect, it } from "vitest";
import { bibtexParser } from "./bibtex.ts";

/** Runs the tokenizer over `source` line by line and returns the styled pieces, skipping unstyled whitespace and commas. */
function tokenize(source: string): Array<[string, string]> {
  const state = bibtexParser.startState?.(2) ?? { entry: null };
  const pieces: Array<[string, string]> = [];
  for (const line of source.split("\n")) {
    const stream = new StringStream(line, 2, 2);
    while (!stream.eol()) {
      stream.start = stream.pos;
      const style = bibtexParser.token(stream, state);
      if (stream.pos === stream.start) throw new Error(`The tokenizer did not advance at "${line.slice(stream.pos)}"`);
      const text = line.slice(stream.start, stream.pos);
      if (style !== null && text.trim() !== "") pieces.push([text, style]);
    }
  }
  return pieces;
}

describe("BibTeX tokenizer", () => {
  it("styles the entry type, the key and the field names of a regular entry", () => {
    const pieces = tokenize("@article{knuth84,\n  author = {Donald Knuth},\n  year = 1984\n}");
    expect(pieces).toEqual([
      ["@article", "keyword"],
      ["{", "bracket"],
      ["knuth84", "labelName"],
      ["author", "propertyName"],
      ["=", "operator"],
      ["{Donald Knuth}", "string"],
      ["year", "propertyName"],
      ["=", "operator"],
      ["1984", "number"],
      ["}", "bracket"],
    ]);
  });

  it("accepts entry types in any letter case and parentheses as delimiters", () => {
    const pieces = tokenize("@Book(key1, title = \"A Title\")");
    expect(pieces.slice(0, 3)).toEqual([
      ["@Book", "keyword"],
      ["(", "bracket"],
      ["key1", "labelName"],
    ]);
    expect(pieces).toContainEqual(['"A Title"', "string"]);
    expect(pieces[pieces.length - 1]).toEqual([")", "bracket"]);
  });

  it("keeps nested braces and escaped quotes inside one string value", () => {
    const pieces = tokenize('@misc{k, title = {A {B {C}} d}, note = "say \\"hi\\" {x}"}');
    expect(pieces).toContainEqual(["{A {B {C}} d}", "string"]);
    expect(pieces).toContainEqual(['"say \\"hi\\" {x}"', "string"]);
    expect(pieces[pieces.length - 1]).toEqual(["}", "bracket"]);
  });

  it("continues a braced value across lines", () => {
    const pieces = tokenize("@misc{k,\n  abstract = {first line\n  second line},\n  year = 2020\n}");
    expect(pieces.filter(([, style]) => style === "string").map(([text]) => text)).toEqual(["{first line", "  second line}"]);
    expect(pieces).toContainEqual(["2020", "number"]);
  });

  it("styles string macros, concatenation and the @string definition", () => {
    const pieces = tokenize('@string{acm = "ACM Press"}\n@misc{k, publisher = acm # " Inc."}');
    expect(pieces[0]).toEqual(["@string", "keyword"]);
    expect(pieces).toContainEqual(["acm", "propertyName"]);
    expect(pieces).toContainEqual(['"ACM Press"', "string"]);
    expect(pieces).toContainEqual(["acm", "variableName"]);
    expect(pieces).toContainEqual(["#", "operator"]);
    expect(pieces).toContainEqual(['" Inc."', "string"]);
  });

  it("treats text outside entries and @comment blocks as comments", () => {
    const pieces = tokenize("Some notes about the file\n@comment{ignored {nested} text}\n@article{k, year = 1}");
    expect(pieces[0]).toEqual(["Some notes about the file", "comment"]);
    expect(pieces[1]).toEqual(["@comment", "keyword"]);
    expect(pieces).toContainEqual(["ignored {nested} text}", "comment"]);
    expect(pieces).toContainEqual(["@article", "keyword"]);
    expect(pieces).toContainEqual(["k", "labelName"]);
  });

  it("styles a @preamble value", () => {
    const pieces = tokenize('@preamble{ "\\newcommand{\\x}{y}" }');
    expect(pieces[0]).toEqual(["@preamble", "keyword"]);
    expect(pieces).toContainEqual(['"\\newcommand{\\x}{y}"', "string"]);
  });

  it("recovers at the next entry when one is left unclosed", () => {
    const pieces = tokenize("@article{broken, title = {never closed\n@book{ok, year = 2001}");
    expect(pieces).toContainEqual(["@book", "keyword"]);
    expect(pieces).toContainEqual(["ok", "labelName"]);
    expect(pieces).toContainEqual(["2001", "number"]);
  });

  it("always advances, even on stray characters", () => {
    expect(() => tokenize("@@{}}}, = = # ## \"\" {{{ ((( @")).not.toThrow();
  });
});
