/**
 * Cubo completo, sob demanda: o unico caminho para CRUZAR duas dimensoes.
 *
 * Os cubos marginais respondem "quanto vendeu a VIBRA" e "quanto foi para SP",
 * nunca "quanto a VIBRA vendeu para SP": a margem de uma dimensao ja somou
 * todas as outras. Para o cruzamento nao ha atalho -- precisa das 725 mil
 * linhas, que sao 2,1 MB comprimidos.
 *
 * Por isso ele NAO entra no boot. A tela inteira abre com 229 KB de cubos
 * marginais; estes 2,1 MB so sao buscados quando o usuario pede um cruzamento,
 * e uma vez por sessao (memoizado abaixo).
 *
 * FORMATO (ver scripts/cubos.py, que o escreve):
 *
 *     gzip de:  "VLQ1" | n_linhas uint32 LE | P uint8 | tipos[P] uint8
 *                       | P colunas contiguas, cada uma com n_linhas valores LE
 *
 * Colunar porque cada coluna tem alcance proprio (mes <= 236 cabe em 1 byte,
 * agente precisa de 2) e porque o gzip comprime muito melhor bytes parecidos
 * lado a lado. O gzip esta no ARQUIVO, nao no transporte: o GitHub Pages nao
 * comprime application/octet-stream, entao confiar no servidor devolveria os
 * 7,3 MB crus.
 */
import { ESCALA, type Dimensao, type Meta } from "./dados";

const MAGICO = "VLQ1";
const U8 = 1, U16 = 2, U32 = 4, I32 = 5;

/** Uma coluna por campo, na ordem de `meta.campos`. */
export type Cubo = { n: number; campos: string[]; cols: Int32Array[] };

function lerColunas(buf: ArrayBuffer, campos: string[]): Cubo {
  const b = new DataView(buf);
  const magico = String.fromCharCode(
    b.getUint8(0), b.getUint8(1), b.getUint8(2), b.getUint8(3));
  if (magico !== MAGICO) {
    throw new Error(`cubo: magico inesperado "${magico}" (esperava ${MAGICO})`);
  }
  const n = b.getUint32(4, true);
  const P = b.getUint8(8);
  if (P !== campos.length) {
    throw new Error(`cubo: ${P} colunas no arquivo contra ${campos.length} em meta.campos`);
  }
  const tipos: number[] = [];
  for (let i = 0; i < P; i++) tipos.push(b.getUint8(9 + i));
  let off = 9 + P;
  const cols: Int32Array[] = [];
  for (let c = 0; c < P; c++) {
    const t = tipos[c]!;
    const col = new Int32Array(n);
    // Copia para Int32Array em vez de criar uma view por tipo: custa uma
    // passada, e em troca quem usa o cubo nao precisa saber a largura de cada
    // coluna -- e largura e justamente o que muda quando a ANP ganha agentes.
    if (t === U8) {
      for (let i = 0; i < n; i++) col[i] = b.getUint8(off + i);
      off += n;
    } else if (t === U16) {
      for (let i = 0; i < n; i++) col[i] = b.getUint16(off + i * 2, true);
      off += n * 2;
    } else if (t === U32) {
      for (let i = 0; i < n; i++) col[i] = b.getUint32(off + i * 4, true);
      off += n * 4;
    } else if (t === I32) {
      // Com sinal de proposito: a ANP publica estornos (quantidade negativa).
      for (let i = 0; i < n; i++) col[i] = b.getInt32(off + i * 4, true);
      off += n * 4;
    } else {
      throw new Error(`cubo: tipo de coluna desconhecido (${t}) em "${campos[c]}"`);
    }
    cols.push(col);
  }
  return { n, campos, cols };
}

/** Descomprime e decodifica. Exportada separada da rede para poder ser testada. */
export async function decodificar(gz: ArrayBuffer, campos: string[]): Promise<Cubo> {
  const fluxo = new Blob([gz]).stream()
    .pipeThrough(new DecompressionStream("gzip"));
  const cru = await new Response(fluxo).arrayBuffer();
  return lerColunas(cru, campos);
}

let cache: Promise<Cubo> | null = null;

