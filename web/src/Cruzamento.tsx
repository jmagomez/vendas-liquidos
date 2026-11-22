/**
 * Cruzamento de duas dimensoes: o que os cubos marginais nao conseguem.
 *
 * A margem de uma dimensao ja somou todas as outras, entao "VIBRA em SP" nao
 * sai de "VIBRA" com "SP" -- precisa das 725 mil linhas. Sao 2,1 MB, buscados
 * quando o usuario CLICA, nao no boot: a tela inteira abre com 229 KB, e quem
 * so quer a serie mensal nunca paga por isto.
 */
import { useMemo, useState } from "react";
import {
  baseDados, NOME_DIM, rotulos, type Dados, type Dimensao,
} from "./dados";
import { fmt1, fmtPct } from "./financeiro";
import { baixarCsv, carregarCubo, cruzar, paraCsv, type Cubo } from "./cruzamento";

const DIMS: Dimensao[] = ["prod", "uf", "mkt", "comp"];
/** Linhas na tela. O CSV leva a tabela inteira. */
const MAX_LINHAS = 25;

export default function Cruzamento({ dados, meses, rotuloJanela }:
  { dados: Dados; meses: Set<number>; rotuloJanela: string }) {
  const [cubo, setCubo] = useState<Cubo | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [dimL, setDimL] = useState<Dimensao>("comp");
  const [dimC, setDimC] = useState<Dimensao>("prod");

  const pedir = () => {
    setCarregando(true);
    setErro(null);
    carregarCubo(baseDados(), dados.meta)
      .then(setCubo)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setCarregando(false));
  };

  const tabela = useMemo(() => {
    if (!cubo || dimL === dimC) return null;
    return cruzar(cubo, rotulos(dados.meta, dimL), rotulos(dados.meta, dimC),
                  dimL, dimC, meses);
  }, [cubo, dados.meta, dimL, dimC, meses]);

  const visiveis = useMemo(() => {
    if (!tabela) return [];
    return tabela.linhas
      .map((nome, i) => ({ nome, i, v: tabela.totalLinha[i] ?? 0 }))
      .filter((x) => x.v !== 0)
      .sort((a, b) => b.v - a.v);
  }, [tabela]);

  return (
    <div className="painel">
      <h2>Cruzamento de duas dimensões</h2>
      <div className="nota">
        Soma do período filtrado ({rotuloJanela}), só meses consolidados. Exige o
        cubo completo (2,1 MB), que é buscado sob demanda — o resto da página sai
        de 229 KB de cubos marginais.
      </div>

      <div className="filtros">
        <div className="filtro">
          <label htmlFor="cdl">Linhas</label>
          <select id="cdl" value={dimL} onChange={(e) => setDimL(e.target.value as Dimensao)}>
            {DIMS.map((d) => <option key={d} value={d}>{NOME_DIM[d]}</option>)}
          </select>
        </div>
        <div className="filtro">
          <label htmlFor="cdc">Colunas</label>
          <select id="cdc" value={dimC} onChange={(e) => setDimC(e.target.value as Dimensao)}>
            {DIMS.map((d) => <option key={d} value={d}>{NOME_DIM[d]}</option>)}
          </select>
        </div>
        {!cubo && (
          <div className="filtro">
            <label>&nbsp;</label>
            <button className="botao" onClick={pedir} disabled={carregando}>
              {carregando ? "Baixando 2,1 MB…" : "Carregar cubo completo"}
            </button>
          </div>
        )}
        {tabela && (
          <div className="filtro">
            <label>&nbsp;</label>
            <button className="botao" onClick={() => baixarCsv(
              `cruzamento-${dimL}-x-${dimC}.csv`,
              paraCsv(tabela, `${NOME_DIM[dimL]} \\ ${NOME_DIM[dimC]}`))}>
              Exportar CSV
            </button>
          </div>
        )}
      </div>

      {erro && (
        <div className="aviso erro">
          <b>Não consegui carregar o cubo completo.</b> {erro}
        </div>
      )}
      {dimL === dimC && (
        <div className="aviso ouro">
          Escolha duas dimensões diferentes: cruzar uma dimensão com ela mesma
          devolve a própria margem, que já está nos gráficos acima.
        </div>
      )}

      {tabela && visiveis.length > 0 && (
        <>
          <div className="rolagem">
            <table className="rank">
              <thead>
                <tr>
                  <th>{NOME_DIM[dimL]}</th>
                  {tabela.colunas.map((c, j) => (
                    (tabela.totalColuna[j] ?? 0) !== 0 ? <th key={c}>{c}</th> : null
                  ))}
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {visiveis.slice(0, MAX_LINHAS).map(({ nome, i, v }) => (
                  <tr key={nome}>
                    <td>{nome}</td>
                    {tabela.colunas.map((c, j) => (
                      (tabela.totalColuna[j] ?? 0) !== 0
                        ? <td key={c}>{fmt1.format(tabela.celulas[i]![j] ?? 0)}</td>
                        : null
                    ))}
                    <td><b>{fmt1.format(v)}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="nota">
            {visiveis.length > MAX_LINHAS
              ? `Mostrando as ${MAX_LINHAS} maiores de ${visiveis.length} linhas com volume — `
              : `${visiveis.length} linha(s) com volume — `}
            total {fmt1.format(tabela.total)} mil m³
            {visiveis.length > MAX_LINHAS
              ? `, equivalente a ${fmtPct.format(
                  visiveis.slice(0, MAX_LINHAS).reduce((a, x) => a + x.v, 0)
                  / (tabela.total || 1) * 100)}% do total nas linhas exibidas. `
              : ". "}
            O CSV leva a tabela inteira, com separador <code>;</code> e decimal
            com vírgula.
          </div>
        </>
      )}
    </div>
  );
}
