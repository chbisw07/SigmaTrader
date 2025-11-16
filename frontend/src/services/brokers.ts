export type BrokerInfo = {
  name: string
  label: string
}

export type BrokerSecret = {
  key: string
  value: string
}

export async function fetchBrokers(): Promise<BrokerInfo[]> {
  const res = await fetch('/api/brokers/')
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load brokers (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as BrokerInfo[]
}

export async function fetchBrokerSecrets(
  brokerName: string,
): Promise<BrokerSecret[]> {
  const res = await fetch(`/api/brokers/${encodeURIComponent(brokerName)}/secrets`)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load broker secrets (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as BrokerSecret[]
}

export async function updateBrokerSecret(
  brokerName: string,
  key: string,
  value: string,
): Promise<BrokerSecret> {
  const res = await fetch(
    `/api/brokers/${encodeURIComponent(
      brokerName,
    )}/secrets/${encodeURIComponent(key)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    },
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to update broker secret (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as BrokerSecret
}

export async function deleteBrokerSecret(
  brokerName: string,
  key: string,
): Promise<void> {
  const res = await fetch(
    `/api/brokers/${encodeURIComponent(
      brokerName,
    )}/secrets/${encodeURIComponent(key)}`,
    {
      method: 'DELETE',
    },
  )
  if (!res.ok && res.status !== 404) {
    const body = await res.text()
    throw new Error(
      `Failed to delete broker secret (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
}

