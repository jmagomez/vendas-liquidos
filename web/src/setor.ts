/**
 * Metricas do setor, em base ENERGETICA -- nao em volume.
 *
 * POR QUE: um litro de etanol hidratado nao substitui um litro de gasolina C.
 * O PCI do hidratado e ~21,3 MJ/L contra ~29,5 MJ/L da gasolina C com 27% de
 * anidro: 72%. Medido no artefato de 2026-11-05, ano de 2025:
 *
 *     hidratado 21.265 mil m3 | gasolina C 46.652 mil m3
 *     participacao do hidratado em VOLUME ................ 31,3%
 *     participacao do hidratado em ENERGIA ............... 24,8%
 *
 * Sao 6,5 pontos de diferenca na mesma serie. O mix por volume que o painel ja
 * mostra responde "quantos litros", que e a pergunta logistica; esta secao
 * responde "quanta energia", que e a pergunta de substituicao e de demanda. Em
 * nenhum momento uma substitui a outra -- as duas estao na tela.
 *
 * E a penetracao do etanol no ciclo Otto nao e a do hidratado: o anidro
 * misturado na gasolina C tambem e etanol. Com E30, quase um terco do volume
 * vendido como "gasolina" e etanol. Somar os dois e o numero que o setor usa.
 *
 * O QUE ESTE MODULO NAO FAZ: nao estima teor de anidro que nao esteja na tabela
 * datada abaixo. Antes de out/2011 a mistura oscilou entre 20% e 25% com datas
 * que nao consegui confirmar em fonte primaria; nesses meses as metricas
 * energeticas devolvem `null` e o painel escreve "n/d". Chutar 25% ali seria
 * publicar numero inventado num indicador que depende linearmente dele.
 */

/**
 * PCI volumetrico, MJ/L. Valores referenciais: o PCI real varia com a
 * especificacao do lote, a octanagem e a agua do hidratado. A metrica e uma
 * RAZAO entre energias, entao um erro comum aos tres se cancela quase todo; o
 * que nao se cancela e erro relativo entre eles, da ordem de 1-2%.
 */
export const PCI = {
  gasolinaA: 32.2,
  anidro: 22.35,
  hidratado: 21.34,
} as const;

/**
 * Teor de etanol anidro na gasolina C comum, por data de vigencia.
 *
 * So entradas confirmaveis em fonte primaria ou em noticia da propria ANP/MME.
 * A gasolina premium ficou em 25% em todas as mudancas recentes; a ANP publica
 * "Gasolina C" sem separar comum de premium, entao o teor aqui e o da comum --
 * a premium e fracao pequena do volume e empurra o numero para baixo em
 * decimos de ponto, nunca em pontos.
 *
 * Datas: E20 out/2011, E25 01/05/2013, E27 16/03/2015, E30 01/08/2025,
 * E32 01/08/2026 (Resolucao CNPE 9/2026).
 */
export const TEOR_ANIDRO: { desde: string; teor: number }[] = [
  { desde: "2011-10-01", teor: 0.20 },
  { desde: "2013-05-01", teor: 0.25 },
  { desde: "2015-03-16", teor: 0.27 },
  { desde: "2025-08-01", teor: 0.30 },
  { desde: "2026-08-01", teor: 0.32 },
];

const PRIMEIRO_MES_CONFIRMADO = TEOR_ANIDRO[0]!.desde.slice(0, 7);

/** Dias no mes "2026-09". */
function diasNoMes(ym: string): number {
  const [a, m] = ym.split("-").map(Number);
  return new Date(a!, m!, 0).getDate();
}

/**
 * Teor medio de anidro no mes, ponderado por DIA de vigencia.
 *
 * Mudanca no meio do mes existe: o E27 entrou em 16/03/2015. Carimbar 27% em
 * marco inteiro erraria o mes em ~3,5 pontos de teor; ponderar por dia acerta
 * o mes inteiro sem precisar de dado novo. `null` antes de out/2011.
 */
