from datetime import datetime
import os
from interfaces import LoggerBackend

class Logger(LoggerBackend):

    def log_llm_call(
        self,
        function_name: str,
        prompt: str,
        response: str,
        tokens: int,
        user_id: str=None,
    ) -> None:
        
        # Validate inputs
        if not function_name:
            raise ValueError("function_name cannot be empty")
        if not prompt:
            raise ValueError("prompt cannot be empty")
        if not response:
            raise ValueError("response cannot be empty")
        if not isinstance(tokens, int) or tokens < 0:
            raise ValueError(f"tokens must be a positive integer, got {tokens}")
        if not user_id:
            raise ValueError("user_id cannot be empty")
        
        os.makedirs("./data/logs", exist_ok=True)

        with open("./data/logs/llm_calls.log", "a") as f:
            f.write(f"[{datetime.now()}] FUNCTION: {function_name}\n")
            f.write(f"PROMPT: {prompt}\n")
            f.write(f"RESPONSE: {response}\n")
            f.write(f"TOKENS: {tokens}\n")
            f.write(f"USER_ID: {user_id}\n")
            f.write("---\n")