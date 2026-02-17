# Microsoft Agent Framework: Foundry & API Guide

> **✅ IMPLEMENTATION STATUS:** This project has successfully implemented **MAF with Foundry V2** using `SequentialBuilder` and `AzureOpenAIChatClient`. See [workflow.py](backend/app/agents/workflow.py) for the implementation.

This document clarifies the differences between:

1. **Microsoft Foundry V1 (Classic) vs V2 (New)** - Portal/platform versions
2. **Assistants API vs Responses API** - API types for building agents
3. **`azure-ai-agents` vs `azure-ai-projects`** - SDK packages used by Microsoft Agent Framework

**📝 Terminology:**
- **`azure-ai-agents`** — Azure AI Agents client library (uses Assistants API)
- **`azure-ai-projects`** — Foundry SDK (uses Responses API in version 2.x)
- **Microsoft Agent Framework (MAF)** — Open-source framework (`agent-framework-azure-ai`) that wraps these packages
- MAF "V1" = `azure-ai-agents`, MAF "V2" = `azure-ai-projects`

---

## ✅ Implementation in This Project

This project uses **Foundry V2** approach with MAF's `SequentialBuilder`:

```python
# Packages used (from requirements.txt)
# agent-framework-core==1.0.0b260128
# agent-framework-azure-ai==1.0.0b260128

from agent_framework.core import SequentialBuilder, AssistantAgent, TextMessage
from agent_framework.azure_ai import AzureOpenAIChatClient

# Create chat client connected to Azure OpenAI
chat_client = AzureOpenAIChatClient(
    endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],  # gpt-5-mini
    credential=DefaultAzureCredential()
)

# Create agents
data_analyst = AssistantAgent(name="DataAnalyst", model_client=chat_client, system_message="...")
capacity_calculator = AssistantAgent(name="CapacityCalculator", model_client=chat_client, system_message="...")
document_researcher = AssistantAgent(name="DocumentResearcher", model_client=chat_client, system_message="...")
planner = AssistantAgent(name="CapacityPlanner", model_client=chat_client, system_message="...")

# Build sequential workflow
workflow = (
    SequentialBuilder()
    .participants([data_analyst, capacity_calculator, document_researcher, planner])
    .build()
)

# Run the workflow
result = await workflow.run(task=TextMessage(content="...", source="user"))
```

**Verification:** Tested with Playwright MCP browser automation on January 30, 2026. All 4 agents execute sequentially with real Azure OpenAI calls.

---

## TL;DR

> **The MAF CLIENT CLASS you use determines which Foundry portal your agents appear in — NOT the SDK version!**

| MAF Client Class | API Type | Agent Appears In |
|------------------|----------|------------------|
| `AzureAIAgentClient` | Assistants API* | Foundry V1 (Classic) |
| `AzureAIClient` | Responses API | Foundry V2 (New) |

