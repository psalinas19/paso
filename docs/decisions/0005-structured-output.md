# ADR 0005 — Salida estructurada con `output_format`, no con tool use

**Fecha:** 2026-09-17
**Estado:** aceptado — se aparta de §4 del SPEC
**Resuelve:** D8

## Contexto

§4 del SPEC dice que el reconocimiento use «salida JSON estructurada (tool use)», y en el mismo párrafo pide consultar la documentación actual de Anthropic en vez de depender de memoria. Al consultarla, resultó que el mecanismo cambió: el SDK expone **salidas estructuradas** de primera clase.

- `client.messages.parse(..., output_format=ModeloPydantic)` devuelve `response.parsed_output` ya validado contra el esquema.
- En `messages.create`, el equivalente es `output_config={"format": {...}}`. El parámetro antiguo `output_format` de `create()` está deprecado.
- Tool use sigue existiendo, pero para *ejecutar herramientas*. Usarlo solo para forzar un JSON es el patrón viejo: obliga a declarar una herramienta falsa, a leer `tool_use.input` y a validar a mano.

La versión instalada es `anthropic` 1.6.0, bastante más nueva de lo que yo habría supuesto.

## Decisión

El reconocimiento usa `client.messages.parse()` con un modelo Pydantic (`RecognitionPayload`) como esquema.

La intención de §4 era obtener JSON estructurado de forma fiable; esto la cumple mejor y con menos código propio. El cambio es de mecanismo, no de contrato: el JSON resultante es el mismo de §6.2 más los campos de ADR 0003.

`LLMProvider` se define al nivel correcto para que esto sea portable de verdad (D8): la interfaz es **«dame los pasos conformes a este esquema»**, no «llama al API». El manejo de salidas estructuradas vive dentro del adaptador de Anthropic, así que cambiar de proveedor no toca el reconocimiento ni el verificador.

## Consecuencias

- El esquema que ve el modelo (`app/llm/schema.py`) es **plano y sin valores por defecto**: todos los campos son obligatorios. Así el modelo tiene que decidir explícitamente `relation` y `derives_from` en vez de que un default los rellene en silencio, que es justo donde ADR 0003 dijo que el prompt es más frágil.
- Si un proveedor futuro no tiene salidas estructuradas, su adaptador implementa la misma interfaz con tool use o con parseo de JSON; el resto del código no se entera.
- Hay que fijarse en `stop_reason` antes de leer el contenido: `max_tokens` trunca y `refusal` no trae resultado.
