import asyncio
import json
import time
from typing import Optional, List
from pydantic import BaseModel, ValidationError
from starlette.responses import StreamingResponse
from fastapi import FastAPI, HTTPException, Request

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
    Handle chat completions (OpenAI-compatible endpoint) with support for streaming.
    """
    # Log the raw payload (for debugging purposes)
    body = await request.json()
    print("RAW Incoming request:", body)

    # Preprocess the "messages" field to fix invalid formats
    if "messages" in body:
        for message in body["messages"]:
            # Check if "content" is not a string, e.g., a list or another structure
            if not isinstance(message.get("content"), str):
                if isinstance(message["content"], list):
                    # Convert list to a concatenated string (example)
                    message["content"] = " ".join(
                        item.get("text", "") for item in message["content"] if isinstance(item, dict) and "text" in item
                    )
                else:
                    message["content"] = str(message["content"])  # Force conversion to string if necessary

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

    # Generate response content (mock logic)
    response_content = f"Mock reply to: {last_message.content}"

    # Handle streaming response
    if parsed_request.stream:
        return StreamingResponse(
            _resp_async_generator(response_content),
            media_type="application/x-ndjson",
        )

    # Standard (non-streaming) response
    return {
        "id": "12345",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": parsed_request.model,
        "choices": [
            {
                "message": {"role": "assistant", "content": response_content}
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},  # Mock usage
    }




# Run the Server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)