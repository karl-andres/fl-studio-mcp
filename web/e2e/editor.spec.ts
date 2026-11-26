import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    let saved: unknown;
    (window as unknown as { toolCalls: string[] }).toolCalls = [];
    window.openai = {
      theme: "light",
      setWidgetState: async (s) => {
        saved = s;
        (window as unknown as { saved: unknown }).saved = s;
      },
      callTool: async (name, args) => {
        (window as unknown as { toolCalls: string[] }).toolCalls.push(name);
        const song = args.document as {
          sections: { chords: { symbol: string; beats: number }[] }[];
        };
        if (name === "validate_song")
          return {
            structuredContent: {
              song,
              events: [
                {
                  section: "Verse",
                  chord: "C",
                  start: 0,
                  beats: 4,
                  notes: [48, 52, 55],
                },
              ],
            },
          };
        if (name === "export_song")
          return {
            structuredContent: {
              download_url: `https://example.com/downloads/${args.format ?? "midi"}`,
              filename:
                args.format === "lyrics"
                  ? "songsflow.lyrics.txt"
                  : args.format === "json"
                    ? "songsflow.song.json"
                    : "songsflow.mid",
              token: "test-" + (args.format ?? "midi"),
            },
          };
        if (name === "prepare_audio_export")
          return {
            structuredContent: {
              upload_url: "https://example.com/audio-exports/ticket",
            },
          };
        return { structuredContent: { revoked: true } };
      },
    };
  });
  await page.goto("/");
});
test("write, attach chords, arrange, preview, export and clear", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Song title").fill("Morning light");
  await page.getByLabel("Lyrics Select").fill("Hello world");
  await page.getByRole("button", { name: "+ Add C", exact: true }).click();
  await expect(page.getByLabel("C duration")).toHaveValue("4");
  await expect(page.getByLabel("Lyrics with chords")).toContainText(
    "Hello world",
  );
  await page.getByRole("button", { name: "+ Section", exact: true }).click();
  await page.getByLabel("Section name").fill("Chorus");
  await page.getByLabel("Add arrangement section").selectOption("verse");
  await expect(page.locator(".arrangementlist>div")).toHaveCount(3);
  await page.getByRole("button", { name: "Preview", exact: false }).click();
  await expect(
    page.getByRole("button", { name: "Stop", exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop", exact: false }).click();
  await page.getByRole("button", { name: "Export MIDI" }).click();
  await expect(
    page.getByRole("link", { name: "Download songsflow.mid" }),
  ).toBeVisible();
  await page.waitForTimeout(400);
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { saved: { song: { title: string } } }).saved.song
          .title,
    ),
  ).toBe("Morning light");
  await page.screenshot({
    path: "/workspace/songsflow-cloud/editor.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Clear draft", exact: true }).click();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByLabel("Song title")).toHaveValue("Untitled song");
  await expect(
    page.getByRole("link", { name: "Download songsflow.mid" }),
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});
test("renders hostile lyrics as plain text on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Lyrics Select").fill("<img src=x onerror=alert(1)>");
  await expect(page.getByLabel("Lyrics with chords")).toContainText(
    "<img src=x onerror=alert(1)>",
  );
  await expect(page.locator(".lyric-sheet img")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("rejects stale ChatGPT proposals", async ({ page }) => {
  await page.getByLabel("Song title").fill("My newer draft");
  await page.evaluate(() => {
    const song = {
      version: 1,
      revision: 0,
      title: "Old suggestion",
      tempo: 120,
      meter: "4/4",
      sections: [{ id: "v", name: "Verse", lyrics: "Old words", chords: [] }],
      arrangement: ["v"],
    };
    window.dispatchEvent(
      new CustomEvent("openai:set_globals", {
        detail: {
          globals: {
            toolOutput: {
              action: "proposal",
              base_revision: 0,
              proposal_id: "test",
              song,
            },
          },
        },
      }),
    );
  });
  await page.getByRole("button", { name: "Accept suggestion" }).click();
  await expect(page.getByRole("alert")).toContainText("out of date");
  await expect(page.getByLabel("Song title")).toHaveValue("My newer draft");
});

test("imports a backup only after confirmation and rejects oversized files", async ({
  page,
}) => {
  const song = {
    version: 1,
    revision: 0,
    title: "Imported song",
    tempo: 90,
    meter: "6/8",
    sections: [
      { id: "v", name: "Verse", lyrics: "Imported words", chords: [] },
    ],
    arrangement: ["v"],
  };
  await page.locator('input[accept=".json,application/json"]').setInputFiles({
    name: "song.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(song)),
  });
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByLabel("Song title")).toHaveValue("Imported song");
  await page.locator('input[accept=".json,application/json"]').setInputFiles({
    name: "large.json",
    mimeType: "application/json",
    buffer: Buffer.alloc(1_048_577),
  });
  await expect(page.getByRole("alert")).toContainText("1 MB");
  await expect(page.getByLabel("Song title")).toHaveValue("Imported song");
});
test("edits tempo and durations without rejecting intermediate keystrokes", async ({
  page,
}) => {
  await page.getByLabel("Tempo", { exact: true }).fill("90");
  await page.getByLabel("Tempo", { exact: true }).blur();
  await expect(page.getByLabel("Tempo", { exact: true })).toHaveValue("90");
  await page.getByRole("button", { name: "+ Add C", exact: true }).click();
  await page.getByLabel("C duration").fill("1.5");
  await page.getByLabel("C duration").blur();
  await expect(page.getByLabel("C duration")).toHaveValue("1.5");
});

