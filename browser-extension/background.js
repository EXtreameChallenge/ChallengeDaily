/* ChallengeDaily Web Tracker — Service Worker (Manifest V3)
 *
 * 核心追踪逻辑：
 *  - 监听标签页切换 / URL 变化 / 窗口焦点 / 系统空闲 / 页面可见性
 *  - 每次打断事件时结束当前会话（计算停留时长），推入待发送队列
 *  - 恢复事件时为新活跃标签页开启新会话
 *  - 每 30 秒或累计 10 条时批量发送到后端
 *  - 网络不可用时缓存到 chrome.storage.local，恢复后重发
 *
 * Service Worker 会被浏览器随时回收，因此：
 *  - 不依赖 setInterval（用 chrome.alarms）
 *  - 关键状态持久化到 chrome.storage.local
 */

const DEFAULT_SETTINGS = {
  backendUrl: 'http://127.0.0.1:59300',
  apiToken: '',
  trackingEnabled: true,
  flushIntervalSec: 30,
  flushBatchSize: 10,
  idleThresholdSec: 60,
  excludeDomains: ['127.0.0.1', 'localhost', 'chrome.com', 'newtab'],
  customRules: {} // { "domain关键字": "分类" }
};

const STORAGE_KEYS = {
  SETTINGS: 'settings',
  CURRENT: 'currentSession',
  QUEUE: 'pendingQueue',
  OFFLINE: 'offlineCache',
  STATUS: 'connStatus', // 'connected' | 'disconnected' | 'error'
  TODAY_CACHE: 'todayCache' // {date, total_sec, top_domains}
};

// 默认域名分类规则
const DEFAULT_CATEGORY_RULES = [
  [['github.com', 'gitlab.com', 'gitee.com', 'bitbucket.org'], '开发'],
  [['stackoverflow.com', 'stackexchange.com', 'leetcode.com', 'coursera.org', 'mooc'], '学习'],
  [['gmail.com', 'outlook.com', 'mail.google.com', 'mail.qq.com', 'feishu.cn'], '沟通'],
  [['notion.so', 'notion.com', 'docs.google.com', 'yuque.com', 'mubu.com'], '文档'],
  [['youtube.com', 'bilibili.com', 'netflix.com', 'youku.com', 'iqiyi.com'], '娱乐']
];

// ── 内存状态（SW 存活期间有效；被回收后从 storage 恢复）──
let settings = { ...DEFAULT_SETTINGS };
let currentSession = null; // {tabId, url, domain, title, category, startTime}
let pendingQueue = [];     // 待发送的已完成记录
let isFlushing = false;    // 防止并发 flush
let lastConnStatus = 'disconnected';

// ── 工具函数 ──

function getDomain(url) {
  if (!url) return '';
  try {
    const u = new URL(url);
    return u.hostname || '';
  } catch (e) {
    return '';
  }
}

function classify(domain, url) {
  const d = (domain || '').toLowerCase();
  const u = (url || '').toLowerCase();
  // 优先用户自定义规则
  const rules = settings.customRules || {};
  for (const [key, cat] of Object.entries(rules)) {
    if (key && (d.includes(key.toLowerCase()) || u.includes(key.toLowerCase()))) {
      return cat;
    }
  }
  for (const [keys, cat] of DEFAULT_CATEGORY_RULES) {
    for (const k of keys) {
      if (d.includes(k) || u.includes(k)) return cat;
    }
  }
  return '其他';
}

function isExcluded(domain, url) {
  const d = (domain || '').toLowerCase();
  const excludes = settings.excludeDomains || [];
  for (const ex of excludes) {
    if (!ex) continue;
    const exl = ex.toLowerCase();
    if (d === exl || d.endsWith('.' + exl) || d.includes(exl)) return true;
  }
  // chrome:// / edge:// / about: 等内部页
  if (url && /^(chrome|edge|about|chrome-extension|moz-extension):/i.test(url)) return true;
  return false;
}

function nowISO() {
  // 本地时间 ISO 格式（无时区后缀），与后端 fromisoformat 兼容
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get([STORAGE_KEYS.SETTINGS], (res) => {
      settings = { ...DEFAULT_SETTINGS, ...(res[STORAGE_KEYS.SETTINGS] || {}) };
      resolve(settings);
    });
  });
}

function persistCurrent() {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_KEYS.CURRENT]: currentSession }, () => resolve());
  });
}

function loadPersistedState() {
  return new Promise((resolve) => {
    chrome.storage.local.get(
      [STORAGE_KEYS.CURRENT, STORAGE_KEYS.QUEUE, STORAGE_KEYS.OFFLINE, STORAGE_KEYS.STATUS],
      (res) => {
        currentSession = res[STORAGE_KEYS.CURRENT] || null;
        pendingQueue = res[STORAGE_KEYS.QUEUE] || [];
        // 启动时把离线缓存并入待发送队列
        const offline = res[STORAGE_KEYS.OFFLINE] || [];
        if (offline.length) {
          pendingQueue = pendingQueue.concat(offline);
          chrome.storage.local.remove([STORAGE_KEYS.OFFLINE]);
        }
        lastConnStatus = res[STORAGE_KEYS.STATUS] || 'disconnected';
        resolve();
      }
    );
  });
}

