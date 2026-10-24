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

## 3. Fases de Implementação & Arquivos Afetados

```
Fase 1: [Nome da Fase]
  └── [arquivos a criar/modificar]
Fase 2: [Nome da Fase]
  └── [arquivos a criar/modificar]
```

---

## 4. Matriz de Critérios de Aceite (DoD)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | [Cenário] | [Resultado esperado] | `pytest tests/...` | ⏳ Pendente |

---

## 5. Checklist de Conclusão da Spec (Congelamento)

- [ ] Todos os critérios de aceite validados.
- [ ] Testes unitários com cobertura adequada e zero regressões.
- [ ] Atualização dos documentos de memória em `.claudex/`.
- [ ] Commit e tag no Git.
