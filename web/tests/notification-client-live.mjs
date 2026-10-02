// Called by the guarded Python verifier; ephemeral synthetic credentials use stdin.
import { createNotificationSocket } from '../src/utils/notificationSocket.js'

let input = ''
for await (const chunk of process.stdin) input += chunk
const args = JSON.parse(input)
const url = new URL(args.baseUrl)
if (url.hostname !== '127.0.0.1' || args.userId !== 'fixture_student_a') throw new Error('Synthetic localhost only')
let authenticated = 0
let deliveries = 0
let token = args.token
const clients = []
const cases = []
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const waitFor = async predicate => {
  for (let attempt = 0; attempt < 60; attempt++) { if (predicate()) return; await sleep(50) }
  throw new Error('Notification client condition timed out')
}
const check = (name, passed) => { cases.push({ case: name, passed }); if (!passed) throw new Error(name) }
class ObservedSocket extends WebSocket {
  constructor (address) {
    super(address)
    this.addEventListener('message', event => { if (JSON.parse(event.data).cmd === 'authenticated') authenticated++ })
  }
}
async function notify () {
  const response = await fetch(args.baseUrl + '/webSocketApi/sendUser', { method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Access-Token': args.adminToken },
    body: JSON.stringify({ userId: args.userId, message: 'fixture-notification-client-live' }) })
  if (response.status !== 200 || !(await response.json()).success) throw new Error('Synthetic send failed')
}
try {
  for (let i = 0; i < 2; i++) clients.push(createNotificationSocket({ baseUrl: args.baseUrl, pageUrl: args.baseUrl,
    userId: args.userId, getToken: () => token, onNotice: () => deliveries++, WebSocketCtor: ObservedSocket }))
  await waitFor(() => authenticated === 2)
  await notify(); await waitFor(() => deliveries === 2)
  check('shipped JavaScript client authenticates and receives on both real sockets', deliveries === 2)
  clients[0].stop(); await sleep(100)
  await notify(); await waitFor(() => deliveries === 3)
  check('disposing one JavaScript client preserves the other subscription', deliveries === 3)
  token = null
  await notify(); await sleep(350)
  check('cleared frontend login prevents notification callbacks', deliveries === 3)
} finally {
  for (const client of clients) client.stop()
}
console.log(JSON.stringify({ cases, passed: cases.filter(c => c.passed).length, total: cases.length,
  transport: 'Node native WebSocket with shipped browser helper and real Java API, not a browser login/UI test' }))
