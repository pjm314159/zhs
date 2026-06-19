"""缓存迁移脚本：将旧格式 AI 作业缓存转为新格式

迁移内容：
1. key 去掉 _version 后缀（如 "1013704824_2" → "1013704824"）
2. 删除每个条目的 "version" 字段
3. 填空题 answer 中被错误转为 #@# 的还原为 /（如 "身体健康#@#心理健康" → "身体健康/心理健康"）
4. 将旧目录 aiexamAnswer 的内容合并到 cache/ai_homework_cache

填空题格式说明：
- questionType=3 的填空题，多个空的答案用 / 合并存储为单个字符串
- 缓存 answer 字段: "答案1/答案2"（一个字符串）
- 代码中 answers 列表: ["答案1/答案2"]（单元素列表）
- 选择题/多选题用 #@# 分隔选项 ID
"""

import json
import shutil
from pathlib import Path


def _is_fill_blank(value: dict) -> bool:
    """判断缓存条目是否为填空题"""
    qdict = value.get("questionDict")
    if isinstance(qdict, dict):
        return qdict.get("question_type") == 3 or qdict.get("questionType") == 3
    return False


def migrate_entry(key: str, value: dict) -> tuple[str, dict]:
    """迁移单个缓存条目，返回 (new_key, new_value)"""
    # 1. key 去掉 _version 后缀
    new_key = key.split("_")[0] if "_" in key else key

    # 2. 删除 version 字段
    if "version" in value:
        del value["version"]

    is_fill = _is_fill_blank(value)

    # 3. 填空题：answer 中 #@# 还原为 /（之前错误迁移的）
    #    非填空题：answer 中 / 转为 #@#（旧格式兼容）
    answer = value.get("answer", "")
    if answer:
        if is_fill:
            # 填空题：#@# → /（修复之前的错误迁移）
            if "#@#" in answer:
                value["answer"] = answer.replace("#@#", "/")
        else:
            # 非填空题：/ → #@#（旧格式兼容）
            if "#@#" not in answer and "/" in answer:
                value["answer"] = answer.replace("/", "#@#")

    answer_content = value.get("answer_content", "")
    if answer_content:
        if is_fill:
            if "#@#" in answer_content:
                value["answer_content"] = answer_content.replace("#@#", "/")
        else:
            if "#@#" not in answer_content and "/" in answer_content:
                value["answer_content"] = answer_content.replace("/", "#@#")

    # questionDict 中的 optionVos content 和 version
    qdict = value.get("questionDict")
    if isinstance(qdict, dict):
        if "version" in qdict:
            del qdict["version"]
        for opt in qdict.get("option_vos", []):
            content = opt.get("content", "")
            if not content:
                continue
            if is_fill:
                # 填空题 option content：#@# → /
                if "#@#" in content:
                    opt["content"] = content.replace("#@#", "/")
            elif "#@#" not in content and "/" in content:
                # 非填空题 option content：/ → #@#
                opt["content"] = content.replace("/", "#@#")

    return new_key, value


def migrate_json_file(file_path: Path) -> bool:
    """迁移单个 JSON 缓存文件，返回是否有变更"""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"  跳过（无法读取）: {file_path}")
        return False

    if not isinstance(data, dict):
        return False

    changed = False
    new_data: dict[str, dict] = {}

    for key, value in data.items():
        if not isinstance(value, dict):
            new_data[key] = value
            continue

        new_key, new_value = migrate_entry(key, value)

        if new_key != key:
            print(f"  key 迁移: {key} → {new_key}")
            changed = True

        if "version" in data[key] and isinstance(data[key], dict):
            print(f"  删除 version 字段: {new_key}")
            changed = True

        old_answer = data[key].get("answer", "") if isinstance(data[key], dict) else ""
        new_answer = new_value.get("answer", "")
        if old_answer != new_answer and isinstance(data[key], dict):
            is_fill = _is_fill_blank(data[key])
            action = "填空题 #@#→/" if is_fill else "非填空题 /→#@#"
            print(f"  answer 迁移 ({action}): {new_key}")
            changed = True

        # 如果 new_key 已存在（多个旧 key 迁移到同一个 new_key），保留后写入的
        new_data[new_key] = new_value

    if changed:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=4)
        print(f"  已更新: {file_path}")

    return changed


