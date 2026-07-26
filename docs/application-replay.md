# Experimental OpenAI Agents application replay

This is an experimental 0.5 library surface. It is not part of the immutable
0.1 promise, has no CLI entry point, and is not release evidence by itself.
RunSieve's 0.1 `materialize`, `reproduce-predicate`, and deprecated `replay`
alias retain their narrower meanings.

## What executes

`OpenAIAgentsCaptureSession` and `OpenAIAgentsReplaySession` receive the same
explicit asynchronous application callback. The callback constructs its real
`Agent`, instructions, and orchestration logic with the session's injected
public `Model` and `FunctionTool` objects, then calls `session.run()`.

Capture executes:

- the application callback and SDK `Runner`;
- the supplied live `Model`;
- the supplied original `FunctionTool` handlers.

Replay executes:

- the application callback and SDK `Runner`;
- RunSieve's recorded-response `Model`;
- RunSieve's recorded-result `FunctionTool` wrappers.

Replay does not call the supplied original tool handlers. The SDK model
provider is replaced with a fail-closed canary. Original handlers are
temporarily replaced with measured canaries for the duration of the callback
and restored in `finally`.

## Library outline

The caller owns the application callback and supplies the live capture model,
declared tools, and redaction policy. Capture and replay receive the same
callback:

```python
from agents import Agent

from runsieve.adapters.openai_agents_replay import (
    OpenAIAgentsCaptureSession,
    OpenAIAgentsReplaySession,
)


async def application(session):
    agent = Agent(
        name="my application",
        instructions="Call the declared tool when needed.",
        model=session.model,
        tools=list(session.tools),
    )
    return await session.run(agent, "the recorded input")


capture = OpenAIAgentsCaptureSession(
    live_model=my_public_model,
    original_tools=(my_function_tool,),
    redaction_policy=my_redaction_policy,
    trace_id="my-reviewed-trace-id",
)
captured = await capture.execute(application)

replay = OpenAIAgentsReplaySession(
    captured.capsule,
    original_tools=(my_function_tool,),
)
report = await replay.execute(application)
```

`my_public_model`, `my_function_tool`, and `my_redaction_policy` are explicit
caller-owned objects; capsule metadata cannot construct them. Check
`report.provider_resolution_attempts`, `report.original_tool_calls`, and
`report.all_interactions_consumed` before accepting the result.

## Matching protocol

The capsule declares `openai-agents-public-v1` and `ordered-exact-v1`.
Replay requires an exact SDK version and compares canonical JSON for:

- system instructions;
- every model input item;
- the supported model-settings subset;
- every exposed tool name, description, strictness flag, and JSON schema;
- each tool name and parsed JSON argument value;
- interaction order;
- complete consumption of every recorded model and tool pair.

Changed instructions or inputs, original-tool injection, argument mutation,
extra calls, early exit, missing calls, and unconsumed interactions are
divergence errors. Invalid and unsupported behavior never becomes a successful
replay.

## Supported boundary

The first adapter supports:

- OpenAI Agents SDK `0.18.3`;
- one non-streaming `Runner.run()` invocation;
- public `Model` and simple public `FunctionTool` interfaces;
- message and function-call model outputs;
- at most one function call per model response;
- no handoffs, MCP servers, structured output schema, prompt template,
  conversation, previous-response chaining, approval flow, dynamic tool
  enablement, tool guardrails, tool timeout, deferred loading, or detailed
  usage entries.

Unsupported surfaces fail explicitly. Adding them requires a new protocol
version and evidence.

## Privacy and trust boundary

Every recorded request, response, tool argument, tool result, and returned
application value passes through RunSieve redaction before capsule
persistence. If any matching field is changed by redaction, the capsule is
marked application-replay-ineligible. This prevents equality matching from
quietly accepting a redacted approximation.

The callback is trusted application code running in the current Python
process. This adapter is not a sandbox and does not prevent the callback from
opening unrelated files, starting processes, using a separate network client,
or directly invoking an object it obtained outside the injected interfaces.
The measured no-live-call claim is limited to the injected SDK model-provider
and supplied original-tool boundaries. Capsule metadata never supplies an
entry point or command to execute.

Use synthetic or disposable inputs. RS-05-AR1 now provides independent
synthetic gate evidence for the adapter mechanics. A permissioned real case
and independent human review remain required before a 0.5 readiness claim.

## Reduction

The adapter returns a normal schema-v1 `Capsule`. The existing reducer can use
successful application replay as its tri-state evaluator, and the independent
verifier can test final-granularity 1-minimality. The synthetic adapter test
removes an irrelevant workspace file, reruns the application, consumes all
recorded interactions, and independently verifies the result as 1-minimal.
