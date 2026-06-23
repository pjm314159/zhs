"""快速检查 initVideo API 返回数据"""
import json
import re
import httpx

video_id = 86989013  # videoSec=0 的视频
r = httpx.get(
    "https://newbase.zhihuishu.com/video/initVideo",
    params={
        "jsonpCallBack": "result",
        "videoID": str(video_id),
        "_": str(int(__import__("time").time() * 1000)),
    },
    timeout=30,
)
match = re.match(r"^result\((.*)\)$", r.text)
if match:
    data = json.loads(match.group(1))
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print(f"Raw response: {r.text[:500]}")