function persistQueue() {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_KEYS.QUEUE]: pendingQueue }, () => resolve());
  });
}

function setConnStatus(status) {
  lastConnStatus = status;
  chrome.storage.local.set({ [STORAGE_KEYS.STATUS]: status });
}

// ── 会话管理 ──

/**
 * 结束当前会话：计算停留时长，推入待发送队列。
 * 幂等：无活动会话时直接返回。
 */
function endSession() {
  if (!currentSession) return;
  const now = Date.now();
  const durationSec = Math.max(0, Math.round((now - currentSession.startTime) / 1000));
  // 时长过短（<2s）的忽略，避免噪音
  if (durationSec >= 2) {
    pendingQueue.push({
      url: currentSession.url,
      domain: currentSession.domain,
      title: currentSession.title,
      start_time: currentSession.startISO,
      duration_sec: durationSec,
      tab_id: currentSession.tabId,
      category: currentSession.category
    });
    persistQueue();
  }
  currentSession = null;
  persistCurrent();
  // 达到批量阈值立即发送
  if (pendingQueue.length >= (settings.flushBatchSize || 10)) {
    flushQueue();
  }
}

/**
 * 为指定标签页开启新会话。
 */
function startSession(tabId, url, title) {
  if (!settings.trackingEnabled) {
    currentSession = null;
    persistCurrent();
    return;
  }
  const domain = getDomain(url);
  if (!domain || isExcluded(domain, url)) {
    currentSession = null;
    persistCurrent();
    return;
  }
  currentSession = {
    tabId,
    url,
    domain,
    title: title || '',
    category: classify(domain, url),
    startTime: Date.now(),
    startISO: nowISO()
  };
  persistCurrent();
}

/**
 * 切换到新活跃标签页：先结束旧会话，再查询新标签页信息并开启新会话。
 */
function switchToTab(tabId) {
  endSession();
  if (tabId == null || tabId < 0) {
    // 窗口失焦等场景，无活跃标签页
    currentSession = null;
    persistCurrent();
    return;
  }
  chrome.tabs.get(tabId, (tab) => {
    if (chrome.runtime.lastError || !tab) {
      currentSession = null;
      persistCurrent();
      return;
    }
    // 仅追踪正常标签页且窗口处于聚焦状态
    startSession(tab.id, tab.url, tab.title);
  });
}

// ── 网络发送 ──

function buildHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (settings.apiToken) {
    headers['Authorization'] = 'Bearer ' + settings.apiToken;
  }
  return headers;
}

/**
 * 批量发送待发送队列到后端。
 * 成功则清空队列；失败则把记录写入 offlineCache 以便稍后重发。
 * 网络请求失败绝不阻塞浏览器（异步、带超时）。
 */
function flushQueue() {
  if (isFlushing) return;
  if (pendingQueue.length === 0) {
    // 队列空也尝试重发离线缓存（如果有）
    return;
  }
  isFlushing = true;
  const batch = pendingQueue.slice();
  const baseUrl = (settings.backendUrl || '').replace(/\/+$/, '');
  const endpoint = baseUrl + '/api/web-activity/batch';
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);

  fetch(endpoint, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify({ activities: batch }),
    signal: controller.signal
  })
    .then((resp) => {
      clearTimeout(timeoutId);
      if (resp.ok) {
        // 发送成功，从队列移除已发送的
        pendingQueue = pendingQueue.slice(batch.length);
        persistQueue();
        setConnStatus('connected');
        // 若仍有积压，继续发送
        if (pendingQueue.length > 0) {
          isFlushing = false;
          flushQueue();
          return;
        }
      } else {
        // HTTP 错误（非 2xx）
        setConnStatus('error');
        cacheOffline(batch);
      }
    })
    .catch((err) => {
      clearTimeout(timeoutId);
      // 网络错误 / 超时 / 后端未启动 → 离线缓存
      setConnStatus('disconnected');
      cacheOffline(batch);
    })
    .finally(() => {
      isFlushing = false;
    });
}

/**
 * 把发送失败的记录写入 offlineCache（合并已有缓存，并限制总量避免无限增长）。
 */
function cacheOffline(records) {
  chrome.storage.local.get([STORAGE_KEYS.OFFLINE], (res) => {
    let offline = res[STORAGE_KEYS.OFFLINE] || [];
    offline = offline.concat(records);
    // 限制离线缓存上限 1000 条，超出则丢弃最早的
    if (offline.length > 1000) {
      offline = offline.slice(offline.length - 1000);
    }
    chrome.storage.local.set({ [STORAGE_KEYS.OFFLINE]: offline }, () => {
      // 离线缓存中的记录也从 pendingQueue 移除（已转入 offline）
      pendingQueue = pendingQueue.slice(records.length);
      persistQueue();
    });
  });
}

