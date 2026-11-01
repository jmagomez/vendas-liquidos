"""Canonicalizacao de nomes de agente regulado.

Por que isto importa mais do que parece: o HHI e QUADRATICO na participacao.
Um agente com 20% de mercado contribui 400 pontos; partido em dois de 10%,
contribui 200. Duplicar o rotulo de um agente grande derruba o indice quase
pela metade sem mudar um unico metro cubico de volume -- e nenhuma trava de
volume deste repositorio pegaria isso, porque o total nao muda.

MEDICAO ANTES DO DESENHO (data.js de 2026-10, 217 agentes, 2017-01 a 2026-08):

    ruido tipografico puro (NFC + espacos duplicados): 0 nomes
    nomes que diferem so por sufixo societario:        0 grupos
    marcas repetidas em CNPJs distintos:               ha, e sao legitimas

O ultimo ponto e o que decide tudo. Exemplo real do arquivo:

    ARAPETRO DISTRIBUIDORA DE COMBUSTIVEIS LTDA
    ARAPETRO DISTRIBUIDORA DE PETROLEO LTDA.

Mesma marca, duas pessoas juridicas. Qualquer regra automatica por semelhanca
-- prefixo comum, distancia de edicao, raiz sem sufixo societario -- fundiria
as duas e publicaria um HHI mais alto do que o real, em silencio. E o erro
simetrico ao que se queria evitar, e pior: inventado por nos, nao pela fonte.

DAI A DIVISAO EM DUAS CAMADAS:

1. Normalizacao TIPOGRAFICA, automatica e irrestrita (`normalizar`): NFC e
   colapso de espacos. Nao funde nomes distintos -- so faz duas grafias
   byte-diferentes do MESMO texto virarem uma. Hoje e no-op; e barata e
   protege de ruido futuro.

2. Fusao por MAPA DE ALIASES versionado (`aplicar`), em scripts/aliases_agentes.json.
   Explicita, revisada em PR, com motivo registrado. Nenhum numero publicado
   muda sem decisao humana no historico do git.

E a camada que falta nas duas: DETECCAO (`detectar_variantes`), que aponta
candidatos a alias sem nunca aplica-los. O relatorio vai para o log da rotina e
para a proveniencia; quem decide e voce.
"""
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

# Sufixos societarios, usados SO para detectar candidatos -- nunca para fundir.
SUFIXOS = (
    "SA", "S A", "LTDA", "ME", "EPP", "EIRELI", "EIRELLI", "CIA",
    "EM RECUPERACAO JUDICIAL", "MASSA FALIDA",
)
_RE_SUFIXO = re.compile(r"\s+(" + "|".join(SUFIXOS) + r")$")

# Fracao maxima dos agentes que o mapa de aliases pode fundir numa rodada. Um
# mapa que funde 30% dos agentes nao e limpeza de grafia: e reorganizacao
# editorial da serie, e isso precisa ser olhado por um humano antes de virar
# numero publicado.
MAX_FRACAO_FUNDIDA = 0.10
# Quantas fusoes passam sem precisar caber na fracao. Existe porque num conjunto
# pequeno (um teste, um recorte) uma unica fusao legitima ja seria 50%.
TOLERANCIA_FUSOES = 3


def normalizar(nome: str) -> str:
    """Ruido tipografico puro: NFC e colapso de espacos. Seguro por construcao.

    Nao remove acento, nao muda caixa, nao toca em pontuacao -- nada que possa
    aproximar dois nomes que a ANP considera agentes diferentes.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", nome or "")).strip()


def raiz_comparavel(nome: str) -> str:
    """Forma agressivamente simplificada, usada SO para DETECTAR candidatos.

    Sem acento, caixa alta, sem pontuacao e sem sufixo societario. Dois nomes
    com a mesma raiz sao *candidatos* a alias -- e nada alem disso.
    """
    t = unicodedata.normalize("NFKD", nome or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t.upper())
    t = re.sub(r"\s+", " ", t).strip()
    while True:
        novo = _RE_SUFIXO.sub("", t)
        if novo == t:
            return t
        t = novo


def detectar_variantes(nomes) -> dict:
    """Agrupa nomes que compartilham a raiz comparavel. NAO funde nada.

    Devolve {raiz: [nomes]} apenas para raizes com mais de um nome.
    """
    grupos = defaultdict(set)
    for n in nomes:
        grupos[raiz_comparavel(n)].add(n)
    return {r: sorted(v) for r, v in grupos.items() if len(v) > 1}


def carregar_aliases(caminho) -> dict:
    """Le o mapa de aliases e valida a estrutura.

    Formato (JSON): {"de": {"VARIANTE": "CANONICO", ...}, "motivos": {...}}
    `motivos` e documentacao e nao participa da aplicacao, mas e exigido para
    cada entrada: alias sem motivo registrado e decisao sem rastro.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    de = {normalizar(k): normalizar(v) for k, v in (dados.get("de") or {}).items()}
    motivos = {normalizar(k): v for k, v in (dados.get("motivos") or {}).items()}

    problemas = []
    for variante, canonico in de.items():
        if variante == canonico:
            problemas.append(f"{variante!r} aponta para si mesmo")
        if canonico in de:
            # Cadeia A->B->C: ambigua e dependente de ordem. Melhor exigir que o
            # mapa ja esteja resolvido do que resolver por conta propria.
            problemas.append(f"cadeia: {variante!r} -> {canonico!r}, que tambem e variante")
        if variante not in motivos:
            problemas.append(f"{variante!r} sem motivo registrado")
    if problemas:
        raise RuntimeError(
            f"mapa de aliases invalido ({caminho.name}): " + " | ".join(problemas[:5])
        )
    return de


