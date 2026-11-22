/**
 * Cubo completo e cruzamento. O formato binario e contrato entre o Python que
 * escreve e este TypeScript que le: se as duas pontas discordarem de um byte,
 * o painel desenha numero errado sem erro nenhum na tela.
 */
import { describe, expect, it } from "vitest";
import { cruzar, decodificar, paraCsv, type Cubo } from "./cruzamento";
import type { Dimensao } from "./dados";

const CAMPOS = ["mes", "comp", "uf", "mkt", "prod", "qtd"];
const U8 = 1, U16 = 2, I32 = 5;

/** Escreve o mesmo formato que scripts/cubos.py grava. */
function cubobin(linhas: number[][], tipos: number[]): ArrayBuffer {
  const n = linhas.length, P = tipos.length;
  const largura = (t: number) => (t === U8 ? 1 : t === U16 ? 2 : 4);
  const tam = 9 + P + n * tipos.reduce((a, t) => a + largura(t), 0);
  const buf = new ArrayBuffer(tam);
  const b = new DataView(buf);
  "VLQ1".split("").forEach((c, i) => b.setUint8(i, c.charCodeAt(0)));
  b.setUint32(4, n, true);
  b.setUint8(8, P);
  tipos.forEach((t, i) => b.setUint8(9 + i, t));
  let off = 9 + P;
  for (let c = 0; c < P; c++) {
    for (let i = 0; i < n; i++) {
      const v = linhas[i]![c]!;
      if (tipos[c] === U8) b.setUint8(off + i, v);
      else if (tipos[c] === U16) b.setUint16(off + i * 2, v, true);
      else b.setInt32(off + i * 4, v, true);
    }
    off += n * largura(tipos[c]!);
  }
  return buf;
}

/** Comprime com a MESMA familia de API que o painel usa para descomprimir. */
async function gz(buf: ArrayBuffer): Promise<ArrayBuffer> {
  const fluxo = new Blob([buf]).stream()
    .pipeThrough(new CompressionStream("gzip"));
  return new Response(fluxo).arrayBuffer();
}

// mes, comp, uf, mkt, prod, qtd (qtd = mil m3 x 10.000)
const LINHAS = [
  [0, 0, 0, 0, 0, 100000],   // m0 A SP TRR Diesel     10,0
  [0, 1, 0, 0, 0,  50000],   // m0 B SP TRR Diesel      5,0
  [0, 0, 1, 0, 0,  20000],   // m0 A RJ TRR Diesel      2,0
  [1, 0, 0, 0, 1,  30000],   // m1 A SP TRR Gasolina    3,0
  [1, 1, 1, 0, 1, -10000],   // m1 B RJ TRR Gasolina   -1,0 (estorno)
];
const TIPOS = [U8, U16, U8, U8, U8, I32];
const COMPS = ["AGENTE A", "AGENTE B"];
const UFS = ["SP", "RJ"];

async function cubo(): Promise<Cubo> {
  return decodificar(await gz(cubobin(LINHAS, TIPOS)), CAMPOS);
}

describe("decodificacao do cubo binario", () => {
  it("le o formato que o Python grava", async () => {
    const c = await cubo();
    expect(c.n).toBe(5);
    expect(c.campos).toEqual(CAMPOS);
    expect([...c.cols[0]!]).toEqual([0, 0, 0, 1, 1]);
    expect([...c.cols[1]!]).toEqual([0, 1, 0, 0, 1]);
  });

  it("preserva quantidade NEGATIVA", async () => {
    // A ANP publica estornos. Coluna sem sinal devolveria 4,29 bilhoes aqui e
    // o volume do mes ficaria absurdo.
    const c = await cubo();
    expect(c.cols[5]![4]).toBe(-10000);
  });

  it("recusa magico errado em vez de ler lixo", async () => {
    const buf = cubobin(LINHAS, TIPOS);
    new DataView(buf).setUint8(0, "X".charCodeAt(0));
    await expect(decodificar(await gz(buf), CAMPOS)).rejects.toThrow(/magico/);
  });

  it("recusa numero de colunas diferente de meta.campos", async () => {
    await expect(decodificar(await gz(cubobin(LINHAS, TIPOS)), CAMPOS.slice(0, 5)))
      .rejects.toThrow(/colunas/);
  });

  it("recusa tipo de coluna desconhecido", async () => {
    const buf = cubobin(LINHAS, TIPOS);
    new DataView(buf).setUint8(9, 99);
    await expect(decodificar(await gz(buf), CAMPOS)).rejects.toThrow(/tipo de coluna/);
  });
});

