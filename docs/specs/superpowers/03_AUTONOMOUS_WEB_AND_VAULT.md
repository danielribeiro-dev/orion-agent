# Superpoder 03 — Navegação Web Autônoma & Secure Vault

> Especificação de navegação web com Model Context Protocol (MCP), gerenciamento de credenciais de conhecimento zero e autenticação biométrica por voz.

---

## 1. O Desafio de Segurança na Web

Permitir que agentes de IA naveguem na internet com senhas e cartões de crédito é o maior vetor de risco de segurança da computação moderna. O ORION resolve isso através de um **Cofre Seguro de Conhecimento Zero (Zero-Knowledge Vault)**.

---

## 2. A Arquitetura do Secure Vault

```
[Solicitação de Ação Web com Login]
                 │
                 ▼
[Policy Enforcement Point (PEP)] ──▶ Exige aprovação explícita
                 │
                 ▼
[Voice Passphrase & Speaker Verification (Biometria Vocal Local)]
  • O usuário diz a senha verbal ("Alpha 7")
  • Modelo local verifica se os harmônicos da voz batem com o perfil do usuário
                 │ Aprovado
                 ▼
[Linux Secret Service / Keyring Seguro (AES-256)]
  • Recupera a credencial em memória protegida
  • O ORION preenche o campo via CDP ou Browser MCP
  • A senha NUNCA é enviada para os servidores da LLM em texto
```

---

## 3. Navegação via Browser MCP (Model Context Protocol)

- Em vez de um script engessado de Playwright, o ORION opera através do padrão **Browser MCP**:
  - Manipulação de abas via árvore de acessibilidade do navegador (ARIA snapshots).
  - Tolerância extrema a mudanças de CSS e atualizações de sites.
  - Modo Stealth: Rotação de headers e comportamentos realistas para contornar falsos positivos de anti-bot da Cloudflare.
