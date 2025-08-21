import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

// 建立一個簡單的內聯 Vue 元件用於測試
const SimpleComponent = {
  template: '<div>你好，Vitest！</div>'
}

describe('SimpleComponent', () => {
  it('應該正確呈現文字', () => {
    // 掛載元件
    const wrapper = mount(SimpleComponent)

    // 斷言元件是否呈現了預期的文字
    expect(wrapper.text()).toContain('你好，Vitest！')
  })
})