⚠️ **Deprecation Notice:** The Assistants API (not the Foundry V1 portal) is deprecated and will shut down on **August 26, 2026**. Microsoft recommends migrating to the Responses API. See: [OpenAI Migration Guide](https://platform.openai.com/docs/assistants/migration) | [Azure Migration Guide](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/migrate)

```python
# For Foundry V1 (Classic) agents:
from agent_framework.azure import AzureAIAgentClient
client = AzureAIAgentClient(...)  # → Agent in V1 (Classic)

# For Foundry V2 (New) agents:
from agent_framework.azure import AzureAIClient
client = AzureAIClient(...)  # → Agent in V2 (New)
```

### Portals vs. Agent Services

The **Foundry portals** (Classic and New) are user interfaces—both can technically call either API. However, the **Foundry Agent Service** (managed backend) differs:

| Portal | Agent Service Built On | State Management |
|--------|------------------------|------------------|
| Foundry (Classic) | Assistants API | Threads → Messages → Runs |
| Foundry (New) | Responses API | Conversations → Responses |

Your MAF **client class choice** determines which Agent Service architecture your agents use—which is why agents appear in different portals.

---

## Package Architecture

Microsoft Agent Framework (MAF) is a **high-level framework** that wraps the low-level Azure SDKs:

```
┌─────────────────────────────────────────────────────────────────┐
│              agent-framework-azure-ai (MAF)                     │
│         High-level framework for building agents                │
│                                                                 │
│  Provides: AzureAIAgentClient, AzureAIClient,                  │
│            AzureAIAgentsProvider, AzureAIProjectAgentProvider  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ uses internally
              ┌─────────────┴─────────────┐
              ▼                           ▼
┌─────────────────────────┐   ┌─────────────────────────────────┐
│    azure-ai-agents      │   │     azure-ai-projects           │
│ (Azure AI Agents SDK)   │   │      (Foundry SDK)              │
│                         │   │                                 │
│ Low-level SDK for       │   │ Low-level SDK for               │
│ Assistants API          │   │ Responses API                   │
│ (threads, runs)         │   │ (conversations, responses)      │
└─────────────────────────┘   └─────────────────────────────────┘
```

| Package | Type | Purpose |
|---------|------|---------|
| `agent-framework-azure-ai` | **High-level framework** | Wraps Azure SDKs with convenient abstractions |
| `azure-ai-agents` | Low-level SDK | Direct access to Assistants API |
| `azure-ai-projects` | Low-level SDK (Foundry SDK) | Direct access to Responses API |

**Installation:** `agent-framework-azure-ai` includes `azure-ai-agents` automatically. For V2 (Responses API), add `azure-ai-projects>=2.0.0b3`.

## Using Azure SDK Directly (Without MAF)

You can use the Azure SDKs **directly without MAF**. This gives you lower-level control but requires more manual work for multi-agent orchestration.

| SDK Package | Direct Client Class | API Type | Agents Appear In |
|-------------|---------------------|----------|------------------|
| `azure-ai-agents` | `AgentsClient` | Assistants API | Foundry V1 (Classic) |
| `azure-ai-projects` (2.x) | `AIProjectClient` | Responses API | Foundry V2 (New) |

### Direct SDK: V1 (Assistants API) Example

```python
# pip install azure-ai-agents azure-identity

from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential

# Create client directly (no MAF)
client = AgentsClient(
    endpoint="https://<your-project>.services.ai.azure.com/api/projects/<project>",
    credential=DefaultAzureCredential()
)

# Create an agent
agent = client.create_agent(
    model="gpt-4o-mini",
    name="my-agent",
    instructions="You are a helpful assistant."
)

# Assistants API pattern: Thread → Messages → Run
thread = client.threads.create()
client.messages.create(thread_id=thread.id, role="user", content="Hello!")
run = client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)

# Get response
messages = client.messages.list(thread_id=thread.id)
print(messages[-1].content)
```

**Reference:** [Quickstart: Create agents with Azure AI Agent Service (Classic)](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/quickstart?view=foundry-classic)

### Direct SDK: V2 (Responses API) Example

```python
# pip install azure-ai-projects azure-identity

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Create client directly (no MAF)
client = AIProjectClient(
    endpoint="https://<your-project>.services.ai.azure.com/api/projects/<project>",
    credential=DefaultAzureCredential()
)

# Create an agent
agent = client.agents.create_version(
    model="gpt-4o-mini",
    name="my-agent",
    instructions="You are a helpful assistant."
)

# Responses API pattern: single API call
response = client.agents.responses.create(
    agent_id=agent.id,
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

**Reference:** [Quickstart: Get started with code in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/quickstarts/get-started-code?view=foundry)

### When to Use MAF vs Direct SDK

| Use Case | Recommendation |
|----------|----------------|
| Multi-agent orchestration | **MAF** - built-in support |
| Quick prototyping | Either works |
| Fine-grained control over API calls | **Direct SDK** |
| Integration with Semantic Kernel | **MAF** - native support |
| Minimal dependencies | **Direct SDK** |

💡 **Note:** Microsoft recommends `azure-ai-projects` for V2 projects. *"While this package can be used independently, we recommend using the Azure AI Projects client library..."* — [PyPI: azure-ai-agents](https://pypi.org/project/azure-ai-agents/)

## MAF Classes: Client vs Provider

MAF provides **two patterns** for creating agents. Choose based on your use case:

| Pattern | Classes | Best For |
|---------|---------|----------|
| **Client** | `AzureAIAgentClient`, `AzureAIClient` | Single agent, simple apps |
| **Provider** | `AzureAIAgentsProvider`, `AzureAIProjectAgentProvider` | Multi-agent orchestration |

| Use Case | V1 (Assistants) | V2 (Responses) |
|----------|-----------------|----------------|
| **Single agent, quick prototype** | `AzureAIAgentClient` | `AzureAIClient` |
| **Multi-agent orchestration** | `AzureAIAgentsProvider` | `AzureAIProjectAgentProvider` |
| **Retrieve existing agent** | `AzureAIAgentsProvider.get_agent()` | `AzureAIProjectAgentProvider.get_agent()` |

See **Code Examples** section below for complete working examples.

---

## Understanding the Three Concepts

These three concepts are **independent but related**:

| Concept | What It Means | Options |
|---------|---------------|---------|
| **Microsoft Agent Framework** | Open-source framework for multi-agent orchestration | Uses Azure SDK packages underneath |
| **Foundry Portal** | The UI at ai.azure.com | V1 (Classic) or V2 (New) |
| **API Type** | How agents communicate | Assistants API or Responses API |
| **SDK Package** | Python package for Azure AI | `azure-ai-agents` or `azure-ai-projects` (Foundry SDK) |

**Key Insight:** Both Foundry portals support both APIs. However, agents created with each API appear in different portal locations because the APIs store data in different backend services.

## Foundry Portals (V1 Classic vs V2 New)

Microsoft Foundry (formerly Azure AI Foundry) is a unified Azure platform for enterprise AI with **two portal experiences**:

| Portal | Toggle Label | Description |
|--------|--------------|-------------|
| **V1 (Classic)** | "Microsoft Foundry (classic)" | Original portal. Supports all resource types. |
| **V2 (New)** | "Microsoft Foundry (new)" | Modernized UI. Streamlined for Foundry projects. |

Switch between them using the toggle at [ai.azure.com](https://ai.azure.com).

## Feature Comparison

| Feature | V1 (Classic) | V2 (New) |
|---------|:------------:|:--------:|
| Azure OpenAI resources | ✅ | ❌ |
| Hub-based projects | ✅ | ❌ |
| Foundry projects | ✅ | ✅ |
| Prompt flow | ✅ | ❌ |
| Multi-agent workflows | ❌ | ✅ |
| Tool Catalog (1,400+) | ❌ | ✅ |
| Memory capabilities | ❌ | ✅ |
| Assistants API agents | ✅ | ✅ |
| Responses API agents | ✅ | ✅ |

## APIs: Assistants vs Responses

### Overview

| API | Description | State Model |
|-----|-------------|-------------|
| **Assistants API** | Original stateful API | Threads → Messages → Runs |
| **Responses API** | Newer unified API | Conversations → Items → Responses |

### What Microsoft Says

From [Microsoft Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/responses):

*"The Responses API is a new stateful API from Azure OpenAI. It brings together the best capabilities from the **chat completions and assistants API** in one unified experience."*

From the [Migration Guide](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/migrate):

*"Future proof: New features and model support will only be added to the new agents."*

### Comparison

| Feature | Assistants API | Responses API |
|---------|----------------|---------------|
| **SDK Package** | `azure-ai-agents` | `azure-ai-projects` (Foundry SDK) |
| **MAF Client Class** | `AzureAIAgentClient` | `AzureAIClient` |
| **Agent Storage** | Persistent by ID | Versioned by name |
| **Agent Versioning** | ❌ | ✅ |
| **RAI Config** | ❌ | ✅ |
| **Reasoning** | ❌ | ✅ |
| **Status** | Stable, limited updates | Active development |

### Migration Mapping

| Assistants API | Responses API |
|----------------|---------------|
| Threads | Conversations |
| Runs | Responses |
| Messages | Items |
| `thread_id` | `conversation_id` |
| `agent_id` | `agent_name` + `agent_version` |

## When to Use What

### Choose Foundry V1 (Classic) when:
- Working with hub-based projects
- Need prompt flow support
- Using Azure OpenAI resources directly
- Prefer the original portal experience

### Choose Foundry V2 (New) when:
- Building multi-agent workflows
- Want the modernized UI
- Using Foundry projects (recommended)
- Need centralized AI asset management

### Choose Assistants API (`AzureAIAgentClient`) when:
- Need persistent thread management
- Want agents stored by ID
- Working with existing Assistants workflows
- Need stable, established API

### Choose Responses API (`AzureAIClient`) when:
- Want latest features (reasoning, RAI config)
- Prefer agent versioning
- Need newer tools (Memory Search, SharePoint, Fabric)
- Want future feature updates (**Microsoft's recommendation**)

## Code Examples

### Using Client Classes (Simple, Single-Agent)

Use **Client classes** when you need one agent with minimal setup.

#### Example: Client with Assistants API → V1 (Classic)

**Source:** [azure_ai_agent/azure_ai_basic.py](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/azure_ai_agent/azure_ai_basic.py)

```python
import asyncio
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

async def main():
    credential = AzureCliCredential()
    client = AzureAIAgentClient(
        credential=credential,
        agent_name="MyAgent",
    )
    agent = client.as_agent(instructions="You are a helpful assistant.")
    result = await agent.run("Hello!")
    print(result)

asyncio.run(main())
# ✅ Agent appears in Foundry V1 (Classic) → Agent Playground
```

#### Example: Client with Responses API → V2 (New)

**Source:** [azure_ai/azure_ai_basic.py](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/azure_ai/azure_ai_basic.py)

```python
import asyncio
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

async def main():
    credential = AzureCliCredential()
    client = AzureAIClient(
        credential=credential,
        agent_name="MyAgent",
    )
    agent = client.as_agent(instructions="You are a helpful assistant.")
    result = await agent.run("Hello!")
    print(result)

asyncio.run(main())
# ✅ Agent appears in Foundry V2 (New) → Agents section
```

### Using Provider Classes (Multi-Agent, Orchestration)

Use **Provider classes** when you need multiple agents or more control.

#### Example: Provider with Assistants API → V1 (Classic)

**Source:** [azure_ai_agent/azure_ai_provider_methods.py](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/azure_ai_agent/azure_ai_provider_methods.py)

```python
import asyncio
from agent_framework.azure import AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential

async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="MyAssistantsAgent",
            instructions="You are a helpful assistant.",
            tools=my_function,
        )
        result = await agent.run("Hello!")
        print(result)

