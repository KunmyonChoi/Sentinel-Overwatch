// 버전 한 줄. 앱과 서버는 따로 올라가서, 둘을 함께 보여줘야 "어느 쪽이 옛것인지"를 알 수 있다.
import { describe, it, expect, afterEach } from 'vitest'
import { readAppVersion, versionLabel } from './version'

describe('versionLabel', () => {
  it('앱과 서버를 함께 보여준다', () => {
    expect(versionLabel({ app: '0.1.1', server: '1.0.0' })).toBe('앱 0.1.1 · 서버 1.0.0')
  })

  it('브라우저에서는 앱 버전이 없으니 서버만 보여준다', () => {
    expect(versionLabel({ app: null, server: '1.0.0' })).toBe('서버 1.0.0')
  })

  it('서버를 아직 못 읽었으면 앱만 보여준다', () => {
    expect(versionLabel({ app: '0.1.1', server: undefined })).toBe('앱 0.1.1')
  })

  it('둘 다 모르면 빈 문자열 — 화면은 아무것도 그리지 않는다', () => {
    expect(versionLabel({})).toBe('')
    expect(versionLabel()).toBe('')
  })
})

describe('readAppVersion', () => {
  const original = globalThis.window
  afterEach(() => { globalThis.window = original })

  it('데스크톱 앱이 아니면 null', async () => {
    globalThis.window = {}
    expect(await readAppVersion()).toBeNull()
  })

  it('데스크톱 앱이면 Tauri 에서 읽은 버전', async () => {
    globalThis.window = { __TAURI__: { app: { getVersion: async () => '0.1.1' } } }
    expect(await readAppVersion()).toBe('0.1.1')
  })

  it('읽다가 실패하면 화면을 깨지 않고 null', async () => {
    globalThis.window = { __TAURI__: { app: { getVersion: async () => { throw new Error('denied') } } } }
    expect(await readAppVersion()).toBeNull()
  })
})
