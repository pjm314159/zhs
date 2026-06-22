"""cli/ 子包：CLI 编排层

将原 __main__.py 的三层职责分离：
- bootstrap.py：基础设施（日志、代理、配置加载、Cookie 恢复、登录）
- course_type.py：课程类型检测与 URL 解析
- services/：业务编排（play/homework/exam/fetch）

__main__.py 仅保留 typer 命令声明，通过 import 委托给本子包。
"""
