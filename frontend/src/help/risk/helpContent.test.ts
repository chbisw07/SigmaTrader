import { describe, expect, it } from 'vitest'

import {
  RISK_GUIDE_MANDATORY_TOPIC_IDS,
  SETTINGS_HELP_BY_TAB,
  riskManagementGuide,
} from './contexts'

function assertNonEmptyString(value: unknown) {
  expect(typeof value).toBe('string')
  expect(String(value).trim().length).toBeGreaterThan(0)
}

describe('risk help content', () => {
  it('each settings help context has required sections and non-empty Q&A', () => {
    for (const ctx of Object.values(SETTINGS_HELP_BY_TAB)) {
      assertNonEmptyString(ctx.id)
      assertNonEmptyString(ctx.title)
      expect(ctx.overview.length).toBeGreaterThan(0)
      expect(ctx.sections.length).toBeGreaterThan(0)
      expect(ctx.gettingStarted.length).toBeGreaterThan(0)
      expect(ctx.troubleshooting.length).toBeGreaterThan(0)

      for (const section of ctx.sections) {
        assertNonEmptyString(section.id)
        assertNonEmptyString(section.title)
        expect(section.qas.length).toBeGreaterThan(0)
        for (const qa of section.qas) {
          assertNonEmptyString(qa.id)
          assertNonEmptyString(qa.question)
          expect(qa.answer.length).toBeGreaterThan(0)
          for (const block of qa.answer) {
            if (block.type === 'p' || block.type === 'callout') {
              assertNonEmptyString(block.text)
            } else if (block.type === 'bullets') {
              expect(block.items.length).toBeGreaterThan(0)
              for (const item of block.items) assertNonEmptyString(item)
            } else if (block.type === 'code') {
              assertNonEmptyString(block.code)
            } else {
              // exhaustive
              expect(block).toBeTruthy()
            }
          }
        }
      }

      for (const item of ctx.gettingStarted) assertNonEmptyString(item)
      for (const qa of ctx.troubleshooting) {
        assertNonEmptyString(qa.id)
        assertNonEmptyString(qa.question)
        expect(qa.answer.length).toBeGreaterThan(0)
      }
    }
  })

  it('consolidated guide includes all mandatory topics', () => {
    const ids = new Set(riskManagementGuide.sections.map((s) => s.id))
    for (const mandatory of RISK_GUIDE_MANDATORY_TOPIC_IDS) {
      expect(ids.has(mandatory)).toBe(true)
    }
  })
})