asyncio.run(main())
# ✅ Agent appears in Foundry V1 (Classic) → Agent Playground
```

#### Example: Provider with Responses API → V2 (New)

**Source:** [azure_ai/azure_ai_provider_methods.py](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/azure_ai/azure_ai_provider_methods.py)

```python
import asyncio
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="MyResponsesAgent",
            model="gpt-4o-mini",
            instructions="You are a helpful assistant.",
            tools=my_function,
        )
        response = await agent.run("Hello!")
        print(response)

asyncio.run(main())
# ✅ Agent appears in Foundry V2 (New) → Agents section
```

## Configuration & Setup

### Environment Variables

Both APIs use the same environment variables:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o-mini
```

### Package Dependencies

**For Assistants API (V1):**
```toml
[project.dependencies]
agent-framework-azure-ai = ">=1.0.0b260123"
# azure-ai-agents installed automatically
```

**For Responses API (V2):**
```toml
[project.dependencies]
agent-framework-azure-ai = ">=1.0.0b260123"
azure-ai-projects = ">=2.0.0b3"
```

### Sample Folder Structure

The Microsoft Agent Framework repository organizes samples by which package they use:

```
python/samples/getting_started/agents/
├── azure_ai_agent/    # Uses azure-ai-agents (V1)
│   └── README: "azure-ai-agents 1.x (V1) API surface"
│
└── azure_ai/          # Uses azure-ai-projects (V2)
    └── README: "azure-ai-projects 2.x (V2) API surface"
```