def migrate_aiexamanswer_to_cache(base_dir: Path) -> None:
    """将旧 aiexamAnswer 目录的内容合并到 cache/ai_homework_cache"""
    old_dir = base_dir / "aiexamAnswer"
    new_dir = base_dir / "cache" / "ai_homework_cache"

    if not old_dir.exists():
        print("旧目录 aiexamAnswer 不存在，跳过合并")
        return

    if not old_dir.is_dir():
        return

    print(f"\n合并旧目录: {old_dir} → {new_dir}")

    for course_dir in old_dir.iterdir():
        if not course_dir.is_dir():
            continue

        target_dir = new_dir / course_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)

        for json_file in course_dir.glob("*.json"):
            target_file = target_dir / json_file.name

            if target_file.exists():
                # 合并两个文件的内容
                print(f"  合并: {json_file.name} (课程 {course_dir.name})")
                try:
                    with open(json_file, encoding="utf-8") as f:
                        old_data = json.load(f)
                    with open(target_file, encoding="utf-8") as f:
                        new_data = json.load(f)

                    if isinstance(old_data, dict) and isinstance(new_data, dict):
                        migrated_old: dict[str, dict] = {}
                        for k, v in old_data.items():
                            if isinstance(v, dict):
                                mk, mv = migrate_entry(k, v)
                                migrated_old[mk] = mv
                            else:
                                migrated_old[k] = v

                        # 旧数据中不在新数据中的条目加入（新数据优先）
                        merged = {**migrated_old, **new_data}

                        with open(target_file, "w", encoding="utf-8") as f:
                            json.dump(merged, f, ensure_ascii=False, indent=4)
                        print(f"    合并完成，共 {len(merged)} 条")
                except (json.JSONDecodeError, OSError) as e:
                    print(f"    合并失败: {e}")
            else:
                # 直接复制并迁移
                print(f"  迁移: {json_file.name} (课程 {course_dir.name})")
                try:
                    with open(json_file, encoding="utf-8") as f:
                        data = json.load(f)

                    if isinstance(data, dict):
                        migrated: dict[str, dict] = {}
                        for k, v in data.items():
                            if isinstance(v, dict):
                                mk, mv = migrate_entry(k, v)
                                migrated[mk] = mv
                            else:
                                migrated[k] = v

                        with open(target_file, "w", encoding="utf-8") as f:
                            json.dump(migrated, f, ensure_ascii=False, indent=4)
                    else:
                        shutil.copy2(json_file, target_file)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"    迁移失败: {e}")

    # 迁移完成后删除旧目录
    print(f"\n删除旧目录: {old_dir}")
    shutil.rmtree(old_dir)
    print("  已删除")


def main() -> None:
    base_dir = Path(".zhs")
    if not base_dir.exists():
        print(f"数据目录不存在: {base_dir}")
        return

    # 1. 迁移 cache/ai_homework_cache 下的 JSON 文件
    cache_dir = base_dir / "cache" / "ai_homework_cache"
    if cache_dir.exists():
        print(f"=== 迁移 AI 作业缓存: {cache_dir} ===")
        total_files = 0
        migrated_files = 0
        for json_file in cache_dir.rglob("*.json"):
            total_files += 1
            if migrate_json_file(json_file):
                migrated_files += 1
        print(f"\n共扫描 {total_files} 个文件，迁移 {migrated_files} 个")
    else:
        print(f"缓存目录不存在: {cache_dir}")

    # 2. 合并旧 aiexamAnswer 目录到 cache/ai_homework_cache
    migrate_aiexamanswer_to_cache(base_dir)

    print("\n迁移完成!")


if __name__ == "__main__":
    main()
