from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

LOCAL_PROVIDERS = {"ollama", "vllm", "llama_cpp"}
GATED_PROVIDERS = {"bedrock"}
ALL_PROVIDERS = LOCAL_PROVIDERS | GATED_PROVIDERS


class ComplianceError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    ollama_api_base: str
    vllm_api_base: str | None
    llama_cpp_api_base: str | None
    aws_region: str | None
    aws_endpoint_url_bedrock: str | None
    bedrock_vpc_confirmed: bool


def load() -> LLMConfig:
    load_dotenv(override=False)
    provider = (
        os.getenv("VOLTAGRID_LLM_PROVIDER")
        or os.getenv("HERMES_LLM_PROVIDER")
        or "ollama"
    ).strip().lower()
    if provider not in ALL_PROVIDERS:
        raise ComplianceError(
            f"Unknown VOLTAGRID_LLM_PROVIDER '{provider}'. "
            f"Valid providers: {sorted(ALL_PROVIDERS)}."
        )
    endpoint = os.getenv("AWS_ENDPOINT_URL_BEDROCK")
    confirmed = (
        os.getenv("VOLTAGRID_BEDROCK_VPC_CONFIRMED") == "1"
        or os.getenv("HERMES_BEDROCK_VPC_CONFIRMED") == "1"
    )
    if provider in GATED_PROVIDERS:
        if not confirmed:
            raise ComplianceError("Bedrock requires VOLTAGRID_BEDROCK_VPC_CONFIRMED=1.")
        host = urlparse(endpoint or "").hostname or ""
        if not host.endswith(".vpce.amazonaws.com"):
            raise ComplianceError(
                "Bedrock endpoint must be an AWS PrivateLink host ending in "
                ".vpce.amazonaws.com."
            )
    return LLMConfig(
        provider=provider,
        model=(
            os.getenv("VOLTAGRID_LLM_MODEL")
            or os.getenv("HERMES_LLM_MODEL")
            or _default_model(provider)
        ),
        ollama_api_base=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
        vllm_api_base=os.getenv("VLLM_API_BASE"),
        llama_cpp_api_base=os.getenv("LLAMA_CPP_API_BASE"),
        aws_region=os.getenv("AWS_REGION"),
        aws_endpoint_url_bedrock=endpoint,
        bedrock_vpc_confirmed=confirmed,
    )


def _default_model(provider: str) -> str:
    if provider == "bedrock":
        return "bedrock/anthropic.claude-sonnet-4-v1:0"
    return "gemma4:e4b"


def get_client():
    import litellm

    cfg = load()

    def completion(**kwargs):
        if cfg.provider == "ollama":
            kwargs.setdefault("api_base", cfg.ollama_api_base)
            model = f"ollama/{cfg.model}" if not cfg.model.startswith("ollama/") else cfg.model
        elif cfg.provider == "vllm":
            kwargs.setdefault("api_base", cfg.vllm_api_base)
            model = cfg.model
        elif cfg.provider == "llama_cpp":
            kwargs.setdefault("api_base", cfg.llama_cpp_api_base)
            model = cfg.model
        else:
            model = cfg.model
            if cfg.aws_endpoint_url_bedrock:
                kwargs.setdefault("api_base", cfg.aws_endpoint_url_bedrock)
        kwargs.setdefault("model", model)
        return litellm.completion(**kwargs)

    return completion
