// ─── 番茄钟悬浮窗渲染逻辑 ───────────────────────────────
// 独立外链脚本：生产模式 CSP script-src 'self' 禁止内联 <script>，
// 内联版本在打包后会被拦截导致悬浮窗冻结在 25:00。
(function () {
  'use strict'

  var phaseLabel = document.getElementById('phaseLabel')
  var dot = document.getElementById('dot')
  var timer = document.getElementById('timer')
  var taskName = document.getElementById('taskName')
  var pomoCount = document.getElementById('pomoCount')
  var distract = document.getElementById('distract')
  var progressFill = document.getElementById('progressFill')
  var closeBtn = document.getElementById('closeBtn')

  var latestData = { phase: 'idle', remaining: 0, totalSec: 0, task: '', duration: 25 }

  // 点击 × ：本次番茄内不再显示（主进程记录关闭意图，不会下一秒又弹回来）
  closeBtn.addEventListener('click', function (e) {
    e.stopPropagation()
    if (window.electronAPI && window.electronAPI.pomodoroWidgetHide) {
      window.electronAPI.pomodoroWidgetHide()
    }
  })

  // 点击倒计时：打开主界面专注页
  timer.addEventListener('click', function () {
    if (window.electronAPI && window.electronAPI.pomodoroWidgetClick) {
      window.electronAPI.pomodoroWidgetClick()
    }
  })

  var PHASE_META = {
    working: { label: '专注中', cls: 'working' },
    short_break: { label: '短休息', cls: 'break' },
    long_break: { label: '长休息', cls: 'long-break' },
    idle: { label: '空闲', cls: 'idle' }
  }

  function fmt(sec) {
    var m = Math.floor(sec / 60)
    var s = sec % 60
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0')
  }

  function render(data) {
    // 倒计时
    timer.textContent = fmt(Math.max(0, data.remaining))

    // 阶段标签 + 状态点 + 进度条配色
    var meta = PHASE_META[data.phase] || PHASE_META.idle
    phaseLabel.textContent = meta.label
    phaseLabel.className = 'phase-text ' + meta.cls
    dot.className = 'dot ' + meta.cls
    var fillCls = meta.cls === 'idle' ? 'working' : meta.cls
    progressFill.className = 'progress-fill ' + fillCls

    // 进度条：totalSec 由主界面按阶段完整时长下发
    var pct = data.totalSec > 0 ? ((data.totalSec - data.remaining) / data.totalSec * 100) : 0
    progressFill.style.width = Math.min(100, Math.max(0, pct)) + '%'

    // 任务名
    taskName.textContent = data.task || '未命名任务'

    // 番茄进度：已完成 / 计划总数
    if (typeof data.completed === 'number' && typeof data.total === 'number') {
      pomoCount.textContent = '🍅 ' + data.completed + '/' + data.total
      pomoCount.hidden = false
    } else {
      pomoCount.hidden = true
    }

    // 分心计数：大于 0 才显示
    if (typeof data.distractions === 'number' && data.distractions > 0) {
      distract.textContent = '分心 ' + data.distractions
      distract.hidden = false
    } else {
      distract.hidden = true
    }
  }

  // 接收主进程转发的计时数据（主界面每秒同步一次）
  if (window.electronAPI && window.electronAPI.onPomodoroTick) {
    window.electronAPI.onPomodoroTick(function (data) {
      latestData = data
      render(data)
    })
  }

  // 本地每秒递减兜底：IPC 抖动时保持走动；主进程 tick 每秒覆盖权威值，不会累积漂移
  setInterval(function () {
    if (latestData.phase === 'idle' || latestData.remaining <= 0) return
    latestData.remaining -= 1
    render(latestData)
  }, 1000)
})()
