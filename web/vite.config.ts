import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base = subpasta do GitHub Pages. O painel novo e servido em /painel/ ao lado
// do antigo, de proposito: da para comparar os dois lado a lado antes de trocar
// a raiz. Os dados ficam um nivel acima (../data/), compartilhados com o painel
// antigo -- uma fonte so, nao duas.
export default defineConfig({
  base: "/vendas-liquidos/painel/",
  plugins: [react()],
  // O limite e tripwire de crescimento, nao enfeite: o bundle foi de 683 KB
  // (recharts 2) para 738 KB (recharts 3), e 800 deixa folga para uma secao
  // nova sem transformar o aviso em ruido permanente que ninguem le.
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 800 },
});
