#!/usr/bin/env python3
"""
Auto Task Checker for kimiclaw_bot
Run this script periodically to check for assigned tasks
"""
import json
import subprocess
import sys

def check_and_execute_tasks():
    """Check tasks.json for assigned tasks and print instructions"""
    try:
        # Pull latest changes
        subprocess.run(['git', 'pull', 'origin', 'main'], 
                      cwd='/root/.openclaw/workspace/kimi-shared-brain',
                      capture_output=True)
        
        with open('/root/.openclaw/workspace/kimi-shared-brain/state/tasks.json') as f:
            tasks = json.load(f)['tasks']
        
        # Find assigned tasks for kimiclaw_bot
        assigned = [t for t in tasks 
                   if t.get('status') == 'assigned' 
                   and t.get('assigned_to') == 'kimiclaw_bot']
        
        if assigned:
            print(f"🔔 Found {len(assigned)} assigned task(s):")
            for t in assigned:
                print(f"\nTask: {t['task_id']}")
                print(f"Title: {t['title']}")
                print(f"Priority: {t.get('priority', 'N/A')}")
                print(f"Output: {t.get('output_file', 'N/A')}")
                print(f"Goal: {t.get('goal', 'N/A')[:100]}...")
                print("\n" + "="*50)
            return True
        else:
            print("✅ No assigned tasks found")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == '__main__':
    check_and_execute_tasks()
