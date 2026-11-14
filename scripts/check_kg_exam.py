#!/usr/bin/env python3
"""离线检查 KG 测验配置；不读取 cookies、不联网、不提交答案。"""

from zhs.config import ConfigManager


def main() -> None:
    config = ConfigManager().load()
    print("KG 配置检查（离线，不调用 AI/题库/课程 API）")
    print(f"enable_kg_exam: {config.homework.enable_kg_exam}")
    print(f"掌握度阈值: {config.homework.kg_exam_threshold}%")
    print(f"最大重试: {config.homework.kg_exam_max_retries}")
    print(f"LLM 可用配置: {bool(config.ai.enabled and config.ai.api_key)}")
    print(f"KG 题库范围启用: {config.question_bank.enabled and 'zhidao_kg_exam' in config.question_bank.scopes}")
    print("没有有效答案会报告失败，不会使用默认选项。此检查不证明真实 API 可用。")


if __name__ == "__main__":
    main()
