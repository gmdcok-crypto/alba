import { Html5Qrcode } from 'html5-qrcode'

let current: Html5Qrcode | null = null
let stopChain: Promise<void> = Promise.resolve()
const SCAN_BOX_EDGE = 300

function applyScanFrameSize(edge: number): void {
  const frame = document.querySelector<HTMLElement>('.scan-frame')
  if (!frame) return
  const px = `${Math.max(120, Math.floor(edge))}px`
  frame.style.width = px
  frame.style.height = px
}

export async function stopAttendQrScanner(): Promise<void> {
  stopChain = stopChain.then(async () => {
    if (!current) return
    const h = current
    current = null
    try {
      await h.stop()
    } catch {
      /* already stopped */
    }
    try {
      h.clear()
    } catch {
      /* */
    }
  })
  return stopChain
}

export async function startAttendQrScanner(
  onDecoded: (text: string) => void,
  onFail?: (message: string) => void,
): Promise<void> {
  await stopAttendQrScanner()
  if (!document.getElementById('qr-reader')) {
    onFail?.('스캔 영역을 찾을 수 없습니다.')
    return
  }

  const html5 = new Html5Qrcode('qr-reader', false)
  current = html5
  let settled = false

  const finish = (text: string) => {
    if (settled) return
    settled = true
    void stopAttendQrScanner().then(() => onDecoded(text))
  }

  try {
    const cams = await Html5Qrcode.getCameras()
    if (!cams.length) {
      current = null
      onFail?.('사용 가능한 카메라가 없습니다.')
      return
    }
    const back = cams.find((c) => /back|rear|environment|후면/i.test(c.label))
    const cameraId = back?.id ?? cams[0].id

    const host = document.getElementById('qr-reader')
    if (host) {
      const initialEdge = Math.min(host.clientWidth, host.clientHeight, SCAN_BOX_EDGE)
      applyScanFrameSize(initialEdge)
    }

    await html5.start(
      cameraId,
      {
        fps: 10,
        qrbox: (viewW, viewH) => {
          const edge = Math.min(viewW, viewH, SCAN_BOX_EDGE)
          applyScanFrameSize(edge)
          return { width: edge, height: edge }
        },
      },
      (decoded) => finish(decoded),
      () => {
        /* frame */
      },
    )
  } catch (e) {
    current = null
    try {
      html5.clear()
    } catch {
      /* */
    }
    onFail?.(e instanceof Error ? e.message : String(e))
  }
}
