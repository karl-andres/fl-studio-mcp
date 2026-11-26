import type { AudioInfo } from "./model";
export const MAX_AUDIO_BYTES = 20 * 1024 * 1024;
export function mediaType(name: string): AudioInfo["media_type"] {
  const extension = name.toLowerCase().split(".").pop();
  const media: Record<string, AudioInfo["media_type"]> = {
    mp3: "audio/mpeg",
    wav: "audio/wav",
    m4a: "audio/mp4",
  };
  if (!extension || !media[extension])
    throw Error("Choose an MP3, WAV or M4A file.");
  return media[extension];
}
export async function inspectReference(file: File): Promise<AudioInfo> {
  if (!file.size || file.size > MAX_AUDIO_BYTES)
    throw Error("Audio must be nonempty and at most 20 MB.");
  const media_type = mediaType(file.name);
  const audio = document.createElement("audio");
  if (!audio.canPlayType(media_type))
    throw Error("This browser cannot play that audio format. Try WAV or MP3.");
  const url = URL.createObjectURL(file);
  let duration: number;
  try {
    duration = await new Promise<number>((resolve, reject) => {
      const timeout = setTimeout(
        () => reject(Error("Audio could not be opened. Try another file.")),
        10000,
      );
      audio.onloadedmetadata = () => {
        clearTimeout(timeout);
        resolve(audio.duration);
      };
      audio.onerror = () => {
        clearTimeout(timeout);
        reject(Error("Invalid or unsupported audio file."));
      };
      audio.preload = "metadata";
      audio.src = url;
    });
  } finally {
    audio.removeAttribute("src");
    audio.load();
    URL.revokeObjectURL(url);
  }
  if (!Number.isFinite(duration) || duration <= 0 || duration > 7200)
    throw Error("Audio duration must be positive and at most two hours.");
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );
  const sha256 = Array.from(new Uint8Array(digest), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");
  return {
    name: file.name.slice(0, 200),
    sha256,
    size: file.size,
    duration,
    media_type,
  };
}
export async function loadChatReference(
  fileId: string,
  name: string,
): Promise<File> {
  if (!window.openai?.getFileDownloadUrl)
    throw Error(
      "This ChatGPT session does not expose attachment access. Use Attach audio instead.",
    );
  const { downloadUrl } = await window.openai.getFileDownloadUrl({ fileId });
  const url = new URL(downloadUrl);
  // Only a host-issued URL on the explicit file origin. Never fetch model-provided URLs.
  if (
    url.protocol !== "https:" ||
    url.hostname !== "files.oaiusercontent.com" ||
    url.username ||
    url.password
  )
    throw Error(
      "This attachment link is not supported. Use Attach audio instead.",
    );
  const response = await fetch(url, { credentials: "omit", redirect: "error" });
  if (!response.ok || !response.body)
    throw Error(
      "Chat attachment could not be opened. Use Attach audio instead.",
    );
  const reader = response.body.getReader(),
    chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_AUDIO_BYTES) throw Error("Audio exceeds 20 MB.");
      chunks.push(new Uint8Array(value));
    }
  } finally {
    await reader.cancel();
  }
  return new File(chunks, name, { type: mediaType(name) });
}
