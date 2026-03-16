Create a FastAPI REST API in a single file named main.py.

Requirements:

- Use FastAPI and Pydantic only
- Store users in an in-memory Python list (no database)
- User model must contain:
    id (int)
    username (str)
    email (str)
    password (str)

Endpoints:

- GET /health
    Returns: {"status": "healthy"}

- POST /users
    Accept JSON: { "username": str, "email": str, "password" }
    Auto-assign incremental integer id starting from 1
    Return created user object

- GET /users
    Return list of all users

- GET /users/{user_id}
    Return specific user or 404 if not found

Other Requirements:

- Include requirements.txt with:
    fastapi
    uvicorn

- Define a variable at the top of the file:
    PORT = 8000

- Do NOT hardcode the port anywhere else.
- The run instruction comment must reference the PORT variable like this:

    # Run with:
    # uvicorn main:app --reload --port {PORT}

- Add a script run.sh that is a shellscript to launch exectly this uvicorn command: python -m uvicorn main:app --reload --port (PORT) (same port value as we use for the application)

- No database
- No authentication
- No additional frameworks
- Keep implementation minimal and clean

STRICT SCOPE RULES:

- Only implement what is explicitly described in this task.
- Do NOT add additional fields, attributes, properties, or metadata.
- Do NOT add password, is_active, timestamps, status flags, or any inferred security features.
- Do NOT extend models beyond what is defined.
- If something is not specified, do not invent it.
- Stay strictly within the defined contract.
