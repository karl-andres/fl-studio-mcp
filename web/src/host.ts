import type { Song } from "./model";
export type Result = {
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
  content?: { type: string; text?: string }[];
};
type Host = {
  theme?: string;
  getFileDownloadUrl?: (args: {
    fileId: string;
  }) => Promise<{ downloadUrl: string }>;
  toolOutput?: Record<string, unknown>;
  widgetState?: { song?: Song; dismissed?: string[]; exportTokens?: string[] };
  setWidgetState?: (state: unknown) => Promise<void>;
  callTool?: (name: string, args: Record<string, unknown>) => Promise<Result>;
  requestDisplayMode?: (args: { mode: string }) => Promise<unknown>;
  openExternal?: (args: { href: string }) => void;
  sendFollowUpMessage?: (args: { prompt: string }) => Promise<unknown>;
};
declare global {
  interface Window {
    openai?: Host;
  }
}
export async function call(
  name: string,
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  if (!window.openai?.callTool)
    throw Error(
      "Open this app in ChatGPT to preview and export. The standalone editor supports writing and local backups.",
    );
  const response = await window.openai.callTool(name, args);
  if (response.isError)
    throw Error(
      "The operation failed. Check your song settings and try again.",
    );
  if (!response.structuredContent)
    throw Error("The server returned no song data.");
  return response.structuredContent;
}
export function saveLocal(data: Blob, filename: string) {
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
