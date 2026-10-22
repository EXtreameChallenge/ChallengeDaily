/* ChallengeDaily Web Tracker — 设置页逻辑
 * 后端地址 / API Token / 追踪精度 / 域名排除 / 自定义分类 / 数据导出
 */
(function () {
  const DEFAULT_SETTINGS = {
    backendUrl: 'http://127.0.0.1:59300',
    apiToken: '',
    trackingEnabled: true,
    flushIntervalSec: 30,
    flushBatchSize: 10,
    idleThresholdSec: 60,
    excludeDomains: ['127.0.0.1', 'localhost', 'chrome.com', 'newtab'],
    customRules: {}
  };

  function showToast(msg, isError) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = 'toast show' + (isError ? ' error' : '');
    setTimeout(() => {
      toast.className = 'toast' + (isError ? ' error' : '');
    }, 2200);
  }

  function loadSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['settings'], (res) => {
        resolve({ ...DEFAULT_SETTINGS, ...(res.settings || {}) });
      });
    });
  }

  function renderForm(settings) {
    document.getElementById('backendUrl').value = settings.backendUrl || '';
    document.getElementById('apiToken').value = settings.apiToken || '';
    document.getElementById('flushInterval').value = String(settings.flushIntervalSec || 30);
    document.getElementById('idleThreshold').value = String(settings.idleThresholdSec || 60);
    const excludes = Array.isArray(settings.excludeDomains) ? settings.excludeDomains : [];
    document.getElementById('excludeDomains').value = excludes.join('\n');
    let rulesText = '';
    try {
      rulesText = settings.customRules && Object.keys(settings.customRules).length
        ? JSON.stringify(settings.customRules, null, 2)
        : '';
    } catch (e) {
      rulesText = '';
    }
    document.getElementById('customRules').value = rulesText;
  }

  function collectSettings() {
    const backendUrl = (document.getElementById('backendUrl').value || '').trim() || DEFAULT_SETTINGS.backendUrl;
    const apiToken = document.getElementById('apiToken').value || '';
    const flushIntervalSec = parseInt(document.getElementById('flushInterval').value, 10) || 30;
    const idleThresholdSec = parseInt(document.getElementById('idleThreshold').value, 10) || 60;
    const excludeRaw = document.getElementById('excludeDomains').value || '';
    const excludeDomains = excludeRaw
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

    let customRules = {};
    const rulesText = (document.getElementById('customRules').value || '').trim();
    if (rulesText) {
      try {
        const parsed = JSON.parse(rulesText);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          customRules = parsed;
        } else {
          throw new Error('规则需为 JSON 对象');
        }
      } catch (e) {
        throw new Error('自定义分类规则 JSON 解析失败：' + e.message);
      }
    }

    return {
      backendUrl,
      apiToken,
      trackingEnabled: true, // 保留原值在保存时合并
      flushIntervalSec,
      flushBatchSize: 10,
      idleThresholdSec,
      excludeDomains,
      customRules
    };
  }

  function saveSettings() {
    let newSettings;
    try {
      newSettings = collectSettings();
    } catch (e) {
      showToast(e.message, true);
      return;
    }
    // 保留 trackingEnabled 原值
    chrome.storage.local.get(['settings'], (res) => {
      const prev = { ...DEFAULT_SETTINGS, ...(res.settings || {}) };
      newSettings.trackingEnabled = prev.trackingEnabled;
      chrome.storage.local.set({ settings: newSettings }, () => {
        showToast('设置已保存');
      });
    });
  }

  async function testConnection() {
    const result = document.getElementById('testResult');
    result.textContent = '测试中...';
    result.style.color = 'var(--muted)';
    let backendUrl, apiToken;
    try {
      const s = collectSettings();
      backendUrl = s.backendUrl;
      apiToken = s.apiToken;
    } catch (e) {
      result.textContent = e.message;
      result.style.color = '#ef4444';
      return;
    }
    const baseUrl = backendUrl.replace(/\/+$/, '');
    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort(), 5000);
    try {
      const resp = await fetch(baseUrl + '/api/web-activity/stats/today', {
        headers: apiToken ? { Authorization: 'Bearer ' + apiToken } : {},
        signal: controller.signal
      });
      clearTimeout(tid);
      if (resp.ok) {
        result.textContent = '✓ 连接成功';
        result.style.color = '#22c55e';
      } else if (resp.status === 401) {
        result.textContent = '✗ Token 无效 (401)';
        result.style.color = '#ef4444';
      } else {
        result.textContent = '✗ HTTP ' + resp.status;
        result.style.color = '#ef4444';
      }
    } catch (e) {
      clearTimeout(tid);
      result.textContent = '✗ 无法连接：' + (e.message || '网络错误');
      result.style.color = '#ef4444';
    }
  }

  function exportData() {
    chrome.storage.local.get(null, (all) => {
      const blob = new Blob([JSON.stringify(all, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'challengedaily-web-tracker-cache-' + new Date().toISOString().slice(0, 10) + '.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('已导出缓存数据');
    });
  }

  function clearData() {
    if (!confirm('确认清空本地缓存（待发送队列 + 离线缓存）？此操作不可撤销。')) return;
    chrome.storage.local.remove(['pendingQueue', 'offlineCache', 'currentSession'], () => {
      showToast('本地缓存已清空');
    });
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const settings = await loadSettings();
    renderForm(settings);
  });

  document.getElementById('save').addEventListener('click', saveSettings);
  document.getElementById('testConn').addEventListener('click', testConnection);
  document.getElementById('exportData').addEventListener('click', exportData);
  document.getElementById('clearData').addEventListener('click', clearData);
})();
