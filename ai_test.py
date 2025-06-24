import asyncio
import json
import time
import requests  # For making external API calls
from typing import Optional, List
from pydantic import BaseModel, ValidationError  # Used to validate data models
from starlette.responses import StreamingResponse  # Used for streaming responses
from fastapi import FastAPI, HTTPException, Request  # FastAPI core modules for building APIs
from fastapi.responses import JSONResponse  # Response object in FastAPI

# Initialize FastAPI app
# This will serve as the base framework for building the API
app = FastAPI(title="OpenAI-Compatible API")

# Models
class Message(BaseModel):
    # Defines the structure of individual chat messages
    role: str  # The role of the message sender: "user", "assistant", or "system"
    content: str  # The content of the message, must always be a string

class ChatCompletionRequest(BaseModel):
    # Defines the structure of the request payload for OpenAI-like chat completions
    model: str = "mock-gpt-model"  # Specifies the model being used; default is "mock-gpt-model"
    messages: List[Message]  # List of messages in the conversation (chat history)
    max_tokens: Optional[int] = 512  # Maximum number of tokens in the completion (optional)
    temperature: Optional[float] = 0.7  # Controls randomness of responses; higher is more random (optional)
    stream: Optional[bool] = False  # Determines if the response should be streamed token-by-token (optional)

# Helper: Simulate a streaming response (slow token generation)
async def _resp_async_generator(response_content: str):
    """
    Simulates tokenized response chunk by chunk for streaming mode.
    If streaming is enabled, returns one token at a time with a slight delay.
    """
    tokens = response_content.split(" ")  # Splits the complete response into tokens (words for simplicity)
    for i, token in enumerate(tokens):
        # Creates a chunked response object matching OpenAI's streaming format
        chunk = {
            "id": f"token-{i}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-gpt-model",
            "choices": [{"delta": {"content": token + " "}}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"  # Yields each token as a chunk for streaming response
        await asyncio.sleep(0.1)  # Simulates a delay for token generation
    # Indicate that the stream is complete
    yield "data: [DONE]\n\n"

# Helper: Fetch the response from the external API
def fetch_external_chat_response(messages, temperature):
    """
    Fetch the chat completion response from the external API (`test.com/chatting`).
    Sends the `messages` and `temperature` as payload.
    """
    url = "https://test.com/chatting"  # External API URL for fetching responses
    payload = {
        "messages": messages,  # Payload format: list of messages with roles and contents
        "temperature": temperature  # The specified randomness level for the response
    }
    try:
        # Makes a POST request to the external API with the conversation payload
        response = requests.post(url, json=payload, timeout=10)  # Timeout is set to 10 seconds
        response.raise_for_status()  # Raises an exception if the API call fails
        return response.json()  # Returns the parsed JSON response
    except requests.exceptions.RequestException as e:
        print(f"Error calling external API: {str(e)}")  # Logs API errors to the console
        # Raises an HTTPException to inform the client of the failure
        raise HTTPException(status_code=500, detail="External API call failed")

# Endpoint: GET /models
@app.get("/models")
async def get_models():
    """
    Returns a list of available models.
    This is a mock implementation for compatibility with OpenAI's `/models` endpoint.
    """
    return {
        "data": [
            {
                "id": "mock-gpt-model",  # ID of the model
                "object": "model",  # Object type (always "model")
                "created": 0,  # Example creation timestamp (mocked as 0)
                "owned_by": "mock",  # Owner/creator of the model (mock implementation)
                "permission": [],  # Permissions list (empty in this mock version)
            }
        ]
    }

# Endpoint: POST /v1/chat/completions
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Handles chat completions with support for external API integration (`test.com/chatting`).
    Behaves like OpenAI's `/v1/chat/completions` endpoint.
    """
    # Log the raw payload from the client for debugging
    body = await request.json()  # Parses raw request body into a dictionary
    print("RAW Incoming request:", body)

    # Fix invalid formats in the "messages" field if necessary
    if "messages" in body:  # Check if 'messages' exists in the payload
        for message in body["messages"]:
            # If the content is not a string, try to convert it (e.g., from list or dict)
            if not isinstance(message.get("content"), str):
                if isinstance(message["content"], list):
                    # Convert list of dicts to a concatenated string
                    message["content"] = " ".join(
                        item.get("text", "") for item in message["content"] if isinstance(item, dict) and "text" in item
                    )
                else:
                    # Force content into a string format as a fallback
                    message["content"] = str(message["content"])  

    # Validate incoming payload against the Pydantic model `ChatCompletionRequest`
    try:
        parsed_request = ChatCompletionRequest(**body)  # Parses and validates the request JSON
    except ValidationError as e:
        print(f"Validation Error: {e}")  # Logs validation errors
        # Returns a validation error response to the client
        raise HTTPException(status_code=422, detail=f"Validation error: {e.errors()}")

    print("Validated request:", parsed_request)  # Logs the successfully validated request

    # Check that the last message in the chat history was sent by the user
    last_message = parsed_request.messages[-1]
    if last_message.role != "user":
        # Raises an error if the last message is not from the user's role
        raise HTTPException(status_code=400, detail="The last message must be from the 'user' role.")
    
    # Fetch response from the external API (`test.com/chatting`)
    external_response = fetch_external_chat_response(
        messages=[{"role": msg.role, "content": msg.content} for msg in parsed_request.messages],
        temperature=parsed_request.temperature,
    )

    # Extract the assistant's response from the external API response
    assistant_response = external_response.get("choices", [{}])[0].get("message", {}).get("content", "No response")

    # Handle streaming mode if requested by the client
    if parsed_request.stream:
        # Return a streaming response (token-by-token simulation)
        return StreamingResponse(
            _resp_async_generator(assistant_response),
            media_type="application/x-ndjson",
        )

    # Standard (non-streaming) response
    return {
        "id": external_response.get("id", "12345"),  # ID from the external API response
        "object": external_response.get("object", "chat.completion"),  # Object type
        "created": external_response.get("created", int(time.time())),  # Creation timestamp
        "model": parsed_request.model,  # Use the model passed in the request
        "choices": [
            {
                "message": {"role": "assistant", "content": assistant_response}  # Assistant's response
            }
        ],
        "usage": external_response.get("usage", {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22}),  # Usage data (mock values if not provided)
    }

# Run the Server
if __name__ == "__main__":
    import uvicorn
    # Starts the FastAPI server on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)