describe("cruzamento", () => {
  const todos = new Set([0, 1]);

  it("cruza agente x UF somando os meses pedidos", async () => {
    const t = cruzar(await cubo(), COMPS, UFS, "comp", "uf", todos);
    expect(t.celulas[0]![0]).toBeCloseTo(13.0, 6);   // A em SP: 10 + 3
    expect(t.celulas[0]![1]).toBeCloseTo(2.0, 6);    // A em RJ
    expect(t.celulas[1]![0]).toBeCloseTo(5.0, 6);    // B em SP
    expect(t.celulas[1]![1]).toBeCloseTo(-1.0, 6);   // B em RJ (estorno)
    expect(t.total).toBeCloseTo(19.0, 6);
  });

  it("o cruzamento soma o mesmo total que a margem", async () => {
    // A trava que pega erro de indice de coluna: se `cruzar` lesse a coluna
    // errada, as celulas mudariam e o total continuaria batendo -- por isso
    // os dois testes, nao so este.
    const c = await cubo();
    const porAgente = cruzar(c, COMPS, UFS, "comp", "uf", todos);
    const porUf = cruzar(c, UFS, COMPS, "uf", "comp", todos);
    expect(porUf.total).toBeCloseTo(porAgente.total, 10);
    expect(porUf.totalLinha[0]).toBeCloseTo(porAgente.totalColuna[0]!, 10);
  });

  it("respeita o recorte de meses", async () => {
    const t = cruzar(await cubo(), COMPS, UFS, "comp", "uf", new Set([0]));
    expect(t.total).toBeCloseTo(17.0, 6);            // so o mes 0
    expect(t.celulas[0]![0]).toBeCloseTo(10.0, 6);
  });

  it("mes nenhum devolve tabela zerada, nao erro", async () => {
    const t = cruzar(await cubo(), COMPS, UFS, "comp", "uf", new Set());
    expect(t.total).toBe(0);
  });

  it("derruba se o campo pedido nao existe no artefato", async () => {
    const c = await cubo();
    expect(() => cruzar({ ...c, campos: ["mes", "x", "y", "z", "w", "qtd"] },
                        COMPS, UFS, "comp", "uf", todos)).toThrow(/campo ausente/);
  });
});

describe("CSV", () => {
  it("abre no Excel em pt-BR: BOM, ponto-e-virgula e decimal com virgula", async () => {
    const t = cruzar(await cubo(), COMPS, UFS, "comp", "uf", new Set([0, 1]));
    const csv = paraCsv(t, "Agente \\ UF");
    expect(csv.startsWith("﻿")).toBe(true);
    expect(csv).toContain("Agente \\ UF;SP;RJ;Total");
    expect(csv).toContain("13,0000");
    expect(csv).toContain("\r\n");
    // Estorno vai com sinal, nao em branco nem em modulo.
    expect(csv).toContain("-1,0000");
  });

  it("protege separador dentro do rotulo", async () => {
    const t = cruzar(await cubo(), ["AGENTE; LTDA", "B"], UFS, "comp", "uf",
                     new Set([0, 1]));
    expect(paraCsv(t, "x")).toContain('"AGENTE; LTDA"');
  });

  it("nao escreve linha de agente sem volume no recorte", async () => {
    const t = cruzar(await cubo(), [...COMPS, "AGENTE SEM VENDA"], UFS,
                     "comp" as Dimensao, "uf", new Set([0, 1]));
    expect(paraCsv(t, "x")).not.toContain("AGENTE SEM VENDA");
  });
});