## Supporting Both APIs (Factory Pattern)

To support both APIs with minimal code changes:

**Pattern Reference:** [Microsoft Agent Framework - Agent Types](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/)

### Factory Function

```python
def build_chat_client() -> tuple[ChatClientProtocol, str]:
    api_type = os.getenv("AZURE_AI_API_TYPE", "responses")
    
    if api_type == "assistants":
        client = build_agents_client()     # → AzureAIAgentClient
    else:
        client = build_responses_client()  # → AzureAIClient
    
    return client, api_type
```

### API-Specific Middleware

```python
if api_type == "assistants":
    chat_client.middleware = [AssistantsApiThreadMiddleware()]
else:
    chat_client.middleware = [ResponsesApiThreadMiddleware()]
```

### Switch via Environment Variable

```bash
# For Foundry V1 (Classic) agents:
AZURE_AI_API_TYPE=assistants

# For Foundry V2 (New) agents:
AZURE_AI_API_TYPE=responses
```

---

## Appendix A: Authoritative References & Evidence

The relationship between client classes and APIs has been verified through multiple authoritative Microsoft sources.

### Reference 1: Microsoft Agent Framework GitHub (V2 Folder)

**Source:** [github.com/microsoft/agent-framework/.../azure_ai](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/azure_ai)

