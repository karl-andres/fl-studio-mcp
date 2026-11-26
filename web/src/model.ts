export type Chord = {
  id: string;
  symbol: string;
  anchor: number | null;
  beats: number;
};
export type Section = {
  id: string;
  name: string;
  lyrics: string;
  chords: Chord[];
};
export type Song = {
  version: 1;
  revision: number;
  title: string;
  tempo: number;
  meter: "4/4" | "3/4" | "6/8";
  sections: Section[];
  arrangement: string[];
};
export type NoteEvent = {
  section: string;
  chord: string;
  start: number;
  beats: number;
  notes: number[];
};
export const id = () => crypto.randomUUID();
export const fresh = (): Song => ({
  version: 1,
  revision: 0,
  title: "Untitled song",
  tempo: 120,
  meter: "4/4",
  sections: [{ id: "verse", name: "Verse", lyrics: "", chords: [] }],
  arrangement: ["verse"],
});
export const barBeats = (meter: string) => (meter === "4/4" ? 4 : 3);
// Offsets use Unicode code points, matching Python validation and avoiding split emoji.
export function remapAnchors(
  before: string,
  after: string,
  chords: Chord[],
): Chord[] {
  const a = Array.from(before),
    b = Array.from(after);
  let start = 0,
    end = 0;
  while (start < Math.min(a.length, b.length) && a[start] === b[start]) start++;
  while (
    end < Math.min(a.length - start, b.length - start) &&
    a[a.length - 1 - end] === b[b.length - 1 - end]
  )
    end++;
  const removed = a.length - end,
    delta = b.length - a.length;
  return chords.map((c) => ({
    ...c,
    anchor:
      c.anchor === null
        ? null
        : c.anchor < start
          ? c.anchor
          : c.anchor >= removed
            ? c.anchor + delta
            : null,
  }));
}
export function parseSong(raw: unknown): Song {
  if (!raw || typeof raw !== "object") throw Error("Invalid song file");
  const s = raw as Song;
  if (
    s.version !== 1 ||
    !Number.isInteger(s.revision) ||
    s.revision < 0 ||
    typeof s.title !== "string" ||
    s.title.length > 200 ||
    !Number.isInteger(s.tempo) ||
    s.tempo < 30 ||
    s.tempo > 300 ||
    !["4/4", "3/4", "6/8"].includes(s.meter) ||
    !Array.isArray(s.sections) ||
    !s.sections.length ||
    s.sections.length > 100 ||
    !Array.isArray(s.arrangement) ||
    s.arrangement.length > 1000
  )
    throw Error("Invalid song settings");
  const ids = new Set<string>();
  for (const section of s.sections) {
    if (
      typeof section.id !== "string" ||
      !section.id ||
      section.id.length > 80 ||
      ids.has(section.id) ||
      typeof section.name !== "string" ||
      !section.name ||
      section.name.length > 80 ||
      typeof section.lyrics !== "string" ||
      Array.from(section.lyrics).length > 50000 ||
      !Array.isArray(section.chords) ||
      section.chords.length > 1000
    )
      throw Error("Invalid section");
    ids.add(section.id);
    const chordIds = new Set<string>();
    for (const c of section.chords) {
      if (
        typeof c.id !== "string" ||
        !c.id ||
        c.id.length > 80 ||
        chordIds.has(c.id) ||
        typeof c.symbol !== "string" ||
        !/^[A-G][#b]?(m7|maj|min|m|7)?$/.test(c.symbol) ||
        !Number.isFinite(c.beats) ||
        c.beats <= 0 ||
        c.beats > 64 ||
        (c.beats * 2) % 1 ||
        (c.anchor !== null &&
          (!Number.isInteger(c.anchor) ||
            c.anchor < 0 ||
            c.anchor > Array.from(section.lyrics).length))
      )
        throw Error("Invalid chord or duration");
      chordIds.add(c.id);
    }
  }
  if (s.arrangement.some((key) => !ids.has(key)))
    throw Error("Unknown arrangement section");
  if (
    s.arrangement.reduce(
      (n, key) => n + s.sections.find((x) => x.id === key)!.chords.length,
      0,
    ) > 10000
  )
    throw Error("Maximum 10,000 arranged chords");
  if (new TextEncoder().encode(JSON.stringify(s)).length > 1_048_576)
    throw Error("Song exceeds 1 MB");
  return s;
}
export function acceptProposal(
  current: Song,
  proposal: Song,
  base: number,
): Song {
  if (current.revision !== base)
    throw Error(
      "This suggestion is out of date. Ask ChatGPT to revise the current draft.",
    );
  return { ...parseSong(proposal), revision: current.revision + 1 };
}
