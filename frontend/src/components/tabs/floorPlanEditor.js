const number = (value, fallback = 0) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export const snapPointToGrid = (point = {}, step = 5) => {
  const grid = Math.max(1, Math.round(number(step, 5)))
  const snap = (value) => Math.round(number(value) / grid) * grid
  return {
    ...point,
    plan_x: snap(point.plan_x),
    plan_y: snap(point.plan_y),
  }
}

export const alignTablePositions = (
  positions = {},
  tableIds = [],
  axis = 'row',
  anchorTableId = null,
) => {
  const ids = [...new Set(tableIds.map(Number))].filter((id) => positions[id])
  if (ids.length < 2 || !['row', 'column'].includes(axis)) return positions
  const anchorId = ids.includes(Number(anchorTableId)) ? Number(anchorTableId) : ids[0]
  const coordinate = axis === 'row' ? 'plan_y' : 'plan_x'
  const anchorValue = number(positions[anchorId]?.[coordinate], NaN)
  if (!Number.isFinite(anchorValue)) return positions
  return {
    ...positions,
    ...Object.fromEntries(ids.map((id) => [id, {
      ...positions[id],
      [coordinate]: anchorValue,
    }])),
  }
}

const tableIds = (combination = {}) => [...new Set(
  (combination.stoliki || []).map((id) => Number(id)).filter((id) => id > 0),
)].sort((first, second) => first - second)

export const edgeKey = (first, second) => {
  const ids = [Number(first), Number(second)].sort((a, b) => a - b)
  return ids[0] > 0 && ids[0] !== ids[1] ? `${ids[0]}:${ids[1]}` : ''
}

export const normalizeEdges = (edges = []) => {
  const normalized = new Map()
  edges.forEach((edge) => {
    const key = edgeKey(edge?.stolik_a_id, edge?.stolik_b_id)
    if (!key) return
    const [stolikA, stolikB] = key.split(':').map(Number)
    normalized.set(key, { stolik_a_id: stolikA, stolik_b_id: stolikB })
  })
  return [...normalized.values()].sort((first, second) => (
    first.stolik_a_id - second.stolik_a_id
    || first.stolik_b_id - second.stolik_b_id
  ))
}

export const combinationKey = (combination = {}) => tableIds(combination).join(':')

export const normalizeCombination = (combination = {}) => {
  const ids = tableIds(combination)
  const minimum = Math.max(1, Math.round(number(combination.pojemnosc_min, 1)))
  const maximum = Math.max(minimum, Math.round(number(combination.pojemnosc_max, minimum)))
  const channel = ['online', 'wewnetrzna', 'oba'].includes(combination.kanal)
    ? combination.kanal
    : 'oba'
  const name = String(combination.nazwa || '').trim() || ids.join(' + ')
  return {
    ...(Number(combination.id) > 0 ? { id: Number(combination.id) } : {}),
    nazwa: name.slice(0, 64),
    stoliki: ids,
    pojemnosc_min: minimum,
    pojemnosc_max: maximum,
    priorytet: Math.round(number(combination.priorytet, 0)),
    kanal: channel,
    aktywna_w_planie: combination.aktywna_w_planie !== false,
  }
}

export const normalizeCombinations = (combinations = []) => {
  const normalized = new Map()
  combinations.forEach((combination) => {
    const value = normalizeCombination(combination)
    const key = combinationKey(value)
    if (value.stoliki.length >= 2 && key) normalized.set(key, value)
  })
  return [...normalized.values()].sort((first, second) => (
    combinationKey(first).localeCompare(combinationKey(second), 'pl', { numeric: true })
  ))
}

export const editorSignature = (positions = {}, edges = [], combinations = []) => JSON.stringify({
  pozycje: Object.entries(positions)
    .sort(([first], [second]) => Number(first) - Number(second))
    .map(([id, value]) => [Number(id), value]),
  krawedzie: normalizeEdges(edges),
  kombinacje: normalizeCombinations(combinations),
})

export const cloneEditorSnapshot = (positions = {}, edges = [], combinations = []) => ({
  positions: Object.fromEntries(Object.entries(positions).map(([id, value]) => [id, { ...value }])),
  edges: normalizeEdges(edges).map((edge) => ({ ...edge })),
  combinations: normalizeCombinations(combinations).map((combination) => ({
    ...combination,
    stoliki: [...combination.stoliki],
  })),
})