// ── 事件监听 ──

// 标签页激活（用户切换标签）
chrome.tabs.onActivated.addListener((activeInfo) => {
  if (!settings.trackingEnabled) return;
  switchToTab(activeInfo.tabId);
});

// 标签页更新（URL 变化 / 标题变化 / 加载完成）
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!settings.trackingEnabled) return;
  // 仅当 URL 变化或页面加载完成，且该标签为当前活跃标签时才处理
  if (!tab || !tab.active) return;
  if (changeInfo.url || changeInfo.status === 'complete') {
    // URL 变化或加载完成 → 视为新页面，结束旧会话开启新会话
    endSession();
    startSession(tab.id, tab.url, tab.title);
  } else if (changeInfo.title && currentSession && currentSession.tabId === tabId) {
    // 仅标题变化，更新标题不重置计时
    currentSession.title = changeInfo.title;
    persistCurrent();
  }
});

// 窗口焦点变化（切换浏览器窗口 / 离开浏览器）
chrome.windows.onFocusChanged.addListener((windowId) => {
  if (!settings.trackingEnabled) return;
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    // 所有窗口失焦 → 结束当前会话
    endSession();
  } else {
    // 焦点切到某窗口 → 查询该窗口的活跃标签
    chrome.tabs.query({ active: true, windowId }, (tabs) => {
      if (tabs && tabs.length > 0) {
        endSession();
        startSession(tabs[0].id, tabs[0].url, tabs[0].title);
      } else {
        endSession();
      }
    });
  }
});

// 系统空闲状态变化（AFK 检测）
chrome.idle.onStateChanged.addListener((newState) => {
  // newState: 'active' | 'idle' | 'locked'
  if (newState === 'active') {
    // 用户回来 → 为当前活跃标签页开启新会话
    if (!settings.trackingEnabled) return;
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs && tabs.length > 0) {
        startSession(tabs[0].id, tabs[0].url, tabs[0].title);
      }
    });
  } else {
    // idle 或 locked → 结束当前会话（停止计时）
    endSession();
  }
});

// 来自 content.js 的页面可见性消息
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== 'VISIBILITY') return;
  const tabId = sender.tab ? sender.tab.id : null;
  if (msg.visible) {
    // 页面变为可见：若它是当前活跃标签且无活动会话，则开启新会话
    if (settings.trackingEnabled && !currentSession && tabId != null) {
      chrome.tabs.get(tabId, (tab) => {
        if (chrome.runtime.lastError || !tab || !tab.active) return;
        startSession(tab.id, tab.url, tab.title);
      });
    }
  } else {
    // 页面隐藏：若是当前活跃会话则结束
    if (currentSession && currentSession.tabId === tabId) {
      endSession();
    }
  }
  sendResponse({ ok: true });
});

// 定时 flush（每 flushIntervalSec 秒）
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'cd-flush') {
    // 先尝试重发离线缓存
    retryOfflineThenFlush();
  }
});

function retryOfflineThenFlush() {
  chrome.storage.local.get([STORAGE_KEYS.OFFLINE], (res) => {
    const offline = res[STORAGE_KEYS.OFFLINE] || [];
    if (offline.length > 0) {
      // 把离线缓存并回 pendingQueue 一起发送
      pendingQueue = offline.concat(pendingQueue);
      chrome.storage.local.remove([STORAGE_KEYS.OFFLINE], () => {
        persistQueue().then(() => flushQueue());
      });
    } else {
      flushQueue();
    }
  });
}

// ── 初始化 ──

function setupAlarm() {
  const period = Math.max(10, settings.flushIntervalSec || 30);
  chrome.alarms.get('cd-flush', (existing) => {
    if (!existing) {
      chrome.alarms.create('cd-flush', { periodInMinutes: period / 60 });
    }
  });
}

function setupIdleDetection() {
  const threshold = Math.max(15, settings.idleThresholdSec || 60);
  chrome.idle.setDetectionInterval(threshold);
}

// SW 启动 / 安装 / 更新时执行
chrome.runtime.onInstalled.addListener(() => {
  init();
});
chrome.runtime.onStartup.addListener(() => {
  init();
});

// Service Worker 每次被唤醒时也会执行顶层代码，因此直接调用 init
init();

async function init() {
  await loadSettings();
  await loadPersistedState();
  setupAlarm();
  setupIdleDetection();
  // 启动时为当前活跃标签页开启会话
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs && tabs.length > 0) {
      startSession(tabs[0].id, tabs[0].url, tabs[0].title);
    }
  });
  // 启动时尝试发送积压数据
  setTimeout(() => retryOfflineThenFlush(), 2000);
}

// 监听设置变化（options 页保存后同步）
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return;
  if (changes[STORAGE_KEYS.SETTINGS]) {
    settings = { ...DEFAULT_SETTINGS, ...(changes[STORAGE_KEYS.SETTINGS].newValue || {}) };
    setupAlarm();
    setupIdleDetection();
  }
});
