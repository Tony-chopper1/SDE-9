

\# SDK-9 AI Voicebot — Operations Runbook



\## 1. Project Overview



SDK-9 is an AI Voicebot application with a Python FastAPI backend.



The backend supports session management, event streaming, and pipeline processing.



Default mode: Mock mode  

Default port: 8000



\## 2. Prerequisites



\- Python 3.10 or later

\- Git

\- Visual Studio Code or another code editor

\- Internet connection for installing dependencies



Paid API credentials are not required for mock mode.



\## 3. Clone the Repository



```powershell

git clone https://github.com/Tony-chopper1/SDK-9.git

cd SDK-9

```



\## 4. Install Dependencies



Create a virtual environment:



```powershell

python -m venv .venv

```



Activate it:



```powershell

.venv\\Scripts\\Activate.ps1

```



Install project dependencies:



```powershell

python -m pip install --upgrade pip

pip install -e ".\[dev]"

```



\## 5. Configure the Backend



Create the environment file:



```powershell

Copy-Item .env.example .env

```



Keep mock mode enabled:



```env

MOCK\_MODE=true

ENVIRONMENT=development

HOST=127.0.0.1

PORT=8000

```



Never commit API keys, tokens, audio recordings, or personal information.



\## 6. Start the Backend



Run:



```powershell

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

```



Open API documentation:



http://127.0.0.1:8000/docs



\## 7. Health and Readiness Checks



Health endpoint:



```powershell

Invoke-RestMethod http://127.0.0.1:8000/api/v1/health

```



Readiness endpoint:



```powershell

Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready

```



\## 8. Run Tests



Run backend tests:



```powershell

python -m pytest backend/tests -v

```



Run the complete project tests:



```powershell

python -m pytest -v

```



\## 9. Demo Workflow



1\. Start the backend.

2\. Open http://127.0.0.1:8000/docs.

3\. Create a session.

4\. Copy the returned session ID.

5\. Publish an event for that session.

6\. Retrieve the event stream.

7\. Test pause, resume, and stop operations.

8\. Test reconnect using Last-Event-ID.

9\. Submit an invalid request and verify the error response.



\## 10. Failure Handling



The backend should handle:



\- Unknown session IDs with HTTP 404.

\- Invalid session transitions with HTTP 409.

\- Malformed requests with typed validation errors.

\- Invalid reconnect cursors with HTTP 400.

\- Oversized event payloads with validation errors.

\- Invalid pipeline credentials with HTTP 401 when authentication is configured.



Internal stack traces and sensitive request payloads must not be exposed to API clients.



\## 11. Security and Logging



\- Keep mock mode enabled for local development.

\- Never log audio or transcript contents.

\- Never log API keys or authentication tokens.

\- Use correlation IDs to trace requests.

\- Never commit `.env` files or credentials.



\## 12. Known Limitations



\- Session and event data are stored in memory.

\- Data is lost when the backend restarts.

\- Rate limiting is process-local.

\- Mock integrations do not replace production AI providers.

\- The pipeline does not execute registered tools.



\## 13. Troubleshooting



\### Port already in use



Start the server on another port:



```powershell

python -m uvicorn backend.main:app --port 8001

```



\### Missing dependencies



```powershell

python -m pip install -e ".\[dev]"

```



\### Tests failing



```powershell

python -m pytest backend/tests -v

```



\### Server not starting



Check the terminal for startup errors and verify environment settings.



\## 14. Release Checklist



\- \[ ] Clean clone setup verified.

\- \[ ] Dependencies installed successfully.

\- \[ ] Backend starts successfully.

\- \[ ] Health and readiness endpoints respond.

\- \[ ] Complete test suite passes.

\- \[ ] Concurrent sessions remain isolated.

\- \[ ] Reconnect replay works.

\- \[ ] Malformed requests return typed errors.

\- \[ ] Logs do not expose sensitive information.

\- \[ ] OpenAPI examples documented.

\- \[ ] Final demo verified.

\- \[ ] Pull request reviewed and merged.



