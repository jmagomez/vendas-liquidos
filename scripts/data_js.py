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
    """Le um data.js. Devolve None se o arquivo nao existe ou nao e legivel."""
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    try:
        bruto = caminho.read_text(encoding="utf-8").strip()
        return json.loads(bruto.removeprefix(PREFIXO).rstrip(";\n"))
    except Exception as exc:  # noqa: BLE001
        print(f"[data_js] aviso: nao consegui ler {caminho} ({exc})")
        return None


def escrever(caminho: Path, data: dict) -> None:
    """Grava o data.js de forma atomica: arquivo temporario + os.replace.

    A rotina roda sozinha num runner que pode ser interrompido (timeout, job
    cancelado, disco cheio). Um write_text direto que morre pela metade deixa um
    data.js truncado -- JSON invalido, dashboard em branco, e a proxima execucao
    perde a base de comparacao contra a qual as travas de regressao existem.
    os.replace e atomico no mesmo sistema de arquivos: ou fica o arquivo antigo
    inteiro, ou o novo inteiro.
    """
    caminho = Path(caminho)
    texto = PREFIXO + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    tmp = caminho.with_name(caminho.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(texto)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, caminho)
    finally:
        if tmp.exists():
            tmp.unlink()


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
