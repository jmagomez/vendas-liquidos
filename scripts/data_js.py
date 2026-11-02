"""Leitura e escrita dos artefatos de dados do painel.

Antes deste modulo o formato estava implementado tres vezes: no script de
atualizacao, no Python embutido no workflow (que monta o e-mail) e no
JavaScript do dashboard. Tres copias da mesma regra de decodificacao e tres
chances de uma delas ficar para tras: quando o produto entrou na chave e as
linhas passaram de 5 para 6 campos, uma copia desatualizada nao daria erro
nenhum -- somaria os campos errados e reportaria numeros inventados com cara de
certos. As duas copias Python vivem aqui; o painel le `campos` do proprio
artefato, que e o mesmo contrato.
"""
from pathlib import Path

import cubos

# Numero e ordem dos campos por linha em rows. Fica gravado no proprio artefato
# (chave "campos") para que quem le nao precise assumir o passo.
CAMPOS = ["mes", "comp", "uf", "mkt", "prod", "qtd"]

# Formato anterior a entrada do produto na chave. `campos_de` cai aqui se a
# marca faltar -- assumir o formato novo produziria numeros errados em silencio.
CAMPOS_LEGADO = ["mes", "comp", "uf", "mkt", "qtd"]

# Quantidades sao gravadas como inteiro: mil m3 com 4 casas decimais.
ESCALA = 10000


def carregar(caminho: Path):
    """Le o artefato anterior de `data/`, ao lado do caminho dado. None se nao houver.

    Ate 2026-11 isto lia um data.js de 13,9 MB com tudo dentro. A migracao para
    `data/` (meta.json + cubo.bin.gz) ja rodou, e o recuo que lia o formato
    antigo foi removido junto: manter duas formas de ler o artefato na arvore
    convida a proxima pessoa a "dar suporte" as duas para sempre.

    Se `data/` sumir, isto devolve None e a rodada NAO remenda nada -- a trava
    de regressao barra o encolhimento da serie e a rotina para alto, que e o
    desfecho correto.
    """
    return cubos.ler(Path(caminho).parent)


def escrever(caminho: Path, data: dict) -> None:
    """Grava os artefatos: data/ (canonico) e o data.js carregador.

    Antes isto escrevia um unico data.js com tudo dentro -- 13,9 MB de JSON que
    o painel baixava num <script> SINCRONO antes de pintar um pixel, e que o
    repositorio versionava inteiro a cada rodada. Agora:

        data/meta.json      dimensoes, marcas e proveniencia   (~18 KB)
        data/cubo.bin.gz    as linhas, colunar e comprimido    (~2,1 MB)
        data/cubo-mes-*.json  cubos marginais, de onde o painel novo tira a
                              tela inteira sem baixar o cubo completo
        data.js             ~3 KB que buscam o que esta acima

    Cada arquivo e escrito de forma atomica (tmp + os.replace), pelo mesmo
    motivo de sempre: um job interrompido no meio nao pode deixar artefato
    truncado sendo servido como se fosse bom.
    """
    caminho = Path(caminho)
    cubos.escrever(caminho.parent, data)
    cubos.escrever_carregador(caminho)


def campos_de(d: dict):
    """Esquema do artefato lido, com fallback explicito para o formato antigo."""
    return d.get("campos") or CAMPOS_LEGADO


def indices(d: dict):
    """Posicao de cada campo dentro de uma linha. `prod` pode nao existir."""
    campos = campos_de(d)
    idx = {nome: campos.index(nome) for nome in campos}
    return idx, len(campos)


def iter_linhas(d: dict):
    """Percorre as linhas ja decodificadas.

    Devolve (mes, comp, uf, mkt, prod, qtd) com indices inteiros e qtd em
    mil m3 (float). `prod` vem None em artefatos do formato antigo.
    """
    idx, passo = indices(d)
    rows = d["rows"]
    i_mes, i_comp = idx["mes"], idx["comp"]
    i_uf, i_mkt, i_qtd = idx["uf"], idx["mkt"], idx["qtd"]
    i_prod = idx.get("prod")
    for i in range(0, len(rows), passo):
        yield (
            rows[i + i_mes],
            rows[i + i_comp],
            rows[i + i_uf],
            rows[i + i_mkt],
            rows[i + i_prod] if i_prod is not None else None,
            rows[i + i_qtd] / ESCALA,
        )


def volume_por_mes(d: dict):
    """Volume total (mil m3) por indice de mes."""
    tot = [0.0] * len(d["months"])
    for mes, _, _, _, _, qtd in iter_linhas(d):
        tot[mes] += qtd
    return tot


def parciais(d: dict):
    """Meses que a ANP ainda nao consolidou, conforme gravado pela rotina.

    Artefatos gerados antes desta marca nao tem a chave: devolvem lista vazia,
    que e o comportamento antigo (todo mes tratado como fechado).
    """
    return list(d.get("parciais") or [])


def meses_completos(d: dict):
    """Indices dos meses fechados, na ordem da serie."""
    p = set(parciais(d))
    return [i for i, m in enumerate(d["months"]) if m not in p]


def ultimo_mes_completo(d: dict):
    """Nome do ultimo mes fechado, ou None se nao houver nenhum."""
    completos = meses_completos(d)
    return d["months"][completos[-1]] if completos else None
