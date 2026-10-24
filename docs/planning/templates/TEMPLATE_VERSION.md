# Spec — [vX.Y.Z] [Nome da Versão ou Feature]

> **Status:** 📋 Planejando | 🔄 Em Execução | ✅ Concluído (congelado)  
> **Criada em:** [YYYY-MM-DD]  
> **Concluída em:** [YYYY-MM-DD ou —]  
> **Autor(es):** [Nome / IA]  
> **Branch:** `version/vX.Y.Z`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
[1–2 parágrafos diretos: o que esta versão entrega e por que ela existe.]

### 1.2 Por que agora?
[Qual dor, dependência desbloqueada ou marco do roadmap motiva esta versão.]

### 1.3 O que NÃO é escopo (anti-metas)
- [Anti-meta 1: o que explicitamente não faremos aqui]
- [Anti-meta 2]

---

## 2. Decisões Arquiteturais & Diretrizes de Design

### 2.1 Padrões e Invariantes Aplicáveis
- [Ex: Separar Brain de Body]
- [Ex: Zero SQL Injection]

### 2.2 Dependências e Relações
- **Depende de:** [Versões anteriores ou componentes]
- **Desbloqueia:** [O que virá a seguir]

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | [Nome] | [Resumo do entregável] | [`sprints/sprint-1.md`](sprints/sprint-1.md) | ⏳ Pendente |
| **Sprint 2** | [Nome] | [Resumo do entregável] | [`sprints/sprint-2.md`](sprints/sprint-2.md) | ⏳ Pendente |
| **Sprint 3** | [Nome] | [Resumo do entregável] | [`sprints/sprint-3.md`](sprints/sprint-3.md) | ⏳ Pendente |
| **Sprint 4** | [Nome] | [Resumo do entregável] | [`sprints/sprint-4.md`](sprints/sprint-4.md) | ⏳ Pendente |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
  ├── [novo ou modificado] caminho/para/modulo/
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | [Cenário] | [Resultado esperado] | `pytest tests/...` | ⏳ Pendente |

---

## 5. Checklist de Conclusão da Spec (Congelamento)

- [ ] Todos os critérios de aceite validados.
- [ ] Testes unitários com cobertura adequada e zero regressões.
- [ ] Atualização dos documentos de memória em `.claudex/`.
- [ ] Commit e tag no Git.
