export type Version = [number, number, number];

/** The first `major.minor.patch` in the first line of a CLI's `--version` output, or null. */
export function versionOf(text: string): Version | null {
  const found = /(\d+)\.(\d+)\.(\d+)/.exec(text.split("\n")[0] ?? "");
  return found === null ? null : [Number(found[1]), Number(found[2]), Number(found[3])];
}

/** True when `version` is lower than the version written in `than`. */
export function isOlder(version: Version, than: string): boolean {
  const target = versionOf(than)!;
  for (let index = 0; index < 3; index += 1) {
    if (version[index]! !== target[index]!) return version[index]! < target[index]!;
  }
  return false;
}
