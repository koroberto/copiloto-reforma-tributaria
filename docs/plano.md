# Plano até a entrega

## O que a disciplina pede
- MVP demonstrável, com a IA numa tarefa específica e com resultado que dá para avaliar.
- Artigo técnico de no mínimo 5 páginas.
- Apresentação de 10 a 15 minutos com demonstração, explicando decisões, testes e limitações.
- Projeto Desafio vale 40% da nota, entregue nas **aulas 7 e 8** (datas a confirmar no Blackboard). Avaliação em grupo: mais 40%, na aula 8.
- Cuidados cobrados: verificação das respostas, entradas incompletas, proteção dos dados, limites para decisões automáticas e revisão humana (NIST AI RMF – GenAI Profile 2024).

## Decisões em aberto (fechar com o grupo)
- [x] Integrantes do Grupo 4: Caio Roberto, Danilo Almeida e Guilherme Monteiro
- [ ] Quem faz cada parte
- [ ] Regime do recorte: Lucro Presumido ou Lucro Real
- [ ] Setor do recorte (sugestão: distribuição)
- [ ] Ano-alvo da simulação (sugestão: 2027, quando a CBS entra inteira)
- [ ] Interface: Streamlit (mais rápido) ou outra
- [ ] De onde vêm os XMLs de teste (NF-e sintéticas ou de empresa real anonimizada)

## Etapas
1. [ ] Fechar as decisões acima
2. [x] Leitura do XML da NF-e ([copiloto/nfe.py](../copiloto/nfe.py))
3. [ ] Conferir as regras e alíquotas da transição na lei ([regras-transicao.md](regras-transicao.md)) e parametrizar
4. [ ] Cálculo determinístico: carga atual × carga CBS/IBS no ano-alvo, margem e preço para manter a margem
5. [ ] Enquadramento pela IA: prompt, saída JSON com confiança, tela de revisão do contador
6. [ ] Relatório: alertas priorizados e explicação em linguagem simples
7. [ ] Testes: base de produtos com enquadramento conhecido (gabarito), medir acerto da IA e conferir o cálculo à mão em alguns casos
8. [ ] Artigo (5+ páginas): problema, solução, arquitetura, testes, limitações
9. [ ] Apresentação com demonstração

## Limitações (para o artigo)
- Não substitui o contador: o enquadramento é sugestão.
- Alíquotas de referência do IBS e da CBS ainda dependem de definição oficial; o simulador trabalha com cenários.
- Recorte de um regime e um setor.
