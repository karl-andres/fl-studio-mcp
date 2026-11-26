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
