import { useState } from 'react'
import { Shield, FileText, ChevronRight } from 'lucide-react'

export default function Legal({ onAccept }: { onAccept: () => void }) {
  const [tab, setTab] = useState<'privacy' | 'terms'>('privacy')

  return (
    <div className="flex-1 flex items-center justify-center bg-cd-bg p-4">
      <div className="w-full max-w-xl">
        {/* Tab Switcher */}
        <div className="flex gap-1 bg-cd-bg-secondary rounded-lg p-1 mb-4">
          <button
            onClick={() => setTab('privacy')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm transition-colors ${
              tab === 'privacy' ? 'bg-cd-card text-cd-green font-medium shadow-sm' : 'text-cd-text-secondary hover:text-cd-text'
            }`}
          >
            <Shield size={16} />
            隐私政策
          </button>
          <button
            onClick={() => setTab('terms')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm transition-colors ${
              tab === 'terms' ? 'bg-cd-card text-cd-green font-medium shadow-sm' : 'text-cd-text-secondary hover:text-cd-text'
            }`}
          >
            <FileText size={16} />
            用户协议
          </button>
        </div>

        {/* Content */}
        <div className="bg-cd-card rounded-xl border border-cd-border p-5 max-h-[50vh] overflow-y-auto text-sm text-cd-text-secondary leading-relaxed">
          {tab === 'privacy' ? <PrivacyContent /> : <TermsContent />}
        </div>

        {/* Accept Button */}
        <div className="mt-4 flex justify-end">
          <button
            onClick={onAccept}
            className="flex items-center gap-2 bg-cd-green text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
          >
            我已阅读并同意
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

function PrivacyContent() {
  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold text-cd-text"><span className="font-brand font-bold">ChallengeDaily</span> 隐私政策</h2>
      <p className="text-xs text-cd-text-tertiary">最后更新：2026年7月</p>

      <section>
        <h3 className="font-medium text-cd-text mb-1">1. 数据存储位置</h3>
        <p>您的所有数据（截图、活动记录、日报、配置）均存储在本地设备上，不会上传至任何远程服务器。数据完全由您掌控。</p>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">2. 截图处理</h3>
        <p>应用会定期截取屏幕画面用于分析您的工作活动。截图处理规则如下：</p>
        <ul className="list-disc ml-5 space-y-1">
          <li>截图仅存储在本地磁盘，不会通过网络传输</li>
          <li>如您启用了 AI 分析功能，截图将发送至您自行配置的 AI 服务（如智谱 GLM）进行分析</li>
          <li>AI 分析结果仅用于工作分类和摘要生成</li>
          <li>排除列表中的应用不会被截图记录</li>
          <li>超过保留期限的截图将自动删除</li>
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">3. AI 服务使用</h3>
        <p>AI 分析是可选功能，默认关闭。启用时：</p>
        <ul className="list-disc ml-5 space-y-1">
          <li>您需自行提供 AI 服务的 API Key 和接口地址</li>
          <li>截图内容将通过您配置的 AI 服务处理，受该服务的隐私政策约束</li>
          <li>我们建议您了解所使用 AI 服务的隐私政策</li>
          <li>AI 生成的内容会标注"AI 辅助生成"</li>
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">4. 网络通信</h3>
        <p>应用的以下功能会涉及网络通信：</p>
        <ul className="list-disc ml-5 space-y-1">
          <li>AI 分析（如您启用）：仅连接您配置的 AI 服务地址</li>
          <li>Webhook 推送（如您配置）：将日报推送到您指定的飞书/钉钉/企业微信</li>
          <li>自动更新检查：连接 GitHub 检查新版本</li>
          <li>以上所有连接均可通过设置关闭，应用可在完全离线环境下运行</li>
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">5. 数据删除</h3>
        <p>您可以随时删除自己的数据：</p>
        <ul className="list-disc ml-5 space-y-1">
          <li>通过设置页面导出或删除全部数据</li>
          <li>卸载应用后，数据目录将保留，您可手动删除</li>
          <li>数据目录位置：应用安装目录下的 data 文件夹</li>
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">6. 我们不会做的事</h3>
        <ul className="list-disc ml-5 space-y-1">
          <li>不会收集、上传或分享您的个人数据</li>
          <li>不会嵌入任何第三方追踪或统计代码</li>
          <li>不会在后台静默连接任何服务器</li>
          <li>不会将您的数据用于任何商业目的</li>
        </ul>
      </section>
    </div>
  )
}

function TermsContent() {
  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold text-cd-text"><span className="font-brand font-bold">ChallengeDaily</span> 用户协议</h2>
      <p className="text-xs text-cd-text-tertiary">最后更新：2026年7月</p>

      <section>
        <h3 className="font-medium text-cd-text mb-1">1. 接受条款</h3>
        <p>下载、安装或使用 ChallengeDaily（以下简称"本软件"）即表示您同意本用户协议。如果您不同意，请勿使用本软件。</p>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">2. 许可授权</h3>
        <p>本软件为免费软件，授予您非独占的、不可转让的、有限的许可，用于个人或商业目的安装和使用本软件。</p>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">3. 使用限制</h3>
        <ul className="list-disc ml-5 space-y-1">
          <li>不得对本软件进行反编译、反汇编或修改</li>
          <li>不得移除或修改软件中的任何版权声明</li>
          <li>不得将本软件用于任何非法目的</li>
          <li>不得将本软件作为服务向第三方提供</li>
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">4. 免责声明</h3>
        <p>本软件按"原样"提供，不做任何明示或暗示的保证，包括但不限于：</p>
        <ul className="list-disc ml-5 space-y-1">
          <li>不保证软件无错误或不间断运行</li>
          <li>不保证软件满足您的特定需求</li>
          <li>对因使用或无法使用本软件造成的任何直接、间接、附带、特殊或后果性损害不承担责任</li>
          <li>AI 生成的内容仅供参考，其准确性不做保证</li>
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">5. 数据责任</h3>
        <p>您对使用本软件所产生的数据负全部责任。建议您定期备份数据。因设备故障、软件错误等原因导致的数据丢失，我们不承担责任。</p>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">6. 知识产权</h3>
        <p>本软件的所有知识产权归开发者所有。本协议不授予您任何知识产权。</p>
      </section>

      <section>
        <h3 className="font-medium text-cd-text mb-1">7. 协议变更</h3>
        <p>我们保留随时修改本协议的权利。继续使用本软件即表示您接受修改后的协议。</p>
      </section>
    </div>
  )
}
