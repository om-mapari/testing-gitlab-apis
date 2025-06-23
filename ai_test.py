import asyncio
import json
import time
import requests  # For making external API calls
from typing import Optional, List
from pydantic import BaseModel, ValidationError
from starlette.responses import StreamingResponse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# Initialize FastAPI app
app = FastAPI(title="OpenAI-Compatible API")

# Models
class Message(BaseModel):
    role: str  # Role: "user", "assistant", or "system"
    content: str  # Must be a string (valid message content, required)

class ChatCompletionRequest(BaseModel):
    model: str = "mock-gpt-model"  # Default model
    messages: List[Message]  # List of Message objects
    max_tokens: Optional[int] = 512  # Maximum token count
    temperature: Optional[float] = 0.7  # Temperature
    stream: Optional[bool] = False  # Streaming mode (default: False)


# Helper: Simulate a streaming response (slow token generation)
async def _resp_async_generator(response_content: str):
    """
    Simulate tokenized response chunk by chunk for streaming mode.
    """
    tokens = response_content.split(" ")
    for i, token in enumerate(tokens):
        chunk = {
            "id": f"token-{i}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-gpt-model",
            "choices": [{"delta": {"content": token + " "}}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.1)  # Simulated delay
    # Mark stream as done
    yield "data: [DONE]\n\n"


# Helper: Fetch the response from the external API
def fetch_external_chat_response(messages, temperature):
    """
    Fetch the response from `test.com/chatting` endpoint using user-provided `messages` data.
    """
    url = "https://test.com/chatting"
    payload = {
        "messages": messages,
        "temperature": temperature
    }
    try:
        response = requests.post(url, json=payload, timeout=10)  # External API call
        response.raise_for_status()  # Raise an HTTPError for bad responses
        return response.json()  # Parse JSON response
    except requests.exceptions.RequestException as e:
        print(f"Error calling external API: {str(e)}")
        raise HTTPException(status_code=500, detail="External API call failed")


# Endpoint: GET /models
@app.get("/models")
async def get_models():
    """
    Return a list of available models.
    """
    return {
        "data": [
            {
                "id": "mock-gpt-model",
                "object": "model",
                "created": 0,
                "owned_by": "mock",
                "permission": [],
            }
        ]
    }


# Endpoint: POST /v1/chat/completions
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Handle chat completions (OpenAI-compatible endpoint) with support for external API.
    """
    # Log the raw payload (for debugging purposes)
    body = await request.json()
    print("RAW Incoming request:", body)

    # Preprocess the "messages" field to fix invalid formats
    if "messages" in body:
        for message in body["messages"]:
            # Check if "content" is not a string
            if not isinstance(message.get("content"), str):
                if isinstance(message["content"], list):
                    # Convert list to a concatenated string
                    message["content"] = " ".join(
                        item.get("text", "") for item in message["content"] if isinstance(item, dict) and "text" in item
                    )
                else:
                    message["content"] = str(message["content"])  # Force conversion to string

    # Validate payload using Pydantic model
    try:
        parsed_request = ChatCompletionRequest(**body)
    except ValidationError as e:
        print(f"Validation Error: {e}")
        raise HTTPException(status_code=422, detail=f"Validation error: {e.errors()}")
    
    print("Validated request:", parsed_request)

    # Process the last user message
    last_message = parsed_request.messages[-1]
    if last_message.role != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the 'user' role.")

    # Fetch response from external API
    external_response = fetch_external_chat_response(
        messages=[{"role": msg.role, "content": msg.content} for msg in parsed_request.messages],
        temperature=parsed_request.temperature,
    )

    # Extract the assistant's response from external API response
    assistant_response = external_response.get("choices", [{}])[0].get("message", {}).get("content", "No response")

    # Handle streaming response
    if parsed_request.stream:
        return StreamingResponse(
            _resp_async_generator(assistant_response),
            media_type="application/x-ndjson",
        )

    # Standard (non-streaming) response
    return {
        "id": external_response.get("id", "12345"),
        "object": external_response.get("object", "chat.completion"),
        "created": external_response.get("created", int(time.time())),
        "model": parsed_request.model,
        "choices": [
            {
                "message": {"role": "assistant", "content": assistant_response}
            }
        ],
        "usage": external_response.get("usage", {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22}),
    }


# Run the Server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)