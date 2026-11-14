"""知到课程守护模式：持续运行直到习惯分课程结束

守护模式会：
1. 每天定时检查并刷习惯分课程（分天学习）
2. 今天的任务完成后，阻塞等待到第二天凌晨
3. 持续运行直到所有习惯分课程的截止日期
4. 所有习惯分课程结束后，刷无习惯分课程和 KG 测验
5. 全部完成后退出
"""

import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from zhs.config import AppConfig
    from zhs.session import ZhsSession


def run_daemon_mode(session: "ZhsSession", config: "AppConfig") -> None:
    """守护模式：持续运行直到所有习惯分课程结束
    
    工作流程：
    1. 获取所有习惯分课程，找到最晚的截止日期
    2. 每天刷习惯分课程（按学习计划）
    3. 今天的任务完成后，等待到明天凌晨继续
    4. 持续到所有习惯分课程结束
    5. 最后刷无习惯分课程和其他任务
    """
    from zhs.cli.services.play_service import run_all
    from zhs.utils.display import course_tag
    from zhs.zhidao.course import ZhidaoCourseManager
    from zhs.zhidao.schedule import end_date_from_ms

    zhidao_mgr = ZhidaoCourseManager(session)
    
    try:
        courses = zhidao_mgr.get_course_list()
    except Exception as e:
        logger.error(f"获取课程列表失败: {e}")
        print(f"获取课程列表失败: {e}")
        return

    # 找到有习惯分的课程
    from zhs.cli.services.play_service import _needs_daily_plan
    habbit_courses = [c for c in courses if _needs_daily_plan(zhidao_mgr, c, config)]
    
    if not habbit_courses:
        print("\n没有需要分天学习的课程，直接运行全刷模式")
        run_all(session, config)
        return

    # 找到最晚的截止日期
    end_dates = [end_date_from_ms(c.course_end_time) for c in habbit_courses if c.course_end_time]
    end_dates = [d for d in end_dates if d is not None]
    
    if not end_dates:
        print("\n习惯分课程没有截止日期，运行一次后退出")
        run_all(session, config)
        return
    
    latest_end = max(end_dates)
    today = datetime.now().date()
    
    print(f"\n{course_tag('daemon')} 守护模式启动")
    print(f"检测到 {len(habbit_courses)} 门需要分天学习的课程")
    print(f"最晚截止日期: {latest_end}")
    print(f"今天: {today}")
    print(f"还需运行 {(latest_end - today).days + 1} 天")
    print("\n按 Ctrl+C 可以随时退出守护模式\n")
    
    try:
        while today <= latest_end:
            print(f"\n{'='*60}")
            print(f"日期: {today} | 距离截止还有 {(latest_end - today).days + 1} 天")
            print(f"{'='*60}\n")
            
            # 只刷习惯分课程
            print(f"{course_tag('zhidao')} 开始今天的学习任务（习惯分课程）")
            run_all(session, config, course_type="zhidao")
            
            # 检查是否已经到达截止日期
            today = datetime.now().date()
            if today > latest_end:
                print(f"\n{course_tag('daemon')} 所有习惯分课程已结束")
                break
            
            # 计算到明天凌晨的等待时间
            tomorrow = today + timedelta(days=1)
            tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
            wait_seconds = (tomorrow_start - datetime.now()).total_seconds()
            
            if wait_seconds > 0:
                hours = int(wait_seconds // 3600)
                minutes = int((wait_seconds % 3600) // 60)
                print(f"\n{course_tag('daemon')} 今天的任务已完成")
                print(f"将在 {hours} 小时 {minutes} 分钟后（{tomorrow_start.strftime('%Y-%m-%d %H:%M:%S')}）继续")
                print("按 Ctrl+C 可以提前退出\n")
                
                try:
                    time.sleep(wait_seconds)
                except KeyboardInterrupt:
                    print(f"\n{course_tag('daemon')} 用户中断，退出守护模式")
                    return
            
            today = datetime.now().date()
        
        # 习惯分课程结束后，刷无习惯分课程和其他任务
        print(f"\n{course_tag('daemon')} 习惯分课程已全部完成，开始刷无习惯分课程")
        run_all(session, config)
        
        print(f"\n{course_tag('daemon')} 所有任务已完成，守护模式退出")
        
    except KeyboardInterrupt:
        print(f"\n{course_tag('daemon')} 用户中断，守护模式退出")
    except Exception as e:
        logger.error(f"守护模式运行出错: {e}")
        print(f"\n守护模式运行出错: {e}")
        raise