function referenceWav() {
  const data = Buffer.alloc(44 + 8 * 8000 * 2);
  data.write("RIFF", 0);
  data.writeUInt32LE(data.length - 8, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(8000, 24);
  data.writeUInt32LE(16000, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(data.length - 44, 40);
  return data;
}
test("reference audio, live marks, corrections, repeated chords and three-file export", async ({
  page,
}) => {
  const data = referenceWav();
  let audioUploads = 0;
  await page.route(
    "https://example.com/audio-exports/ticket",
    async (route) => {
      const headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "Content-Type",
      };
      if (route.request().method() === "OPTIONS") {
        await route.fulfill({ status: 204, headers });
        return;
      }
      expect(route.request().postDataBuffer()).toEqual(data);
      audioUploads++;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers,
        body: JSON.stringify({
          download_url: "https://example.com/downloads/audio",
          filename: "reference.wav",
          token: "audio-test",
        }),
      });
    },
  );
  await page.getByLabel("Lyrics Select").fill("Hello world");
  await page.getByRole("button", { name: "+ Add C", exact: true }).click();
  await page.getByRole("button", { name: "+ Add C", exact: true }).click();
  await page.getByLabel("Add arrangement section").selectOption("verse");
  await page.getByLabel("Attach reference audio").setInputFiles({
    name: "reference.wav",
    mimeType: "audio/wav",
    buffer: data,
  });
  await expect(page.getByLabel("Reference playback")).toBeVisible();
  await expect(page.getByLabel("Chord timing mode")).toHaveValue("performance");
  expect(audioUploads).toBe(0);
  expect(
    await page.evaluate(
      () => (window as unknown as { toolCalls: string[] }).toolCalls,
    ),
  ).toEqual([]);
  const playback = page.getByLabel("Reference playback");
  expect(await playback.evaluate((el: HTMLAudioElement) => el.paused)).toBe(
    true,
  );
  await playback.evaluate(async (el: HTMLAudioElement) => {
    await el.play();
    el.pause();
  });
  for (const at of [0.75, 1.5, 3.1, 5.2]) {
    await playback.evaluate((el: HTMLAudioElement, at) => {
      el.currentTime = at;
    }, at);
    await page.getByRole("button", { name: /Mark next chord/ }).click();
  }
  await playback.evaluate((el: HTMLAudioElement) => {
    el.currentTime = 7.7;
  });
  await page
    .getByRole("button", { name: "End progression", exact: true })
    .click();
  await expect(page.getByLabel("Chord 1 start seconds")).toHaveValue("0.750");
  await page.getByLabel("Chord 1 end seconds").fill("1.2");
  await page.getByLabel("Chord 1 end seconds").blur();
  await expect(page.getByLabel("Chord 1 end seconds")).toHaveValue("1.200");
  await page.getByLabel("Chord 1 symbol").selectOption("Cm");
  await expect(page.getByLabel("Chord 1 start seconds")).toHaveValue("0.750");
  await page
    .getByRole("button", { name: "Export for FL Studio", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Download songsflow.mid", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: "Download songsflow.lyrics.txt",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download reference.wav", exact: true }),
  ).toBeVisible();
  expect(audioUploads).toBe(1);
  await page.waitForTimeout(350);
  const saved = await page.evaluate(
    () =>
      (window as unknown as { saved: { song: Record<string, unknown> } }).saved
        .song,
  );
  expect(Object.keys(saved.audio as object).sort()).toEqual([
    "duration",
    "media_type",
    "name",
    "sha256",
    "size",
  ]);
  // Reopening a backup preserves marks, but intentionally drops the in-memory audio File.
  await page.locator('input[accept=".json,application/json"]').setInputFiles({
    name: "backup.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(saved)),
  });
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByText(/^Reattach the same audio file/)).toBeVisible();
  await expect(page.getByLabel("Chord 1 start seconds")).toHaveValue("0.750");
  await page.getByLabel("Attach reference audio").setInputFiles({
    name: "reference.wav",
    mimeType: "audio/wav",
    buffer: data,
  });
  await expect(page.getByLabel("Reference playback")).toBeVisible();
  await expect(page.getByLabel("Chord 1 start seconds")).toHaveValue("0.750");
  // A structural arrangement change invalidates the marks, not the attached recording.
  await page.getByLabel("Add arrangement section").selectOption("verse");
  await expect(page.getByLabel("Chord 1 start seconds")).toHaveValue("");
  await expect(page.getByLabel("Reference playback")).toBeVisible();
});
test("invalid audio does not replace the draft and incomplete timing blocks MIDI", async ({
  page,
}) => {
  await page.getByLabel("Attach reference audio").setInputFiles({
    name: "fake.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("not audio"),
  });
  await expect(page.getByRole("alert")).toContainText("Invalid or unsupported");
  await page.getByLabel("Attach reference audio").setInputFiles({
    name: "reference.wav",
    mimeType: "audio/wav",
    buffer: referenceWav(),
  });
  await expect(page.getByLabel("Reference playback")).toBeVisible();
  await page.getByRole("button", { name: "+ Add C", exact: true }).click();
  await page.getByRole("button", { name: "Export MIDI", exact: false }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Mark every chord start and end",
  );
});
