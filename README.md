# Vendas de Combustíveis Líquidos — Dashboard ANP

Dashboard interativo com as vendas mensais de combustíveis líquidos por distribuidora (dados abertos da ANP), com filtros por companhia, estado (UF de destino), tipo de consumidor, combustível e período, série de variação anual, evolução do mix, ranking de companhias, indicadores de estrutura de mercado e exportação em CSV.

**Dashboard:** https://jmagomez.github.io/vendas-liquidos/

## Estrutura

```
vendas-liquidos/
├── scripts/
│   ├── update_dashboard.py   # baixa o CSV da ANP, agrega e gera data.js
│   ├── data_js.py            # leitura/escrita do data.js (contrato único)
│   └── resumo_email.py       # monta o resumo do e-mail mensal
├── data.js                   # dados agregados (mês × companhia × UF × mercado × produto)
├── index.html                # dashboard (GitHub Pages)
├── vendor/chart.umd.js       # Chart.js versionado (gerado pelo workflow vendorizar)
└── .github/workflows/
    ├── update-dashboard.yml  # rotina (dias 5 e 28) + e-mail
    ├── vendorizar.yml        # sob demanda: baixa o Chart.js para vendor/
    └── ci.yml                # ruff + pytest
```

## Rotina automática

Nos dias 5 e 28 de cada mês (9h de Brasília), o GitHub Actions baixa o
`Liquidos_Vendas_Atual.csv` da ANP, regenera o `data.js`, commita e envia
um resumo por e-mail com link para o dashboard.

São duas passadas de propósito: **a ANP não fecha o mês anterior no dia 5**. Os
agentes ainda estão dentro do prazo de declaração, e o arquivo já lista o mês
corrente com as poucas entregas antecipadas.

A janela de consolidação foi medida no histórico deste repositório: em
**18/jul/2026 o arquivo não trazia junho; em 30/jul/2026 junho já estava
completo**. A ANP fecha o mês M na segunda metade de M+1 — por isso a rodada do
dia 28, que é a que costuma pegar o mês consolidado; a do dia 5 recolhe revisões
e serve de rede se a do dia 28 tiver pego o mês ainda em formação.

28 e não 30 de propósito: 29, 30 e 31 não existem em todo mês, e um cron nesses
dias não dispara em fevereiro. 28 é o último dia presente nos doze meses.

Para o envio de e-mail funcionar, configure os secrets `MAIL_USERNAME` e
`MAIL_PASSWORD_ANP` (senha de app do Gmail) em Settings → Secrets and variables → Actions.
O workflow lê `MAIL_PASSWORD_ANP`, não `MAIL_PASSWORD`.

## Integridade dos dados

A rotina falha alto em vez de gravar dados ruins. São seis travas, e cada uma
existe por causa de um jeito concreto de o número sair errado sem ninguém notar:

1. **Cabeçalho conferido por nome.** Contar colunas pega inserção no fim; não
   pega reordenação entre duas colunas numéricas. Ano e mês trocados passariam
   por toda a validação por linha (os dois são inteiros pequenos e plausíveis) e
   deslocariam a série inteira. A conferência é por raiz do nome, sem acento, para
   não quebrar por um `(mil m3)` que virou `(mil m³)`.
2. **Cada linha validada** — ano entre 2000 e 2100, mês entre 1 e 12, volume
   numérico. Se mais de 1% das linhas não passar, a execução é interrompida.
3. **Mês da ponta ainda não consolidado é marcado, não somado.** Veja abaixo.
4. **Comparação com o `data.js` atual.** Se o número de meses cair, ou as
   combinações caírem mais de 5%, o arquivo antigo fica intacto e a rotina falha.
5. **Comparação mês a mês.** Nenhum mês já fechado pode encolher mais de 10% nem
   voltar à condição de incompleto. As checagens de contagem só enxergam o
   agregado: a ANP pode republicar o arquivo com um mês antigo pela metade e o
   total continuar dentro da tolerância.

6. **Escrita atômica.** O `data.js` vai para um temporário e só então entra no
   lugar por `os.replace`. A rotina roda num runner que pode ser interrompido; um
   `write_text` que morre pela metade deixa JSON inválido — dashboard em branco e,
   pior, a próxima execução sem a base de comparação contra a qual as travas 4 e
   5 existem.

Em todos os casos o `data.js` não é tocado e o workflow dispara o e-mail de falha.

### Proveniência

Cada `data.js` grava de que arquivo da ANP veio: `sha256` (16 hex), tamanho,
linhas lidas, descartadas, negativas e o instante do download. Quando um número
do painel for contestado — e vai ser —, essa é a primeira pergunta, e sem o
registro não há como reproduzir a rodada. Com o hash gravado, o histórico do git
do `data.js` vira trilha de auditoria: cada commit diz exatamente qual arquivo o
produziu. O rodapé do dashboard mostra a mesma informação.

### O mês em formação

Em **2026-09-05** a rotina gravou `2026-08` com **71,3 mil m³, 64 linhas, 3
distribuidoras e 7 UFs** — contra 12.365 mil m³, 4.164 linhas, 145 companhias e
28 UFs em julho. Agosto estava em **0,58%** de um mês normal, e Vibra, Ipiranga e
Raízen (56% do mercado) não apareciam.

Não era dado ruim: era o mês corrente ainda em formação. O
`Liquidos_Vendas_Atual.csv` passa a listar o mês assim que o primeiro agente
entrega a declaração, muito antes do prazo de envio.