*"This folder contains examples demonstrating different ways to create and use agents with the Azure AI client from the `agent_framework.azure` package. These examples use the **`AzureAIClient` with the `azure-ai-projects` 2.x (V2) API surface** (see [changelog](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/CHANGELOG.md#200b1-2025-11-11)). For V1 (`azure-ai-agents` 1.x) samples using **`AzureAIAgentClient`**, see the [Azure AI V1 examples folder](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/azure_ai_agent)."*

### Reference 2: Microsoft Agent Framework GitHub (V1 Folder)

**Source:** [github.com/microsoft/agent-framework/.../azure_ai_agent](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/azure_ai_agent)

*"This folder contains examples demonstrating different ways to create and use agents with Azure AI using the **`AzureAIAgentsProvider`** from the `agent_framework.azure` package. These examples use the **`azure-ai-agents` 1.x (V1) API surface**. For updated V2 (`azure-ai-projects` 2.x) samples, see the [Azure AI V2 examples folder](https://github.com/microsoft/agent-framework/blob/main/python/samples/getting_started/agents/azure_ai)."*

### Reference 3: Azure SDK Changelog (azure-ai-projects 2.0.0b1)

**Source:** [github.com/Azure/azure-sdk-for-python/.../CHANGELOG.md](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/CHANGELOG.md)

*"New Agent operations (**now built on top of OpenAI's `Responses` protocol**) were added to the `AIProjectClient`. **This package no longer depends on `azure-ai-agents` package.**"*

### Reference 4: Microsoft Learn API Documentation

**AzureAIAgentClient:**
- **Source:** [learn.microsoft.com/.../azureaiagentclient](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.azure.azureaiagentclient)
- Uses `agents_client: AgentsClient` from `azure.ai.agents`
- Uses `thread_id` parameter (**threads** = Assistants API)

**AzureAIClient:**
- **Source:** [learn.microsoft.com/.../azureaiclient](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.azure.azureaiclient)
- Uses `project_client: AIProjectClient` from `azure.ai.projects`
- Uses `conversation_id` parameter (**conversations** = Responses API)

### Evidence from Constructor Signatures

**AzureAIAgentClient (Assistants API):**
```python
def __init__(
    *,
    agents_client: AgentsClient | None = None,  # ← From azure-ai-agents
    thread_id: str | None = None,  # ← THREAD (Assistants API)
    ...
)
```

**AzureAIClient (Responses API):**
```python
def __init__(
    *,
    project_client: AIProjectClient | None = None,  # ← From azure-ai-projects
    conversation_id: str | None = None,  # ← CONVERSATION (Responses API)
    ...
)
```

---

## Appendix B: Reference Links

### GitHub
| Resource | URL |
|----------|-----|
| Agent Framework | https://github.com/microsoft/agent-framework |
| V1 Samples (Assistants) | https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/azure_ai_agent |
| V2 Samples (Responses) | https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/azure_ai |

### Azure SDK
| Resource | URL |
|----------|-----|
| azure-ai-agents (PyPI) | https://pypi.org/project/azure-ai-agents/ |
| azure-ai-projects (PyPI) | https://pypi.org/project/azure-ai-projects/ |
| Changelog | https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/CHANGELOG.md |

### Microsoft Learn
| Resource | URL |
|----------|-----|
| Foundry Overview | https://learn.microsoft.com/azure/ai-foundry/what-is-foundry |
| Responses API Guide | https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/responses |
| Migration Guide | https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/migrate |
| Agent Framework Types | https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/ |

---

*Last Updated: January 2026*
