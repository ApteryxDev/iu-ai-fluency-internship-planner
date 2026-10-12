"""Make an OpenAI research request when the user asks for suggestions."""

import json
import urllib.error
import urllib.request


class OpenAIResearchError(RuntimeError):
    pass


class OpenAIClient:
    ENDPOINT = 'https://api.openai.com/v1/responses'

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 240,
                 max_output_tokens: int = 12000):
        if not api_key:
            raise OpenAIResearchError('An OpenAI API key is required.')

        self._key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def research(self, prompt: str, domains: list[str] | None = None) -> dict:
        search_tool = {'type': 'web_search'}
        if domains:
            search_tool['filters'] = {'allowed_domains': domains}

        request_body = {
            'model': self.model,
            'input': prompt,
            'tools': [search_tool],
            'tool_choice': 'required',
            'store': False,
            'max_output_tokens': self.max_output_tokens,
        }
        request = urllib.request.Request(
            self.ENDPOINT,
            data=json.dumps(request_body).encode('utf-8'),
            headers={
                'Authorization': 'Bearer ' + self._key,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Avoid putting API keys or request headers into user-visible errors.
            raise OpenAIResearchError(
                f'OpenAI returned HTTP {error.code}. Check the API key, account billing, '
                'selected model, and tool permissions.'
            ) from None
        except (urllib.error.URLError, TimeoutError) as error:
            reason = getattr(error, 'reason', 'timeout')
            raise OpenAIResearchError(f'OpenAI connection failed: {reason}') from None
        except (ValueError, OSError):
            raise OpenAIResearchError('Could not read the OpenAI API response.') from None
