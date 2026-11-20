import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const FIXTURE_DIR = fileURLToPath(new URL("../fixtures/tectonic/", import.meta.url));

/** A recorded tectonic output file (stderr or kept log) from `test/fixtures/tectonic`. */
export function fixture(name: string): string {
  return readFileSync(`${FIXTURE_DIR}${name}`, "utf8");
}

export function fixtureNames(): string[] {
  return readdirSync(FIXTURE_DIR).filter((name) => !name.startsWith("."));
}