export const neighborIds = (tableId, edges = []) => {
  const id = Number(tableId)
  return normalizeEdges(edges).flatMap((edge) => {
    if (edge.stolik_a_id === id) return [edge.stolik_b_id]
    if (edge.stolik_b_id === id) return [edge.stolik_a_id]
    return []
  })
}

export const isConnectedSet = (ids, edges = []) => {
  const wanted = [...new Set((ids || []).map(Number).filter((id) => id > 0))]
  if (wanted.length < 2) return false
  const wantedSet = new Set(wanted)
  const adjacency = new Map(wanted.map((id) => [id, new Set()]))
  normalizeEdges(edges).forEach((edge) => {
    if (!wantedSet.has(edge.stolik_a_id) || !wantedSet.has(edge.stolik_b_id)) return
    adjacency.get(edge.stolik_a_id).add(edge.stolik_b_id)
    adjacency.get(edge.stolik_b_id).add(edge.stolik_a_id)
  })
  const visited = new Set([wanted[0]])
  const queue = [wanted[0]]
  while (queue.length) {
    const current = queue.shift()
    adjacency.get(current).forEach((next) => {
      if (visited.has(next)) return
      visited.add(next)
      queue.push(next)
    })
  }
  return visited.size === wanted.length
}

const capacityMaximum = (table = {}) => Math.max(
  1,
  Math.round(number(table.pojemnosc_max ?? table.pojemnosc, 1)),
)

const capacityMinimum = (table = {}) => Math.max(
  1,
  Math.min(capacityMaximum(table), Math.round(number(table.pojemnosc_min, 1))),
)

const placesWord = (count) => {
  const absolute = Math.abs(Number(count) || 0)
  if (absolute === 1) return 'miejsce'
  const lastTwo = absolute % 100
  const last = absolute % 10
  return last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)
    ? 'miejsca'
    : 'miejsc'
}

export const combinationCapacityBreakdown = (combination = {}, tables = []) => {
  const byId = new Map(tables.map((table) => [Number(table.id), table]))
  const ids = tableIds(combination)
  if (ids.length < 2 || ids.some((id) => !byId.has(id))) return null
  const capacities = ids.map((id) => {
    const table = byId.get(id)
    const parsed = Number(table?.pojemnosc_max ?? table?.pojemnosc)
    return Number.isFinite(parsed) && parsed >= 1 ? Math.round(parsed) : null
  })
  if (capacities.some((capacity) => capacity == null)) return null
  const total = capacities.reduce((sum, capacity) => sum + capacity, 0)
  return {
    capacities,
    total,
    label: `${capacities.join(' + ')} = ${total} ${placesWord(total)}`,
  }
}

