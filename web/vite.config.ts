import { defineConfig, type Plugin } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";

// Preserve license notices for the dependency code actually included in the widget.
function notices(): Plugin {
  return {
    name: "songsflow-license-notices",
    generateBundle(_options, bundle) {
      const packages = new Map<string, string>();
      for (const output of Object.values(bundle)) {
        if (output.type !== "chunk") continue;
        for (const [module, info] of Object.entries(output.modules)) {
          if (!info.renderedLength || !module.includes("/node_modules/"))
            continue;
          let directory = dirname(module.split("?")[0]);
          while (
            directory !== "/" &&
            !existsSync(join(directory, "package.json"))
          )
            directory = dirname(directory);
          if (directory === "/" || !directory.includes("/node_modules/"))
            continue;
          const pkg = JSON.parse(
            readFileSync(join(directory, "package.json"), "utf8"),
          );
          const key = `${pkg.name}@${pkg.version}`;
          if (packages.has(key)) continue;
          const files = readdirSync(directory).filter((name) =>
            /^(licen[sc]e|copying|notice)(\..*)?$/i.test(name),
          );
          const text = files
            .map((file) => readFileSync(join(directory, file), "utf8"))
            .join("\n");
          if (!text)
            throw Error(`Missing license text for bundled dependency ${key}`);
          packages.set(
            key,
            `${key}\nLicense: ${pkg.license ?? "See text below"}\n${text}`,
          );
        }
      }
      this.emitFile({
        type: "asset",
        fileName: "third-party-notices.txt",
        source: [...packages.values()].sort().join("\n\n---\n\n"),
      });
    },
  };
}
export default defineConfig({
  plugins: [viteSingleFile(), notices()],
  build: { outDir: "../src/songsflow/widget", emptyOutDir: true },
});
