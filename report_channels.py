"""
日报多渠道自动提交通道
- 飞书日报 API（开放平台日报应用）
- 钉钉汇报 API
- 企业微信日报 API
- 邮件 SMTP（Outlook/Gmail/QQ企业邮箱）
- Notion 归档
- OneNote 归档

解决小黑日报"日报生成了还得手动复制粘贴到公司系统"的最大痛点。
"""
import logging
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


# ── 通道基类 ──

class ReportChannel:
    """日报提交通道基类"""
    name = "base"

    def __init__(self, config: dict):
        self.config = config

    def submit(self, report_text: str, report_date: str = None) -> dict:
        """提交日报，返回 {success: bool, message: str, channel: str}"""
        raise NotImplementedError

    def test_connection(self) -> dict:
        """测试连接"""
        raise NotImplementedError


# ── 邮件 SMTP 通道 ──

class EmailChannel(ReportChannel):
    """邮件 SMTP 通道：自动发送日报邮件给直属领导"""
    name = "email"

    def submit(self, report_text: str, report_date: str = None) -> dict:
        cfg = self.config
        smtp_host = cfg.get("smtp_host", "")
        smtp_port = int(cfg.get("smtp_port", 465))
        username = cfg.get("username", "")
        password = cfg.get("password", "")
        sender = cfg.get("sender", username)
        recipient = cfg.get("recipient", "")
        cc = cfg.get("cc", "")
        subject = cfg.get("subject", "工作日报 {date}").format(
            date=report_date or datetime.now().strftime("%Y-%m-%d")
        )

        if not all([smtp_host, username, password, recipient]):
            return {"success": False, "message": "邮件配置不完整", "channel": self.name}

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = formataddr(("ChallengeDaily", sender))
            msg["To"] = recipient
            if cc:
                msg["Cc"] = cc
            msg["Subject"] = subject

            # 纯文本版本
            msg.attach(MIMEText(report_text, "plain", "utf-8"))
            # HTML 版本（简单换行转换）
            html = report_text.replace("\n", "<br>")
            msg.attach(MIMEText(f"<div style='font-family:微软雅黑;'>{html}</div>", "html", "utf-8"))

            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(username, password)
                recipients = [recipient] + (cc.split(",") if cc else [])
                server.sendmail(sender, recipients, msg.as_string())

            logger.info(f"日报邮件已发送至 {recipient}")
            return {"success": True, "message": f"邮件已发送至 {recipient}", "channel": self.name}
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return {"success": False, "message": f"发送失败: {e}", "channel": self.name}

    def test_connection(self) -> dict:
        try:
            cfg = self.config
            with smtplib.SMTP_SSL(cfg.get("smtp_host", ""), int(cfg.get("smtp_port", 465)), timeout=10) as s:
                s.login(cfg.get("username", ""), cfg.get("password", ""))
            return {"success": True, "message": "SMTP 连接成功", "channel": self.name}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {e}", "channel": self.name}


# ── 飞书日报 API 通道 ──

