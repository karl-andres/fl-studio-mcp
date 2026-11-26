export type AudioInfo = {
  name: string;
  sha256: string;
  size: number;
  duration: number;
  media_type: "audio/mpeg" | "audio/wav" | "audio/mp4";
};
export type Timing = { key: string; start: number | null; end: number | null };
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
  version: 2;
  revision: number;
  title: string;
  tempo: number;
  meter: "4/4" | "3/4" | "6/8";
  sections: Section[];
  arrangement: string[];
  timing_mode: "beats" | "performance";
  audio: AudioInfo | null;
  performance: Timing[];
};
export type NoteEvent = {
  section: string;
  chord: string;
  start: number;
  beats: number;
  notes: number[];
  start_seconds?: number;
  duration_seconds?: number;
};
export const id = () => crypto.randomUUID();
export const fresh = (): Song => ({
  version: 2,
  timing_mode: "beats",
  audio: null,
  performance: [],
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
  const source = raw as Record<string, unknown>;
  if (source.version !== 1 && source.version !== 2)
    throw Error("Unsupported song version");
  if (
    source.version === 1 &&
    ["audio", "performance", "timing_mode"].some((key) => key in source)
  )
    throw Error("Invalid version 1 backup");
  const s = {
    ...source,
    version: 2,
    timing_mode: source.timing_mode ?? "beats",
    audio: source.audio ?? null,
    performance: source.performance ?? [],
  } as Song;
  if (
    s.version !== 2 ||
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
  if (
    !["beats", "performance"].includes(s.timing_mode) ||
    !Array.isArray(s.performance)
  )
    throw Error("Invalid timing mode");
  if (s.audio !== null) {
    const a = s.audio;
    if (
      typeof a.name !== "string" ||
      !a.name ||
      a.name.length > 200 ||
      !/^[a-f0-9]{64}$/.test(a.sha256) ||
      !Number.isInteger(a.size) ||
      a.size <= 0 ||
      a.size > 20 * 1024 * 1024 ||
      !Number.isFinite(a.duration) ||
      a.duration <= 0 ||
      a.duration > 7200 ||
      !["audio/mpeg", "audio/wav", "audio/mp4"].includes(a.media_type)
    )
      throw Error("Invalid audio metadata");
  }
  if (s.timing_mode === "performance" && !s.audio)
    throw Error("Attach reference audio before marking timings");
  const sequence = occurrences(s);
  if (
    s.performance.length &&
    (s.performance.length !== sequence.length ||
      s.performance.some((m, i) => m.key !== sequence[i].key))
  )
    throw Error("Progression changed: mark timings again");
  let previous = 0;
  for (const m of s.performance) {
    if (m.start === null) {
      if (m.end !== null) throw Error("Set a start before an end");
      continue;
    }
    if (
      !Number.isFinite(m.start) ||
      m.start < previous ||
      !s.audio ||
      m.start < 0 ||
      m.start >= s.audio.duration
    )
      throw Error("Chord starts must be in order and within the audio");
    if (
      m.end !== null &&
      (!Number.isFinite(m.end) || m.end <= m.start || m.end > s.audio.duration)
    )
      throw Error("Chord end must follow its start and stay within the audio");
    previous = m.end ?? m.start;
  }
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
  const candidate = parseSong({
    ...proposal,
    version: 2,
    audio: current.audio,
    timing_mode: current.timing_mode,
    performance: [],
  });
  candidate.performance =
    sequenceKey(candidate) === sequenceKey(current) ? current.performance : [];
  return { ...parseSong(candidate), revision: current.revision + 1 };
}

export function occurrences(song: Song) {
  return song.arrangement.flatMap((key, index) => {
    const section = song.sections.find((s) => s.id === key)!;
    return section.chords.map((chord, position) => ({
      key: `${index}:${position}:${key}:${chord.id}`,
      section: section.name,
      chord: chord.symbol,
    }));
  });
}
export const sequenceKey = (song: Song) =>
  JSON.stringify(occurrences(song).map((item) => item.key));
export function reconcileTiming(before: Song, next: Song): Song {
  return sequenceKey(before) !== sequenceKey(next) ||
    before.audio?.sha256 !== next.audio?.sha256
    ? { ...next, performance: [] }
    : next;
}
export function emptyMarks(song: Song): Timing[] {
  return occurrences(song).map((item) => ({
    key: item.key,
    start: null,
    end: null,
  }));
}
export function markNext(song: Song, time: number): Timing[] {
  const marks = song.performance.length
    ? song.performance.map((m) => ({ ...m }))
    : emptyMarks(song);
  const index = marks.findIndex((m) => m.start === null);
  if (index < 0)
    throw Error("All chords are marked. Set the final end or reset timing.");
  if (
    !song.audio ||
    time < 0 ||
    time >= song.audio.duration ||
    (index > 0 && time <= marks[index - 1].start!)
  )
    throw Error("Seek forward past the previous chord start.");
  if (index > 0) marks[index - 1].end = time;
  marks[index].start = time;
  return marks;
}
export function endProgression(song: Song, time: number): Timing[] {
  const marks = song.performance.map((m) => ({ ...m }));
  if (!marks.length || marks.some((m) => m.start === null))
    throw Error("Mark all chord starts before ending the progression.");
  const last = marks[marks.length - 1];
  if (!song.audio || time <= last.start! || time > song.audio.duration)
    throw Error("End after the last chord start, within the audio.");
  last.end = time;
  return marks;
}

export function performanceComplete(song: Song): boolean {
  return (
    song.timing_mode === "beats" ||
    (song.performance.length > 0 &&
      song.performance.every((m) => m.start !== null && m.end !== null))
  );
}
