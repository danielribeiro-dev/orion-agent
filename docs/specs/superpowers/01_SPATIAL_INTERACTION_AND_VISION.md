# Superpoder 01 — Interação Espacial, Gestos & Olhos Virtuais (Next-Gen)

> Especificação de controle do computador por gestos de mão, rastreamento espacial e compreensão visual da tela sem sobrecarga de CPU.

---

## 1. O Desafio e a Evolução Técnica

No planejamento legado (v2.3.0 e v2.7.0), o ORION pretendia usar MediaPipe contínuo para gestos e OCR (Tesseract) para ler telas.
Em 2026, sabemos que:
- Câmera rodando a 30 FPS contínua aquece a máquina e consome até 20% de CPU.
- OCR cru perde toda a hierarquia visual (cores, estados de botões desabilitados e layout).
- No Linux Wayland moderno, ferramentas como `xdotool` e captura ingênua de tela são bloqueadas por padrão.

---

## 2. A Nova Arquitetura de Visão e Espaço

```
[Gatilho de Voz / Atalho] ── "Orion, organize essa janela"
         │
         ▼
[Câmera On-Demand (Burst 500ms)] ──▶ [MediaPipe ONNX Quantizado (8ms)]
         │ Detecta vetor do dedo indicador (Ray Casting)
         ▼
[Wayland DBus / kwin / wlr-foreign-toplevel]
         │ Faz o cruzamento das coordenadas com as janelas abertas
         ▼
[Identificação da Janela Alvo] ──▶ Executa ação (Mover, Fechar, Maximizar)
```

### 2.1 Visão de Tela em Duas Camadas (Sem Custo e Sem VLM Pesado)
1. **Camada 1 — Acessibilidade Nativa (AT-SPI2 Linux API):**
   - O ORION acessa a árvore de acessibilidade do sistema em <10ms.
   - Lê todos os textos, caixas de diálogo, logs de terminal e botões como **dados estruturados**, com consumo zero de GPU/CPU e sem tirar screenshots.
2. **Camada 2 — VLM Local On-Demand (Qwen2.5-VL / Moondream2 ONNX):**
   - Acionado apenas quando a tela possui elementos gráficos puros (gráficos, diagramas, IDEs customizadas).
   - O modelo retorna bounding boxes normalizadas `[ymin, xmin, ymax, xmax]` para cliques precisos.