class FeishuReportChannel(ReportChannel):
    """飞书日报 API 通道：直接写入飞书日报应用表单

    需要：app_id / app_secret / 员工 user_id / 日报应用 table_id
    调用飞书开放平台 bitable API 写入日报记录
    """
    name = "feishu_report"

    def _get_token(self) -> str:
        cfg = self.config
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        data = json.dumps({"app_id": cfg.get("app_id"), "app_secret": cfg.get("app_secret")}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                return result.get("tenant_access_token", "")
        except Exception as e:
            logger.error(f"飞书获取 token 失败: {e}")
            return ""

    def submit(self, report_text: str, report_date: str = None) -> dict:
        cfg = self.config
        token = self._get_token()
        if not token:
            return {"success": False, "message": "飞书 token 获取失败", "channel": self.name}

        app_token = cfg.get("app_token", "")
        table_id = cfg.get("table_id", "")
        user_id = cfg.get("user_id", "")

        if not all([app_token, table_id]):
            return {"success": False, "message": "飞书配置不完整（app_token/table_id）", "channel": self.name}

        # 写入 bitable 记录
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        record_data = {
            "fields": {
                "日期": report_date or datetime.now().strftime("%Y-%m-%d"),
                "日报内容": report_text,
                "提交人": user_id,
            }
        }
        data = json.dumps(record_data).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                if result.get("code") == 0:
                    logger.info(f"飞书日报已提交: {report_date}")
                    return {"success": True, "message": "飞书日报已提交", "channel": self.name}
                return {"success": False, "message": f"飞书返回错误: {result.get('msg')}", "channel": self.name}
        except Exception as e:
            logger.error(f"飞书日报提交失败: {e}")
            return {"success": False, "message": f"提交失败: {e}", "channel": self.name}

    def test_connection(self) -> dict:
        token = self._get_token()
        if token:
            return {"success": True, "message": "飞书 API 连接成功", "channel": self.name}
        return {"success": False, "message": "飞书 API 连接失败", "channel": self.name}


# ── 钉钉汇报 API 通道 ──

class DingtalkReportChannel(ReportChannel):
    """钉钉汇报 API 通道：写入钉钉智能填报/汇报

    需要：app_key / app_secret / 员工 userid / 汇报模板 template_id
    """
    name = "dingtalk_report"

    def _get_token(self) -> str:
        cfg = self.config
        url = f"https://oapi.dingtalk.com/gettoken?appkey={cfg.get('app_key')}&appsecret={cfg.get('app_secret')}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                return result.get("access_token", "")
        except Exception as e:
            logger.error(f"钉钉获取 token 失败: {e}")
            return ""

    def submit(self, report_text: str, report_date: str = None) -> dict:
        cfg = self.config
        token = self._get_token()
        if not token:
            return {"success": False, "message": "钉钉 token 获取失败", "channel": self.name}

        template_id = cfg.get("template_id", "")
        userid = cfg.get("userid", "")
        if not all([template_id, userid]):
            return {"success": False, "message": "钉钉配置不完整（template_id/userid）", "channel": self.name}

        # 调用智能填报提交汇报
        url = f"https://oapi.dingtalk.com/topapi/smartwork/hrm/employee/report/submit?access_token={token}"
        data = json.dumps({
            "userid": userid,
            "template_id": template_id,
            "contents": [
                {"key": "日报内容", "value": report_text},
                {"key": "日期", "value": report_date or datetime.now().strftime("%Y-%m-%d")},
            ],
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                if result.get("errcode") == 0:
                    logger.info(f"钉钉日报已提交: {report_date}")
                    return {"success": True, "message": "钉钉日报已提交", "channel": self.name}
                return {"success": False, "message": f"钉钉返回错误: {result.get('errmsg')}", "channel": self.name}
        except Exception as e:
            logger.error(f"钉钉日报提交失败: {e}")
            return {"success": False, "message": f"提交失败: {e}", "channel": self.name}

    def test_connection(self) -> dict:
        token = self._get_token()
        if token:
            return {"success": True, "message": "钉钉 API 连接成功", "channel": self.name}
        return {"success": False, "message": "钉钉 API 连接失败", "channel": self.name}


# ── 企业微信日报 API 通道 ──

class WeComReportChannel(ReportChannel):
    """企业微信日报 API 通道"""
    name = "wecom_report"

    def submit(self, report_text: str, report_date: str = None) -> dict:
        # 企业微信日报 API 较复杂，暂用 Webhook 群机器人兜底
        return {"success": False, "message": "企微日报 API 暂未实现，请使用 Webhook 通道", "channel": self.name}

    def test_connection(self) -> dict:
        return {"success": False, "message": "企微日报 API 暂未实现", "channel": self.name}


# ── 通道工厂 ──

CHANNEL_CLASSES = {
    "email": EmailChannel,
    "feishu_report": FeishuReportChannel,
    "dingtalk_report": DingtalkReportChannel,
    "wecom_report": WeComReportChannel,
}


def get_channel(channel_type: str, config: dict) -> ReportChannel:
    """获取提交通道实例"""
    cls = CHANNEL_CLASSES.get(channel_type)
    if not cls:
        raise ValueError(f"未知通道类型: {channel_type}")
    return cls(config)


def submit_to_all_channels(report_text: str, channels_config: list, report_date: str = None) -> list:
    """提交日报到所有已配置的通道

    Args:
        report_text: 日报正文
        channels_config: [{"type": "email", "config": {...}}, ...]
        report_date: 日报日期

    Returns:
        [{"channel": "email", "success": True, "message": "..."}]
    """
    results = []
    for ch in channels_config:
        ch_type = ch.get("type")
        ch_config = ch.get("config", {})
        if not ch_type or not ch_config:
            continue
        try:
            channel = get_channel(ch_type, ch_config)
            result = channel.submit(report_text, report_date)
            results.append(result)
        except Exception as e:
            results.append({"channel": ch_type, "success": False, "message": f"通道异常: {e}"})
    return results
