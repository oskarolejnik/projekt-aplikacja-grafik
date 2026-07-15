import { describe, expect, it } from 'vitest'
import {
  combinationKey,
  editorSignature,
  findStructuralSeating,
  isConnectedSet,
  neighborIds,
  normalizeCombinations,
  normalizeEdges,
  proposeConnectedCombinations,
} from './floorPlanEditor'

const tables = [
  { id: 1, nazwa: 'S1', pojemnosc: 4 },
  { id: 2, nazwa: 'S2', pojemnosc: 6 },
  { id: 3, nazwa: 'S3', pojemnosc: 8 },
  { id: 4, nazwa: 'S4', pojemnosc: 2 },
  { id: 5, nazwa: 'Bankiet', pojemnosc: 20, pojemnosc_min: 10 },
]

describe('floorPlanEditor R2.2a', () => {
  it('normalizuje nieskierowane krawędzie i pełny snapshot deterministycznie', () => {
    const edges = normalizeEdges([
      { stolik_a_id: 2, stolik_b_id: 1 },
      { stolik_a_id: 1, stolik_b_id: 2 },
      { stolik_a_id: 3, stolik_b_id: 3 },
    ])

    expect(edges).toEqual([{ stolik_a_id: 1, stolik_b_id: 2 }])
    expect(neighborIds(2, edges)).toEqual([1])
    expect(editorSignature({ 2: { plan_x: 20 }, 1: { plan_x: 10 } }, edges, []))
      .toBe(editorSignature({ 1: { plan_x: 10 }, 2: { plan_x: 20 } }, [...edges].reverse(), []))
    expect(normalizeCombinations([{
      nazwa: 'Bardzo długa nazwa zestawu '.repeat(4),
      stoliki: [1, 2],
      pojemnosc_min: 2,
      pojemnosc_max: 10,
    }])[0].nazwa).toHaveLength(64)
  })

  it('proponuje wyłącznie spójne zestawy do czterech stołów i pomija zatwierdzone', () => {
    const edges = [
      { stolik_a_id: 1, stolik_b_id: 2 },
      { stolik_a_id: 2, stolik_b_id: 3 },
      { stolik_a_id: 3, stolik_b_id: 4 },
    ]
    const approved = [{
      nazwa: 'S1 + S2',
      stoliki: [2, 1],
      pojemnosc_min: 7,
      pojemnosc_max: 10,
      kanal: 'oba',
    }]
    const proposals = proposeConnectedCombinations(tables.slice(0, 4), edges, approved)

    expect(proposals.some((proposal) => combinationKey(proposal) === '1:2')).toBe(false)
    expect(proposals.some((proposal) => combinationKey(proposal) === '1:2:3')).toBe(true)
    expect(proposals.every((proposal) => proposal.stoliki.length <= 4)).toBe(true)
    expect(proposals.every((proposal) => isConnectedSet(proposal.stoliki, edges))).toBe(true)
    expect(proposals.some((proposal) => combinationKey(proposal) === '1:3')).toBe(false)
    expect(proposals.every((proposal) => proposal.priorytet === 1)).toBe(true)
  })

  it('wylicza propozycje kontekstowo także dla dalszych stołów w planie 5x5', () => {
    const gridTables = Array.from({ length: 25 }, (_, index) => ({
      id: index + 1,
      nazwa: `S${index + 1}`,
      pojemnosc: 4,
    }))
    const gridEdges = []
    for (let row = 0; row < 5; row += 1) {
      for (let column = 0; column < 5; column += 1) {
        const id = row * 5 + column + 1
        if (column < 4) gridEdges.push({ stolik_a_id: id, stolik_b_id: id + 1 })
        if (row < 4) gridEdges.push({ stolik_a_id: id, stolik_b_id: id + 5 })
      }
    }

    const proposals = proposeConnectedCombinations(gridTables, gridEdges, [], {
      focusTableId: 25,
    })

    expect(proposals.length).toBeGreaterThan(0)
    expect(proposals.length).toBeLessThanOrEqual(100)
    expect(proposals.every((proposal) => proposal.stoliki.includes(25))).toBe(true)
    expect(proposals.some((proposal) => combinationKey(proposal) === '24:25')).toBe(true)
    expect(proposals.some((proposal) => combinationKey(proposal) === '20:25')).toBe(true)
    expect(proposals.every((proposal) => proposal.stoliki.length <= 4)).toBe(true)
    expect(proposals.every((proposal) => isConnectedSet(proposal.stoliki, gridEdges))).toBe(true)
  })

  it('sprawdzian używa tylko pojedynczego stołu albo jawnie zatwierdzonego zestawu', () => {
    expect(findStructuralSeating(tables.slice(0, 4), [], 18)).toBeNull()

    const approved = normalizeCombinations([{
      nazwa: 'S1 + S2 + S3',
      stoliki: [3, 1, 2],
      pojemnosc_min: 9,
      pojemnosc_max: 18,
      priorytet: 0,
      kanal: 'wewnetrzna',
      aktywna_w_planie: true,
    }])
    expect(findStructuralSeating(tables.slice(0, 4), approved, 18)).toMatchObject({
      type: 'combination',
      name: 'S1 + S2 + S3',
      tableIds: [1, 2, 3],
    })
    expect(findStructuralSeating(tables, approved, 18)).toMatchObject({
      type: 'table',
      name: 'Bankiet',
    })
    expect(findStructuralSeating(tables, approved, 19)).toMatchObject({
      type: 'table',
      name: 'Bankiet',
    })
  })

  it('rankuje jak runtime i respektuje kanał oraz status zestawu', () => {
    const rankedTables = [
      { id: 1, nazwa: 'Dokładny, ale niski priorytet', pojemnosc: 8, priorytet: 100 },
      { id: 2, nazwa: 'Dwa miejsca zapasu', pojemnosc: 10, priorytet: 0 },
    ]
    expect(findStructuralSeating(rankedTables, [], 8)).toMatchObject({
      name: 'Dwa miejsca zapasu',
    })

    const combinationTables = tables.slice(0, 3)
    const onlineCombination = {
      nazwa: 'S1 + S2 + S3 online',
      stoliki: [1, 2, 3],
      pojemnosc_min: 18,
      pojemnosc_max: 18,
      priorytet: 0,
      kanal: 'online',
      aktywna_w_planie: true,
    }
    expect(findStructuralSeating(combinationTables, [onlineCombination], 18)).toBeNull()
    expect(findStructuralSeating(combinationTables, [onlineCombination], 18, {
      channel: 'online',
    })).toMatchObject({ name: 'S1 + S2 + S3 online' })
    expect(findStructuralSeating(combinationTables, [{
      ...onlineCombination,
      aktywna_w_planie: false,
    }], 18, { channel: 'online' })).toBeNull()
  })
})
