"""验证码求解编排。

对外只有一个入口 ``CaptchaService.solve()``：成功返回 ``CaptchaSolution``，
任何失败都返回 ``None``，由调用方按原有逻辑回落。
"""

from dataclasses import dataclass
from io import BytesIO

import httpx
from loguru import logger
from PIL import Image

from zhs.captcha import click, slider, vision, yidun
from zhs.captcha import fp as fp_tool
from zhs.captcha.models import CaptchaChallenge, CaptchaKind, CaptchaSolution
from zhs.config import AppConfig

SLIDE_WIDTH = 400
CLICK_WIDTH = 320
SLIDE_TYPE = 2
CLICK_TYPE = 11


@dataclass(frozen=True)
class CaptchaTrigger:
    """一次求解决定的题型与来源页。"""

    kind: CaptchaKind
    referer: str

    @property
    def captcha_id(self) -> str:
        return yidun.CAPTCHA_CLICK if self.kind == "click" else yidun.CAPTCHA_SLIDE

    @property
    def width(self) -> int:
        return CLICK_WIDTH if self.kind == "click" else SLIDE_WIDTH

    @property
    def type_code(self) -> int:
        return CLICK_TYPE if self.kind == "click" else SLIDE_TYPE


class CaptchaService:
    """按配置执行一次取题 → 求解 → 校验。"""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._cfg = config.captcha

    def enabled(self) -> bool:
        """配置层面是否可用（不看运行时依赖）。"""
        return bool(self._cfg.enabled and fp_tool.normalize_fp(self._cfg.fp))

    def solve(self, trigger: CaptchaTrigger) -> CaptchaSolution | None:
        if not self._cfg.enabled:
            logger.debug("验证码求解未启用")
            return None

        fp_value = fp_tool.normalize_fp(self._cfg.fp)
        if not fp_value:
            logger.debug("验证码 fp 未配置，跳过求解")
            return None

        if trigger.kind == "slide" and not slider.available():
            logger.warning("OpenCV 不可用，跳过滑块求解")
            return None
        if trigger.kind == "click" and (not self._cfg.api_key or not self._cfg.model):
            logger.warning("验证码识图缺少 api_key 或 model，跳过点选求解")
            return None

        try:
            with yidun.create_client(self._config) as client:
                return self._solve_with_client(client, trigger, fp_value)
        except Exception as exc:  # 网络/解析异常一律回落
            logger.warning(f"验证码求解失败: {exc}")
            return None

    # ------------------------------------------------------------------ 内部

    def _solve_with_client(
        self,
        client: httpx.Client,
        trigger: CaptchaTrigger,
        fp_value: str,
    ) -> CaptchaSolution | None:
        conf = yidun.getconf(client, trigger.captcha_id, trigger.referer)
        dt = (conf.get("data") or {}).get("dt", "")

        for attempt in range(1, self._cfg.max_retry + 1):
            challenge = self._fetch(client, trigger, fp_value, dt)
            if challenge is None:
                continue

            data = self._build_data(client, trigger, challenge)
            if data is None:
                logger.warning(f"验证码求解失败（第 {attempt}/{self._cfg.max_retry} 次）")
                continue

            result = yidun.check(
                client,
                challenge.captcha_id,
                challenge.token,
                data,
                trigger.width,
                trigger.type_code,
                dt,
                trigger.referer,
            )
            payload = result.get("data") or {}
            if result.get("error") == 0 and payload.get("result") is True:
                raw = payload.get("validate", "")
                logger.debug(f"验证码通过，validate 长度={len(raw)}")
                return CaptchaSolution(validate=yidun.compose_validate(raw, fp_value), raw_validate=raw)

            logger.warning(
                f"验证码未通过（第 {attempt}/{self._cfg.max_retry} 次）: "
                f"error={result.get('error')} msg={result.get('msg')}"
            )
        return None

    def _fetch(
        self,
        client: httpx.Client,
        trigger: CaptchaTrigger,
        fp_value: str,
        dt: str,
    ) -> CaptchaChallenge | None:
        got = yidun.fetch(client, trigger.captcha_id, fp_value, trigger.width, dt, "", trigger.referer)
        if got.get("error") != 0:
            logger.warning(f"验证码取题失败: error={got.get('error')} msg={got.get('msg')}")
            return None

        payload = got.get("data") or {}
        bg = payload.get("bg")
        bg_url = bg[0] if isinstance(bg, list) and bg else (bg if isinstance(bg, str) else "")
        front = payload.get("front")
        if not payload.get("token") or not bg_url:
            logger.warning("验证码取题返回缺少 token 或背景图")
            return None
        return CaptchaChallenge(
            captcha_id=trigger.captcha_id,
            kind=trigger.kind,
            token=payload["token"],
            bg_url=bg_url,
            front=front if isinstance(front, (str, list)) else "",
            raw=payload,
        )

    def _build_data(
        self,
        client: httpx.Client,
        trigger: CaptchaTrigger,
        challenge: CaptchaChallenge,
    ) -> dict[str, object] | None:
        if trigger.kind == "slide":
            return self._build_slide_data(client, trigger, challenge)
        return self._build_click_data(client, trigger, challenge)

    def _build_slide_data(
        self,
        client: httpx.Client,
        trigger: CaptchaTrigger,
        challenge: CaptchaChallenge,
    ) -> dict[str, object] | None:
        front_url = challenge.front[0] if isinstance(challenge.front, list) and challenge.front else ""
        if not front_url:
            return None

        background_bytes = self._download(client, challenge.bg_url)
        front_bytes = self._download(client, front_url)
        self._save(challenge, background_bytes, front_bytes)

        import cv2
        import numpy as np

        background = cv2.imdecode(np.frombuffer(background_bytes, np.uint8), cv2.IMREAD_COLOR)
        front = cv2.imdecode(np.frombuffer(front_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
        if background is None or front is None:
            logger.warning("验证码图片解码失败")
            return None

        gap = slider.find_gap_x(background, front)
        distance = gap * trigger.width / background.shape[1]
        trace = slider.build_track(distance)
        return slider.build_data(challenge.token, trace, distance, trigger.width)

    def _build_click_data(
        self,
        client: httpx.Client,
        trigger: CaptchaTrigger,
        challenge: CaptchaChallenge,
    ) -> dict[str, object] | None:
        tips = challenge.front if isinstance(challenge.front, str) else ""
        if not tips:
            return None

        image = self._download(client, challenge.bg_url)
        self._save(challenge, image)

        options = vision.VisionOptions(
            api_key=self._cfg.api_key,
            base_url=self._cfg.base_url,
            model=self._cfg.model,
            timeout=self._cfg.timeout,
        )
        point = vision.click_point(options, image, tips)
        if point is None:
            return None

        with Image.open(BytesIO(image)) as img:
            image_width = img.size[0]
        x, y = click.to_css(point[0], point[1], image_width, trigger.width)
        logger.debug(f"点选坐标: 原图({point[0]:.0f},{point[1]:.0f}) -> css({x},{y})")
        return click.build_data(challenge.token, x, y)

    @staticmethod
    def _download(client: httpx.Client, url: str) -> bytes:
        response = client.get(url)
        response.raise_for_status()
        return response.content

    def _save(self, challenge: CaptchaChallenge, *images: bytes) -> None:
        """``save_challenge_dir`` 非空时落盘题目素材。"""
        directory = self._cfg.save_challenge_dir.strip()
        if not directory:
            return
        try:
            from pathlib import Path

            target = Path(directory).expanduser()
            target.mkdir(parents=True, exist_ok=True)
            for index, data in enumerate(images):
                (target / f"{challenge.token}_{index}.img").write_bytes(data)
            logger.info(f"验证码素材已保存到 {target}")
        except Exception as exc:
            logger.warning(f"验证码素材保存失败: {exc}")


__all__ = ["CLICK_WIDTH", "SLIDE_WIDTH", "CaptchaService", "CaptchaTrigger"]
