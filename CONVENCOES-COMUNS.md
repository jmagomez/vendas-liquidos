# Convenções comuns — pipelines de dados do jmagomez

**Este é o arquivo canônico**, em
[jmagomez/convencoes-claude](https://github.com/jmagomez/convencoes-claude).
Toda cópia em outro repositório é gerada pelo workflow "Sincronizar convenções"
e é sobrescrita sem aviso na rodada seguinte. Para mudar uma regra, mude aqui.

Cada repositório de destino guarda a cópia na raiz e a carrega com uma linha
`@CONVENCOES-COMUNS.md` no seu próprio `CLAUDE.md` — o Claude Code expande
imports relativos sem pedir confirmação, então a regra vale desde a primeira
mensagem da conversa.

Nada aqui foi inventado: cada regra já está escrita, com palavras diferentes,
em pelo menos dois dos repositórios — `vendas-liquidos`, `anp-ppi-dashboard`,
`b3-derivatives-dashboard`, `mag7-financial-dashboard`, `projeto_bloomberg`,
`resumo-focus`, `boletim_focus`, `oil-gas-financial-dashboard`. A citação
embaixo de cada regra diz de onde ela veio, porque regra sem origem vira
folclore e a primeira pessoa com pressa a remove.

---

## O que estes projetos são

Pipelines que coletam dado público de fonte oficial (ANP, BCB, B3, SEC, Yahoo),
transformam, publicam um artefato estático no GitHub Pages e mandam e-mail.
Rodam sozinhos, em agenda, e são lidos como se fossem verdade.

**O pior desfecho não é a rotina falhar. É ela publicar número errado sem avisar
ninguém.** Tudo abaixo existe por causa disso, e é o critério para decidir
qualquer dúvida que não esteja coberta.

---

## 1. Dado

**Nunca invente número.** Sem fonte confiável e datada: mantenha o valor
anterior, ou publique `n/d`. Nunca interpole, extrapole, projete, complete com
média ou assuma zero por omissão. Publicar um pregão um dia depois é melhor do
que publicá-lo errado hoje.
> Está em todos os sete repositórios.

**Todo número carrega a data a que pertence.** Duas séries com fechamentos
diferentes nunca aparecem sob um rótulo só. Dado velho exibido com a sua data é
informação; exibido sem data é mentira.
> `anp-ppi` (invariante 2), `mag7`, `vendas-liquidos`.

**Não codifique calendário de feriado.** Pergunte à fonte qual foi o último
período válido — o campo existe, e ele acerta emenda e feriado regional que
nenhuma lista local acerta.
> `projeto_bloomberg` (regra 2).

**Agregação num lugar só.** O cálculo nasce no Python, com teste; o front lê e
formata. Reimplementar a conta na camada de apresentação cria duas verdades que
um dia divergem — e divergem em silêncio.
> `b3-derivatives` (invariante 3 e 7), `vendas-liquidos` (invariante 6), `mag7`.

**Uma definição por coisa.** Lista de códigos, regra de unidade, limiar: moram
num módulo só, e os outros leem. Já houve regra de unidade em três arquivos, e
os três divergiram.
> `b3-derivatives` (invariante 4).

**Escrita idempotente.** Arquivo cujo conteúdo não mudou não é tocado, e o
carimbo de geração passa a significar *quando este dado foi gerado*, não *quando
o robô passou por aqui*. Sem isso o pipeline diário produz um commit por dia sem
dado novo e apaga do histórico a informação mais útil: quando o dado mudou.
> `anp-ppi` (invariante 5), `vendas-liquidos`.

---

## 2. Falhas e alarmes

**"Não consegui coletar" não é "coletei e o dado está errado".** São severidades
opostas:

| situação | reação |
|---|---|
| erro de rede, HTTP 5xx, fonte atrasada | degrada: segue com o dado que tem e **avisa** |
| HTTP 4xx, arquivo truncado, layout mudado | **para na hora**, sem retry |

404 é arquivo que mudou de lugar e 403 é bloqueio declarado: os dois precisam de
gente, não de paciência.
> `anp-ppi` (invariante 8), `projeto_bloomberg` (contrato de saída).

**Alarme só quando há ação possível.** Alarme que toca todo dia sem exigir nada
ensina a ignorar o alarme — e o próximo, que exigir, vai parecer igual aos
anteriores. Em `projeto_bloomberg` isso custou 34 rodadas falhando sem que nada
estivesse errado. Se a falha se repete e a reação é sempre "esperar", ela deve
ser aviso, não erro; escale por insistência, não por ocorrência.
> `projeto_bloomberg` (regra 5), `anp-ppi` (invariante 8).

**Trava que dispara é hipótese sobre a fonte, não bug nosso.** Vá olhar o arquivo
da origem antes de mexer no parser. **Não afrouxe limiar para a rotina passar.**
Mudar um limiar exige, no PR: o trecho da fonte que motivou, e um teste que falha
antes e passa depois.

O contrário também vale: trava que acusa dado bom também é defeito. Em
`vendas-liquidos`, a trava de mojibake derrubou uma rodada acusando `Ã`, que é
letra legítima em `DISTRIBUIÇÃO`.
> `vendas-liquidos`, `anp-ppi`, `projeto_bloomberg`.

**Escrita de artefato é atômica** (temporário + `os.replace`). Runner
interrompido no meio de um `write_text` deixa arquivo inválido e, pior, a próxima
rodada sem base de comparação.
> `vendas-liquidos` (invariante 8), `anp-ppi`.

---

## 3. Testes

- **Nenhum teste toca a rede. Sem exceção.** Use fixtures reais, capturadas da
  fonte, em vez de simular o que você imagina que ela devolve.
- **Teste confere contra aritmética independente**, não contra a própria
  implementação. Ao mudar uma métrica, acrescente um caso calculável à mão.
- **O docstring diz por que o teste existe**, citando o incidente que o motivou.
  A suíte é um registro de falhas reais, não um exercício de cobertura.
> `b3-derivatives`, `projeto_bloomberg` (regra 7), `vendas-liquidos`, `anp-ppi`.

---

## 4. Código

- **Português.** Comentário, docstring, nome de função, teste e mensagem de
  commit. Termo técnico consagrado fica em inglês.
- **Comentário e identificador sem acento** (ASCII); **mensagem de erro e texto
  de tela com acento**. `cabecalho` na variável, "cabeçalho não confere" no
  `raise`.
- **Constante de regra de negócio em maiúscula, no topo do módulo, com o
  comentário do porquê daquele número.** Número mágico no meio da função é a
  forma mais fácil de um limiar virar folclore.
> `projeto_bloomberg` (regra 6), `b3-derivatives`, `vendas-liquidos`, `anp-ppi`.

---

## 5. Publicação

- **Mudança entra por pull request, com CI verde.** Não commite direto na `main`.
- **O GitHub App não escreve em `.github/workflows/`** (falta o escopo
  `workflow`; `push_files` e `gh` devolvem 403). O caminho é o editor web do
  GitHub — e conferir o resultado pela API depois.
- **Confira o conteúdo publicado depois de todo push.** `git hash-object` local
  contra o `sha` que a API devolve, ou `git clone --depth 1` + `cmp`. Já houve
  acento trocado em silêncio numa transcrição: o tamanho batia e o diff não
  mostrava.
- **`raw.githubusercontent.com` serve conteúdo velho por minutos.** Para conferir
  o que foi realmente commitado, use a API de contents ou fixe o SHA.
- **Reescrever arquivo inteiro pela API perde caractere invisível** — espaço
  inseparável, hífen não separável, aspas tipográficas. Nenhum teste pega.
> `projeto_bloomberg` (ambiente), `anp-ppi` (armadilhas), `mag7`, `b3-derivatives`.

---

## 6. Ambiente

- **O shell do sandbox não alcança as fontes** (gov.br, Yahoo, B3). O pipeline só
  roda de verdade no runner; para trabalhar offline, carregue os artefatos já
  publicados.
- **Mas o `web_fetch` do Claude alcança.** Serve para responder a pergunta que
  mais importa quando a coleta falha: *a origem está no ar?* Se ela responde e o
  runner não, o problema é o cliente, não o endereço — e nenhuma quantidade de
  paciência resolve bloqueio de IP.
- **Antes de propor correção, leia o log da rodada que falhou.** Falha de rotina
  quase sempre é a fonte, não o código.
> `anp-ppi`, `projeto_bloomberg` (diagnóstico).

---

## 7. Texto

Público: analista, com formação em finanças. Conteúdo informativo, **sem
recomendação de investimento**.

**Nunca usar:** "cirúrgico", "do zero", "próximo nível", "virada de chave",
"destrava", "regra de ouro", a construção "não é X, é Y", tríades decorativas
("rápido, eficiente e escalável"), e aberturas como "Vale ressaltar que" ou
"É importante destacar".

**Afirmação de verificação é recalculada, nunca escrita à mão.** Já houve um
"erro máximo de 0,12%" fixo no HTML, que seguiu lá depois de o erro mudar.
> `resumo-focus` (vícios), `mag7` (postura), `anp-ppi` (invariante 6).

---

## O que este bloco não cobre

O que é específico de cada projeto: o fluxo de ponta a ponta, quem escreve qual
arquivo, os invariantes do domínio, as armadilhas daquela fonte e os comandos.
Isso fica no `CLAUDE.md` do repositório, que também não repete o `README` — o
`README` explica o produto, o `CLAUDE.md` explica o que quebra se alguém mexer
sem saber.
