import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { abortPiRun, piSessionKey, readPiStream, sendPiMessage } from './piRemote'

const { authFailureMock, tokenMock, fetchAPIMock } = vi.hoisted(() => ({
  authFailureMock: vi.fn(),
  tokenMock: vi.fn(() => 'test-token'),
  fetchAPIMock: vi.fn(),
}))

vi.mock('../api', () => ({
  API_BASE: 'http://api.test/api',
  getToken: tokenMock,
  handleAuthFailure: authFailureMock,
  fetchAPI: fetchAPIMock,
}))

const fetchMock = vi.fn()

function streamResponse(text, status = 200) {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text))
      controller.close()
    },
  })
  return { ok: status >= 200 && status < 300, status, body: stream }
}

beforeEach(() => {
  fetchMock.mockReset()
  authFailureMock.mockReset()
  fetchAPIMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('readPiStream', () => {
  it('sends bearer and Last-Event-ID', async () => {
    fetchMock.mockResolvedValue(
      streamResponse('event: snapshot\nid: 1\ndata: {"sessions":[]}\n\n'),
    )
    await readPiStream('/pi/sessions/stream', { lastEventId: 5 })

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://api.test/api/pi/sessions/stream')
    expect(options.headers.Authorization).toBe('Bearer test-token')
    expect(options.headers['Last-Event-ID']).toBe('5')
  })

  it('delivers parsed frames', async () => {
    fetchMock.mockResolvedValue(
      streamResponse(
        'event: session\nid: 2\ndata: {"session_id":"s1","instance_id":"i1"}\n\n',
      ),
    )
    const frames = []
    await readPiStream('/pi/sessions/s1/i1/stream', {
      onFrame: (frame) => frames.push(frame),
    })
    expect(frames).toEqual([
      {
        event: 'session',
        id: '2',
        data: { session_id: 's1', instance_id: 'i1' },
      },
    ])
  })

  it('401 calls handleAuthFailure', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401 })
    await expect(readPiStream('/pi/sessions/stream')).rejects.toMatchObject({
      status: 401,
    })
    expect(authFailureMock).toHaveBeenCalledTimes(1)
  })

  it('non-2xx throws with status', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500 })
    await expect(readPiStream('/pi/sessions/stream')).rejects.toMatchObject({
      status: 500,
    })
    expect(authFailureMock).not.toHaveBeenCalled()
  })
})

describe('piSessionKey', () => {
  it('is session_id plus instance_id', () => {
    expect(piSessionKey({ session_id: 's1', instance_id: 'i1' })).toBe('s1/i1')
  })
})


describe('sendPiMessage', () => {
  it('posts text', async () => {
    fetchAPIMock.mockResolvedValue({ command_id: 'cmd-1', ok: true, error: null })
    const result = await sendPiMessage('s1', 'i1', 'hello')
    expect(fetchAPIMock).toHaveBeenCalledWith(
      '/pi/sessions/s1/i1/messages',
      { method: 'POST', body: JSON.stringify({ text: 'hello' }) },
    )
    expect(result).toEqual({
      status: 200,
      body: { command_id: 'cmd-1', ok: true, error: null },
    })
  })

  it('202 and 409 do not throw', async () => {
    fetchAPIMock.mockResolvedValue({ command_id: 'cmd-1', pending: true })
    await expect(sendPiMessage('s1', 'i1', 'hello')).resolves.toEqual({
      status: 202,
      body: { command_id: 'cmd-1', pending: true },
    })

    const error = new Error('pi is offline')
    error.status = 409
    error.body = { error: 'pi_session_offline' }
    fetchAPIMock.mockRejectedValue(error)
    await expect(abortPiRun('s1', 'i1')).resolves.toEqual({
      status: 409,
      body: { error: 'pi_session_offline' },
    })
  })
})

describe('abortPiRun', () => {
  it('posts', async () => {
    fetchAPIMock.mockResolvedValue({ command_id: 'cmd-1', ok: true, error: null })
    const result = await abortPiRun('s1', 'i1')
    expect(fetchAPIMock).toHaveBeenCalledWith(
      '/pi/sessions/s1/i1/abort',
      { method: 'POST', body: '{}' },
    )
    expect(result).toEqual({
      status: 200,
      body: { command_id: 'cmd-1', ok: true, error: null },
    })
  })
})
