# Requisitos do enquadramento em lote (EARS)

Formato EARS, como na Aula 07 de Construção de Assistentes (EARS → BDD → TDD → teste de mutação). Cada requisito é uma frase testável e tem número. O número vai no nome do teste (`test_REQ05_...`), e a tabela no fim liga cada requisito aos testes que o cobrem. Os requisitos detalham o RF01 a RF04 e o RNF02 a RNF04 da Aula 2 para a versão em lote.

## Entrada

- **REQ-01** Quando o contador envia um cadastro em CSV ou XLSX, o sistema deve achar as colunas de código, descrição e NCM pelo nome, em qualquer ordem e com ou sem acento.
- **REQ-02** Se a planilha não tiver uma coluna de descrição, o sistema deve recusar o arquivo e dizer qual cabeçalho usar.
- **REQ-03** Quando o contador envia XMLs de NF-e, o sistema deve listar cada produto uma vez só, mesmo que ele apareça em várias notas.
- **REQ-04** Se um XML estiver com defeito, o sistema deve listar o arquivo como não lido e seguir com os outros.

## Verificação, antes da IA

- **REQ-05** Se a descrição estiver vazia ou o NCM não tiver 8 dígitos, o sistema deve barrar o item antes da IA e mostrar o motivo.
- **REQ-06** Se o NCM tiver 7 dígitos, o sistema deve completar o zero à esquerda e anotar a correção no item.

## IA

- **REQ-07** O sistema deve mandar à IA só a descrição e o NCM dos itens válidos, num único prompt (ou em blocos de 40 no modo integrado).
- **REQ-08** Se a IA responder com categoria fora da lista, resposta vazia ou fora do formato, o sistema deve tratar o item como REVISAO_HUMANA com confiança baixa.
- **REQ-09** Se a IA deixar de responder um item, o sistema deve mandar o item para a fila e avisar quais faltaram.
- **REQ-10** Se a IA estiver indisponível (sem chave, sem rede ou com erro num bloco), o sistema deve seguir com o resto do lote e mandar os itens afetados para a fila, sem inventar resultado.

## Conferência e aprovação automática

- **REQ-11** Se a IA sugerir uma redução que a tabela oficial não prevê para o produto, o sistema deve mandar o item para a fila. Um tratamento que depende de quem compra (produtor rural, órgão público) não confirma a redução.
- **REQ-12** Quando a tabela oficial e a IA concordam, com confiança alta, sem alertas e com um único cClassTrib possível, o sistema deve aprovar o item sozinho, com o cClassTrib, e marcá-lo como "automático".
- **REQ-13** Se o NCM puder ter um tratamento que a tabela por NCM não mostra (9619 para absorvente e fralda, capítulo 30 para medicamentos), o sistema deve mandar o item para a fila.
- **REQ-14** Se a IA sugerir PADRAO para um NCM que aparece num anexo do produto, o sistema deve mandar o item para a fila com os anexos possíveis.

## Decisão do contador e saída

- **REQ-15** Quando o contador aceita a sugestão ou escolhe o enquadramento, o sistema deve preencher o cClassTrib pela tabela oficial se houver um só.
- **REQ-16** Se o contador escolher uma redução sem informar um cClassTrib possível, ou PADRAO com código diferente de 000001, o sistema deve recusar a decisão e dizer o motivo.
- **REQ-17** Quando o contador muda um item aprovado automaticamente, o sistema deve registrar a decisão como do contador.
- **REQ-18** Enquanto houver item pendente, o sistema deve bloquear o download da planilha de saída.
- **REQ-20** Enquanto o modo Simulada estiver ativo, quando o contador consulta um único produto que está no cadastro de exemplo ou nos casos T1 a T6, o sistema deve devolver a resposta gravada do Gemini, sem diferenciar maiúsculas, acentos, pontuação e espaços.
- **REQ-21** Se, no modo Simulada, o produto consultado não tiver resposta gravada, o sistema deve dizer que é um modo de demonstração e indicar o que fazer (escolher um produto de exemplo ou usar o modo Manual), sem sugerir enquadramento.
- **REQ-19** O sistema deve exportar, por item, código, descrição, NCM, enquadramento, cClassTrib, descrição do cClassTrib, anexo e quem decidiu, em CSV que abre direto no Excel.

## Requisito → teste

| Requisito | Testes (pytest) |
|---|---|
| REQ-01 | `test_lote.py::test_REQ01_*` |
| REQ-02 | `test_lote.py::test_REQ02_*` |
| REQ-03, REQ-04 | `test_lote.py::test_REQ03_REQ04_*`, `test_nfe.py` |
| REQ-05 | `test_lote.py::test_REQ05_*`, `test_enquadramento.py::test_descricao_vazia_para_o_fluxo`, `test_ncm_malformado_para_o_fluxo` |
| REQ-06 | `test_lote.py::test_REQ01_REQ06_*` |
| REQ-07 | `test_lote.py::test_REQ07_*` |
| REQ-08 | `test_lote.py::test_REQ08_REQ09_*`, `test_enquadramento.py::test_categoria_inesperada_vira_revisao`, `test_resposta_vazia_vira_revisao`, `test_revisao_humana_sempre_com_confianca_baixa` |
| REQ-09 | `test_lote.py::test_REQ08_REQ09_*` |
| REQ-10 | `test_lote.py::test_REQ10_*`, `test_enquadramento.py::test_integrada_sem_chave_e_ia_indisponivel`, `test_integrada_com_erro_de_rede` |
| REQ-11 | `test_lote.py::test_REQ11_*`, `test_tabela_oficial.py` (casos DIVERGE) |
| REQ-12 | `test_lote.py::test_REQ12_*` |
| REQ-13, REQ-14 | `test_lote.py::test_REQ13_REQ14_*`, `test_tabela_oficial.py` (casos ATENCAO) |
| REQ-15, REQ-16, REQ-19 | `test_lote.py::test_REQ15_REQ16_REQ19_*` |
| REQ-17 | `test_lote.py::test_REQ17_*` |
| REQ-20, REQ-21 | `test_lote.py::test_REQ20_*`, `test_lote.py::test_REQ21_*` |
| REQ-18 | `test_lote.py::test_REQ18_*` (contagem de pendentes; o botão desabilitado foi conferido na tela) |

## Teste de mutação

O `mutmut` (configurado em `setup.cfg`) altera o código de propósito, um "mutante" por vez, e roda os testes. Mutante que sobrevive aponta um teste fraco ou um caso que ninguém escreveu. Rodar e ver o resultado:

```bash
.venv/bin/mutmut run
.venv/bin/mutmut results
```
