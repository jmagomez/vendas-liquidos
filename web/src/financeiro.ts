/**
 * Indicadores. Funcoes puras, sem React: e onde um erro vira numero errado
 * publicado, entao ficam isoladas e testaveis.
 *
 * Regra que atravessa tudo: MES NAO CONSOLIDADO FICA FORA de media, acumulado,
 * media movel, variacao a/a e HHI. A ANP passa a listar o mes corrente assim
 * que o primeiro agente declara -- em 2026-09-05 agosto entrou com 0,6% de um
 * mes normal. Um mes com 0,6% da amostra nao e um ponto baixo da serie; e um
 * ponto de outra serie.
 */
import { ESCALA, type Marginal } from "./dados";

/** Serie total por mes (mil m3), a partir de qualquer cubo marginal. */
export function totalPorMes(cubo: Marginal, nMeses: number): number[] {
  const out = new Array<number>(nMeses).fill(0);
  for (let i = 0; i < cubo.k.length; i++) {
    const par = cubo.k[i]!;
    out[par[0]] = (out[par[0]] ?? 0) + cubo.v[i]! / ESCALA;
  }
  return out;
}

/** Serie por mes de UMA categoria (ex.: so Diesel B, so SP). */
export function serieDaCategoria(cubo: Marginal, cat: number, nMeses: number): number[] {
  const out = new Array<number>(nMeses).fill(0);
  for (let i = 0; i < cubo.k.length; i++) {
    const par = cubo.k[i]!;
    if (par[1] === cat) out[par[0]] = (out[par[0]] ?? 0) + cubo.v[i]! / ESCALA;
  }
  return out;
}

/** Matriz [mes][categoria] em mil m3 -- base do mix e do ranking. */
export function porMesECategoria(cubo: Marginal, nMeses: number, nCats: number): number[][] {
  const m = Array.from({ length: nMeses }, () => new Array<number>(nCats).fill(0));
  for (let i = 0; i < cubo.k.length; i++) {
    const [mes, cat] = cubo.k[i]!;
    m[mes]![cat] = (m[mes]![cat] ?? 0) + cubo.v[i]! / ESCALA;
  }
  return m;
}

/**
 * Media movel de 12 meses, pulando meses nao consolidados.
 *
 * `null` quando a janela nao tem 12 meses fechados: inventar uma media com 7
 * meses e chamar de "media movel de 12" seria desenhar uma linha que nao
 * existe, exatamente no trecho em que alguem olharia para decidir algo.
 */
export function mediaMovel12(serie: number[], fechado: boolean[]): (number | null)[] {
  return serie.map((_, i) => {
    let soma = 0, n = 0;
    for (let j = Math.max(0, i - 11); j <= i; j++) {
      if (fechado[j]) { soma += serie[j]!; n++; }
    }
    return n === 12 ? soma / 12 : null;
  });
}

/**
 * Variacao contra o mesmo mes do ano anterior, em %.
 *
 * A/a e nao m/m porque a serie tem sazonalidade de safra, entressafra e dias
 * uteis: contra o mes anterior, tendencia e calendario se misturam.
 */
export function variacaoAnual(serie: number[], fechado: boolean[]): (number | null)[] {
  return serie.map((v, i) => {
    const base = serie[i - 12];
    if (i < 12 || !fechado[i] || !fechado[i - 12] || !base) return null;
    return (v / base - 1) * 100;
  });
}

/**
 * HHI do mes, em pontos (0-10.000): soma dos quadrados das participacoes.
 *
 * Quadratico na participacao -- por isso o pipeline e tao severo com rotulo
 * duplicado de agente: partir um agente de 20% em dois de 10% derruba a
 * contribuicao dele de 400 para 200 pontos sem mudar um metro cubico.
 */
export function hhi(linha: number[]): number | null {
  const total = linha.reduce((a, b) => a + b, 0);
  if (total <= 0) return null;
  return linha.reduce((acc, v) => acc + Math.pow((v / total) * 100, 2), 0);
}

export const fmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
export const fmt1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
export const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1, maximumFractionDigits: 1,
});

/** "2026-09" -> "set/2026" */
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
               "jul", "ago", "set", "out", "nov", "dez"];
export function mesCurto(ym: string): string {
  const [a, m] = ym.split("-");
  return `${MESES[Number(m) - 1]}/${a}`;
}
