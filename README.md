### **README**

---

## **OpenAI-Compatible Chat Completion API**

### **Overview**
This is a **FastAPI-based web server** that mimics the behavior of OpenAI's chat completion API (`/v1/chat/completions`) while integrating responses from an external chat API (`https://test.com/chatting`). It allows you to keep the interface of OpenAI's API while fetching actual responses from a custom endpoint (or third-party service). 

The project enables you to seamlessly switch between OpenAI-style APIs and substitute external APIs, allowing compatibility with existing tools that rely on OpenAI's API structure.

---

### **Features**
1. **OpenAI-Compatible Endpoints**:
   - `/models`: Retrieves available models for chat completion.
   - `/v1/chat/completions`: Main endpoint that handles chat requests and returns responses similar to OpenAI.

2. **External API Integration**:
   - Fetches the assistant's replies from `https://test.com/chatting`. The external API processes chat messages and generates a reply.

3. **Streaming Mode Support**:
   - Simulates token-by-token responses (as OpenAI does during streaming).

4. **Payload Validation**:
   - Ensures incoming requests conform to OpenAI's specification using Pydantic models.

5. **Error Handling**:
   - Handles malformed requests.
   - Gracefully manages errors from the external API (e.g., network issues).

---

### **Why Use This Project?**

#### **Use Case 1: OpenAI Compatibility**
The interface replicates OpenAI’s API, allowing you to use tools built for OpenAI (e.g., SDKs, user interfaces) with other chat models or external APIs.

#### **Use Case 2: Replace OpenAI with Custom Model/API**
You might want to:
- Use a self-hosted LLM or an alternative service for cost savings.
- Use APIs that align better with your privacy or compliance policies (e.g., `test.com/chatting`).

#### **Use Case 3: Add Middleware Logic**
This project provides an extensible structure where you can add pre/post-processing, middleware, logging, or any other custom logic.

---

### **Installation**
1. Clone this repository:
   ```bash
   git clone <REPOSITORY_LINK>
   cd <REPOSITORY_FOLDER>
   ```

2. Install dependencies:
   ```bash
   pip install fastapi uvicorn pydantic requests
   ```

---

### **Usage**

#### **1. Running the Server**
Start the FastAPI server:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### **2. Endpoints**

##### **List Models**
Fetch available models:
```bash
GET /models
```

Example Response:
```json
{
    "data": [
        {
            "id": "mock-gpt-model",
            "object": "model",
            "created": 0,
            "owned_by": "mock",
            "permission": []
        }
    ]
}
```

---

##### **Chat Completions**
Send a chat request:
```bash
POST /v1/chat/completions
```

Payload Example:
```json
{
    "model": "mock-gpt-model",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the weather like today?"}
    ],
    "temperature": 0.7,
    "stream": false
}
```

---

#### **Test Responses**
Internally, this endpoint forwards requests to `https://test.com/chatting`. Responses (from the external API) are transformed to OpenAI-compatible formats before being returned.

---

### **Streaming Mode**
If `stream: true` is included in the payload, responses are streamed token-by-token.

---

### **Error Handling**
Common issues (e.g., validation errors, external API failures) will return appropriate HTTP responses:
- `422 Unprocessable Entity`: Invalid payload format.
- `500 Internal Server Error`: Failed connection to the external API.

The server logs raw incoming requests for debugging purposes.

---

### **Customization**
1. **Change External API**:
   Modify the `fetch_external_chat_response` function to integrate with any API of your choice.

2. **Pre/Post-Processing**:
   Add your logic in the `/v1/chat/completions` handler, either before or after interacting with the external API.

---

### **Extensibility**
This project demonstrates how you can replicate OpenAI's API interface while integrating it with different backends. You can enhance it further:
- **Middleware**: Add logging, rate-limiting, or authentication.
- **Custom Business Logic**: Preprocess user input or post-process external responses.
- **Multi-Backend Support**: Dynamically switch between APIs or models based on context.

---

### **Contributions**
Feel free to contribute by:
- Fixing bugs.
- Adding features (e.g., function call support, embeddings, Azure-like deployment endpoint, etc.).
- Improving API compatibility across providers.

---

### **Dependencies**
- **FastAPI**: Framework for building APIs.
- **Pydantic**: Data validation for request payloads.
- **Requests**: To interact with external APIs.
- **Uvicorn**: ASGI server for running FastAPI applications.

---

### **Acknowledgments**
Inspired by OpenAI's Chat Completions API schema and designed to bridge compatibility for alternative backends.

---

Let me know if you need further customization for the README or additional details!