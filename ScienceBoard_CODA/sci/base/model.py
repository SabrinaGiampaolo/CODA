import sys
import string
import base64
import time
import requests
from requests import RequestException, Response
from dataclasses import dataclass, field
from io import BytesIO
import io
from typing import Optional, List, Dict
from typing import Literal, Any, ClassVar

from PIL import Image

import requests
from requests import Response
import os

sys.dont_write_bytecode = True
from . import utils
from .manager import OBS
from .override import *

ModelType = Literal["openai", "anthropic"]
RoleType = Literal["system", "user", "assistant"]


@dataclass
class Content:
    PLACEHOLDER: ClassVar[str] = "..."

    def _asdict(
        self,
        style: ModelType = "openai",
        hide_text: bool = False,
        hide_image: bool = False,
        **_
    ) -> Dict[str, Any]:
        return getattr(self, f"_{style}")(
            hide_text=hide_text,
            hide_image=hide_image
        )

    def __dict_factory_override__(self) -> Dict[str, Any]:
        return self._asdict()


@dataclass
class TextContent(Content):
    text: str
    args: Dict[str, str] = field(default_factory=lambda: {})

    # overwrite Content._asdict()
    # asdict(TextContent(...)) will also be redirected here
    def _asdict(
        self,
        hide_text: bool = False,
        use_format: bool = False,
        **_
    ) -> Dict[str, Any]:
        text = self.text
        if use_format:
            formatter = string.Formatter()
            slots = [key for _, key, _, _ in formatter.parse(self.text) if key]

            args = {key: (
                self.args[key]
                if key in self.args and not hide_text
                else Content.PLACEHOLDER
            ) for key in slots}
            try:
                text = self.text.format(**args)
            except:
                test = self.text

        return {
            "type": "text",
            "text": text
        }


@dataclass
class ImageContent(Content):
    image: Image.Image

    @property
    def base64_png(self):
        self.image.save(buffered:=BytesIO(), format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    def _openai(self, hide_image: bool = False, **_) -> Dict[str, Any]:
        return {
            "type": "image_url",
            "image_url": {
                "url": (
                    Content.PLACEHOLDER if hide_image \
                        else f"data:image/png;base64,{self.base64_png}"
                ),
                "detail": "high"
            }
        }

    def _anthropic(self, hide_image: bool = False, **_) -> Dict[str, Any]:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": Content.PLACEHOLDER if hide_image else self.base64_png
            }
        }


@dataclass
class Message:
    # message's style follows model_style
    style: ModelType
    role: RoleType
    content: List[Content]
    context_window: Optional[int] = None

    def _asdict(
        self,
        show_context: bool = False,
        hide_text: bool = False,
        hide_image: bool = False
    ) -> Dict[str, Any]:
        result = {
            "role": self.role,
            "content": [
                content._asdict(
                    style=self.style,
                    hide_text=hide_text,
                    hide_image=hide_image,
                    use_format=self.role=="user"
                )
                for content in self.content
            ]
        }

        if show_context and self.context_window is not None:
            result["context_window"] = self.context_window
        return result

    def __dict_factory_override__(self) -> Dict[str, Any]:
        return self._asdict()


@dataclass
class Model:
    model_style: ModelType
    base_url: str
    model_name: str
    api_key: Optional[str] = None
    proxy: Optional[str] = None
    version: Optional[str] = None
    max_tokens: Optional[int] = 1500
    top_p: Optional[float] = 0.9
    temperature: Optional[float] = 1.0

    def message(
        self,
        role: Literal["system", "user", "assistant"],
        content: List[Content] = []
    ) -> Message:
        return Message(style=self.model_style, role=role, content=content)

    @property
    def proxies(self) -> Dict:
        return None if self.proxy is None else {
            "http": self.proxy,
            "https": self.proxy
        }

    def _request_openai(self, messages: Dict, timeout: int) -> Response:
        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "temperature": self.temperature
        }

        if os.getenv("TARS_DPO_NAME") == "ui-tars":
            image_data_url = messages[-1]['content'][0]['image_url']['url']
        else:
            image_data_url = messages[-1]['content'][1]['image_url']['url']
        header, encoded = image_data_url.split(',', 1)
        image_data = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(image_data))
        print("="*10, image.size)

        if self.max_tokens is None:  del payload["max_tokens"]
        if self.top_p is None:       del payload["top_p"]
        if self.temperature is None: del payload["temperature"]
        # import json
        # print("===== [DEBUG] Request Debug Info =====")
        # print(f"URL: {self.base_url}")
        # print("Headers:")
        # print(json.dumps(headers, indent=4))
        # print("Proxies:")
        # print(json.dumps(self.proxies, indent=4))
        # print("Payload:")
        # print(json.dumps(payload, indent=4))
        # print(f"Timeout: {timeout}")
        # print("======================================")
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                return requests.post(
                    self.base_url,
                    headers=headers,
                    proxies=self.proxies,
                    json=payload,
                    timeout=timeout
                )
            except RequestException as e:
                print(f"[Attempt {attempt}] Request failed: {e}")
                if attempt == max_retries:
                    raise  # 最后一次也失败了，就抛出异常
                time.sleep(2)  # 等待2秒后重试

    def _request_anthropic(self, messages: Dict, timeout: int) -> Response:
        assert self.api_key is not None
        assert self.version is not None
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
            "content-type": "application/json"
        }

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p
        }

        return requests.post(
            self.base_url,
            headers=headers,
            proxies=self.proxies,
            json=payload,
            timeout=timeout
        )

    def __call__(self, messages: Dict, timeout: int) -> Response:
        # import json
        # json.dump(messages, open('test_message.json', 'w'), indent=4)
        return getattr(self, f"_request_{self.model_style}")(messages, timeout)

    @staticmethod
    def _access_openai(response: Response) -> Message:
        message = response.json()["choices"][0]["message"]
        return Message(
            style="openai",
            role=message["role"],
            content=[TextContent(message["content"])]
        )

    @staticmethod
    def _access_anthropic(response: Response) -> Message:
        message = response.json()
        return Message(
            style="anthropic",
            role=message["role"],
            content=[TextContent(message["content"][0]["text"])]
        )

    @utils.error_factory(None)
    def access(self, response: Response, context_window: int) -> Message:
        message = getattr(Model, f"_access_{self.model_style}")(response)
        message.context_window = context_window
        return message
