module.exports = {
  apps: [
    {
      name: 'sf-scheduler',
      script: 'scripts/run_scheduler.py',
      interpreter: 'python3',
      cwd: '/root/.openclaw/workspace/kimi-shared-brain',
      env: { PYTHONPATH: '/root/.openclaw/workspace/kimi-shared-brain' },
      autorestart: true,
      max_restarts: 50,
      restart_delay: 5000,
      out_file: 'logs/scheduler_pm2.log',
      error_file: 'logs/scheduler_pm2_err.log'
    },
    {
      name: 'sf-dashboard',
      script: 'app.py',
      interpreter: 'python3',
      cwd: '/root/.openclaw/workspace/kimi-shared-brain/ui',
      autorestart: true,
      max_restarts: 50,
      restart_delay: 5000,
      out_file: 'dashboard_pm2.log',
      error_file: 'dashboard_pm2_err.log'
    }
  ]
}
