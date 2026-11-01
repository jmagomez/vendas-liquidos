import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend,
  Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  NOME_DIM, carregar, rotulos, type Dados, type Dimensao,
} from "./dados";
import {
  fmt, fmt1, fmtPct, hhi, mediaMovel12, mesCurto, porMesECategoria,
  serieDaCategoria, totalPorMes, variacaoAnual,
} from "./financeiro";

const CORES = ["#58a6ff", "#3fb950", "#d29922", "#f85149", "#a371f7", "#39c5cf"];
const EIXO = { stroke: "#8b949e", fontSize: 11 };
const GRADE = "rgba(139,148,158,.15)";

export default function App() {
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [dim, setDim] = useState<Dimensao>("prod");
  const [cat, setCat] = useState<number>(-1);          // -1 = todas
  const [desde, setDesde] = useState<number>(0);

  useEffect(() => {
    carregar().then(setDados).catch((e: Error) => setErro(e.message));
  }, []);

  // Janela inicial: ultimos 10 anos, que e o que cabe num grafico legivel.
  useEffect(() => {
    if (dados) setDesde(Math.max(0, dados.meta.months.length - 120));
  }, [dados]);

  const calc = useMemo(() => {
    if (!dados) return null;
    const { meta, cubos } = dados;
    const n = meta.months.length;
    const parciais = new Set(meta.parciais);
    const fechado = meta.months.map((m) => !parciais.has(m));
    const cubo = cubos[dim];
    const serie = cat < 0 ? totalPorMes(cubo, n) : serieDaCategoria(cubo, cat, n);
    return {
      n, fechado, serie,
      mm12: mediaMovel12(serie, fechado),
      yoy: variacaoAnual(serie, fechado),
      porProd: porMesECategoria(cubos.prod, n, meta.prods.length),
      porMkt: porMesECategoria(cubos.mkt, n, meta.mkts.length),
      porComp: porMesECategoria(cubos.comp, n, meta.comps.length),
      porUf: porMesECategoria(cubos.uf, n, meta.ufs.length),
    };
  }, [dados, dim, cat]);

  if (erro) {
    return (
      <div className="container">
        <div className="aviso erro">
          <b>Não consegui carregar os dados.</b> {erro}. A página busca{" "}
          <code>../data/meta.json</code> e os cubos por <code>fetch</code>; abrindo
          o arquivo direto do disco o navegador bloqueia essa leitura.
        </div>
      </div>
    );
  }
  if (!dados || !calc) return <div className="carregando">Carregando os cubos…</div>;

  const { meta } = dados;
  const { n, fechado, serie, mm12, yoy, porProd, porMkt, porComp, porUf } = calc;
  const faixa = Array.from({ length: n - desde }, (_, i) => i + desde);
  const iUltimo = meta.ultimo_completo ? meta.months.indexOf(meta.ultimo_completo) : n - 1;
  const cats = rotulos(meta, dim);

  // Agregados do recorte, sempre so com meses fechados.
  const fechados = faixa.filter((i) => fechado[i]);
  const total = fechados.reduce((a, i) => a + serie[i]!, 0);
  const media = fechados.length ? total / fechados.length : 0;
  const melhor = fechados.reduce((a, i) => (serie[i]! > serie[a]! ? i : a), fechados[0] ?? 0);
  const ativos = porComp[iUltimo]?.filter((v) => v > 0).length ?? 0;

  const serieChart = faixa.map((i) => ({
    mes: mesCurto(meta.months[i]!), v: serie[i], mm: mm12[i],
    yoy: yoy[i], parcial: !fechado[i],
  }));
  const mixChart = (m: number[][], nomes: string[]) =>
    faixa.filter((i) => fechado[i]).map((i) => {
      const linha = m[i] ?? [];
      const tot = linha.reduce((a, b) => a + b, 0) || 1;
      const o: Record<string, number | string> = { mes: mesCurto(meta.months[i]!) };
      nomes.forEach((nome, j) => { o[nome] = ((linha[j] ?? 0) / tot) * 100; });
      return o;
    });

  // Ranking do ultimo mes fechado.
  const linhaUlt = porComp[iUltimo] ?? [];
  const totUlt = linhaUlt.reduce((a, b) => a + b, 0) || 1;
  const ranking = meta.comps
    .map((nome, j) => ({ nome, v: linhaUlt[j] ?? 0 }))
    .filter((x) => x.v > 0)
    .sort((a, b) => b.v - a.v)
    .slice(0, 12);
  const serieHhi = faixa.filter((i) => fechado[i])
    .map((i) => ({ mes: mesCurto(meta.months[i]!), hhi: hhi(porComp[i] ?? []) }));
  const topUf = meta.ufs
    .map((nome, j) => ({ nome, v: fechados.reduce((a, i) => a + (porUf[i]?.[j] ?? 0), 0) }))
    .sort((a, b) => b.v - a.v).slice(0, 10);

  return (
    <div className="container">
      <header>
        <h1><span className="h1a">Combustíveis Líquidos</span> — Vendas por distribuidora</h1>
        <span className="periodo">
          {meta.months[0]} a <b>{meta.ultimo_completo}</b> consolidado · coletado em {meta.updated}<br />
          fonte: ANP · volumes em mil m³
        </span>
      </header>

      {meta.parciais.length > 0 && (
        <div className="aviso ouro">
          <b>Mês não consolidado:</b> {meta.parciais.join(", ")}. A ANP lista o mês
          corrente assim que o primeiro agente declara. Esses meses aparecem no gráfico
          mas ficam fora de média, acumulado, média móvel, variação a/a e HHI.
        </div>
      )}
      {(meta.herdados?.length ?? 0) > 0 && (
        <div className="aviso ouro">
          <b>{meta.herdados!.length} meses herdados</b> ({meta.herdados![0]} a{" "}
          {meta.herdados![meta.herdados!.length - 1]}): a ANP não os publica em nenhum
          arquivo de vendas do zip atual; vieram do artefato anterior e estão marcados
          na proveniência.
        </div>
      )}

      <div className="filtros">
        <div className="filtro">
          <label htmlFor="fdim">Recortar por</label>
          <select id="fdim" value={dim}
                  onChange={(e) => { setDim(e.target.value as Dimensao); setCat(-1); }}>
            {(["prod", "uf", "mkt", "comp"] as Dimensao[]).map((d) => (
              <option key={d} value={d}>{NOME_DIM[d]}</option>
            ))}
          </select>
        </div>
        <div className="filtro">
          <label htmlFor="fcat">{NOME_DIM[dim]}</label>
          <select id="fcat" value={cat} onChange={(e) => setCat(Number(e.target.value))}>
            <option value={-1}>Todos</option>
            {cats.map((c, j) => <option key={c} value={j}>{c}</option>)}
          </select>
        </div>
        <div className="filtro">
          <label htmlFor="fdesde">Início da série</label>
          <select id="fdesde" value={desde} onChange={(e) => setDesde(Number(e.target.value))}>
            {[0, n - 60, n - 120, n - 180].filter((i) => i >= 0)
              .sort((a, b) => a - b)
              .map((i) => <option key={i} value={i}>{meta.months[i]}</option>)}
          </select>
        </div>
      </div>

      <div className="cartoes">
        <Cartao rot="Volume total" val={fmt.format(total)} sub="mil m³ no recorte (meses fechados)" />
        <Cartao rot="Média mensal" val={fmt.format(media)} sub="mil m³ por mês" />
        <Cartao rot="Melhor mês" val={meta.months[melhor] ?? "—"}
                sub={`${fmt.format(serie[melhor] ?? 0)} mil m³`} />
        <Cartao rot="Agentes ativos" val={String(ativos)}
                sub={`com venda em ${meta.ultimo_completo}`} />
      </div>

      <Painel titulo="Vendas mensais (mil m³) e média móvel de 12 meses"
              nota="A média móvel ignora meses não consolidados e só aparece quando há 12 meses fechados na janela — uma média de 7 meses desenhada como se fosse de 12 seria uma linha que não existe.">
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={serieChart}>
            <CartesianGrid stroke={GRADE} />
            <XAxis dataKey="mes" {...EIXO} minTickGap={40} />
            <YAxis {...EIXO} tickFormatter={(v: number) => fmt.format(v)} />
            <Tooltip {...tooltip} formatter={(v: number) => fmt1.format(v)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="v" name="Vendas" fill="#58a6ff">
              {serieChart.map((p, i) => (
                <Cell key={i} fill={p.parcial ? "#d29922" : "#58a6ff"} />
              ))}
            </Bar>
            <Line type="monotone" dataKey="mm" name="Média móvel 12m" stroke="#3fb950"
                  dot={false} strokeWidth={2} connectNulls={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </Painel>

      <Painel titulo="Variação anual (%)"
              nota="Cada mês contra o mesmo mês do ano anterior. Numa série com safra, entressafra e dias úteis, a comparação com o mês imediatamente anterior mistura tendência com calendário.">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={serieChart}>
            <CartesianGrid stroke={GRADE} />
            <XAxis dataKey="mes" {...EIXO} minTickGap={40} />
            <YAxis {...EIXO} tickFormatter={(v: number) => `${fmt.format(v)}%`} />
            <Tooltip {...tooltip} formatter={(v: number) => `${fmtPct.format(v)}%`} />
            <Bar dataKey="yoy" name="Variação a/a">
              {serieChart.map((p, i) => (
                <Cell key={i} fill={(p.yoy ?? 0) >= 0 ? "#3fb950" : "#f85149"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Painel>

      <Painel titulo="Mix por combustível (%)" nota="Participação de cada combustível no volume do mês. Só meses consolidados.">
        <Mix dados={mixChart(porProd, meta.prods)} nomes={meta.prods} />
      </Painel>

      <Painel titulo="Mix por tipo de consumidor (%)" nota="Mesma leitura, agora por mercado destinatário.">
        <Mix dados={mixChart(porMkt, meta.mkts)} nomes={meta.mkts} />
      </Painel>

      <Painel titulo={`Ranking de agentes — ${meta.ultimo_completo}`}
              nota="Participação no último mês consolidado. HHI é a soma dos quadrados das participações, em pontos: referência antitruste usual é 1.500 e 2.500 como faixas de concentração.">
        <div style={{ marginBottom: 14 }}>
          <b style={{ fontSize: "1.1rem" }}>HHI {fmt.format(hhi(linhaUlt) ?? 0)}</b>{" "}
          <span className="nota" style={{ display: "inline" }}>
            pontos · {ranking.length ? `líder ${ranking[0]!.nome} com ${fmtPct.format(ranking[0]!.v / totUlt * 100)}%` : ""}
          </span>
        </div>
        <table className="rank">
          <thead><tr><th>Agente regulado</th><th>Volume (mil m³)</th><th>Participação</th></tr></thead>
          <tbody>
            {ranking.map((r) => (
              <tr key={r.nome}>
                <td>{r.nome}</td>
                <td>{fmt1.format(r.v)}</td>
                <td>{fmtPct.format((r.v / totUlt) * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Painel>

      <Painel titulo="Concentração (HHI) ao longo do tempo" nota="Por agente regulado, mês a mês. Agente regulado ≠ grupo econômico: grupos com mais de uma razão social aparecem separados, então este HHI é um piso da concentração real.">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={serieHhi}>
            <CartesianGrid stroke={GRADE} />
            <XAxis dataKey="mes" {...EIXO} minTickGap={40} />
            <YAxis {...EIXO} tickFormatter={(v: number) => fmt.format(v)} />
            <Tooltip {...tooltip} formatter={(v: number) => fmt.format(v)} />
            <Area type="monotone" dataKey="hhi" name="HHI" stroke="#a371f7"
                  fill="rgba(163,113,247,.18)" />
          </AreaChart>
        </ResponsiveContainer>
      </Painel>

      <Painel titulo="Top 10 UFs de destino no recorte" nota="Soma do período filtrado, só meses consolidados.">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={topUf} layout="vertical" margin={{ left: 20 }}>
            <CartesianGrid stroke={GRADE} />
            <XAxis type="number" {...EIXO} tickFormatter={(v: number) => fmt.format(v)} />
            <YAxis type="category" dataKey="nome" {...EIXO} width={40} />
            <Tooltip {...tooltip} formatter={(v: number) => fmt.format(v)} />
            <Bar dataKey="v" name="mil m³" fill="#58a6ff" />
          </BarChart>
        </ResponsiveContainer>
      </Painel>

      <footer>
        {fmt.format(meta.n_linhas)} combinações · {meta.months.length} meses ·{" "}
        {meta.comps.length} agentes · fonte sha256:{meta.fonte.sha256}
        <br />
        Cruzar duas dimensões (agente × UF, por exemplo) exige o cubo completo
        (2,1 MB) e ainda não está nesta versão: esta tela inteira sai de 232 KB de
        cubos marginais.
      </footer>
    </div>
  );
}

const tooltip = {
  contentStyle: { background: "#161b22", border: "1px solid #30363d", borderRadius: 8 },
  labelStyle: { color: "#e6edf3" },
} as const;

function Cartao({ rot, val, sub }: { rot: string; val: string; sub: string }) {
  return (
    <div className="cartao">
      <div className="rot">{rot}</div>
      <div className="val">{val}</div>
      <div className="sub">{sub}</div>
    </div>
  );
}

function Painel({ titulo, nota, children }:
                { titulo: string; nota: string; children: React.ReactNode }) {
  return (
    <div className="painel">
      <h2>{titulo}</h2>
      <div className="nota">{nota}</div>
      {children}
    </div>
  );
}

function Mix({ dados, nomes }: { dados: Record<string, number | string>[]; nomes: string[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={dados} stackOffset="expand">
        <CartesianGrid stroke={GRADE} />
        <XAxis dataKey="mes" {...EIXO} minTickGap={40} />
        <YAxis {...EIXO} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
        <Tooltip {...tooltip} formatter={(v: number) => `${fmtPct.format(v)}%`} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {nomes.map((nome, i) => (
          <Area key={nome} type="monotone" dataKey={nome} stackId="1"
                stroke={CORES[i % CORES.length]} fill={CORES[i % CORES.length]} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