/** Busca o cubo completo uma vez por sessao. */
export function carregarCubo(base: string, meta: Meta): Promise<Cubo> {
  if (!cache) {
    cache = (async () => {
      const r = await fetch(base + "cubo.bin.gz");
      if (!r.ok) throw new Error(`cubo.bin.gz: HTTP ${r.status}`);
      const cubo = await decodificar(await r.arrayBuffer(), meta.campos);
      if (cubo.n !== meta.n_linhas) {
        throw new Error(
          `cubo com ${cubo.n} linhas contra ${meta.n_linhas} em meta.json: ` +
          "artefato e metadados de rodadas diferentes");
      }
      return cubo;
    })().catch((e) => { cache = null; throw e; });   // erro nao fica cacheado
  }
  return cache;
}

const CAMPO: Record<Dimensao, string> = {
  prod: "prod", uf: "uf", mkt: "mkt", comp: "comp",
};

export type Tabela = {
  linhas: string[];
  colunas: string[];
  /** [linha][coluna] em mil m3. */
  celulas: number[][];
  totalLinha: number[];
  totalColuna: number[];
  total: number;
};

/**
 * Cruzamento de duas dimensoes, somando os meses pedidos.
 *
 * `meses` e um conjunto de INDICES de mes -- quem chama decide se mes nao
 * consolidado entra. Aqui nao entra regra de negocio nenhuma: uma funcao que
 * silenciosamente descartasse meses seria impossivel de conferir depois.
 */
export function cruzar(cubo: Cubo, rotulosLinha: string[],
                       rotulosColuna: string[], dimLinha: Dimensao,
                       dimColuna: Dimensao, meses: Set<number>): Tabela {
  const iMes = cubo.campos.indexOf("mes");
  const iQtd = cubo.campos.indexOf("qtd");
  const iL = cubo.campos.indexOf(CAMPO[dimLinha]);
  const iC = cubo.campos.indexOf(CAMPO[dimColuna]);
  if (iMes < 0 || iQtd < 0 || iL < 0 || iC < 0) {
    throw new Error(`cruzar: campo ausente em meta.campos (${cubo.campos.join(",")})`);
  }
  const L = rotulosLinha.length, C = rotulosColuna.length;
  const celulas = Array.from({ length: L }, () => new Array<number>(C).fill(0));
  const colMes = cubo.cols[iMes]!, colQtd = cubo.cols[iQtd]!;
  const colL = cubo.cols[iL]!, colC = cubo.cols[iC]!;
  for (let i = 0; i < cubo.n; i++) {
    if (!meses.has(colMes[i]!)) continue;
    const l = colL[i]!, c = colC[i]!;
    celulas[l]![c] = celulas[l]![c]! + colQtd[i]! / ESCALA;
  }
  const totalLinha = celulas.map((r) => r.reduce((a, b) => a + b, 0));
  const totalColuna = new Array<number>(C).fill(0);
  for (let l = 0; l < L; l++) {
    for (let c = 0; c < C; c++) totalColuna[c] = totalColuna[c]! + celulas[l]![c]!;
  }
  return {
    linhas: rotulosLinha, colunas: rotulosColuna, celulas, totalLinha, totalColuna,
    total: totalLinha.reduce((a, b) => a + b, 0),
  };
}

/**
 * CSV da tabela cruzada, para quem vai conferir numero em planilha.
 *
 * Ponto-e-virgula e decimal com virgula: e o que o Excel em pt-BR abre sem
 * caixa de dialogo de importacao. Com BOM, senao o Excel le UTF-8 como ANSI e
 * "COMBUSTÍVEIS" chega "COMBUSTÃVEIS" na planilha de quem recebeu.
 */
export function paraCsv(t: Tabela, cabecalhoCanto: string): string {
  const num = (v: number) => (v ? v.toFixed(4).replace(".", ",") : "0");
  const esc = (s: string) => (/[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  const linhas = [[esc(cabecalhoCanto), ...t.colunas.map(esc), "Total"].join(";")];
  t.linhas.forEach((nome, l) => {
    if (!t.totalLinha[l]) return;      // linha vazia nao vira linha de planilha
    linhas.push([esc(nome), ...t.celulas[l]!.map(num), num(t.totalLinha[l]!)].join(";"));
  });
  linhas.push(["Total", ...t.totalColuna.map(num), num(t.total)].join(";"));
  return "﻿" + linhas.join("\r\n") + "\r\n";
}

/** Dispara o download do CSV sem passar por servidor. */
export function baixarCsv(nome: string, conteudo: string): void {
  const url = URL.createObjectURL(
    new Blob([conteudo], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
}
