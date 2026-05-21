from utils.common import get_time
import os
from interfaces import LoggerBackend
from data.schemas import LLMCallLog

class Logger(LoggerBackend):

    async def log_llm_call(
        self,
        function_name: str,
        prompt: str,
        response: str,
        tokens: int,
        user_id: str,
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

        # 2. Kreiramo instancu našeg modela
        log_entry = LLMCallLog(
            timestamp=get_time(),
            function_name=function_name,
            prompt=prompt,
            response=response,
            tokens=tokens,
            user_id=user_id
        )
        
        # 3. Asinhrono ga "bacamo" u MongoDB kao poseban JSON dokument
        await log_entry.insert()