export function teorAnidro(ym: string): number | null {
  if (ym < PRIMEIRO_MES_CONFIRMADO) return null;
  const dias = diasNoMes(ym);
  let soma = 0;
  for (let d = 1; d <= dias; d++) {
    const dia = `${ym}-${String(d).padStart(2, "0")}`;
    let teor: number | null = null;
    for (const r of TEOR_ANIDRO) if (r.desde <= dia) teor = r.teor;
    if (teor === null) return null;   // mes que comeca antes da tabela
    soma += teor;
  }
  return soma / dias;
}

/** PCI da gasolina C no mes, MJ/L -- muda com o teor de anidro. */
export function pciGasolinaC(teor: number): number {
  return (1 - teor) * PCI.gasolinaA + teor * PCI.anidro;
}

/**
 * Paridade de rendimento: quanto o hidratado rende contra a gasolina C.
 *
 * E a regra dos "70%" do posto, que deixou de ser 70% quando o teor subiu:
 * com E27 da 72,2%, com E30 73,0% e com E32 73,5%. Quem continua usando 70%
 * com E32 subestima o etanol em 3,5 pontos na decisao de encher o tanque.
 */
export function paridade(teor: number): number {
  return PCI.hidratado / pciGasolinaC(teor);
}

export type Otto = {
  /** Energia total do ciclo Otto no mes, TJ. */
  energia: number;
  /** Participacao de TODO o etanol (hidratado + anidro) na energia, %. */
  penetracaoEtanol: number;
  /** Participacao so do hidratado na energia, %. */
  penetracaoHidratado: number;
  /** Participacao do hidratado em VOLUME, %, para comparar com a de energia. */
  volumeHidratado: number;
  /** Ciclo Otto em mil m3 equivalentes de gasolina C do proprio mes. */
  equivalenteGasolinaC: number;
  teor: number;
  paridade: number;
};

/**
 * Ciclo Otto do mes a partir dos volumes em mil m3.
 *
 * 1 mil m3 = 1e6 L, e 1 TJ = 1e6 MJ, entao volume(mil m3) x PCI(MJ/L) = TJ
 * direto, sem fator de escala -- uma conversao a menos para errar.
 *
 * `null` quando o teor do mes nao esta na tabela datada, ou quando nao houve
 * venda de ciclo Otto no mes (mes nao consolidado sem declarante, por exemplo).
 */
export function otto(volGasolinaC: number, volHidratado: number,
                     ym: string): Otto | null {
  const teor = teorAnidro(ym);
  if (teor === null) return null;
  const pciC = pciGasolinaC(teor);
  const energiaGas = volGasolinaC * pciC;
  const energiaHid = volHidratado * PCI.hidratado;
  const energia = energiaGas + energiaHid;
  if (energia <= 0) return null;
  const energiaAnidro = volGasolinaC * teor * PCI.anidro;
  const volTotal = volGasolinaC + volHidratado;
  return {
    energia,
    penetracaoEtanol: ((energiaHid + energiaAnidro) / energia) * 100,
    penetracaoHidratado: (energiaHid / energia) * 100,
    volumeHidratado: volTotal > 0 ? (volHidratado / volTotal) * 100 : 0,
    equivalenteGasolinaC: energia / pciC,
    teor,
    paridade: paridade(teor),
  };
}

/**
 * CR-n: soma das participacoes dos n maiores, em %.
 *
 * Acompanha o HHI porque os dois erram de formas diferentes. O HHI de um
 * mercado com 4 iguais de 25% e 2.500; com um de 60% e muitos pequenos,
 * tambem fica perto disso -- estruturas opostas, mesmo numero. O CR4 separa as
 * duas: 100% contra ~65%. Ler os dois juntos e o padrao antitruste.
 */
export function cr(linha: number[], n = 4): number | null {
  const total = linha.reduce((a, b) => a + b, 0);
  if (total <= 0) return null;
  const topo = [...linha].sort((a, b) => b - a).slice(0, n);
  return (topo.reduce((a, b) => a + b, 0) / total) * 100;
}
