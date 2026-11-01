"""Artefatos que o painel carrega: metadados, cubo binario e cubos marginais.

O PROBLEMA, medido no artefato de 2026-11-01 (237 meses, 725.581 combinacoes):

    data.js                      13,9 MB  (3,5 MB gzip)  <script> BLOQUEANTE
    colunar binario, gzip         2,16 MB                 fetch assincrono
    cubos marginais (mes x dim)   0,23 MB                 fetch assincrono

O `data.js` e um `<script src>` sincrono: o navegador para de construir a pagina,
baixa 3,5 MB comprimidos, descomprime 13,9 MB de texto e roda JSON.parse em cima
disso antes de pintar um pixel. Em 4G isso e um painel que nao abre. E a serie
acabou de DOBRAR (116 -> 237 meses), entao o arquivo dobrou junto.

POR QUE BINARIO COLUNAR, E NAO SO "comprimir melhor":

- o conteudo e uma matriz de inteiros pequenos. Em JSON cada numero vira texto
  mais uma virgula; em binario, 1 a 4 bytes por valor, sem separador;
- colunar porque cada coluna tem alcance proprio (mes <= 236 cabe em 1 byte,
  produto em 1, agente em 2) e valores vizinhos parecidos, o que o gzip adora.
  Intercalado, os bytes de um indice pequeno ficam espremidos entre os de uma
  quantidade grande e a compressao piora;
- e, o que mais importa no celular: `new Uint8Array(buffer)` custa ~zero,
  enquanto JSON.parse de 13,9 MB custa segundos de thread principal travada.

Os cubos marginais existem para o painel ter numero na tela ANTES de o cubo
completo chegar: a serie mensal, o mix por produto e por mercado saem de
arquivos de dezenas de KB. O cubo completo so e necessario quando o usuario
cruza filtros (agente x UF x produto), e ai ja pode ter chegado em segundo plano.

FORMATO DE `cubo.bin.gz` (gzip de):

    "VLQ1"            4 bytes, magico e versao
    n_linhas          uint32 little-endian
    n_colunas (P)     uint8
    tipos[P]          uint8 cada: 1=u8, 2=u16, 4=u32, 5=i32
    colunas           P blocos contiguos, cada um n_linhas valores LE

Gzip no arquivo, e nao no transporte, de proposito: o GitHub Pages nao comprime
`application/octet-stream`, entao confiar no servidor devolveria os 7,3 MB crus.
Assim o tamanho e o mesmo em qualquer hospedagem, e o navegador descomprime com
DecompressionStream.
"""
import array
import gzip
import io
import json
import os
import struct
from collections import defaultdict
from pathlib import Path

MAGICO = b"VLQ1"
# Codigos de tipo. Indices sao sempre sem sinal; a quantidade e sempre int32
# com sinal, porque a ANP publica estornos (quantidade negativa).
U8, U16, U32, I32 = 1, 2, 4, 5
_FORMATO = {U8: "B", U16: "H", U32: "I", I32: "i"}
_LARGURA = {U8: 1, U16: 2, U32: 4, I32: 4}

DIR_DADOS = "data"
NOME_META = "meta.json"
NOME_CUBO = "cubo.bin.gz"
# Cubos marginais: (nome do arquivo, campo da chave alem do mes).
MARGINAIS = (("cubo-mes-produto.json", "prod"),
             ("cubo-mes-uf.json", "uf"),
             ("cubo-mes-mercado.json", "mkt"),
             ("cubo-mes-agente.json", "comp"))


def _tipo_para(valores, com_sinal=False) -> int:
    if com_sinal:
        return I32
    mx = max(valores) if valores else 0
    if mx < 256:
        return U8
    if mx < 65536:
        return U16
    return U32


def codificar(data: dict) -> bytes:
    """Serializa data["rows"] no formato colunar comprimido."""
    campos = data.get("campos") or []
    p = len(campos)
    if not p:
        raise RuntimeError("data sem 'campos': nao da para saber o passo das linhas")
    rows = data["rows"]
    if len(rows) % p:
        raise RuntimeError(f"{len(rows)} inteiros nao e multiplo de {p} campos")
    n = len(rows) // p

    colunas = [rows[i::p] for i in range(p)]
    i_qtd = campos.index("qtd")
    tipos = [_tipo_para(c, com_sinal=(i == i_qtd)) for i, c in enumerate(colunas)]

    buf = io.BytesIO()
    buf.write(MAGICO)
    buf.write(struct.pack("<I", n))
    buf.write(struct.pack("<B", p))
    buf.write(bytes(tipos))
    for tipo, col in zip(tipos, colunas):
        a = array.array(_FORMATO[tipo], col)
        if sys_byteorder_big():
            a.byteswap()
        buf.write(a.tobytes())
    # mtime=0: sem isso o gzip carimba a hora e o arquivo muda a cada rodada
    # mesmo quando o conteudo e identico -- um commit por mes sem dado novo.
    return gzip.compress(buf.getvalue(), compresslevel=6, mtime=0)


