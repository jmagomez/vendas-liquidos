import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend,
  Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  NOME_DIM, carregar, rotulos, type Dados, type Dimensao,
} from "./dados";
import {
  fmt, fmt1, fmtPct, formatador, hhi, mediaMovel12, mesCurto, porMesECategoria,
  serieDaCategoria, totalPorMes, variacaoAnual,
} from "./financeiro";
import { cr, otto } from "./setor";
import Cruzamento from "./Cruzamento";
import ConcentracaoUf from "./ConcentracaoUf";

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

  // Janela inicial: nunca antes do primeiro mes comparavel. O diesel so entra
  // na fonte em mar/2010 e e metade do mercado -- abrir em 2007 mostraria o
  // mercado triplicando por artefato de cobertura. Ver scripts/cobertura.py.
  useEffect(() => {
    if (!dados) return;
    const { months, cobertura } = dados.meta;
    const minimo = cobertura?.inicio_comparavel
      ? Math.max(0, months.indexOf(cobertura.inicio_comparavel)) : 0;
    setDesde(Math.max(minimo, months.length - 120));
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

  // Janela comparavel da fonte.
  const inicioComp = meta.cobertura?.inicio_comparavel ?? null;
  const iComp = inicioComp ? meta.months.indexOf(inicioComp) : 0;
  const foraDaJanela = faixa.filter((i) => i < iComp);
  const produtosTardios = Object.entries(meta.cobertura?.por_produto ?? {})
    .filter(([, d]) => d.razao !== undefined)
    .map(([p, d]) => ({ prod: p, ...d }));

  // Agregados do recorte, sempre so com meses fechados.
  const fechados = faixa.filter((i) => fechado[i]);
  const total = fechados.reduce((a, i) => a + serie[i]!, 0);
  const media = fechados.length ? total / fechados.length : 0;
  const melhor = fechados.reduce((a, i) => (serie[i]! > serie[a]! ? i : a), fechados[0] ?? 0);
  const ativos = porComp[iUltimo]?.filter((v) => v > 0).length ?? 0;
  const mesesFechados = new Set(fechados);
  const rotuloJanela = `${meta.months[desde]} a ${meta.ultimo_completo}`;

  const serieChart = faixa.map((i) => ({
    mes: mesCurto(meta.months[i]!), v: serie[i], mm: mm12[i],
    yoy: yoy[i], parcial: !fechado[i], semCobertura: i < iComp,
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
  const serieHhi = faixa.filter((i) => fechado[i]).map((i) => ({
    mes: mesCurto(meta.months[i]!),
    hhi: hhi(porComp[i] ?? []),
    cr4: cr(porComp[i] ?? [], 4),
  }));

  // Top UF: "NI" (nao informado) nao e estado e sai do ranking geografico --
  // fica embaixo, com o volume dele a parte, em vez de virar um estado
  // inexistente no meio da lista.
  const naoGeo = new Set(meta.ufs_nao_geograficas ?? []);
  const volPorUf = meta.ufs.map((nome, j) => ({
    nome, v: fechados.reduce((a, i) => a + (porUf[i]?.[j] ?? 0), 0),
  }));
  const topUf = volPorUf.filter((x) => !naoGeo.has(x.nome))
    .sort((a, b) => b.v - a.v).slice(0, 10);
  const volNaoGeo = volPorUf.filter((x) => naoGeo.has(x.nome));
  const totalUf = volPorUf.reduce((a, x) => a + x.v, 0) || 1;

  // Ciclo Otto em base energetica.
  const iGas = meta.prods.indexOf("Gasolina C");
  const iHid = meta.prods.indexOf("Etanol Hidratado");
  const serieOtto = (iGas >= 0 && iHid >= 0)
    ? faixa.filter((i) => fechado[i] && i >= iComp).map((i) => {
        const o = otto(porProd[i]?.[iGas] ?? 0, porProd[i]?.[iHid] ?? 0,
                       meta.months[i]!);
        return {
          mes: mesCurto(meta.months[i]!),
          etanol: o?.penetracaoEtanol ?? null,
          hidratadoEnergia: o?.penetracaoHidratado ?? null,
          hidratadoVolume: o?.volumeHidratado ?? null,
        };
      })
    : [];
  const ottoUlt = (iGas >= 0 && iHid >= 0 && meta.ultimo_completo)
    ? otto(porProd[iUltimo]?.[iGas] ?? 0, porProd[iUltimo]?.[iHid] ?? 0,
           meta.ultimo_completo)
    : null;
  const semTeor = serieOtto.filter((p) => p.etanol === null).length;

  return (
    <div className="container">
      <header>
        <h1><span className="h1a">Combustíveis Líquidos</span> — Vendas por distribuidora</h1>
        <span className="periodo">
          {meta.months[0]} a <b>{meta.ultimo_completo}</b> consolidado · coletado em {meta.updated}<br />
          fonte: ANP · volumes em mil m³
        </span>
      </header>

      {produtosTardios.length > 0 && (
        <div className={foraDaJanela.length > 0 ? "aviso erro" : "aviso"}>
          <b>Série comparável a partir de {inicioComp}.</b>{" "}
          {produtosTardios.map((p) => (
            <span key={p.prod}>
              A fonte da ANP só traz <b>{p.prod}</b> a partir de {p.inicio} — nos
              12 meses anteriores são {fmt.format(p.antes_12m ?? 0)} mil m³ contra{" "}
              {fmt.format(p.depois_12m ?? 0)} nos 12 seguintes.{" "}
            </span>
          ))}
          {foraDaJanela.length > 0
            ? <>A janela selecionada inclui {foraDaJanela.length} mês(es) anteriores
                a isso, marcados em vermelho no gráfico: ali o total, o mix e o HHI
                descrevem um mercado sem metade do seu volume, e a variação a/a de
                cada mês da virada compara contra uma base que não existia.</>
            : <>Esses meses ficam fora da janela inicial de propósito; dá para
                incluí-los em "Início da série", e eles aparecem marcados.</>}
        </div>
      )}

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
          na proveniência. Isso significa que <b>não são mais reproduzíveis a partir
          da fonte de hoje</b> — se a cadeia de artefatos se romper, esses meses se
          perdem.
          {(meta.fonte.divergencias_de_rotulo ?? []).map((d) => (
            <div key={d.membro} style={{ marginTop: 6 }}>
              O arquivo <code>{d.membro}</code> promete {d.declarado[0]} a{" "}
              {d.declarado[1]} e entrega {d.real[0]} a {d.real[1]}: o nome do
              arquivo é rótulo, não dado.
            </div>
          ))}
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
            {[0, iComp, n - 60, n - 120, n - 180].filter((i) => i >= 0)
              .filter((i, j, a) => a.indexOf(i) === j)
              .sort((a, b) => a - b)
              .map((i) => (
                <option key={i} value={i}>
                  {meta.months[i]}{i < iComp ? " ⚠ sem cobertura completa" : ""}
                </option>
              ))}
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
              nota="A média móvel ignora meses não consolidados e só aparece quando há 12 meses fechados na janela — uma média de 7 meses desenhada como se fosse de 12 seria uma linha que não existe. Barras vermelhas: meses anteriores à cobertura completa da fonte.">
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={serieChart}>
            <CartesianGrid stroke={GRADE} />
            <XAxis dataKey="mes" {...EIXO} minTickGap={40} />
            <YAxis {...EIXO} tickFormatter={(v: number) => fmt.format(v)} />
            <Tooltip {...tooltip} formatter={formatador((v) => fmt1.format(v))} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="v" name="Vendas" fill="#58a6ff">
              {serieChart.map((p, i) => (
                <Cell key={i} fill={p.semCobertura ? "#f85149"
                                  : p.parcial ? "#d29922" : "#58a6ff"} />
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
            <Tooltip {...tooltip} formatter={formatador((v) => `${fmtPct.format(v)}%`)} />
            <Bar dataKey="yoy" name="Variação a/a">
              {serieChart.map((p, i) => (
                <Cell key={i} fill={(p.yoy ?? 0) >= 0 ? "#3fb950" : "#f85149"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Painel>

      {serieOtto.length > 0 && (
        <Painel titulo="Ciclo Otto: penetração do etanol em base energética (%)"
                nota="Um litro de hidratado não substitui um litro de gasolina C: rende cerca de 73% da energia. A linha de volume está no gráfico junto com as de energia justamente para mostrar o tamanho do erro de ler o mix por litro. 'Etanol total' soma o hidratado com o anidro misturado na gasolina C — com E30, quase um terço do que se vende como gasolina é etanol.">
          {ottoUlt && (
            <div className="cartoes" style={{ marginBottom: 14 }}>
              <Cartao rot={`Etanol no ciclo Otto — ${meta.ultimo_completo}`}
                      val={`${fmtPct.format(ottoUlt.penetracaoEtanol)}%`}
                      sub="da energia (hidratado + anidro)" />
              <Cartao rot="Só hidratado"
                      val={`${fmtPct.format(ottoUlt.penetracaoHidratado)}%`}
                      sub={`energia · ${fmtPct.format(ottoUlt.volumeHidratado)}% em volume`} />
              <Cartao rot="Teor de anidro na gasolina C"
                      val={`${fmtPct.format(ottoUlt.teor * 100)}%`}
                      sub="média do mês, ponderada por dia" />
              <Cartao rot="Paridade de rendimento"
                      val={`${fmtPct.format(ottoUlt.paridade * 100)}%`}
                      sub="hidratado contra gasolina C" />
            </div>
          )}
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={serieOtto}>
              <CartesianGrid stroke={GRADE} />
              <XAxis dataKey="mes" {...EIXO} minTickGap={40} />
              <YAxis {...EIXO} tickFormatter={(v: number) => `${fmt.format(v)}%`} />
              <Tooltip {...tooltip} formatter={formatador((v) => `${fmtPct.format(v)}%`)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="etanol" name="Etanol total (energia)"
                    stroke="#3fb950" fill="rgba(63,185,80,.15)" connectNulls={false} />
              <Line type="monotone" dataKey="hidratadoEnergia" name="Hidratado (energia)"
                    stroke="#58a6ff" dot={false} strokeWidth={2} connectNulls={false} />
              <Line type="monotone" dataKey="hidratadoVolume" name="Hidratado (volume)"
                    stroke="#d29922" dot={false} strokeWidth={2} strokeDasharray="4 3"
                    connectNulls={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="nota">
            PCI de referência: gasolina A 32,2 MJ/L, anidro 22,35 MJ/L, hidratado
            21,34 MJ/L. O teor de anidro vem de tabela datada com as mudanças de
            vigência (E20 out/2011, E25 mai/2013, E27 mar/2015, E30 ago/2025,
            E32 ago/2026), ponderada por dia dentro do mês.
            {semTeor > 0 && <> Antes de out/2011 a mistura oscilou entre 20% e 25%
              com datas que não consegui confirmar em fonte primária: {semTeor}{" "}
              mês(es) do recorte ficam sem valor em vez de receber um teor
              chutado.</>}{" "}
            A ANP publica "Gasolina C" sem separar comum de premium (que ficou em
            25%), o que empurra o teor efetivo para baixo em décimos de ponto.
          </div>
        </Painel>
      )}

      <Painel titulo="Mix por combustível (%)" nota="Participação de cada combustível no volume do mês. Só meses consolidados. Para a leitura em energia, veja o ciclo Otto acima.">
        <Mix dados={mixChart(porProd, meta.prods)} nomes={meta.prods} />
      </Painel>

      <Painel titulo="Mix por tipo de consumidor (%)" nota="Mesma leitura, agora por mercado destinatário.">
        <Mix dados={mixChart(porMkt, meta.mkts)} nomes={meta.mkts} />
      </Painel>

      <Painel titulo={`Ranking de agentes — ${meta.ultimo_completo}`}
              nota="Participação no último mês consolidado. HHI é a soma dos quadrados das participações, em pontos; CR4 é a soma dos quatro maiores. Os dois erram de formas diferentes: quatro agentes de 25% e um de 60% com muitos pequenos dão HHI parecido e CR4 bem distinto.">
        <div style={{ marginBottom: 14 }}>
          <b style={{ fontSize: "1.1rem" }}>HHI {fmt.format(hhi(linhaUlt) ?? 0)}</b>{" "}
          <span className="nota" style={{ display: "inline" }}>
            pontos · CR4 {fmtPct.format(cr(linhaUlt, 4) ?? 0)}%
            {ranking.length ? ` · líder ${ranking[0]!.nome} com ${fmtPct.format(ranking[0]!.v / totUlt * 100)}%` : ""}
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

      <Painel titulo="Concentração (HHI e CR4) ao longo do tempo" nota="Por agente regulado, mês a mês. Agente regulado ≠ grupo econômico: grupos com mais de uma razão social aparecem separados, então este HHI é um piso da concentração real.">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={serieHhi}>
            {/* `yAxisId` obrigatorio aqui: o recharts 3 amarra a grade a um eixo
                especifico, e este grafico nao tem o eixo padrao (0) -- so "h" e
                "c". Sem isto a grade simplesmente nao desenha, calada. */}
            <CartesianGrid stroke={GRADE} yAxisId="h" />
            <XAxis dataKey="mes" {...EIXO} minTickGap={40} />
            <YAxis yAxisId="h" {...EIXO} tickFormatter={(v: number) => fmt.format(v)} />
            <YAxis yAxisId="c" orientation="right" {...EIXO} domain={[0, 100]}
                   tickFormatter={(v: number) => `${fmt.format(v)}%`} />
            <Tooltip {...tooltip} formatter={formatador((v) => fmt1.format(v))} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area yAxisId="h" type="monotone" dataKey="hhi" name="HHI (pontos)"
                  stroke="#a371f7" fill="rgba(163,113,247,.18)" />
            <Line yAxisId="c" type="monotone" dataKey="cr4" name="CR4 (%)"
                  stroke="#39c5cf" dot={false} strokeWidth={2} />
          </ComposedChart>
        </ResponsiveContainer>
      </Painel>

      <ConcentracaoUf dados={dados} meses={mesesFechados} rotuloJanela={rotuloJanela} />

      <Painel titulo="Top 10 UFs de destino no recorte" nota="Soma do período filtrado, só meses consolidados.">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={topUf} layout="vertical" margin={{ left: 20 }}>
            <CartesianGrid stroke={GRADE} />
            <XAxis type="number" {...EIXO} tickFormatter={(v: number) => fmt.format(v)} />
            <YAxis type="category" dataKey="nome" {...EIXO} width={40} />
            <Tooltip {...tooltip} formatter={formatador((v) => fmt.format(v))} />
            <Bar dataKey="v" name="mil m³" fill="#58a6ff" />
          </BarChart>
        </ResponsiveContainer>
        {volNaoGeo.length > 0 && (
          <div className="nota">
            Fora do ranking: {volNaoGeo.map((x) => (
              `${x.nome} (não informado) com ${fmt.format(x.v)} mil m³, ` +
              `${fmtPct.format((x.v / totalUf) * 100)}% do volume`
            )).join("; ")}. Não é um estado — é o destino que o declarante não
            informou, e somá-lo a qualquer UF inventaria geografia. Continua no
            total e no cubo, só não entra no mapa.
          </div>
        )}
      </Painel>

      <Cruzamento dados={dados} meses={mesesFechados} rotuloJanela={rotuloJanela} />

      <footer>
        {fmt.format(meta.n_linhas)} combinações · {meta.months.length} meses ·{" "}
        {meta.comps.length} agentes · fonte sha256:{meta.fonte.sha256}
        {inicioComp && <> · série comparável desde {inicioComp}</>}
        <br />
        Esta tela abre com 229 KB de cubos marginais; o cubo completo (2,1 MB) só
        é buscado quando você pede um cruzamento ou a concentração por UF.
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
        <Tooltip {...tooltip} formatter={formatador((v) => `${fmtPct.format(v)}%`)} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {nomes.map((nome, i) => (
          <Area key={nome} type="monotone" dataKey={nome} stackId="1"
                stroke={CORES[i % CORES.length]} fill={CORES[i % CORES.length]} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
