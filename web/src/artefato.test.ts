/**
 * Canario contra o artefato REAL publicado em data/.
 *
 * Os outros testes usam cubos sinteticos de cinco linhas e provam que a logica
 * esta certa. Este prova outra coisa, que nenhum deles pega: que o Python que
 * ESCREVE e o TypeScript que LE continuam de acordo sobre as 725 mil linhas de
 * verdade. Uma mudanca de largura de coluna, de ordem de campo ou de escala
 * passaria nos dois lados isoladamente e so apareceria no painel, como numero
 * errado sem erro na tela.
 *
 * A trava central e a reconciliacao: a soma do cubo completo por mes tem de
 * bater, mes a mes, com cada um dos quatro cubos marginais. Sao cinco caminhos
 * independentes para o mesmo total.
 *
 * Pula se `data/` nao estiver no checkout, em vez de falhar: o painel tem de
 * poder ser compilado sem o artefato.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { cruzar, decodificar } from "./cruzamento";
import { ESCALA, type Dimensao, type Marginal, type Meta } from "./dados";
import { hhi } from "./financeiro";
import { cr, otto } from "./setor";

const DADOS = resolve(dirname(fileURLToPath(import.meta.url)), "../../data");
const temArtefato = existsSync(resolve(DADOS, "meta.json"));
const quando = temArtefato ? describe : describe.skip;

function json<T>(nome: string): T {
  return JSON.parse(readFileSync(resolve(DADOS, nome), "utf-8")) as T;
}

const ARQUIVO: Record<Dimensao, string> = {
  prod: "cubo-mes-produto.json",
  uf: "cubo-mes-uf.json",
  mkt: "cubo-mes-mercado.json",
  comp: "cubo-mes-agente.json",
};

quando("artefato publicado", () => {
  const meta = temArtefato ? json<Meta>("meta.json") : ({} as Meta);
  const lerCubo = async () => {
    const gz = readFileSync(resolve(DADOS, "cubo.bin.gz"));
    const buf = gz.buffer.slice(gz.byteOffset, gz.byteOffset + gz.byteLength);
    return decodificar(buf as ArrayBuffer, meta.campos);
  };

  it("o cubo completo tem o numero de linhas que o meta declara", async () => {
    const c = await lerCubo();
    expect(c.n).toBe(meta.n_linhas);
    expect(c.campos).toEqual(meta.campos);
  });

  it("a soma por mes bate com TODOS os quatro cubos marginais", async () => {
    const c = await lerCubo();
    const iMes = c.campos.indexOf("mes"), iQtd = c.campos.indexOf("qtd");
    const doCompleto = new Array<number>(meta.months.length).fill(0);
    for (let i = 0; i < c.n; i++) {
      const mes = c.cols[iMes]![i]!;
      doCompleto[mes] = doCompleto[mes]! + c.cols[iQtd]![i]! / ESCALA;
    }
    for (const dim of ["prod", "uf", "mkt", "comp"] as Dimensao[]) {
      const m = json<Marginal>(ARQUIVO[dim]);
      const daMargem = new Array<number>(meta.months.length).fill(0);
      for (let i = 0; i < m.k.length; i++) {
        const mes = m.k[i]![0];
        daMargem[mes] = daMargem[mes]! + m.v[i]! / ESCALA;
      }
      for (let mes = 0; mes < meta.months.length; mes++) {
        // 4 casas decimais e a precisao do artefato (ESCALA = 10.000); a
        // tolerancia aqui e so o acumulo de ponto flutuante da soma.
        expect(Math.abs(daMargem[mes]! - doCompleto[mes]!))
          .toBeLessThan(Math.max(0.01, Math.abs(doCompleto[mes]!) * 1e-9));
      }
    }
  });

  it("o cruzamento agente x UF soma o mesmo total que a serie", async () => {
    const c = await lerCubo();
    const fechados = new Set(
      meta.months.map((m, i) => [m, i] as const)
        .filter(([m]) => !meta.parciais.includes(m)).map(([, i]) => i));
    const t = cruzar(c, meta.comps, meta.ufs, "comp", "uf", fechados);
    const m = json<Marginal>(ARQUIVO.comp);
    const daMargem = m.k.reduce((a, k, i) =>
      fechados.has(k[0]) ? a + m.v[i]! / ESCALA : a, 0);
    expect(t.total).toBeCloseTo(daMargem, 2);
  });

  it("o ultimo mes fechado tem HHI e CR4 coerentes entre si", () => {
    const m = json<Marginal>(ARQUIVO.comp);
    const iMes = meta.months.indexOf(meta.ultimo_completo!);
    const linha = new Array<number>(meta.comps.length).fill(0);
    for (let i = 0; i < m.k.length; i++) {
      if (m.k[i]![0] !== iMes) continue;
      const cat = m.k[i]![1];
      linha[cat] = linha[cat]! + m.v[i]! / ESCALA;
    }
    const h = hhi(linha)!, c4 = cr(linha, 4)!;
    // Identidade estrutural: o HHI nunca pode passar do quadrado do CR1 somado
    // ao resto, e nunca pode ser menor que CR4^2/4 (Cauchy-Schwarz nos 4
    // maiores). Se o loader embaralhasse colunas, uma das duas quebraria.
    expect(h).toBeGreaterThan((c4 * c4) / 4 * 0.99);
    expect(h).toBeLessThanOrEqual(10000);
    expect(c4).toBeGreaterThan(0);
    expect(c4).toBeLessThanOrEqual(100);
  });

  it("no ciclo Otto, a energia do hidratado fica abaixo do volume dele", () => {
    const m = json<Marginal>(ARQUIVO.prod);
    const iMes = meta.months.indexOf(meta.ultimo_completo!);
    const iGas = meta.prods.indexOf("Gasolina C");
    const iHid = meta.prods.indexOf("Etanol Hidratado");
    expect(iGas).toBeGreaterThanOrEqual(0);
    expect(iHid).toBeGreaterThanOrEqual(0);
    let gas = 0, hid = 0;
    for (let i = 0; i < m.k.length; i++) {
      if (m.k[i]![0] !== iMes) continue;
      if (m.k[i]![1] === iGas) gas += m.v[i]! / ESCALA;
      if (m.k[i]![1] === iHid) hid += m.v[i]! / ESCALA;
    }
    const o = otto(gas, hid, meta.ultimo_completo!)!;
    expect(o).not.toBeNull();
    // O hidratado rende ~73% da gasolina C, entao a participacao em energia e
    // SEMPRE menor que a em volume. Inverter isso significaria PCI trocado.
    expect(o.penetracaoHidratado).toBeLessThan(o.volumeHidratado);
    // E o etanol total (com o anidro da gasolina C) e sempre maior que o
    // hidratado sozinho.
    expect(o.penetracaoEtanol).toBeGreaterThan(o.penetracaoHidratado);
    expect(o.paridade).toBeGreaterThan(0.70);
    expect(o.paridade).toBeLessThan(0.76);
  });

  it("a janela comparavel do meta aponta para um mes que existe", () => {
    const inicio = meta.cobertura?.inicio_comparavel;
    if (!inicio) return;                    // artefato gerado antes do modulo
    expect(meta.months).toContain(inicio);
  });
});
