import { Component } from 'react'
import GenericToolBody from './GenericToolBody'

export default class ToolBodyBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false, resetKey: props.resetKey }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  static getDerivedStateFromProps(props, state) {
    return props.resetKey === state.resetKey ? null : { failed: false, resetKey: props.resetKey }
  }

  render() {
    return this.state.failed ? <GenericToolBody tool={this.props.tool} /> : this.props.children
  }
}
