"""Leitura, escrita e decodificacao do data.js.

Antes deste modulo o formato do data.js estava implementado tres vezes: no
script de atualizacao, no Python embutido no workflow (que monta o e-mail) e no
JavaScript do dashboard. Tres copias da mesma regra de decodificacao e tres
chances de uma delas ficar para tras: quando o produto entrou na chave e as
linhas passaram de 5 para 6 campos, uma copia desatualizada nao daria erro
nenhum -- somaria os campos errados e reportaria numeros inventados com cara de
certos. As duas copias Python agora vivem aqui; o dashboard le `campos` do
proprio arquivo, que e o mesmo contrato.
"""
import json
import os
from pathlib import Path

import cubos

# Numero e ordem dos campos por linha em data.js["rows"]. Fica gravado no
# proprio arquivo (chave "campos") para que quem le nao precise assumir o passo.
CAMPOS = ["mes", "comp", "uf", "mkt", "prod", "qtd"]

# Formato anterior a entrada do produto na chave. Usado so quando o arquivo lido
# nao traz a marca "campos" -- assumir o formato novo ali produziria numeros
# errados em silencio.
CAMPOS_LEGADO = ["mes", "comp", "uf", "mkt", "qtd"]

PREFIXO = "window.VENDAS = "

# Quantidades sao gravadas como inteiro: mil m3 com 4 casas decimais.
ESCALA = 10000


def carregar(caminho: Path):
    """Le o artefato anterior. None se nao houver nenhum legivel.

    A partir de 2026-11 o artefato canonico e `data/` ao lado do caminho dado
    (meta.json + cubo.bin.gz, ~2,1 MB); o data.js virou um carregador de 2 KB.
    A leitura do data.js ANTIGO continua aqui como recuo porque a primeira
    rodada depois da migracao ainda encontra o arquivo velho no repositorio --
    e e dele que vem a lacuna de 2017, que seria perdida se `carregar`
    devolvesse None.
    """
    caminho = Path(caminho)
    d = cubos.ler(caminho.parent)
    if d is not None:
        return d
    if not caminho.exists():
        return None
    try:
        bruto = caminho.read_text(encoding="utf-8").strip()
        if not bruto.startswith(PREFIXO):
            # Ja e o carregador, e data/ nao existe: nao ha artefato anterior.
            return None
        return json.loads(bruto.removeprefix(PREFIXO).rstrip(";\n"))
    except Exception as exc:  # noqa: BLE001
        print(f"[data_js] aviso: nao consegui ler {caminho} ({exc})")
        return None


def escrever(caminho: Path, data: dict) -> None:
    """Grava os artefatos: data/ (canonico) e o data.js carregador.

    Antes isto escrevia um unico data.js com tudo dentro -- 13,9 MB de JSON que
    o painel baixava num <script> SINCRONO antes de pintar um pixel, e que o
    repositorio versionava inteiro a cada rodada. Agora:

        data/meta.json      dimensoes, marcas e proveniencia   (~18 KB)
        data/cubo.bin.gz    as linhas, colunar e comprimido    (~2,1 MB)
        data/cubo-mes-*.json  cubos marginais, para o painel ter numero
                              na tela antes do cubo completo chegar
        data.js             ~2 KB que buscam o que esta acima

    Cada arquivo e escrito de forma atomica (tmp + os.replace), pelo mesmo
    motivo de sempre: um job interrompido no meio nao pode deixar artefato
    truncado sendo servido como se fosse bom.
    """
    caminho = Path(caminho)
    cubos.escrever(caminho.parent, data)
    cubos.escrever_carregador(caminho)


def campos_de(d: dict):
    """Esquema do arquivo lido, com fallback explicito para o formato antigo."""
    return d.get("campos") or CAMPOS_LEGADO


def indices(d: dict):
    """Posicao de cada campo dentro de uma linha. `prod` pode nao existir."""
    campos = campos_de(d)
    idx = {nome: campos.index(nome) for nome in campos}
    return idx, len(campos)


def iter_linhas(d: dict):
    """Percorre as linhas ja decodificadas.

    Devolve (mes, comp, uf, mkt, prod, qtd) com indices inteiros e qtd em
    mil m3 (float). `prod` vem None em arquivos do formato antigo.
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

    Arquivos gerados antes desta marca nao tem a chave: devolvem lista vazia,
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