export const proposeConnectedCombinations = (
  tables = [],
  edges = [],
  approved = [],
  { maxTables = 4, limit = 100, focusTableId = null } = {},
) => {
  const byId = new Map(tables.map((table) => [Number(table.id), table]))
  const adjacency = new Map([...byId.keys()].map((id) => [id, new Set()]))
  normalizeEdges(edges).forEach((edge) => {
    if (!byId.has(edge.stolik_a_id) || !byId.has(edge.stolik_b_id)) return
    adjacency.get(edge.stolik_a_id).add(edge.stolik_b_id)
    adjacency.get(edge.stolik_b_id).add(edge.stolik_a_id)
  })
  const normalizedApproved = normalizeCombinations(approved)
  const approvedKeys = new Set(normalizedApproved.map(combinationKey))
  const nextPriority = normalizedApproved.length
    ? Math.max(0, ...normalizedApproved.map((combination) => combination.priorytet + 1))
    : 0
  const maximumTables = Math.max(2, Math.min(4, Math.round(number(maxTables, 4))))
  const proposalLimit = Math.max(0, Math.round(number(limit, 100)))
  const focusId = focusTableId == null ? null : Number(focusTableId)
  if (focusId != null && !byId.has(focusId)) return []

  const found = new Map()
  const seeds = focusId == null
    ? [...byId.keys()].sort((a, b) => a - b).map((id) => [id])
    : [[focusId]]
  const queue = [...seeds]
  const queued = new Set(seeds.map((ids) => ids.join(':')))

  // BFS pokazuje najpierw pary, potem trĂłjki i czwĂłrki. W trybie
  // kontekstowym limit dotyczy wybranego stoĹ‚u, a nie pierwszych ID w sali.
  for (let cursor = 0; cursor < queue.length && found.size < proposalLimit; cursor += 1) {
    const ids = queue[cursor]
    const key = ids.join(':')
    if (ids.length >= 2 && !approvedKeys.has(key)) found.set(key, ids)
    if (ids.length >= maximumTables) continue
    const frontier = new Set()
    ids.forEach((id) => adjacency.get(id)?.forEach((neighbor) => {
      if (!ids.includes(neighbor)) frontier.add(neighbor)
    }))
    ;[...frontier].sort((a, b) => a - b).forEach((next) => {
      const expanded = [...ids, next].sort((a, b) => a - b)
      const expandedKey = expanded.join(':')
      if (queued.has(expandedKey)) return
      queued.add(expandedKey)
      queue.push(expanded)
    })
  }

  return [...found.values()]
    .sort((first, second) => first.length - second.length || first.join(':').localeCompare(second.join(':'), 'pl', { numeric: true }))
    .map((ids) => {
      const selected = ids.map((id) => byId.get(id))
      const maximum = selected.reduce((sum, table) => sum + capacityMaximum(table), 0)
      const minimum = Math.min(maximum, Math.max(...selected.map(capacityMaximum)) + 1)
      return normalizeCombination({
        nazwa: selected.map((table) => table.nazwa).join(' + '),
        stoliki: ids,
        pojemnosc_min: minimum,
        pojemnosc_max: maximum,
        priorytet: nextPriority,
        kanal: 'oba',
        aktywna_w_planie: true,
      })
    })
}

const structuralCost = ({ maximum, tableIds, tablePriority, combinationPriority = 0 }, people) => {
  const excess = Math.max(0, maximum - people)
  const cost = excess
    + 2 * (tableIds.length - 1)
    + 0.3 * tablePriority
    + 0.3 * combinationPriority
    + (excess >= 4 ? 0.6 * excess ** 2 : 0)
  return Math.round(cost * 1000) / 1000
}

export const findStructuralSeating = (
  tables = [],
  combinations = [],
  people = 18,
  { channel = 'wewnetrzna' } = {},
) => {
  const count = Math.max(1, Math.round(number(people, 18)))
  const candidates = []
  const activeTables = tables.filter((table) => table.aktywny_w_planie !== false)
  const tablesById = new Map(activeTables.map((table) => [Number(table.id), table]))
  activeTables.forEach((table) => {
    const minimum = capacityMinimum(table)
    const maximum = capacityMaximum(table)
    if (minimum <= count && count <= maximum) {
      const candidate = {
        type: 'table',
        name: table.nazwa,
        tableIds: [Number(table.id)],
        minimum,
        maximum,
        tablePriority: Math.round(number(table.priorytet, 0)),
        combinationPriority: 0,
      }
      candidates.push({ ...candidate, cost: structuralCost(candidate, count) })
    }
  })
  normalizeCombinations(combinations).forEach((combination) => {
    if (!combination.aktywna_w_planie) return
    if (channel && !['oba', channel].includes(combination.kanal)) return
    const members = combination.stoliki.map((tableId) => tablesById.get(tableId))
    if (members.some((table) => !table)) return
    if (combination.pojemnosc_min <= count && count <= combination.pojemnosc_max) {
      const candidate = {
        type: 'combination',
        name: combination.nazwa,
        tableIds: combination.stoliki,
        minimum: combination.pojemnosc_min,
        maximum: combination.pojemnosc_max,
        tablePriority: members.reduce(
          (sum, table) => sum + Math.round(number(table.priorytet, 0)),
          0,
        ) / members.length,
        combinationPriority: combination.priorytet,
      }
      candidates.push({ ...candidate, cost: structuralCost(candidate, count) })
    }
  })
  return candidates.sort((first, second) => (
    first.cost - second.cost
    || first.tableIds.length - second.tableIds.length
    || first.tableIds.join(':').localeCompare(second.tableIds.join(':'), 'pl', { numeric: true })
  ))[0] || null
}
