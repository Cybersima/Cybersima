import { useEffect, useState, type FormEvent } from 'react'
import {
  api,
  type BlockRule,
  type GuardNode,
  type NetworkEvent,
} from '../lib/api'

export function NetworkGuardPage() {
  const [summary, setSummary] = useState({
    nodes: 0,
    onlineNodes: 0,
    packetsSeen: 0,
    packetsBlocked: 0,
    activeBlocks: 0,
  })
  const [nodes, setNodes] = useState<GuardNode[]>([])
  const [events, setEvents] = useState<NetworkEvent[]>([])
  const [blocks, setBlocks] = useState<BlockRule[]>([])
  const [blockIp, setBlockIp] = useState('')
  const [blockReason, setBlockReason] = useState('Manual edge block')
  const [nodeName, setNodeName] = useState('Office edge gateway')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')

  async function load() {
    const res = await api.networkSummary()
    setSummary(res.summary)
    setNodes(res.nodes)
    setEvents(res.events)
    setBlocks(res.blocks)
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message))
    const timer = window.setInterval(() => {
      load().catch(() => undefined)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [])

  async function addBlock(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await api.createBlock({ ip: blockIp, reason: blockReason })
      setBlockIp('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create block')
    }
  }

  async function createNode(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await api.createGuardNode({ name: nodeName, mode: 'simulate' })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create node')
    }
  }

  async function removeBlock(id: number) {
    await api.deleteBlock(id)
    await load()
  }

  function copyToken(token: string) {
    void navigator.clipboard.writeText(token)
    setCopied(token)
    window.setTimeout(() => setCopied(''), 2000)
  }

  const primary = nodes[0]

  return (
    <div>
      <h1 className="page-title">Network Guard</h1>
      <p className="page-sub">
        Live edge monitoring for hostile packet patterns. Deploy the agent on your
        gateway/firewall so drops happen before traffic forwards into the LAN.
      </p>

      {error && <p className="error">{error}</p>}

      <div className="metric-row">
        <div className="metric">
          <span>Guard nodes</span>
          <strong>
            {summary.onlineNodes}/{summary.nodes}
          </strong>
        </div>
        <div className="metric">
          <span>Packets seen</span>
          <strong>{summary.packetsSeen}</strong>
        </div>
        <div className="metric">
          <span>Packets blocked</span>
          <strong>{summary.packetsBlocked}</strong>
        </div>
        <div className="metric">
          <span>Active blocks</span>
          <strong>{summary.activeBlocks}</strong>
        </div>
      </div>

      <section className="panel" style={{ width: '100%', marginBottom: '1.25rem' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', marginTop: 0 }}>
          Deploy on the edge
        </h2>
        <p>
          A browser app cannot intercept WAN packets. Run Network Guard on the
          router, firewall appliance, or a Linux box routing your LAN.
        </p>
        {primary ? (
          <pre className="secret-preview">{`cd backend
source .venv/bin/activate
export LOCKWELL_API=http://127.0.0.1:5000
export LOCKWELL_GUARD_TOKEN=${primary.agentToken}
python -m network_guard.agent --mode simulate
# Gateway host with privileges:
# python -m network_guard.agent --mode enforce --interface eth0`}</pre>
        ) : (
          <p>Create a guard node to get an agent token.</p>
        )}
        <form className="form-stack" onSubmit={createNode}>
          <label>
            New node name
            <input value={nodeName} onChange={(e) => setNodeName(e.target.value)} />
          </label>
          <button className="btn btn-primary" type="submit">
            Create guard node
          </button>
        </form>
      </section>

      <section className="stack" style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', margin: 0 }}>Guard nodes</h2>
        {nodes.map((node) => (
          <article key={node.id} className="list-row">
            <header>
              <h3>
                {node.name} · {node.status}
              </h3>
              <span className={`badge ${node.status === 'online' ? 'low' : 'medium'}`}>
                {node.mode}/{node.backend}
              </span>
            </header>
            <p>
              iface {node.interface} · seen {node.packetsSeen} · blocked{' '}
              {node.packetsBlocked}
              {node.lastSeenAt
                ? ` · last seen ${new Date(node.lastSeenAt).toLocaleString()}`
                : ' · waiting for agent'}
            </p>
            <p>
              Token:{' '}
              <code>{node.agentToken.slice(0, 12)}…</code>{' '}
              <button className="btn btn-ghost" type="button" onClick={() => copyToken(node.agentToken)}>
                {copied === node.agentToken ? 'Copied' : 'Copy token'}
              </button>
            </p>
          </article>
        ))}
      </section>

      <section className="panel" style={{ width: '100%', marginBottom: '1.25rem' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', marginTop: 0 }}>
          Manual blocklist
        </h2>
        <form className="form-stack" onSubmit={addBlock}>
          <label>
            Source IP
            <input
              value={blockIp}
              onChange={(e) => setBlockIp(e.target.value)}
              placeholder="203.0.113.50"
              required
            />
          </label>
          <label>
            Reason
            <input
              value={blockReason}
              onChange={(e) => setBlockReason(e.target.value)}
              required
            />
          </label>
          <button className="btn btn-primary" type="submit">
            Block at edge
          </button>
        </form>
        <div className="stack" style={{ marginTop: '1rem' }}>
          {blocks.map((block) => (
            <article key={block.id} className="list-row">
              <header>
                <h3>
                  {block.ip} {block.active ? '' : '(inactive)'}
                </h3>
                {block.active && (
                  <button className="btn btn-danger" onClick={() => void removeBlock(block.id)}>
                    Unblock
                  </button>
                )}
              </header>
              <p>
                {block.reason} · hits {block.hits}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="stack">
        <h2 style={{ fontFamily: 'var(--font-display)', margin: 0 }}>
          Recent network events
        </h2>
        {events.length === 0 && (
          <p className="page-sub">No edge events yet. Start the agent to begin live monitoring.</p>
        )}
        {events.map((event) => (
          <article key={event.id} className="list-row">
            <header>
              <h3>{event.title}</h3>
              <span className={`badge ${event.severity}`}>{event.action}</span>
            </header>
            <p>
              {event.srcIp} → {event.dstIp}:{event.dstPort}/{event.protocol} ·{' '}
              {event.category}
            </p>
            <p>{event.detail}</p>
            <p>{new Date(event.createdAt).toLocaleString()}</p>
          </article>
        ))}
      </section>
    </div>
  )
}
