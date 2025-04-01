import webbrowser
from typing import Any, Optional
from dataclasses import dataclass

from arcadepy import Arcade
from arcadepy.types import AuthorizationResponse
from openai import OpenAI
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from arcade.cli.utils import (get_tool_authorization, get_tool_messages,
                              handle_streaming_content, markdownify_urls,
                              wait_for_authorization_completion)

console = Console()

@dataclass
class ChatInteractionResult:
    history: list[dict]
    tool_messages: list[dict]
    tool_authorization: dict | None


class ModelClientWrapper:
    def __init__(self, api_key: str, base_url: str = None, model: str = "gpt-3.5-turbo"):
        self.api_key = api_key
        self.base_url = base_url or "https://api.arcade.dev/v1"  # Default to OpenAI if base_url is None
        self.model = model.lower()


    def chat(self, history: Optional[list] = None, user_email: Optional[str] = None, stream: bool = False):
        # Handle chat interaction based on the client type
        if self.client_type == "openai":
            # Assuming OpenAI client has chat support
            return self.client.chat.completions.create(
                model=self.model,
                messages=history,
                user=user_email,
                stream=stream
            )
        elif self.client_type == "anthropic":
            # Handle chat with Anthropic (replace with real client code)
            return self._handle_anthropic_chat(self.model, history, user_email, stream)

    
    def handle_chat_interaction(
        self, history: list[dict], user_email: str | None, stream: bool = False
    ) -> ChatInteractionResult:
        """
        Handle a single chat-request/chat-response interaction for both streamed and non-streamed responses.
        Handling the chat response includes:
        - Streaming the response if the stream flag is set
        - Displaying the response in the console
        - Getting the tool messages and tool authorization from the response
        - Updating the history with the response, tool calls, and tool responses
        """
        if stream:
            # TODO Fix this in the client so users don't deal with these
            # typing issues
            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model,
                messages=history,
                tool_choice="generate",
                user=user_email,
                stream=True,
            )
            streaming_result = handle_streaming_content(response, self.model)
            role, message_content = streaming_result.role, streaming_result.full_message
            tool_messages, tool_authorization = (
                streaming_result.tool_messages,
                streaming_result.tool_authorization,
            )
        else:
            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model,
                messages=history,
                tool_choice="generate",
                user=user_email,
                stream=False,
            )
            message_content = response.choices[0].message.content or ""

            # Get extra fields from the response
            tool_messages = get_tool_messages(response.choices[0])
            tool_authorization = get_tool_authorization(response.choices[0])

            role = response.choices[0].message.role

            if role == "assistant" and tool_authorization:
                pass  # Skip the message if it's an auth request (handled later in handle_tool_authorization)
            elif role == "assistant":
                message_content = markdownify_urls(message_content)
                console.print(
                    f"\n[blue][bold]Assistant[/bold] ({self.model}):[/blue] ", Markdown(message_content)
                )
            else:
                console.print(f"\n[bold]{role}:[/bold] {message_content}")

        history += tool_messages
        history.append({"role": role, "content": message_content})

        return ChatInteractionResult(history, tool_messages, tool_authorization)
    

    def handle_tool_authorization(
        self,
        arcade_client: Arcade,
        tool_authorization: AuthorizationResponse,
        history: list[dict[str, Any]],
        user_email: str | None,
        stream: bool,
    ) -> ChatInteractionResult:
        with Live(console=console, refresh_per_second=4) as live:
            if tool_authorization.url:
                authorization_url = str(tool_authorization.url)
                webbrowser.open(authorization_url)
                message = (
                    "You'll need to authorize this action in your browser.\n\n"
                    f"If a browser doesn't open automatically, click [this link]({authorization_url}) "
                    f"or copy this URL and paste it into your browser:\n\n{authorization_url}"
                )
                live.update(Markdown(message, style="dim"))

            wait_for_authorization_completion(arcade_client, tool_authorization)

            message = "Thanks for authorizing the action! Sending your request..."
            live.update(Text(message, style="dim"))

        history.pop()
        return self.handle_chat_interaction(self.model, history, user_email, stream)

