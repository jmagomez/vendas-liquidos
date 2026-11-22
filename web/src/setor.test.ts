/**
 * Metricas setoriais. E onde um erro vira numero publicado, nao tela quebrada:
 * uma paridade errada em 3 pontos nao parece errada no grafico.
 */
import { describe, expect, it } from "vitest";
import { PCI, cr, otto, paridade, pciGasolinaC, teorAnidro } from "./setor";

describe("teor de anidro", () => {
  it("devolve o teor em vigor no mes", () => {
    expect(teorAnidro("2016-06")).toBeCloseTo(0.27, 10);
    expect(teorAnidro("2014-01")).toBeCloseTo(0.25, 10);
    expect(teorAnidro("2012-05")).toBeCloseTo(0.20, 10);
    expect(teorAnidro("2026-09")).toBeCloseTo(0.32, 10);
  });

  it("pondera por dia o mes em que a regra muda no meio", () => {
    // E27 entrou em 16/03/2015: 15 dias a 25% e 16 a 27%.
    const esperado = (15 * 0.25 + 16 * 0.27) / 31;
    expect(teorAnidro("2015-03")).toBeCloseTo(esperado, 10);
    // Carimbar 27% no mes inteiro erraria o mes em ~1 ponto de teor.
    expect(Math.abs(teorAnidro("2015-03")! - 0.27)).toBeGreaterThan(0.009);
    expect(teorAnidro("2015-04")).toBeCloseTo(0.27, 10);
  });

  it("vira na data certa, nao no mes seguinte", () => {
    expect(teorAnidro("2025-07")).toBeCloseTo(0.27, 10);
    expect(teorAnidro("2025-08")).toBeCloseTo(0.30, 10);
    expect(teorAnidro("2026-07")).toBeCloseTo(0.30, 10);
    expect(teorAnidro("2026-08")).toBeCloseTo(0.32, 10);
  });

  it("devolve null antes da primeira data confirmada", () => {
    // 2007-2011 a mistura oscilou entre 20% e 25% com datas que nao foram
    // confirmadas em fonte primaria. Chutar 25% ali publicaria numero
    // inventado num indicador linear no teor.
    expect(teorAnidro("2007-01")).toBeNull();
    expect(teorAnidro("2011-09")).toBeNull();
    expect(teorAnidro("2011-10")).toBeCloseTo(0.20, 10);
  });
});

describe("paridade de rendimento", () => {
  it("sobe quando o teor de anidro sobe", () => {
    // A regra dos "70%" do posto deixou de ser 70%: com E32 da ~73,5%.
    expect(paridade(0.27) * 100).toBeCloseTo(72.2, 1);
    expect(paridade(0.30) * 100).toBeCloseTo(73.0, 1);
    expect(paridade(0.32) * 100).toBeCloseTo(73.5, 1);
    expect(paridade(0.32)).toBeGreaterThan(paridade(0.27));
  });

  it("o PCI da gasolina C cai conforme entra anidro", () => {
    expect(pciGasolinaC(0)).toBeCloseTo(PCI.gasolinaA, 10);
    expect(pciGasolinaC(1)).toBeCloseTo(PCI.anidro, 10);
    expect(pciGasolinaC(0.27)).toBeLessThan(PCI.gasolinaA);
  });
});

describe("ciclo Otto", () => {
  // Ano de 2025 do artefato de 2026-11-05, com o teor de 2025-06 (E27).
  const GAS = 46652, HID = 21265;

  it("a participacao em energia e MENOR que a em volume", () => {
    const o = otto(GAS, HID, "2025-06")!;
    expect(o.volumeHidratado).toBeCloseTo(31.3, 1);
    expect(o.penetracaoHidratado).toBeCloseTo(24.8, 1);
    // 6,5 pontos de diferenca na mesma serie: e o motivo do painel.
    expect(o.volumeHidratado - o.penetracaoHidratado).toBeGreaterThan(6);
  });

  it("o etanol total inclui o anidro da gasolina C", () => {
    const o = otto(GAS, HID, "2025-06")!;
    expect(o.penetracaoEtanol).toBeGreaterThan(o.penetracaoHidratado);
    expect(o.penetracaoEtanol).toBeCloseTo(40.1, 1);
  });

  it("volume x PCI da TJ direto, sem fator de escala", () => {
    // 1 mil m3 = 1e6 L e 1 TJ = 1e6 MJ.
    const o = otto(1, 0, "2025-06")!;
    expect(o.energia).toBeCloseTo(pciGasolinaC(0.27), 6);
  });

  it("sem hidratado, a penetracao de etanol e so o anidro", () => {
    const o = otto(100, 0, "2016-01")!;
    expect(o.penetracaoHidratado).toBe(0);
    expect(o.penetracaoEtanol).toBeCloseTo(0.27 * PCI.anidro / pciGasolinaC(0.27) * 100, 6);
  });

  it("o equivalente em gasolina C devolve o proprio volume quando so ha gasolina", () => {
    const o = otto(1234, 0, "2016-01")!;
    expect(o.equivalenteGasolinaC).toBeCloseTo(1234, 6);
  });

  it("null onde o teor nao esta na tabela, em vez de numero chutado", () => {
    expect(otto(GAS, HID, "2008-05")).toBeNull();
  });

  it("null em mes sem venda de ciclo Otto", () => {
    expect(otto(0, 0, "2025-06")).toBeNull();
  });
});

describe("CR-n", () => {
  it("soma os n maiores", () => {
    expect(cr([40, 30, 20, 5, 5], 4)).toBeCloseTo(95, 10);
    expect(cr([40, 30, 20, 5, 5], 1)).toBeCloseTo(40, 10);
  });

  it("separa estruturas que o HHI confunde", () => {
    // Quatro de 25% e um de 60% com muitos pequenos dao HHI parecido
    // (2.500 contra 2.600) e CR4 bem distinto.
    const iguais = [25, 25, 25, 25];
    const dominante = [60, ...Array<number>(40).fill(1)];
    expect(cr(iguais, 4)).toBeCloseTo(100, 10);
    expect(cr(dominante, 4)).toBeLessThan(70);
  });

  it("null em mercado sem volume", () => {
    expect(cr([], 4)).toBeNull();
    expect(cr([0, 0], 4)).toBeNull();
  });

  it("nao se engana com menos de n agentes", () => {
    expect(cr([10, 10], 4)).toBeCloseTo(100, 10);
  });
});
