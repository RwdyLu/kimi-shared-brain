#!/usr/bin/env python3
"""
Auto Task Checker for second_bot
檢查並執行指派給 second_bot / kimiclaw_bot 的任務
"""
import json
import subprocess
import os
from datetime import datetime

REPO_DIR = '/root/.openclaw/workspace/kimi-shared-brain'


def load_tasks():
    """從 tasks.json 與 state/tasks.json 載入所有任務"""
    all_tasks = []
    
    # 根目錄 tasks.json
    root_path = os.path.join(REPO_DIR, 'tasks.json')
    try:
        with open(root_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            tasks = data.get('tasks', []) if isinstance(data, dict) else data
            for t in tasks:
                t['_source'] = root_path
                t['_is_list'] = not isinstance(data, dict)
                all_tasks.append(t)
    except Exception as e:
        print(f"⚠️ 無法讀取 tasks.json: {e}")
    
    # state/tasks.json
    state_path = os.path.join(REPO_DIR, 'state', 'tasks.json')
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            tasks = data.get('tasks', []) if isinstance(data, dict) else data
            for t in tasks:
                t['_source'] = state_path
                t['_is_list'] = not isinstance(data, dict)
                all_tasks.append(t)
    except Exception as e:
        print(f"⚠️ 無法讀取 state/tasks.json: {e}")
    
    return all_tasks


def is_task_for_me(task):
    """檢查任務是否指派給本 bot（向下兼容 kimiclaw_bot）"""
    status = task.get('status', '')
    target = task.get('target', '')
    assigned_to = task.get('assigned_to', '')
    
    # 狀態必須是 pending 或 assigned
    if status not in ('pending', 'assigned'):
        return False
    
    # target 或 assigned_to 匹配
    valid_names = ('second', 'second_bot', 'kimiclaw_bot')
    if target in valid_names or assigned_to in valid_names:
        return True
    
    return False


def execute_task(task):
    """執行任務命令"""
    command = task.get('command')
    tid = task.get('id') or task.get('task_id', 'unknown')
    
    if not command:
        print(f"ℹ️ 任務 {tid} 無 command，標記為完成")
        return True
    
    print(f"🚀 執行: {command}")
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"✅ 執行成功")
            if result.stdout.strip():
                print(f"輸出: {result.stdout.strip()[:200]}")
            return True
        else:
            print(f"❌ 執行失敗: {result.stderr.strip()[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️ 執行超時 (60s)")
        return False
    except Exception as e:
        print(f"❌ 執行異常: {e}")
        return False


def save_task_status(task, new_status='done'):
    """更新任務狀態並寫回來源檔案"""
    source = task.get('_source')
    if not source or not os.path.exists(source):
        print(f"⚠️ 找不到來源檔案，無法儲存狀態")
        return False
    
    try:
        with open(source, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        is_list_format = task.get('_is_list', False)
        tasks = data if is_list_format else data.get('tasks', [])
        
        task_id = task.get('id') or task.get('task_id')
        found = False
        for t in tasks:
            tid = t.get('id') or t.get('task_id')
            if tid == task_id:
                t['status'] = new_status
                t['completed_at'] = datetime.now().isoformat()
                if 'last_updated' in t:
                    t['last_updated'] = datetime.now().isoformat()
                found = True
                break
        
        if not found:
            print(f"⚠️ 在來源檔案中找不到任務 {task_id}")
            return False
        
        # 寫回
        with open(source, 'w', encoding='utf-8') as f:
            if is_list_format:
                json.dump(tasks, f, indent=2, ensure_ascii=False)
            else:
                data['tasks'] = tasks
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"❌ 儲存狀態失敗: {e}")
        return False


def git_push():
    """git add / commit / push"""
    try:
        # add
        subprocess.run(['git', 'add', '.'], cwd=REPO_DIR, capture_output=True)
        
        # commit（允許無變更時不報錯）
        result = subprocess.run(
            ['git', 'commit', '-m', 'fix: task checker now matches pending tasks with target=second'],
            cwd=REPO_DIR, capture_output=True, text=True
        )
        if result.returncode != 0 and 'nothing to commit' not in result.stdout:
            print(f"⚠️ Commit 提示: {result.stdout.strip()}")
        
        # push
        result = subprocess.run(
            ['git', 'push', 'origin', 'main'],
            cwd=REPO_DIR, capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ 已 push 到 GitHub")
            return True
        else:
            print(f"⚠️ Push 輸出: {result.stdout.strip()}")
            print(f"⚠️ Push 錯誤: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ Git push 失敗: {e}")
        return False


def main():
    print("=" * 50)
    print("Auto Task Checker / second_bot")
    print("=" * 50)
    
    # 先 pull 最新
    subprocess.run(['git', 'pull', 'origin', 'main'], cwd=REPO_DIR, capture_output=True)
    
    tasks = load_tasks()
    my_tasks = [t for t in tasks if is_task_for_me(t)]
    
    if not my_tasks:
        print("✅ 沒有指派給我的任務")
        return False
    
    print(f"🔔 找到 {len(my_tasks)} 個任務:")
    
    executed_count = 0
    for task in my_tasks:
        tid = task.get('id') or task.get('task_id', 'unknown')
        title = task.get('title', task.get('command', 'N/A'))
        print(f"\n📋 {tid} | {title}")
        print("-" * 40)
        
        success = execute_task(task)
        if success:
            if save_task_status(task, 'done'):
                print(f"✅ {tid} → done")
                executed_count += 1
            else:
                print(f"⚠️ {tid} 執行了但狀態未儲存")
        else:
            print(f"❌ {tid} 執行失敗，保持原狀態")
    
    # 如果有執行成功的任務，push 變更
    if executed_count > 0:
        print(f"\n🔄 Push {executed_count} 個完成任務到 GitHub...")
        git_push()
    
    return executed_count > 0


if __name__ == '__main__':
    main()
