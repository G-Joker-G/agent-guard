import { Component } from 'react'

/**
 * ErrorBoundary：防止单个页面的一次渲染崩溃拖垮整个应用
 * （2026-10-13 教训：Demo.jsx 一个未定义变量曾导致演示页整树黑屏）。
 *
 * 用法：在 App.jsx 中每个 Tab 页面外包一层，并用 key={tab} 使切换 Tab 时重置错误态：
 *   <ErrorBoundary key={tab} name="实时运行"><LivePage /></ErrorBoundary>
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error(`[ErrorBoundary:${this.props.name || 'page'}]`, error, info)
  }

  render() {
    const { error } = this.state
    if (error) {
      return (
        <div className="panel">
          <h2>页面渲染出错</h2>
          <p className="muted">
            「{this.props.name || '当前页面'}」渲染时崩溃了，其他 Tab 不受影响。
            这是前端展示问题——后端网关、审批与审计不受影响。
          </p>
          <pre className="mono s-resp">{String(error?.message || error)}</pre>
          <div className="row">
            <button className="btn" onClick={() => this.setState({ error: null })}>重试渲染</button>
            <button className="btn" onClick={() => window.location.reload()}>刷新整个页面</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