As travas de então não pegaram porque **defendiam a ponta errada da série**: elas
protegem o histórico contra *encolher*, e um mês novo incompleto faz o oposto —
adiciona um mês e 64 linhas. Passavam com folga. Pior, o eixo Y do gráfico mensal
começava em 7.000, então a barra de 71 mil m³ simplesmente sumia: o erro ficava
invisível justamente no mês em que era grave. E o e-mail saiu com a manchete
`Vendas ANP 2026-08: 71 mil m³ (-99,4% no mês)`.

O que passou a acontecer:

- um mês da ponta cujo **volume** ou **número de agentes declarantes** fique
  abaixo de 60% da mediana dos 12 meses anteriores é marcado em
  `data.js["parciais"]`. Mediana, e não média, para que um mês parcial já
  detectado não contamine a referência do seguinte;
- só a **ponta** é avaliada: a varredura para no primeiro mês fechado. Um colapso
  real no meio da série (greve, choque regulatório) é dado de verdade e não pode
  ser reclassificado por uma heurística de volume;
- se mais de 3 meses seguidos caírem no limiar, a rotina falha: aí o problema não
  é a ponta, é o arquivo;
- o mês marcado **continua no `data.js`** — quem audita precisa ver o que a ANP
  publicou. Ele aparece em âmbar no gráfico mensal e fica fora de toda média,
  acumulado, média móvel, variação a/a, mix, pizza, ranking e HHI;
- a manchete do e-mail passa a ser sempre o **último mês fechado**, com o mês em
  formação virando aviso.

Barras voltaram a começar do zero. Barra codifica magnitude pelo comprimento:
truncada, mente. Quem quer enxergar a variação tem agora a média móvel de 12
meses sobre o mesmo gráfico e o painel de variação a/a.

### Quantidades negativas

O arquivo da ANP traz ~185 linhas com quantidade negativa em 116 meses, somando
−11 mil m³ contra 1,3 milhão de volume total, distribuídas por todos os anos. São
estornos publicados pela própria agência: entram na soma e ficam contados no log,
porque um *salto* nessa contagem seria sinal de outra coisa.

## Leitura do dashboard

- **Média móvel 12m** sobre o gráfico mensal — a série bruta é dominada por
  sazonalidade de safra, entressafra e dias úteis. Um ponto da média móvel é nulo
  se qualquer mês da janela estiver faltando ou não consolidado: média móvel com
  buraco dentro não é média móvel, é um número menor com cara de queda.
- **Variação anual (%)** — cada mês contra o mesmo mês do ano anterior.
- **Ranking de companhias** — volume, participação, participação na mesma janela
  12 meses antes, Δ em pontos percentuais e variação de volume. As colunas de
  comparação só aparecem quando *todos* os meses do recorte têm contraparte na
  base: comparar 115 meses contra 103 produzia um "+11%" que era tamanho de
  janela, não crescimento.
- **HHI e CR4** — concentração do mercado de distribuição. Referência antitruste
  usual: abaixo de 1.500 desconcentrado, 1.500–2.500 moderado.
- **Etanol hidratado no ciclo Otto** — etanol ÷ (etanol + gasolina C), em volume.
- **Consolidar por grupo econômico** — a ANP identifica o *agente regulado* (um
  CNPJ), não o grupo. Raízen declara por duas razões sociais; somadas, o grupo
  passa a Ipiranga no acumulado da série (18,2% contra 18,1%). O mapa é curto e
  manual de propósito: consolidar por semelhança de nome juntaria homônimos sem
  relação. O caminho definitivo é mapear por CNPJ, que o arquivo agregado não traz.
- **Cobertura da base** — agentes regulados com venda declarada em cada mês. Não
  é indicador de mercado, é indicador de *qualidade do dado*: foi a queda dessa
  série, de ~150 agentes para 3, que denunciou agosto/2026. Uma queda dela em
  qualquer mês significa arquivo da ANP incompleto, não distribuidora saindo do
  mercado — e o painel avisa quando um mês já fechado fica abaixo de 75% da
  mediana dos 12 anteriores.
- **Exportar recorte (CSV)** — mês × companhia do recorte filtrado, com `;` e
  decimal `,` para abrir no Excel em pt-BR sem perguntar nada.

O painel imprime: em `@media print` o tema vira tinta sobre branco, os controles
somem e os gráficos são repintados (o Chart.js desenha em canvas, onde o CSS não
alcança — sem isso os rótulos externos da pizza sairiam brancos no papel).

### Chart.js sem depender do CDN

A página tenta primeiro `vendor/chart.umd.js` e só então o `cdn.jsdelivr.net`.
O dashboard é aberto de dentro de rede corporativa, onde CDN costuma estar
bloqueado, e antes disso um CDN inacessível devolvia **uma página em branco sem
uma linha de erro**. Hoje, se nem a cópia local nem o CDN responderem, a página
diz exatamente o que faltou — e o mesmo vale para o `data.js`.

Para gerar a cópia local: **Actions → "Versiona Chart.js em vendor/" → Run
workflow**. Roda uma vez só. O download vem do registro do npm via `npm pack`,
que valida o pacote pelo integrity hash publicado — buscar direto de um CDN não
daria essa garantia.

## Desenvolvimento

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                       # travas de integridade e resumo do e-mail
ruff check .
python -m http.server 8000   # e abrir http://localhost:8000
```

Abrir o `index.html` direto do disco não funciona: o navegador bloqueia o
`data.js` por `file://`. A página avisa isso em vez de ficar em branco.

## Fonte

[Dados abertos da ANP — vendas de derivados de petróleo](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos) · volumes em mil m³.
