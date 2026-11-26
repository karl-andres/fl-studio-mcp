import { describe, it, expect } from "vitest";
import {
  fresh,
  parseSong,
  remapAnchors,
  acceptProposal,
  barBeats,
} from "./model";
const c = { id: "c", symbol: "C", beats: 4, anchor: 6 };
describe("song editing", () => {
  it("remaps insertion and deletion", () => {
    expect(remapAnchors("Hello world", "Oh Hello world", [c])[0].anchor).toBe(
      9,
    );
    expect(remapAnchors("Hello world", "Hello ", [c])[0].anchor).toBe(null);
  });
  it("uses Unicode codepoints", () => {
    expect(
      remapAnchors("🌎 hi", "Hello 🌎 hi", [{ ...c, anchor: 2 }])[0].anchor,
    ).toBe(8);
  });
  it("rejects stale proposals", () => {
    expect(() =>
      acceptProposal({ ...fresh(), revision: 2 }, fresh(), 0),
    ).toThrow("out of date");
  });
  it("advances accepted revision", () => {
    expect(acceptProposal(fresh(), fresh(), 0).revision).toBe(1);
  });
  it("round trips backups", () =>
    expect(parseSong(JSON.parse(JSON.stringify(fresh())))).toEqual(fresh()));
  it("rejects unknown arrangements", () =>
    expect(() => parseSong({ ...fresh(), arrangement: ["bad"] })).toThrow());
  it("uses correct quarter note bar lengths", () =>
    expect(["4/4", "3/4", "6/8"].map(barBeats)).toEqual([4, 3, 3]));
});

import {
  emptyMarks,
  markNext,
  endProgression,
  occurrences,
  reconcileTiming,
  type Song,
} from "./model";
function performanceSong(): Song {
  const s = fresh();
  s.audio = {
    name: "take.wav",
    sha256: "a".repeat(64),
    size: 100,
    duration: 10,
    media_type: "audio/wav",
  };
  s.timing_mode = "performance";
  s.sections[0].chords = [
    { id: "c", symbol: "C", anchor: 0, beats: 4 },
    { id: "f", symbol: "F", anchor: 0, beats: 4 },
  ];
  s.arrangement = ["verse", "verse"];
  return s;
}
describe("reference timing", () => {
  it("migrates legacy backups", () => {
    const { audio, performance, timing_mode, ...legacy } = fresh();
    const restored = parseSong({ ...legacy, version: 1 });
    expect(restored.version).toBe(2);
    expect(restored.audio).toBe(null);
  });
  it("captures each repeated chord separately and ends the last one", () => {
    const s = performanceSong();
    for (const at of [0.5, 2, 4, 6]) s.performance = markNext(s, at);
    s.performance = endProgression(s, 8);
    expect(s.performance.map((m) => [m.start, m.end])).toEqual([
      [0.5, 2],
      [2, 4],
      [4, 6],
      [6, 8],
    ]);
    expect(new Set(occurrences(s).map((o) => o.key)).size).toBe(4);
    expect(parseSong(s).performance).toEqual(s.performance);
  });
  it("rejects backward taps and ending before all starts", () => {
    const s = performanceSong();
    s.performance = markNext(s, 2);
    expect(() => markNext(s, 1)).toThrow("Seek forward");
    expect(() => endProgression(s, 8)).toThrow("all chord starts");
  });
  it("invalidates structural changes but preserves words and chord qualities", () => {
    const s = performanceSong();
    s.performance = emptyMarks(s);
    const words = structuredClone(s);
    words.sections[0].lyrics = "New words";
    words.sections[0].chords[0].symbol = "Cm";
    expect(reconcileTiming(s, words).performance).toEqual(s.performance);
    expect(
      reconcileTiming(s, { ...s, arrangement: ["verse"] }).performance,
    ).toEqual([]);
  });
  it("rejects overlap and preserves gaps", () => {
    const s = performanceSong();
    s.performance = emptyMarks(s);
    s.performance[0] = { ...s.performance[0], start: 1, end: 2 };
    s.performance[1] = { ...s.performance[1], start: 3, end: 4 };
    expect(parseSong(s).performance[1].start).toBe(3);
    s.performance[1].start = 1.5;
    expect(() => parseSong(s)).toThrow("in order");
  });
  it("keeps timing when accepting a lyric revision", () => {
    const s = performanceSong();
    s.performance = emptyMarks(s);
    const proposal = structuredClone(s);
    proposal.title = "Revised";
    proposal.performance = [];
    expect(acceptProposal(s, proposal, 0).performance).toEqual(s.performance);
  });
});
