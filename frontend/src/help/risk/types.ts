export type HelpBlock =
  | { type: 'p'; text: string }
  | { type: 'bullets'; items: string[] }
  | { type: 'callout'; tone: 'info' | 'warning' | 'error'; text: string }
  | { type: 'code'; code: string }

export type HelpQA = {
  id: string
  question: string
  answer: HelpBlock[]
}

export type HelpSection = {
  id: string
  title: string
  qas: HelpQA[]
}

export type HelpContext = {
  id: string
  title: string
  overview: string[]
  sections: HelpSection[]
  gettingStarted: string[]
  troubleshooting: HelpQA[]
}

export type ReasonCodeEntry = {
  code: string
  title: string
  whenItHappens: string
  whereYouSeeIt: string[]
  whatToDo: string[]
}

