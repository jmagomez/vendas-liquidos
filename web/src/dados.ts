/**
 * Carga dos artefatos publicados pelo ETL.
 *
 * O painel antigo baixava um unico data.js de 13,9 MB num <script> SINCRONO.
 * Aqui so os CUBOS MARGINAIS sao buscados no boot -- 232 KB no total, contra
 * 2,1 MB do cubo completo -- porque tudo que esta na tela inicial (serie
 * mensal, mix, ranking, HHI) sai de agregados por mes x uma dimensao.
 *
 * O cubo completo so e necessario para CRUZAR duas dimensoes (agente x UF, por
 * exemplo). Enquanto o painel nao oferecer esse cruzamento, nao ha motivo para
 * baixa-lo -- e quando oferecer, ele entra sob demanda, nao no caminho critico.
 */

// Quantidades vem como inteiro: mil m3 com 4 casas decimais (ver data_js.ESCALA).
export const ESCALA = 10000;

/** Os dados moram um nivel acima: /vendas-liquidos/data/, nao /painel/data/. */
const BASE_DADOS = new URL("../data/", window.location.href).href;

export type Meta = {
  months: string[];
  comps: string[];
  ufs: string[];
  mkts: string[];
  prods: string[];
  campos: string[];
  parciais: string[];
  ultimo_completo: string | null;
  herdados?: string[];
  n_linhas: number;
  updated: string;
  fonte: {
    sha256: string;
    bytes: number;
    baixado_em: string;
    membros?: { nome: string; sha256: string; bytes: number }[];
    herdados?: string[];
    linhas?: number;
    fusoes_agente?: Record<string, string[]>;
    variantes_detectadas?: Record<string, string[]>;
  };
};

/** Cubo marginal: soma por (indice do mes, indice da categoria). */
export type Marginal = { dim: string; k: [number, number][]; v: number[] };

export type Dimensao = "prod" | "uf" | "mkt" | "comp";

const ARQUIVO: Record<Dimensao, string> = {
  prod: "cubo-mes-produto.json",
  uf: "cubo-mes-uf.json",
  mkt: "cubo-mes-mercado.json",
  comp: "cubo-mes-agente.json",
};

/** Rotulos de cada dimensao, na mesma ordem dos indices do cubo. */
export function rotulos(meta: Meta, dim: Dimensao): string[] {
  return dim === "prod" ? meta.prods
       : dim === "uf" ? meta.ufs
       : dim === "mkt" ? meta.mkts
       : meta.comps;
}

export const NOME_DIM: Record<Dimensao, string> = {
  prod: "Combustível",
  uf: "UF de destino",
  mkt: "Tipo de consumidor",
  comp: "Agente regulado",
};

async function pedir<T>(arquivo: string): Promise<T> {
  const r = await fetch(BASE_DADOS + arquivo);
  if (!r.ok) throw new Error(`${arquivo}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

export type Dados = { meta: Meta; cubos: Record<Dimensao, Marginal> };

export async function carregar(): Promise<Dados> {
  const [meta, prod, uf, mkt, comp] = await Promise.all([
    pedir<Meta>("meta.json"),
    pedir<Marginal>(ARQUIVO.prod),
    pedir<Marginal>(ARQUIVO.uf),
    pedir<Marginal>(ARQUIVO.mkt),
    pedir<Marginal>(ARQUIVO.comp),
  ]);
  return { meta, cubos: { prod, uf, mkt, comp } };
}