def sys_byteorder_big() -> bool:
    import sys
    return sys.byteorder == "big"


def decodificar(blob: bytes, campos) -> list:
    """Inverso de `codificar`: devolve a lista plana de inteiros (rows).

    Existe para os testes e para quem precisar reconstruir o artefato sem
    passar pelo navegador. O painel faz o mesmo em JavaScript.
    """
    bruto = gzip.decompress(blob)
    if bruto[:4] != MAGICO:
        raise RuntimeError(f"cubo com magico inesperado: {bruto[:4]!r}")
    n = struct.unpack_from("<I", bruto, 4)[0]
    p = bruto[8]
    if p != len(campos):
        raise RuntimeError(f"cubo tem {p} colunas, campos tem {len(campos)}")
    tipos = list(bruto[9:9 + p])
    pos = 9 + p
    colunas = []
    for tipo in tipos:
        a = array.array(_FORMATO[tipo])
        a.frombytes(bruto[pos:pos + n * _LARGURA[tipo]])
        if sys_byteorder_big():
            a.byteswap()
        colunas.append(a)
        pos += n * _LARGURA[tipo]
    rows = [0] * (n * p)
    for j, col in enumerate(colunas):
        rows[j::p] = col
    return rows


def marginais(data: dict) -> dict:
    """Cubos mes x dimensao, para o painel ter numero antes do cubo completo.

    Formato enxuto: {"dim": "<campo>", "k": [[mes, cat], ...], "v": [qtd, ...]},
    com qtd no mesmo inteiro escalado do data.js (sem converter aqui, para nao
    introduzir uma segunda convencao de unidade).
    """
    campos = data["campos"]
    p = len(campos)
    i_mes, i_qtd = campos.index("mes"), campos.index("qtd")
    rows = data["rows"]
    saida = {}
    for arquivo, campo in MARGINAIS:
        if campo not in campos:
            continue
        ix = campos.index(campo)
        acc = defaultdict(int)
        for i in range(0, len(rows), p):
            acc[(rows[i + i_mes], rows[i + ix])] += rows[i + i_qtd]
        chaves = sorted(acc)
        saida[arquivo] = {"dim": campo,
                          "k": [list(k) for k in chaves],
                          "v": [acc[k] for k in chaves]}
    return saida


def meta(data: dict) -> dict:
    """Tudo menos as linhas: dimensoes, marcas e proveniencia.

    E o que o painel precisa para desenhar eixos, legendas e avisos antes de o
    cubo chegar.
    """
    return {k: v for k, v in data.items() if k != "rows"} | {
        "n_linhas": len(data["rows"]) // len(data["campos"]),
    }


