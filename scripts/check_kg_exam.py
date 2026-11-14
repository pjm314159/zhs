#!/usr/bin/env python3
"""测试知识图谱课章节测验功能

这个脚本会：
1. 检查配置是否启用
2. 检查是否有题库和 AI 配置
3. 模拟调用 kg_exam_start 看看是否有测验
"""

import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

from zhs.config import AppConfig, ConfigManager
from zhs.session import ZhsSession


def main() -> None:
    print("=== 知识图谱课章节测验功能检查 ===\n")
    
    # 1. 检查配置
    print("1. 检查配置...")
    config = AppConfig()
    print(f"   enable_kg_exam: {config.homework.enable_kg_exam}")
    print(f"   kg_exam_threshold: {config.homework.kg_exam_threshold}%")
    print(f"   kg_exam_max_retries: {config.homework.kg_exam_max_retries}")
    
    if not config.homework.enable_kg_exam:
        print("   ⚠️  章节测验已在配置中禁用")
    else:
        print("   ✅ 章节测验已启用")
    print()
    
    # 2. 检查 AI 配置
    print("2. 检查 AI 和题库配置...")
    print(f"   AI enabled: {config.ai.enabled}")
    print(f"   AI api_key: {'已配置' if config.ai.api_key else '未配置'}")
    print(f"   题库 enabled: {config.question_bank.enabled}")
    print(f"   题库 api_key: {'已配置' if config.question_bank.api_key else '未配置'}")
    
    if not config.ai.api_key and not config.question_bank.api_key:
        print("   ⚠️  AI 和题库都未配置，将使用默认策略（选第一个选项）")
    else:
        print("   ✅ 已配置答题工具")
    print()
    
    # 3. 检查登录状态
    print("3. 检查登录状态...")
    config_manager = ConfigManager()
    cookies = config_manager.load_cookies()
    
    if not cookies:
        print("   ❌ 未登录，请先运行 zhs login")
        return
    
    print("   ✅ 已登录")
    print()
    
    # 4. 测试 API
    print("4. 测试章节测验 API...")
    session = ZhsSession(config)
    session.cookies = cookies
    
    # 这里需要真实的 recruitId 和 knowledgeId
    # 可以从录制文件中获取
    print("   需要真实的课程数据才能测试")
    print("   请运行: uv run zhs play --all --debug")
    print("   查看日志中是否有：")
    print("     - '开始检查节点 XXX 的章节测验'")
    print("     - '检查节点 XXX 是否有章节测验'")
    print("     - '发现章节测验: N 题'")
    print()
    
    print("=== 检查完成 ===")
    print("\n如果运行时没有看到上述日志，可能的原因：")
    print("1. 你刷的课程不是知识图谱课（新版共享课）")
    print("2. 知识图谱课的节点没有章节测验")
    print("3. question_bank 或 homework_config 没有正确传递给播放器")
    print("\n建议：运行 'uv run zhs play --all --debug' 并查看日志")


if __name__ == "__main__":
    main()
