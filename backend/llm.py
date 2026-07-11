"""Provider-agnostic LLM client.

Supports three backends, selected by ``LLM_PROVIDER``:
  * ``openai``  - OpenAI (or any OpenAI-compatible endpoint via OPENAI_BASE_URL)
  * ``groq``    - Groq's OpenAI-compatible API (serves gpt-oss and other models)
  * ``bedrock`` - AWS Bedrock (Anthropic Claude messages API)

The client is intentionally tiny and dependency-light. If the provider is
``none`` or misconfigured, ``is_available()`` returns ``False`` and callers
fall back to the deterministic heuristic ranker. No call ever raises into the
request path unless the caller opts in.
"""
import json
import logging

from config import config

logger = logging.getLogger(__name__)

# Default per-request timeout (seconds) to keep a public endpoint responsive.
_REQUEST_TIMEOUT = 30


class LLMUnavailable(Exception):
    """Raised when the LLM cannot produce a usable response."""


class LLMClient:
    def __init__(self, provider=None):
        self.provider = (provider or config.LLM_PROVIDER or "none").lower()
        self._client = None
        self._init_error = None
        self._initialize()

    # -- setup -------------------------------------------------------------
    def _initialize(self):
        if self.provider == "openai":
            self._client = self._init_openai_compatible(
                config.OPENAI_API_KEY, config.OPENAI_BASE_URL, "OPENAI_API_KEY")
        elif self.provider == "groq":
            self._client = self._init_openai_compatible(
                config.GROQ_API_KEY, config.GROQ_BASE_URL, "GROQ_API_KEY")
        elif self.provider == "bedrock":
            self._init_bedrock()
        else:
            self._init_error = "LLM provider disabled (LLM_PROVIDER=none)"

    def _init_openai_compatible(self, api_key, base_url, key_name):
        """Build an OpenAI SDK client for any OpenAI-compatible endpoint.

        Returns the client, or ``None`` (recording ``_init_error``) so the app
        degrades to the heuristic ranker instead of raising at startup.
        """
        if not api_key:
            self._init_error = f"{key_name} is not set"
            return None
        try:
            from openai import OpenAI
        except ImportError:
            self._init_error = "openai package is not installed"
            return None
        kwargs = {
            "api_key": api_key,
            "timeout": _REQUEST_TIMEOUT,
            # The SDK honors the provider's Retry-After header, so retries let
            # calls ride out transient per-minute (TPM/RPM) rate limits.
            "max_retries": config.LLM_MAX_RETRIES,
        }
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    def _init_bedrock(self):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            self._init_error = "boto3 package is not installed"
            return
        try:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=config.AWS_REGION,
                config=BotoConfig(read_timeout=_REQUEST_TIMEOUT, retries={"max_attempts": 2}),
            )
        except Exception as exc:  # credential/region issues
            self._init_error = f"could not create Bedrock client: {exc}"

    # -- public API --------------------------------------------------------
    def is_available(self):
        return self._client is not None

    @property
    def model_name(self):
        if self.provider == "openai":
            return config.OPENAI_MODEL
        if self.provider == "groq":
            return config.GROQ_MODEL
        if self.provider == "bedrock":
            return config.BEDROCK_MODEL_ID
        return "none"

    def complete_json(self, system, user, max_tokens=900, temperature=0.2):
        """Return a parsed JSON dict from the model.

        Raises ``LLMUnavailable`` if the LLM is off, errors, or returns
        unparseable content. Callers are expected to catch and fall back.
        """
        raw = self._complete(system, user, max_tokens, temperature, json_mode=True)
        return _extract_json(raw)

    def complete_text(self, system, user, max_tokens=600, temperature=0.3):
        """Return raw text from the model, or raise ``LLMUnavailable``."""
        return self._complete(system, user, max_tokens, temperature, json_mode=False)

    # -- internals ---------------------------------------------------------
    def _complete(self, system, user, max_tokens, temperature, json_mode):
        if not self.is_available():
            raise LLMUnavailable(self._init_error or "LLM is not available")
        try:
            if self.provider in ("openai", "groq"):
                return self._openai_complete(system, user, max_tokens, temperature, json_mode)
            if self.provider == "bedrock":
                return self._bedrock_complete(system, user, max_tokens, temperature)
        except LLMUnavailable:
            raise
        except Exception as exc:  # normalize every backend failure
            logger.warning("LLM call failed (%s): %s", self.provider, exc)
            raise LLMUnavailable(str(exc)) from exc
        raise LLMUnavailable("Unsupported LLM provider")

    def _openai_complete(self, system, user, max_tokens, temperature, json_mode):
        kwargs = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        # gpt-oss on Groq is a reasoning model; cap the reasoning budget so the
        # hidden chain-of-thought doesn't eat into max_tokens and truncate JSON.
        if self.provider == "groq" and config.GROQ_REASONING_EFFORT:
            kwargs["extra_body"] = {"reasoning_effort": config.GROQ_REASONING_EFFORT}
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _bedrock_complete(self, system, user, max_tokens, temperature):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
        }
        resp = self._client.invoke_model(
            modelId=config.BEDROCK_MODEL_ID, body=json.dumps(body)
        )
        payload = json.loads(resp["body"].read())
        parts = payload.get("content", []) or []
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def _extract_json(text):
    """Parse a JSON object from a model response, tolerating code fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except (ValueError, TypeError):
                pass
    raise LLMUnavailable("Could not parse JSON from LLM response")


_singleton = None


def get_llm_client():
    """Return a process-wide cached ``LLMClient``."""
    global _singleton
    if _singleton is None:
        _singleton = LLMClient()
        if _singleton.is_available():
            logger.info("LLM enabled: provider=%s model=%s",
                        _singleton.provider, _singleton.model_name)
        else:
            logger.info("LLM disabled (%s); using heuristic ranking.",
                        _singleton._init_error)
    return _singleton
