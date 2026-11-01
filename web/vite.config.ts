import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base = subpasta do GitHub Pages. O painel novo e servido em /painel/ ao lado
// do antigo, de proposito: da para comparar os dois lado a lado antes de trocar
// a raiz. Os dados ficam um nivel acima (../data/), compartilhados com o painel
// antigo -- uma fonte so, nao duas.
export default defineConfig({
  base: "/vendas-liquidos/painel/",
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 700 },
});
