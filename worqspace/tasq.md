Build a small, production-ready HTTP web server that serves a single HTML page with “Hello from QonQrete” plus a JSON /health endpoint returning { "status": "ok" }.

The project should include:
- a clear README.md with run instructions
- a simple configuration mechanism (port from an environment variable with a sensible default)
- basic logging of incoming requests
- at least one automated test that hits the health endpoint.

Containerize the app with a minimal Dockerfile suitable for local development, and structure the code so it’s easy to extend with new routes later.
