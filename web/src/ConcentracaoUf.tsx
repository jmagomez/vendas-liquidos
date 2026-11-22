/**
 * Concentracao por UF: onde a concentracao de verdade aparece.
 *
 * O HHI nacional do ultimo mes fechado fica na casa de 1.100 pontos, que a
 * referencia antitruste classifica como mercado NAO concentrado. So que
 * ninguem compra combustivel no mercado nacional: compra no estado onde esta.
 * Rodando o mesmo indice por UF, estados pequenos passam de 2.500 pontos --
 * faixa de alta concentracao -- com os mesmos dados que dao 1.100 no agregado.
 * O numero nacional nao esta errado; esta medindo outra coisa.
 *
 * Precisa do cruzamento agente x UF, logo do cubo completo: sob demanda.
 *
 * Duas ressalvas que o painel repete na tela, porque mudam a leitura:
 * - agente regulado nao e grupo economico, entao este HHI e PISO da
 *   concentracao real (grupo com duas razoes sociais conta como dois);
 * - a UF e a de DESTINO declarado, nao o ponto de venda.
 */
import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { baseDados, rotulos, type Dados } from "./dados";
import { fmt, fmt1, fmtPct, hhi } from "./financeiro";
import { cr } from "./setor";
import { carregarCubo, cruzar, type Cubo } from "./cruzamento";

/** Faixas usuais de leitura antitruste do HHI. */
const MODERADO = 1500, ALTO = 2500;

export default function ConcentracaoUf({ dados, meses, rotuloJanela }:
  { dados: Dados; meses: Set<number>; rotuloJanela: string }) {
  const [cubo, setCubo] = useState<Cubo | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const pedir = () => {
    setCarregando(true);
    setErro(null);
    carregarCubo(baseDados(), dados.meta)
      .then(setCubo)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setCarregando(false));
  };

  const linhas = useMemo(() => {
    if (!cubo) return null;
    const { meta } = dados;
    const naoGeo = new Set(meta.ufs_nao_geograficas ?? []);
    const t = cruzar(cubo, rotulos(dados.meta, "uf"), rotulos(dados.meta, "comp"),
                     "uf", "comp", meses);
    return t.linhas
      .map((uf, i) => ({
        uf,
        v: t.totalLinha[i] ?? 0,
        hhi: hhi(t.celulas[i] ?? []),
        cr4: cr(t.celulas[i] ?? [], 4),
        agentes: (t.celulas[i] ?? []).filter((x) => x > 0).length,
      }))
      .filter((x) => x.v > 0 && x.hhi !== null && !naoGeo.has(x.uf))
      .sort((a, b) => (b.hhi ?? 0) - (a.hhi ?? 0));
  }, [cubo, dados, meses]);

  return (
    <div className="painel">
      <h2>Concentração por UF — HHI e CR4</h2>
      <div className="nota">
        Mesmo índice do gráfico nacional, agora dentro de cada estado, somando o
        período filtrado ({rotuloJanela}). Faixas usuais: até {fmt.format(MODERADO)}{" "}
        não concentrado, {fmt.format(MODERADO)}–{fmt.format(ALTO)} moderado,
        acima de {fmt.format(ALTO)} alto. CR4 é a soma dos quatro maiores: HHI e
        CR4 erram de formas diferentes e se leem juntos. Exige o cubo completo
        (2,1 MB), sob demanda.
      </div>

      {!cubo && (
        <button className="botao" onClick={pedir} disabled={carregando}>
          {carregando ? "Baixando 2,1 MB…" : "Calcular por UF"}
        </button>
      )}
      {erro && <div className="aviso erro"><b>Não consegui carregar o cubo.</b> {erro}</div>}

      {linhas && linhas.length > 0 && (
        <>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={linhas.slice(0, 15)} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid stroke="rgba(139,148,158,.15)" />
              <XAxis type="number" stroke="#8b949e" fontSize={11}
                     tickFormatter={(v: number) => fmt.format(v)} />
              <YAxis type="category" dataKey="uf" stroke="#8b949e" fontSize={11} width={40} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8 }}
                labelStyle={{ color: "#e6edf3" }}
                formatter={(v: number) => fmt.format(v)} />
              <Bar dataKey="hhi" name="HHI">
                {linhas.slice(0, 15).map((d, i) => (
                  <Cell key={i} fill={(d.hhi ?? 0) >= ALTO ? "#f85149"
                                    : (d.hhi ?? 0) >= MODERADO ? "#d29922" : "#3fb950"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="rolagem">
            <table className="rank">
              <thead>
                <tr><th>UF de destino</th><th>HHI</th><th>CR4</th>
                    <th>Agentes</th><th>Volume (mil m³)</th></tr>
              </thead>
              <tbody>
                {linhas.map((d) => (
                  <tr key={d.uf}>
                    <td>{d.uf}</td>
                    <td>{fmt.format(d.hhi ?? 0)}</td>
                    <td>{fmtPct.format(d.cr4 ?? 0)}%</td>
                    <td>{d.agentes}</td>
                    <td>{fmt1.format(d.v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="nota">
            Agente regulado ≠ grupo econômico: grupos com mais de uma razão social
            contam como agentes separados, então cada HHI aqui é um <b>piso</b> da
            concentração real. A UF é a de destino declarado, não o ponto de venda.
          </div>
        </>
      )}
    </div>
  );
}
