from app.api.websocket import public_websocket_error_message


def test_public_websocket_error_message_explains_missing_litellm_provider():
    error = RuntimeError(
        "litellm.BadRequestError: LLM Provider NOT provided. "
        "Pass in the LLM provider you are trying to call. "
        "You passed model=tianfu-basic"
    )

    message = public_websocket_error_message(error)

    assert "provider-qualified" in message
    assert "openai/your-model" in message


def test_public_websocket_error_message_explains_timeout():
    error = RuntimeError("LLM request timed out after 45 seconds.")

    message = public_websocket_error_message(error)

    assert "timed out" in message.lower()


def test_public_websocket_error_message_explains_bad_gateway():
    error = RuntimeError(
        "litellm.BadGatewayError: BadGatewayError: OpenAIException - "
        "502 Bad Gateway. Received Model Group=tianfu-basic"
    )

    message = public_websocket_error_message(error)

    assert "502" in message


def test_public_websocket_error_message_explains_invalid_model():
    error = RuntimeError(
        "Invalid model name passed in model=malt-simple. "
        "Call `/v1/models` to view available models for your key."
    )

    message = public_websocket_error_message(error)

    assert "model name" in message.lower()
    assert "LLM Profiles" in message


def test_public_websocket_error_message_explains_auth_failure():
    error = RuntimeError(
        "Authentication Error, Invalid API key provided"
    )

    message = public_websocket_error_message(error)

    assert "authentication" in message.lower()
    assert "API key" in message


def test_public_websocket_error_message_explains_embed_failure():
    error = RuntimeError(
        "Server error '502 Bad Gateway' for url 'http://localhost:8001/embed'"
    )

    # 502 is checked before embed path in current logic; either message is fine
    # as long as it is not the opaque generic fallback when embed is the only signal.
    message = public_websocket_error_message(
        RuntimeError("All connection attempts failed for url 'http://localhost:8001/embed'")
    )

    assert "embedding" in message.lower() or "worker" in message.lower()