def _escrever_atomico(caminho: Path, conteudo: bytes) -> None:
    """tmp + os.replace, pelo mesmo motivo do data.js: um job interrompido no
    meio deixaria um artefato truncado servido como se fosse bom."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(conteudo)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, caminho)
    finally:
        if tmp.exists():
            tmp.unlink()


def escrever(base: Path, data: dict) -> dict:
    """Grava data/meta.json, data/cubo.bin.gz e os cubos marginais.

    Devolve {arquivo: bytes} para a rotina poder registrar os tamanhos no log --
    e para a proxima pessoa saber, sem adivinhar, quanto o painel baixa.
    """
    pasta = Path(base) / DIR_DADOS
    pasta.mkdir(parents=True, exist_ok=True)
    tamanhos = {}

    bruto = json.dumps(meta(data), ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
    _escrever_atomico(pasta / NOME_META, bruto)
    tamanhos[NOME_META] = len(bruto)

    blob = codificar(data)
    _escrever_atomico(pasta / NOME_CUBO, blob)
    tamanhos[NOME_CUBO] = len(blob)

    for arquivo, conteudo in marginais(data).items():
        bruto = json.dumps(conteudo, separators=(",", ":")).encode("utf-8")
        _escrever_atomico(pasta / arquivo, bruto)
        tamanhos[arquivo] = len(bruto)
    return tamanhos


def ler(base: Path) -> dict | None:
    """Reconstroi o dict completo a partir de data/. None se nao houver."""
    pasta = Path(base) / DIR_DADOS
    arq_meta, arq_cubo = pasta / NOME_META, pasta / NOME_CUBO
    if not (arq_meta.exists() and arq_cubo.exists()):
        return None
    d = json.loads(arq_meta.read_text(encoding="utf-8"))
    d.pop("n_linhas", None)
    d["rows"] = decodificar(arq_cubo.read_bytes(), d["campos"])
    return d


# --- o carregador que fica no lugar do antigo data.js -----------------------
# O index.html continua com <script src="data.js"> e continua esperando por
# `window.__chartPronto`. Em vez de mexer em 1.000 linhas de painel para trocar
# o contrato, o proprio data.js virou o carregador: ~2 KB que buscam data/ e
# encadeiam na mesma promessa que a pagina ja espera.
#
# `rows` sai como Array comum, e nao Int32Array, de proposito: a guarda do
# painel usa Array.isArray, e o consumo de memoria e o MESMO de antes (o
# JSON.parse do arquivo velho tambem produzia um Array de 4,35 milhoes de
# numeros). O que some e o download de 13,9 MB e o parse bloqueante.
CARREGADOR_JS = """// data.js — este arquivo NAO contem mais os dados: ele os carrega.
//
// Ate 2026-11 aqui moravam 13,9 MB de JSON (`window.VENDAS = {...}`) servidos
// num <script> SINCRONO: o navegador parava de construir a pagina, baixava
// 3,5 MB comprimidos, descomprimia e rodava JSON.parse antes de pintar um
// pixel. Com a serie indo de 116 para 237 meses, o arquivo dobrou.
//
// Agora os dados estao em data/meta.json (dimensoes) e data/cubo.bin.gz (as
// linhas, colunar e comprimido, ~2,1 MB), buscados em segundo plano. O formato
// esta documentado em scripts/cubos.py. GERADO — nao edite a mao.
(function(){
  var antes = window.__chartPronto || Promise.resolve();

  async function inflar(buffer){
    // Gzip no arquivo, nao no transporte: o GitHub Pages nao comprime
    // application/octet-stream, entao confiar no servidor traria 7,3 MB crus.
    if (typeof DecompressionStream === 'undefined') throw new Error('navegador sem DecompressionStream');
    var fluxo = new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'));
    return await new Response(fluxo).arrayBuffer();
  }

  function decodificar(cru, nCampos){
    var cab = new DataView(cru);
    var magico = String.fromCharCode(cab.getUint8(0), cab.getUint8(1),
                                     cab.getUint8(2), cab.getUint8(3));
    if (magico !== 'VLQ1') throw new Error('cubo com magico inesperado: ' + magico);
    var n = cab.getUint32(4, true), P = cab.getUint8(8);
    if (P !== nCampos) throw new Error('cubo tem ' + P + ' colunas, meta diz ' + nCampos);
    var tipos = new Uint8Array(cru, 9, P), pos = 9 + P;
    // Array comum, e nao typed array: a guarda do painel usa Array.isArray, e
    // o arquivo antigo tambem entregava Array. Mesma memoria de antes.
    var rows = new Array(n * P);
    for (var c = 0; c < P; c++){
      var t = tipos[c], larg = (t === 1 ? 1 : t === 2 ? 2 : 4);
      // .slice() em vez de view: Uint16Array/Int32Array exigem deslocamento
      // multiplo de 2/4 bytes, e as colunas nao caem alinhadas.
      var fatia = cru.slice(pos, pos + n * larg);
      var col = t === 1 ? new Uint8Array(fatia)
              : t === 2 ? new Uint16Array(fatia)
              : t === 4 ? new Uint32Array(fatia)
                        : new Int32Array(fatia);
      for (var i = 0; i < n; i++) rows[i * P + c] = col[i];
      pos += n * larg;
    }
    return rows;
  }

  async function carregar(){
    var pedir = function(url, como){
      return fetch(url).then(function(r){
        if (!r.ok) throw new Error(url + ': HTTP ' + r.status);
        return r[como]();
      });
    };
    var partes = await Promise.all([pedir('data/meta.json', 'json'),
                                    pedir('data/cubo.bin.gz', 'arrayBuffer')]);
    var meta = partes[0];
    meta.rows = decodificar(await inflar(partes[1]), meta.campos.length);
    window.VENDAS = meta;
  }

  // Encadeia na promessa que o index.html ja espera, para nao precisar mexer
  // nele. Se falhar, marca __semDados e o painel mostra o aviso de sempre.
  window.__chartPronto = Promise.all([antes, carregar().catch(function(e){
    if (window.console) console.error('[dados]', e);
    window.__semDados = 1;
  })]);
})();
"""


def escrever_carregador(caminho: Path) -> int:
    """Grava o data.js que carrega data/. Devolve o tamanho em bytes."""
    bruto = CARREGADOR_JS.encode("utf-8")
    _escrever_atomico(Path(caminho), bruto)
    return len(bruto)