def carregar_revisados(caminho) -> dict:
    """Raizes ja olhadas e deliberadamente NAO fundidas, com o motivo.

    Serve para a CI distinguir "candidato novo, ninguem olhou" de "candidato
    conhecido, decisao registrada". Sem isso, so restariam dois extremos ruins:
    falhar para sempre nos mesmos quatro, ou nao falhar nunca.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return dict(dados.get("revisados") or {})


def aplicar(agg, aliases: dict):
    """Aplica normalizacao tipografica e o mapa de aliases ao cubo agregado.

    Devolve (novo_agg, fusoes), com fusoes = {canonico: [variantes fundidas]}.
    A normalizacao tipografica e sempre aplicada; os aliases, so os declarados.
    """
    agentes_antes = {normalizar(k[1]) for k in agg}

    # O destino do alias tem de ser um nome que a ANP realmente publica. Conferir
    # DEPOIS de aplicar nao serve para nada: o proprio alias teria criado o nome.
    # Um ponto final a menos no mapa viraria um agente novo, com a grafia errada,
    # e a fusao pretendida simplesmente nao aconteceria -- em silencio.
    orfaos = sorted(set(aliases.values()) - agentes_antes)
    if orfaos:
        raise RuntimeError(
            f"{len(orfaos)} alias apontam para nome que nao aparece nos dados "
            f"(erro de digitacao no mapa?): {orfaos[:5]}. data.js NAO foi alterado."
        )

    novo = defaultdict(float)
    fusoes = defaultdict(set)
    for (mes, comp, uf, mkt, prod), q in agg.items():
        limpo = normalizar(comp)
        canonico = aliases.get(limpo, limpo)
        if canonico != comp:
            fusoes[canonico].add(comp)
        novo[(mes, canonico, uf, mkt, prod)] += q

    sumidos = len(agentes_antes) - len({k[1] for k in novo})
    # Piso absoluto alem da fracao: num conjunto pequeno, uma fusao legitima ja
    # seria uma fracao enorme. Ate TOLERANCIA_FUSOES fusoes passam sem discussao;
    # acima disso, tambem tem de caber na fracao.
    if sumidos > max(TOLERANCIA_FUSOES, len(agentes_antes) * MAX_FRACAO_FUNDIDA):
        raise RuntimeError(
            f"os aliases fundiram {sumidos} de {len(agentes_antes)} agentes "
            f"({sumidos / len(agentes_antes):.0%}), acima do limite de "
            f"{MAX_FRACAO_FUNDIDA:.0%}. Isso nao e limpeza de grafia, e "
            "reorganizacao da serie. data.js NAO foi alterado."
        )
    return novo, {k: sorted(v) for k, v in fusoes.items()}


def hhi_do_mes(agg, mes: str) -> float:
    """HHI por agente regulado no mes, em pontos (0-10.000).

    Serve para medir o efeito de uma fusao: e exatamente o indicador que uma
    duplicata de rotulo distorce.
    """
    vol = defaultdict(float)
    for (m, comp, _, _, _), q in agg.items():
        if m == mes:
            vol[comp] += q
    total = sum(vol.values())
    if total <= 0:
        return 0.0
    return sum((v / total * 100) ** 2 for v in vol.values())
