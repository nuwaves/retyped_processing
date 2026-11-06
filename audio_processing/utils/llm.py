import logging
import time

import requests
from constance import config
from django.conf import settings

logger = logging.getLogger(__name__)

# One first try plus two retries.
MAX_ATTEMPTS = 3

# Seconds to wait before each retry, unless the provider sends Retry-After.
RETRY_DELAYS = (15, 60)

# Longest Retry-After we will honour; a provider asking for more is treated as
# this, so one step can't stall the whole processing task.
MAX_RETRY_AFTER = 120

# 429 means we are being rate limited; 5xx are provider-side failures. Both
# tend to clear up within a minute, which is what bursts of episodes hit.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# DeepInfra holds a flex request for up to this long waiting for capacity,
# then answers 429 (retried above). The read timeout has to cover that wait
# on top of the time to generate.
FLEX_QUEUE_WAIT = 600


def _apply_service_tier(data):
    """Add service_tier to the request and return the read timeout to use."""
    if config.LLM_SERVICE_TIER == "flex":
        data = {**data, "service_tier": "flex"}
        return data, settings.LLM_TIMEOUT + FLEX_QUEUE_WAIT
    return data, settings.LLM_TIMEOUT


class EmptyCompletion(Exception):
    """The provider answered 200 but the message content was empty."""


def _retry_delay(attempt, response):
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), MAX_RETRY_AFTER)
            except ValueError:
                pass
    return RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]


def post_chat_completion(data, label="LLM request"):
    """
    POST a chat completion to LLM_API_URL and return the raw message content.

    Retries connection errors, rate limits (429), 5xx responses and empty
    completions. A read timeout is not retried: with LLM_TIMEOUT at several
    minutes, retrying it could run the processing task past its time limit.

    Raises the last requests error if every attempt fails, so callers keep
    their existing error handling. Malformed responses (KeyError/IndexError)
    are not retried.
    """
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    data, timeout = _apply_service_tier(data)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = None
        try:
            response = requests.post(
                settings.LLM_API_URL,
                headers=headers,
                json=data,
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not (content or "").strip() and attempt < MAX_ATTEMPTS:
                raise EmptyCompletion("LLM returned an empty completion")
            # On the last attempt an empty completion is handed back as-is;
            # callers already treat it as "no content".
            return content or ""
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            EmptyCompletion,
        ) as e:
            # ConnectTimeout is a ConnectionError and is retried; ReadTimeout is not.
            if isinstance(e, requests.exceptions.HTTPError):
                status = e.response.status_code if e.response is not None else None
                if status not in RETRYABLE_STATUS:
                    raise
            if attempt == MAX_ATTEMPTS:
                raise
            delay = _retry_delay(attempt, response)
            logger.warning(
                f"{label} failed (attempt {attempt}/{MAX_ATTEMPTS}): {e}; "
                f"retrying in {delay:.0f}s"
            )
            time.sleep(delay)
