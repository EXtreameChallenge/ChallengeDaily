/**
 * AIChat 组件单元测试
 * 覆盖：renderMarkdown XSS 转义、renderMarkdown 保留 <strong> 标签
 */
import { render, waitFor } from '@testing-library/react'
import AIChat from './AIChat'

// Mock API client 避免真实网络调用
jest.mock('../api/client', () => ({
  getChatHistory: jest.fn(),
  clearChatHistory: jest.fn(),
  aiChatStream: jest.fn(),
  executeChatAction: jest.fn(),
}))

import { getChatHistory } from '../api/client'

describe('AIChat renderMarkdown', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  // ── 测试1：<script> 被转义为 &lt;script&gt; ──
  it('escapes <script> tags to prevent XSS', async () => {
    ;(getChatHistory as jest.Mock).mockResolvedValue({
      history: [
        {
          id: 1,
          role: 'assistant',
          content: '<script>alert("xss")</script>',
          created_at: new Date().toISOString(),
        },
      ],
    })

    const { container } = render(<AIChat />)

    await waitFor(() => {
      const html = container.innerHTML
      // <script> 应被 HTML 实体转义
      expect(html).toContain('&lt;script&gt;')
      // 原始 <script> 标签不应出现在 HTML 中
      expect(html).not.toContain('<script>alert')
    })
  })

  // ── 测试2：**bold** 被保留为 <strong>bold</strong> ──
  it('preserves **bold** as <strong>', async () => {
    ;(getChatHistory as jest.Mock).mockResolvedValue({
      history: [
        {
          id: 1,
          role: 'assistant',
          content: '**bold text**',
          created_at: new Date().toISOString(),
        },
      ],
    })

    const { container } = render(<AIChat />)

    await waitFor(() => {
      expect(container.innerHTML).toContain('<strong>bold text</strong>')
    })
  })
})
