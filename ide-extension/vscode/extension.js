/**
 * ChallengeDaily Tracker — VS Code 扩展
 * 在状态栏显示今日专注时长与当前分类，提供快捷命令
 */
const vscode = require('vscode');
const http = require('http');
const url = require('url');

let statusBar;
let refreshTimer;
let outputChannel;

function activate(context) {
    outputChannel = vscode.window.createOutputChannel('ChallengeDaily');
    context.subscriptions.push(outputChannel);

    // 创建状态栏
    statusBar = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        50
    );
    statusBar.command = 'challengedaily.showStatus';
    statusBar.text = '$(clock) CD ...';
    statusBar.tooltip = 'ChallengeDaily — 点击查看今日状态';
    context.subscriptions.push(statusBar);
    statusBar.show();

    // 注册命令
    context.subscriptions.push(
        vscode.commands.registerCommand('challengedaily.showStatus', showStatus),
        vscode.commands.registerCommand('challengedaily.startPomodoro', startPomodoro),
        vscode.commands.registerCommand('challengedaily.openDashboard', openDashboard),
        vscode.commands.registerCommand('challengedaily.setToken', setToken)
    );

    // 启动定时刷新
    startRefresh();
    context.subscriptions.push({ dispose: stopRefresh });

    // 配置变更时重启定时器
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('challengedaily.refreshIntervalSec')) {
                stopRefresh();
                startRefresh();
            }
        })
    );

    outputChannel.appendLine('[ChallengeDaily] 扩展已激活');
    refreshOnce();
}

function deactivate() {
    stopRefresh();
}

// ── 配置读取 ──

function getConfig() {
    const cfg = vscode.workspace.getConfiguration('challengedaily');
    return {
        apiUrl: cfg.get('apiUrl', 'http://127.0.0.1:58888'),
        apiToken: cfg.get('apiToken', ''),
        refreshSec: cfg.get('refreshIntervalSec', 30),
    };
}

// ── HTTP 请求封装 ──

function apiGet(pathStr) {
    return new Promise((resolve, reject) => {
        const { apiUrl, apiToken } = getConfig();
        if (!apiToken) {
            reject(new Error('未配置 API Token，请运行 "ChallengeDaily: 配置 API Token"'));
            return;
        }
        const target = url.parse(`${apiUrl}${pathStr}`);
        const req = http.request({
            hostname: target.hostname,
            port: target.port,
            path: target.path,
            method: 'GET',
            headers: { 'X-API-Token': apiToken },
            timeout: 5000,
        }, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                if (res.statusCode !== 200) {
                    reject(new Error(`HTTP ${res.statusCode}`));
                    return;
                }
                try { resolve(JSON.parse(body)); }
                catch (e) { reject(new Error('响应解析失败')); }
            });
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('请求超时')); });
        req.end();
    });
}

function apiPost(pathStr, payload) {
    return new Promise((resolve, reject) => {
        const { apiUrl, apiToken } = getConfig();
        if (!apiToken) {
            reject(new Error('未配置 API Token'));
            return;
        }
        const target = url.parse(`${apiUrl}${pathStr}`);
        const bodyStr = JSON.stringify(payload || {});
        const req = http.request({
            hostname: target.hostname,
            port: target.port,
            path: target.path,
            method: 'POST',
            headers: {
                'X-API-Token': apiToken,
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(bodyStr),
            },
            timeout: 5000,
        }, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    try { resolve(JSON.parse(body)); }
                    catch (e) { resolve({}); }
                } else {
                    reject(new Error(`HTTP ${res.statusCode}`));
                }
            });
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('请求超时')); });
        req.write(bodyStr);
        req.end();
    });
}

// ── 状态栏刷新 ──

function startRefresh() {
    const { refreshSec } = getConfig();
    refreshTimer = setInterval(refreshOnce, refreshSec * 1000);
}

function stopRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

async function refreshOnce() {
    try {
        // 优先尝试 /api/coach/status（包含当前分类和工作时长）
        const status = await apiGet('/api/coach/status');
        const workMin = status.work_minutes || 0;
        const distractionMin = status.distraction_minutes || 0;
        const hours = Math.floor(workMin / 60);
        const mins = Math.round(workMin % 60);
        const timeStr = hours > 0 ? `${hours}h${mins}m` : `${mins}m`;

        // 当前分类提示
        const alerts = status.alerts || [];
        let icon = '$(clock)';
        if (alerts.length > 0) {
            icon = '$(warning)';
        } else if (workMin > 120) {
            icon = '$(flame)';
        }

        statusBar.text = `${icon} CD ${timeStr}`;
        statusBar.tooltip = `ChallengeDaily\n今日专注：${timeStr}\n分心时长：${Math.round(distractionMin)}m\n告警：${alerts.length}`;
        statusBar.backgroundColor = alerts.length > 0
            ? new vscode.ThemeColor('statusBarItem.warningBackground')
            : undefined;
    } catch (err) {
        statusBar.text = '$(circle-slash) CD offline';
        statusBar.tooltip = `ChallengeDaily 连接失败：${err.message}`;
        statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    }
}

// ── 命令实现 ──

async function showStatus() {
    try {
        const [status, today] = await Promise.all([
            apiGet('/api/coach/status'),
            apiGet('/api/stats/today'),
        ]);
        const workMin = status.work_minutes || 0;
        const distractionMin = status.distraction_minutes || 0;
        const alerts = status.alerts || [];

        const lines = [
            '=== ChallengeDaily 今日状态 ===',
            ``,
            `专注时长：${Math.floor(workMin / 60)}h ${Math.round(workMin % 60)}m`,
            `分心时长：${Math.round(distractionMin)}m`,
            `告警数量：${alerts.length}`,
            ``,
        ];
        if (alerts.length > 0) {
            lines.push('--- 告警列表 ---');
            alerts.forEach((a, i) => {
                lines.push(`${i + 1}. ${a.message || a.type || JSON.stringify(a)}`);
            });
            lines.push('');
        }
        if (today && today.by_category) {
            lines.push('--- 分类占比 ---');
            Object.entries(today.by_category).forEach(([cat, val]) => {
                lines.push(`  ${cat}：${val}分钟`);
            });
        }
        outputChannel.clear();
        outputChannel.appendLine(lines.join('\n'));
        outputChannel.show();
    } catch (err) {
        vscode.window.showErrorMessage(`ChallengeDaily 状态获取失败：${err.message}`);
    }
}

async function startPomodoro() {
    try {
        await apiPost('/api/pomodoro/start', { duration_min: 25 });
        vscode.window.showInformationMessage('ChallengeDaily 番茄钟已启动（25 分钟）');
        refreshOnce();
    } catch (err) {
        vscode.window.showErrorMessage(`启动番茄钟失败：${err.message}`);
    }
}

async function openDashboard() {
    const { apiUrl } = getConfig();
    // 通过系统默认浏览器打开（或 Electron 主窗口）
    vscode.env.openExternal(vscode.Uri.parse(apiUrl));
}

async function setToken() {
    const token = await vscode.window.showInputBox({
        prompt: '请输入 ChallengeDaily API Token',
        placeHolder: '在 ChallengeDaily 设置页面查看',
        password: true,
        ignoreFocusOut: true,
    });
    if (token) {
        await vscode.workspace.getConfiguration('challengedaily').update('apiToken', token, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage('ChallengeDaily Token 已保存');
        refreshOnce();
    }
}

module.exports = { activate, deactivate };
