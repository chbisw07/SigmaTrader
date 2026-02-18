"""Provider clients for AI test + model discovery.

These are intentionally small and synchronous (httpx.Client) to keep the
implementation reliable and easy to test. Orchestrator can wrap them later.
"""

