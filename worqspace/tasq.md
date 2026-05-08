Goal

Create a chat webapp with no authentication, where each browser instance acts as a separate user session.

When two different browser instances are opened:

they must appear as 2 different users
each user can choose a display name when joining
users can send chat messages to each other in real time
users can see who is online
users can send files to each other
the receiver must get a confirmation prompt to accept or deny the incoming file
Core behavior
Session identity rules
No login system
No passwords
No authentication
Each browser instance must get its own session identity
Each browser instance can choose a display name when joining
Two separate browser instances must behave like two separate users
A page refresh may reset the local session identity unless the implementation intentionally preserves it in browser storage
Do not implement user accounts
Chat behavior
A user enters a display name and joins the chat
Joined users appear in an online users list
Users can send text messages
Messages must appear in real time without manually refreshing the page
Messages must show:
sender name
recipient name or broadcast target
message text
Online users behavior
Show a visible list of currently online users
When a user joins, they appear in the list
When a user disconnects or leaves, they disappear from the list
Do not fake presence with hardcoded names
File transfer behavior

A user must be able to send a file to another online user.

Flow:

sender selects a target user
sender selects a file
receiver gets an incoming file request
receiver can:
accept
deny
if accepted:
file becomes available to the receiver
if denied:
file is not delivered

The UI must clearly show:

who sent the file
filename
pending / accepted / denied state
Tech rules
Use FastAPI and Pydantic
Use Python standard library where needed
No database
No authentication framework
No external storage service
No Redis
No Celery
No extra backend frameworks
Keep implementation modular and clean
Required architecture

The app must be split across multiple Python files.

Required files:

main.py
schemas.py
store.py
chat_routes.py
file_routes.py
ws_manager.py
utils.py
requirements.txt
run.sh

You may add small helper files only if truly necessary.

Storage rules
Runtime state

Store runtime state in memory only:

online users
chat messages
pending file transfer requests
accepted file transfer metadata

Do not use:

SQLite
Postgres
MongoDB
Redis
JSON persistence
File storage

All uploaded/sent files must land in exactly:

UPLOAD_DIR = "storage/uploads"

Rules:

create the directory automatically if needed
no final file storage outside storage/uploads
sanitize filenames
block path traversal
handle duplicate filenames safely
only accepted transfers should be considered delivered
Required models
UserSession

Must contain exactly:

id (str)
name (str)
ChatMessage

Must contain exactly:

id (int)
sender_id (str)
recipient_id (str)
text (str)
FileTransfer

Must contain exactly:

id (int)
sender_id (str)
recipient_id (str)
filename (str)
status (str)

Allowed status values:

pending
accepted
denied

Do not add timestamps, avatars, emails, auth flags, typing status, or extra metadata unless explicitly required.

Required file responsibilities
main.py
define PORT = 8000 at the top
create the FastAPI app
register route modules
mount or serve the minimal frontend UI
include this run comment:
# Run with:
# uvicorn main:app --reload --port {PORT}
schemas.py

Define all Pydantic models:

UserSession
JoinRequest
ChatMessage
ChatMessageCreate
FileTransfer
any minimal request models needed for accept/deny flow

Keep models minimal.

store.py

Shared in-memory state logic.

Responsibilities:

track online users
track chat messages
track file transfer requests
assign incremental integer ids for messages and file transfers starting from 1
expose helpers for:
add/remove/get online users
create/list chat messages
create/get/update file transfers
ws_manager.py

Handle WebSocket connection management.

Responsibilities:

connect/disconnect browser sessions
map session ids to live connections
broadcast online user updates
deliver chat messages in real time
deliver file transfer requests in real time
deliver accept/deny decisions in real time
chat_routes.py

Provide endpoints and/or websocket handlers for chat behavior.

Required features:

join chat with chosen display name
send message
list messages
list online users
file_routes.py

Provide endpoints for:

sending a file request to another user
accepting a pending file request
denying a pending file request
listing file transfers relevant to the current session
downloading an accepted file
utils.py

Shared helpers for:

ensuring upload directory exists
sanitizing filenames
generating safe suffixed filenames
saving uploaded files safely
Frontend requirements

Provide a minimal browser UI.

The UI must include:

a name input / join action
an online users list
a chat message area
a message input box
a send button
a file picker
a target-user selector for sending a file
visible incoming file request prompts
accept and deny controls

The frontend may be:

plain HTML + vanilla JavaScript

Do not use:

React
Vue
Angular
authentication UI
CSS frameworks unless explicitly required
Real-time requirement

The app must support real-time updates between two browser instances.

Using WebSockets is allowed and recommended.

At minimum, these must update live:

online user list
incoming chat messages
incoming file requests
accept/deny results
Session behavior requirement

Because there is no authentication:

each browser instance must get a separate session id
the session id may be stored in browser memory or local storage
the chosen display name belongs only to that session
two browser windows must be able to join with different names
Required endpoints / behaviors

At minimum, the system must support:

GET /health
returns { "status": "healthy" }
join action
choose a name
create a session
online users retrieval
message send
message list retrieval
file send
file accept
file deny
accepted file download

Exact endpoint naming is up to the implementation, but behavior must match the task.

requirements.txt

Must include only what is actually needed to run the app.

At minimum:

fastapi
uvicorn

Do not add unnecessary libraries.

run.sh

Must launch exactly:

python -m uvicorn main:app --reload --port 8000
Scope rules
Only implement what is explicitly described
Do not add authentication
Do not add databases
Do not add message edit/delete
Do not add avatars
Do not add read receipts
Do not add typing indicators
Do not add group chat rooms unless explicitly required
Do not add encryption
Do not add persistent message history across restarts
Do not add admin roles
Do not add email notifications
Acceptance criteria

The task is complete only if:

two browser instances behave as two separate users
each can choose a name and join
online users list works
real-time chat works
file transfer request works
receiver can accept or deny
accepted files are retrievable
denied files are not delivered
all files land in exactly storage/uploads
runtime state is kept in memory only
the code is split across the required Python files
implementation stays minimal and in scope
