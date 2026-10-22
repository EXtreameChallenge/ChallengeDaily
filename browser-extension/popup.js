/* ChallengeDaily Web Tracker — Popup 逻辑
 * 显示：连接状态 / 今日统计 / 当前活跃标签 / 启停开关 / 设置入口
 */
(function () {
  const DEFAULT_SETTINGS = {
    backendUrl: 'http://127.0.0.1:59300',
    apiToken: '',
    trackingEnabled: true
  };

  const STATUS_TEXT = {
    connected: '已连接',
    disconnected: '未连接',
    error: '错误'
  };

  function formatDuration(sec) {
    sec = Math.round(sec || 0);
    if (sec < 60) return sec + 's';
    if (sec < 3600) return Math.round(sec / 60) + ' 分钟';
    return (sec / 3600).toFixed(1) + ' 小时';
  }

  function loadSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['settings'], (res) => {
        resolve({ ...DEFAULT_SETTINGS, ...(res.settings || {}) });
      });
    });
  }

  function setStatus(status) {
    const el = document.getElementById('connStatus');
    el.textContent = STATUS_TEXT[status] || '未连接';
    el.className = 'status-badge ' + (status || 'disconnected');
  }

  async function refreshStats() {
    const settings = await loadSettings();
    const baseUrl = (settings.backendUrl || '').replace(/\/+$/, '');
    try {
      const resp = await fetch(baseUrl + '/api/web-activity/stats/today', {
        headers: settings.apiToken
          ? { Authorization: 'Bearer ' + settings.apiToken }
          : {}
      });
      if (resp.ok) {
        const data = await resp.json();
        setStatus('connected');
        renderStats(data);
      } else {
        setStatus('error');
      }
    } catch (e) {
      setStatus('disconnected');
    }
  }

  function renderStats(data) {
    document.getElementById('todayTotal').textContent =
      formatDuration(data.total_sec || 0);

    const list = document.getElementById('topList');
    const domains = data.top_domains || [];
    if (domains.length === 0) {
      list.innerHTML = '<li class="empty">暂无数据</li>';
      return;
    }
    const maxSec = Math.max(...domains.map((d) => d.duration_sec || 0), 1);
    list.innerHTML = domains
      .map((d) => {
        const pct = Math.round(((d.duration_sec || 0) / maxSec) * 100);
        return (
          '<li>' +
          '<span class="domain" title="' + escapeHtml(d.domain) + '">' + escapeHtml(d.domain) + '</span>' +
          '<span class="bar"><span class="bar-fill" style="width:' + pct + '%"></span></span>' +
          '<span class="duration">' + formatDuration(d.duration_sec) + '</span>' +
          '</li>'
        );
      })
      .join('');
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderCurrent(session) {
    if (!session) {
      document.getElementById('currentTitle').textContent = '（无活跃追踪）';
      document.getElementById('currentDomain').textContent = '—';
      document.getElementById('currentCategory').textContent = '—';
      document.getElementById('currentDuration').textContent = '0s';
      return;
    }
    document.getElementById('currentTitle').textContent = session.title || session.domain || '—';
    document.getElementById('currentDomain').textContent = session.domain || '—';
    document.getElementById('currentCategory').textContent = session.category || '其他';
    const dur = Math.round((Date.now() - (session.startTime || Date.now())) / 1000);
    document.getElementById('currentDuration').textContent = formatDuration(dur);
  }

  function renderPending(queueLen, offlineLen) {
    const info = document.getElementById('pendingInfo');
    info.textContent = '待发送：' + queueLen + ' 条' + (offlineLen ? '（离线缓存：' + offlineLen + '）' : '');
  }

  async function loadState() {
    chrome.storage.local.get(
      ['currentSession', 'connStatus', 'pendingQueue', 'offlineCache', 'settings'],
      (res) => {
        setStatus(res.connStatus || 'disconnected');
        renderCurrent(res.currentSession || null);
        renderPending(
          (res.pendingQueue || []).length,
          (res.offlineCache || []).length
        );
        const settings = { ...DEFAULT_SETTINGS, ...(res.settings || {}) };
        const toggle = document.getElementById('toggleTracking');
        toggle.checked = !!settings.trackingEnabled;
        document.getElementById('toggleLabel').textContent =
          settings.trackingEnabled ? '追踪中' : '已暂停';
      }
    );
  }

  // 启停开关
  document.getElementById('toggleTracking').addEventListener('change', (e) => {
    chrome.storage.local.get(['settings'], (res) => {
      const settings = { ...DEFAULT_SETTINGS, ...(res.settings || {}) };
      settings.trackingEnabled = e.target.checked;
      chrome.storage.local.set({ settings }, () => {
        document.getElementById('toggleLabel').textContent =
          settings.trackingEnabled ? '追踪中' : '已暂停';
      });
    });
  });

  // 设置按钮
  document.getElementById('openOptions').addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
  });

  // 初始化
  loadState();
  refreshStats();

  // 实时刷新当前标签计时
  setInterval(loadState, 3000);
  // 每 15 秒刷新统计
  setInterval(refreshStats, 15000);
})();
