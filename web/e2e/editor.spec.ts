import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    let saved: unknown;
    window.openai = {
      theme: "light",
      setWidgetState: async (s) => {
        saved = s;
        (window as unknown as { saved: unknown }).saved = s;
      },
      callTool: async (name, args) => {
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
              download_url: "https://example.com/downloads/test",
              token: "test",
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
  await page.locator("input[type=file]").setInputFiles({
    name: "song.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(song)),
  });
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByLabel("Song title")).toHaveValue("Imported song");
  await page.locator("input[type=file]").setInputFiles({
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
