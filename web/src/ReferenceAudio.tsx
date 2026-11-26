import { useEffect, useRef, useState } from "react";
import {
  emptyMarks,
  endProgression,
  markNext,
  occurrences,
  type Song,
  type AudioInfo,
} from "./model";
import { inspectReference, loadChatReference } from "./reference";

type Props = {
  disabled: boolean;
  previewPlaying: boolean;
  onPlay: () => void;
  song: Song;
  file: File | null;
  onAttach: (file: File, info: AudioInfo) => Promise<void>;
  onChange: (song: Song) => void;
  onError: (message: string) => void;
  onRemove: () => Promise<void>;
};
function Seconds({
  label,
  value,
  max,
  onChange,
}: {
  label: string;
  value: number | null;
  max: number;
  onChange: (n: number | null) => void;
}) {
  const [draft, setDraft] = useState(value === null ? "" : value.toFixed(3));
  useEffect(() => setDraft(value === null ? "" : value.toFixed(3)), [value]);
  return (
    <input
      aria-label={label}
      type="number"
      min={0}
      max={max}
      step="0.001"
      placeholder="—"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const n = draft === "" ? null : Number(draft);
        if (n !== null && (!Number.isFinite(n) || n < 0 || n > max)) {
          setDraft(value === null ? "" : value.toFixed(3));
          return;
        }
        onChange(n);
        setDraft(value === null ? "" : value.toFixed(3));
      }}
    />
  );
}
export function ReferenceAudio({
  song,
  disabled,
  previewPlaying,
  onPlay,
  file,
  onAttach,
  onChange,
  onError,
  onRemove,
}: Props) {
  const player = useRef<HTMLAudioElement>(null);
  const [url, setUrl] = useState(""),
    [working, setWorking] = useState(false),
    [time, setTime] = useState(0);
  useEffect(() => {
    if (!file) {
      setUrl("");
      setTime(0);
      return;
    }
    const next = URL.createObjectURL(file);
    setUrl(next);
    setTime(0);
    return () => {
      player.current?.pause();
      URL.revokeObjectURL(next);
    };
  }, [file]);
  useEffect(() => {
    if (previewPlaying) player.current?.pause();
  }, [previewPlaying]);
  const sequence = occurrences(song),
    marks = song.performance.length ? song.performance : emptyMarks(song);
  const next = marks.findIndex((m) => m.start === null);
  async function attach(file: File) {
    setWorking(true);
    try {
      await onAttach(file, await inspectReference(file));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  function edit(action: () => Song) {
    try {
      onChange(action());
    } catch (e) {
      onError((e as Error).message);
    }
  }
  function update(index: number, field: "start" | "end", value: number | null) {
    edit(() => ({
      ...song,
      performance: marks.map((mark, i) =>
        i === index
          ? {
              ...mark,
              [field]: value,
              ...(field === "start" && value === null ? { end: null } : {}),
            }
          : mark,
      ),
    }));
  }
  const [hostOutput, setHostOutput] = useState(window.openai?.toolOutput);
  useEffect(() => {
    const sync = (event: Event) => {
      const output = (event as CustomEvent).detail?.globals?.toolOutput;
      if (output) setHostOutput(output);
    };
    window.addEventListener("openai:set_globals", sync);
    return () => window.removeEventListener("openai:set_globals", sync);
  }, []);
  return (
    <section
      className="reference-panel"
      aria-label="Reference audio and performance timing"
    >
      <div className="sectionheading">
        <div>
          <span className="eyebrow">REFERENCE AUDIO</span>
          <h2>Your recording. Your timing.</h2>
        </div>
        <label className="filebutton">
          {working ? "Opening audio…" : "Attach audio"}
          <input
            aria-label="Attach reference audio"
            type="file"
            accept=".mp3,.wav,.m4a,audio/mpeg,audio/wav,audio/mp4"
            disabled={working || disabled}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void attach(file);
            }}
          />
        </label>
      </div>
      <p className="muted">
        Write the lyrics and chords yourself. Audio is a reference only—no
        transcription or chord detection. MP3, WAV or M4A, up to 20 MB.
      </p>
      {typeof hostOutput?.audio_file_id === "string" &&
        window.openai?.getFileDownloadUrl && (
          <button
            disabled={working || disabled}
            onClick={() => {
              setWorking(true);
              void loadChatReference(
                hostOutput.audio_file_id as string,
                typeof hostOutput.audio_filename === "string"
                  ? hostOutput.audio_filename
                  : "reference.mp3",
              )
                .then((file) => attach(file))
                .catch((e) => onError((e as Error).message))
                .finally(() => setWorking(false));
            }}
          >
            Load chat attachment
          </button>
        )}
      {song.audio && (
        <>
          <p>
            {song.audio.name} · {song.audio.duration.toFixed(2)} seconds{" "}
            <button
              className="quiet"
              disabled={disabled || working}
              onClick={() => void onRemove()}
            >
              Remove reference
            </button>
          </p>
          {!file && (
            <p role="status" className="audio-notice">
              Reattach the same audio file to listen or export the original.
              Your saved timing marks are retained.
            </p>
          )}
          {url && (
            <audio
              ref={player}
              src={url}
              controls
              preload="metadata"
              aria-label="Reference playback"
              onPlay={onPlay}
              onError={() =>
                onError(
                  "This browser could not play the reference. Try another audio format.",
                )
              }
              onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
            />
          )}
          <label>
            Chord timing
            <select
              aria-label="Chord timing mode"
              value={song.timing_mode}
              onChange={(e) =>
                onChange({
                  ...song,
                  timing_mode: e.target.value as Song["timing_mode"],
                })
              }
            >
              <option value="beats">Beat durations</option>
              <option value="performance">Follow the performance</option>
            </select>
          </label>
          <p className="muted">
            Original audio is unchanged when you rearrange the song. Reordering
            chords clears timing marks. Changing lyrics or chord qualities keeps
            them.
          </p>
          {song.timing_mode === "performance" && (
            <>
              <div className="actions">
                <button
                  disabled={!file || !sequence.length || next < 0}
                  onClick={() =>
                    edit(() => ({
                      ...song,
                      performance: markNext(
                        song,
                        player.current?.currentTime ?? 0,
                      ),
                    }))
                  }
                >
                  Mark next chord
                  {next >= 0 && sequence[next]
                    ? ` · ${sequence[next].chord}`
                    : ""}
                </button>
                <button
                  disabled={!file || !sequence.length || next >= 0}
                  onClick={() =>
                    edit(() => ({
                      ...song,
                      performance: endProgression(
                        song,
                        player.current?.currentTime ?? 0,
                      ),
                    }))
                  }
                >
                  End progression
                </button>
                <button onClick={() => onChange({ ...song, performance: [] })}>
                  Reset timing
                </button>
                <output aria-live="off">
                  {time.toFixed(2)} / {song.audio.duration.toFixed(2)} s
                </output>
              </div>
              <p className="muted">
                Play the recording and tap at each chord change. Set the last
                end, or enter timestamps below. Starts and ends are seconds from
                the beginning; gaps stay silent.
              </p>
              <div
                className="performance-table"
                role="group"
                aria-label="Performance timestamps"
              >
                {sequence.map((item, index) => (
                  <div className="performance-row" key={item.key}>
                    <span>
                      <b>{item.chord}</b>{" "}
                      <small>
                        {index + 1} · {item.section}
                      </small>
                    </span>
                    <label>
                      Start (s)
                      <Seconds
                        label={`Chord ${index + 1} start seconds`}
                        value={marks[index].start}
                        max={song.audio!.duration}
                        onChange={(n) => update(index, "start", n)}
                      />
                    </label>
                    <label>
                      End (s)
                      <Seconds
                        label={`Chord ${index + 1} end seconds`}
                        value={marks[index].end}
                        max={song.audio!.duration}
                        onChange={(n) => update(index, "end", n)}
                      />
                    </label>
                    <button
                      disabled={!file || marks[index].start === null}
                      onClick={() => {
                        if (player.current) {
                          player.current.currentTime = marks[index].start!;
                          void player.current
                            .play()
                            .catch(() =>
                              onError(
                                "Press play on the audio controls to enable playback.",
                              ),
                            );
                        }
                      }}
                    >
                      Listen
                    </button>
                  </div>
                ))}
              </div>
              {!sequence.length && (
                <p>
                  Add chords to your arranged sections, then mark their timing.
                </p>
              )}
            </>
          )}
        </>
      )}
      <p className="privacy">
        Audio stays in this browser while editing. Explicit audio export uploads
        a temporary copy; JSON backups contain metadata and timing, not the
        recording.
      </p>
    </section>
  );
}
