# Vendas de Combustíveis Líquidos — Dashboard ANP

Dashboard interativo com as vendas mensais de combustíveis líquidos por distribuidora (dados abertos da ANP), com filtros por companhia, estado (UF de destino), tipo de consumidor, combustível e período, série de variação anual, evolução do mix, ranking de companhias, indicadores de estrutura de mercado e exportação em CSV.

**Dashboard (Chart.js, painel original):** https://jmagomez.github.io/vendas-liquidos/

**Painel novo (Vite + React + TypeScript):** https://jmagomez.github.io/vendas-liquidos/painel/

Os dois leem o MESMO artefato em `data/` — uma fonte, não duas. O painel novo
abre com 229 KB em vez de 3,5 MB bloqueantes, traz as métricas setoriais em base
energética e os avisos de cobertura descritos abaixo; o original segue na raiz
para comparação lado a lado enquanto o cruzamento, a exportação e a impressão do
novo não tiverem substituído tudo o que ele faz.

## Estrutura

```
vendas-liquidos/
├── scripts/
│   ├── update_dashboard.py   # baixa o zip da ANP, agrega e gera o artefato
│   ├── leitura.py            # detecção de encoding e trava de mojibake
│   ├── membros.py            # leitura multi-membro do zip, lacunas, rótulos
│   ├── agentes.py            # canonicalização de nome de agente regulado
│   ├── cobertura.py          # onde a fonte passa a cobrir cada produto
│   ├── cubos.py              # formato binário colunar + cubos marginais
│   ├── data_js.py            # leitura/escrita do artefato (contrato único)
│   └── resumo_email.py       # monta o resumo do e-mail mensal
├── data/                     # artefato que o painel carrega
│   ├── meta.json             # dimensões, marcas de qualidade, proveniência
│   ├── cubo.bin.gz           # 725 mil linhas, colunar, 2,1 MB
│   └── cubo-mes-*.json       # marginais (mês × dimensão), 229 KB no total
├── data.js                   # carregador de 3 KB (era 13,9 MB de JSON)
├── index.html                # painel antigo (Chart.js, na raiz)
├── web/                      # painel novo (Vite + React + TypeScript)
│   └── src/
│       ├── dados.ts          # carga dos cubos marginais
│       ├── financeiro.ts     # série, média móvel, a/a, HHI
│       ├── setor.ts          # ciclo Otto em base energética, CR4
│       ├── cruzamento.ts     # cubo completo sob demanda + CSV
│       └── *.test.ts         # vitest, inclusive canário no artefato real
├── painel/                   # bundle publicado (gerado, não editado à mão)
└── .github/workflows/
    ├── update-dashboard.yml  # rotina (dias 5 e 28) + e-mail
    ├── painel.yml            # compila web/ e publica em painel/
    ├── diagnostico-zip.yml   # só lista os membros do zip, não escreve nada
    ├── vendorizar.yml        # sob demanda: baixa o Chart.js para vendor/
    └── ci.yml                # ruff + pytest + tsc + vitest + build
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

A rotina falha alto em vez de gravar dados ruins. São oito travas, e cada uma
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

7. **Janela comparável por produto.** Medido no artefato de 2026-11-05, o
   Diesel B sai de 46 mil m³ em dez/2009 para 3.037 em mar/2010: a fonte da ANP
   só passa a trazer diesel em 2010, e o diesel é metade do mercado. Somar
   2007-2009 com 2010 em diante mostra um mercado triplicando por artefato de
   cobertura — e o HHI de 2007-2009, calculado sem as distribuidoras de diesel,
   é o índice de outro mercado com o mesmo nome. Nenhuma trava de volume pega
   isso: os números de 2007-2009 estão **certos para o que a fonte traz**, e o
   que está errado é compará-los. `scripts/cobertura.py` detecta o degrau
   (12 meses somando menos de 10% dos 12 seguintes), grava
   `cobertura.inicio_comparavel` no artefato, e a rotina falha se a janela
   **encurtar** de uma rodada para a outra. A comparação é entre janelas
   vizinhas, nunca contra o máximo da série: o Óleo Comb. cai 80% em 18 anos de
   verdade, e contra o máximo seria acusado e truncaria a série.
8. **Rótulo do arquivo conferido contra o conteúdo.**
   `Liquidos_Vendas_Historico_2007_a_2017.csv` cobre 2007-01 a **2016-12**. O ano
   de 2017 inteiro não está nele, apesar do nome — é por isso que 2017 precisa
   ser herdado do artefato anterior, ou seja, **deixou de ser reproduzível a
   partir do zip de hoje**. A divergência é reportada no artefato e aparece no
   painel; não é "corrigida", porque o arquivo é o que é.

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

A execução de 2026-09-11 contou **448 linhas negativas em 1.033.272** (0,04%),
distribuídas por todos os anos; agregadas, somam −11 mil m³ contra 1,3 milhão de
volume total. São estornos publicados pela própria agência: entram na soma e
ficam contados no log, porque um *salto* nessa contagem seria sinal de outra
coisa. (O número antigo aqui, "~185", contava combinações agregadas negativas no
`data.js`, não linhas do CSV — duas coisas diferentes.)

## Métricas setoriais (painel novo)

### Ciclo Otto em base energética

Um litro de etanol hidratado não substitui um litro de gasolina C: o PCI do
hidratado é ~21,3 MJ/L contra ~29,0 MJ/L da gasolina C com E32 — 73,5%. Ler o
mix por litro, como o painel antigo faz, superestima o etanol. Medido em
set/2026 (3.874 mil m³ de gasolina C e 2.028 de hidratado):

| | |
|---|---|
| Hidratado, participação em **volume** | 34,4% |
| Hidratado, participação em **energia** | 27,8% |
| Diferença | **6,6 pontos** |
| **Etanol total** no ciclo Otto (hidratado + anidro) | **45,6%** |
| Teor de anidro na gasolina C | 32,0% |
| Paridade de rendimento | 73,5% |

O "etanol total" é o número que o setor usa: o anidro misturado na gasolina C
também é etanol, e com E32 quase um terço do que se vende como gasolina é
etanol. As duas leituras ficam na tela juntas — a de volume responde "quantos
litros" (pergunta logística) e a de energia responde "quanta energia" (pergunta
de substituição). Nenhuma substitui a outra.

A paridade de rendimento é a regra dos "70%" do posto, que **deixou de ser 70%**
quando o teor subiu: 72,2% com E27, 73,0% com E30, 73,5% com E32.

O teor de anidro vem de tabela datada em `web/src/setor.ts`, ponderada por dia
dentro do mês — o E27 entrou em 16/03/2015, e carimbar 27% em março inteiro
erraria o mês. Entradas: E20 out/2011, E25 01/05/2013, E27 16/03/2015, E30
01/08/2025, E32 01/08/2026. **Antes de out/2011 as métricas energéticas devolvem
`n/d`**: a mistura oscilou entre 20% e 25% com datas que não foram confirmadas em
fonte primária, e o indicador é linear no teor — um chute ali seria número
inventado. A ANP publica "Gasolina C" sem separar comum de premium (que ficou em
25%), o que empurra o teor efetivo para baixo em décimos de ponto.

### Concentração por UF

O HHI nacional de set/2026 é **1.142** pontos, com CR4 de 59,5% — faixa de
mercado *não concentrado*. Só que ninguém compra combustível no mercado
nacional. O mesmo índice por UF de destino, nos mesmos dados:

| UF | HHI | CR4 | Agentes |
|---|---|---|---|
| AP | 4.853 | 99,8% | 5 |
| AM | 3.953 | 92,5% | 6 |
| AC | 2.868 | 93,8% | 5 |
| SE | 2.759 | 88,0% | 18 |
| ... | | | |
| GO | 890 | — | — |

Mediana de 1.660, quatro UFs acima de 2.500 (faixa de alta concentração). O
número nacional não está errado; está medindo outra coisa. HHI e CR4 ficam
juntos porque erram de formas diferentes: quatro agentes de 25% e um de 60%
cercado de pequenos dão HHI parecido e CR4 bem distinto.

Em toda leitura de concentração, duas ressalvas que o painel repete na tela:
**agente regulado ≠ grupo econômico** (grupo com duas razões sociais conta como
dois, então todo HHI aqui é *piso* da concentração real), e a UF é a de
**destino declarado**, não o ponto de venda.

### Cruzamento de duas dimensões

A margem de uma dimensão já somou todas as outras, então "VIBRA em SP" não sai
de "VIBRA" com "SP" — precisa das 725 mil linhas do cubo completo. São 2,1 MB,
buscados **quando o usuário clica**, não no boot: a tela abre com 229 KB de
cubos marginais, e quem só quer a série mensal nunca paga por isso. A mesma
carga sob demanda serve a concentração por UF. O CSV sai com `;`, decimal `,` e
BOM, para abrir no Excel em pt-BR sem caixa de diálogo.

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

Painel novo:

```bash
cd web
npm install
npm run typecheck            # tsc, strict + noUncheckedIndexedAccess
npm test                     # vitest: métricas, formato do cubo e canário
npm run build                # gera web/dist (o painel.yml publica em painel/)
npm run dev                  # servidor de desenvolvimento
```

Os três entram no CI do pull request. Antes disso um erro de TypeScript passava
no PR e só quebrava depois do merge, na build do `painel.yml`.

O canário `web/src/artefato.test.ts` lê o `data/` versionado e reconcilia a soma
do cubo completo, mês a mês, com cada um dos quatro cubos marginais: são cinco
caminhos independentes para o mesmo total. É a trava que pega o Python que
*escreve* e o TypeScript que *lê* discordando sobre largura de coluna, ordem de
campo ou escala — divergência que passa nos dois lados isoladamente e só
apareceria no painel, como número errado sem erro na tela.

Abrir o `index.html` direto do disco não funciona: o navegador bloqueia o
`data.js` por `file://`. A página avisa isso em vez de ficar em branco.

## Fonte

[Dados abertos da ANP — vendas de derivados de petróleo](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos) · volumes em mil m³.
