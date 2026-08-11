import { defineConfig } from "vite";

// На GitHub Pages сайт лежит по адресу /<repo>/. Появится свой домен —
// поменяй base на "/".
export default defineConfig({
  base: process.env.GITHUB_ACTIONS ? "/spravka/" : "/",
  build: { outDir: "dist", emptyOutDir: true },
});
